#!/usr/bin/env python3
"""Build the Python ZIP, SHA-256 sidecar and release build manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_info import (
    APP_NAME,
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    PYTHON_RELEASE_MANIFEST,
    fingerprint_package_files,
    is_python_package_file,
)


def package_files(source: Path) -> list[Path]:
    candidates = []
    for path in source.iterdir():
        if path.is_file() and is_python_package_file(path.name):
            candidates.append(path)
    for folder in (source / "assets", source / "packaging"):
        if folder.is_dir():
            for path in folder.iterdir():
                relative = path.relative_to(source).as_posix()
                if path.is_file() and is_python_package_file(relative):
                    candidates.append(path)
    return sorted(candidates, key=lambda path: path.relative_to(source).as_posix())


def stamp_release_build(
    source: Path,
    release_id: str,
    release_commit: str,
    package_fingerprint: str,
) -> Path:
    """Stamp the official release identity and shipped-file fingerprint."""
    release_id = str(release_id or "").strip()
    release_commit = str(release_commit or "").strip().lower()
    package_fingerprint = str(package_fingerprint or "").strip().lower()
    if not re.fullmatch(r"[1-9][0-9]*", release_id):
        raise ValueError("A numeric GitHub release ID is required")
    if not re.fullmatch(r"[0-9a-f]{40}", release_commit):
        raise ValueError("A full 40-character release commit is required")
    if not re.fullmatch(r"[0-9a-f]{64}", package_fingerprint):
        raise ValueError("A valid package file fingerprint is required")
    build_info = source / "build_info.py"
    build_info.write_text(
        '"""Official release identity for same-version commit and file checks."""\n\n'
        f'APP_RELEASE_ID = "{release_id}"\n'
        f'APP_RELEASE_COMMIT = "{release_commit}"\n'
        f'APP_PACKAGE_FINGERPRINT = "{package_fingerprint}"\n',
        encoding="utf-8",
    )
    return build_info


def build_python_package(
    source: Path,
    output: Path,
    *,
    release_id: str = "",
    release_commit: str = "",
) -> tuple[Path, Path, Path]:
    source = source.resolve()
    output = output.resolve()
    release_id = str(release_id or "").strip()
    release_commit = str(release_commit or "").strip().lower()
    if release_commit and not re.fullmatch(r"[0-9a-f]{40}", release_commit):
        raise ValueError("A full 40-character release commit is required")
    if release_commit and not release_id:
        raise ValueError("A release commit requires a numeric release ID")

    files = package_files(source)
    names = {path.relative_to(source).as_posix() for path in files}
    missing = sorted(set(PYTHON_PACKAGE_REQUIRED_FILES) - names)
    if missing:
        raise RuntimeError(f"Python release is missing required files: {', '.join(missing)}")

    file_hashes = {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
        if path.name != "build_info.py"
    }
    package_fingerprint = fingerprint_package_files(file_hashes)
    if release_id:
        stamp_release_build(source, release_id, release_commit, package_fingerprint)

    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / PYTHON_RELEASE_ASSET
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(source).as_posix())
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = output / f"{PYTHON_RELEASE_ASSET}.sha256"
    checksum_path.write_text(f"{digest}  {PYTHON_RELEASE_ASSET}\n", encoding="ascii")

    manifest_path = output / PYTHON_RELEASE_MANIFEST
    manifest = {
        "format": 1,
        "application": APP_NAME,
        "version": APP_VERSION,
        "release_id": release_id,
        "commit": release_commit,
        "package_fingerprint": package_fingerprint,
        "files": dict(sorted(file_hashes.items())),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return archive_path, checksum_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", default="", help="Numeric GitHub release ID for official release packages")
    parser.add_argument("--release-commit", default="", help="Full source commit for official release packages")
    args = parser.parse_args()
    artifacts = build_python_package(
        args.source,
        args.output,
        release_id=args.release_id,
        release_commit=args.release_commit,
    )
    for artifact in artifacts:
        print(artifact)


if __name__ == "__main__":
    main()
