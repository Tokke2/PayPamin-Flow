#!/usr/bin/env python3
"""Package a native build and its SHA-256 checksum for GitHub Releases."""
from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_info import RELEASE_ASSET_NAMES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Required build output is missing: {path}")
    return path


def package_release(platform: str, dist: Path, output: Path) -> tuple[Path, Path]:
    if platform not in RELEASE_ASSET_NAMES:
        raise ValueError(f"Unsupported release platform: {platform}")
    output.mkdir(parents=True, exist_ok=True)
    asset = output / RELEASE_ASSET_NAMES[platform]

    if platform == "windows":
        executable = _required_file(dist / "PayPamin Flow.exe")
        with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(executable, executable.name)
    elif platform == "macos":
        app = dist / "PayPamin Flow.app"
        if not app.is_dir():
            raise FileNotFoundError(f"Required build output is missing: {app}")
        with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(dist).as_posix())
    else:
        executable = _required_file(dist / "paypamin-flow")
        with tarfile.open(asset, "w:gz") as archive:
            archive.add(executable, arcname="paypamin-flow", recursive=False)

    checksum = asset.with_name(asset.name + ".sha256")
    checksum.write_text(f"{sha256_file(asset)}  {asset.name}\n", encoding="ascii")
    return asset, checksum


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=sorted(RELEASE_ASSET_NAMES))
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("release-assets"))
    args = parser.parse_args()
    asset, checksum = package_release(args.platform, args.dist, args.output)
    print(asset)
    print(checksum)


if __name__ == "__main__":
    main()
