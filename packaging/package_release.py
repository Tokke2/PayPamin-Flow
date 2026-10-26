#!/usr/bin/env python3
"""Build the cross-platform Python-only release ZIP and SHA-256 sidecar."""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_info import PYTHON_PACKAGE_REQUIRED_FILES, PYTHON_RELEASE_ASSET, is_python_package_file


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


def build_python_package(source: Path, output: Path) -> tuple[Path, Path]:
    source = source.resolve()
    output = output.resolve()
    files = package_files(source)
    names = {path.relative_to(source).as_posix() for path in files}
    missing = sorted(set(PYTHON_PACKAGE_REQUIRED_FILES) - names)
    if missing:
        raise RuntimeError(f"Python release is missing required files: {', '.join(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / PYTHON_RELEASE_ASSET
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(source).as_posix())
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = output / f"{PYTHON_RELEASE_ASSET}.sha256"
    checksum_path.write_text(f"{digest}  {PYTHON_RELEASE_ASSET}\n", encoding="ascii")
    return archive_path, checksum_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive, checksum = build_python_package(args.source, args.output)
    print(archive)
    print(checksum)


if __name__ == "__main__":
    main()
