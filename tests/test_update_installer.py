import hashlib
import io
import os
import stat
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app_info import RELEASE_ASSET_NAMES
from update_checker import ReleaseAsset, ReleaseInfo
from update_installer import (
    UpdateInstallError,
    UpdatePlan,
    download_verified_package,
    extract_update_package,
    launch_update,
    stage_update,
)


class FakeResponse:
    def __init__(self, content, url):
        self.content = content
        self.url = url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def geturl(self):
        return self.url

    def read(self, size):
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def linux_package(content=b"new-linux-app"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("paypamin-flow")
        info.size = len(content)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def release_with_package(package_name, package_content, declared_checksum=None):
    package_url = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/{package_name}"
    checksum_url = package_url + ".sha256"
    checksum = declared_checksum or hashlib.sha256(package_content).hexdigest()
    checksum_content = f"{checksum}  {package_name}\n".encode("ascii")
    responses = {package_url: package_content, checksum_url: checksum_content}

    def opener(request, timeout):
        return FakeResponse(responses[request.full_url], request.full_url)

    release = ReleaseInfo(
        version="0.6.0",
        tag_name="v0.6.0",
        url="https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
        assets=(ReleaseAsset(package_name, package_url), ReleaseAsset(package_name + ".sha256", checksum_url)),
    )
    return release, opener


class UpdateInstallerTests(unittest.TestCase):
    def test_downloads_and_verifies_package(self):
        content = linux_package()
        release, opener = release_with_package(RELEASE_ASSET_NAMES["linux"], content)
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = download_verified_package(release, "linux", Path(temporary_directory), opener)
            self.assertEqual(package.read_bytes(), content)

    def test_checksum_mismatch_is_rejected(self):
        release, opener = release_with_package(RELEASE_ASSET_NAMES["linux"], linux_package(), "0" * 64)
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(UpdateInstallError):
                download_verified_package(release, "linux", Path(temporary_directory), opener)
            self.assertFalse((Path(temporary_directory) / RELEASE_ASSET_NAMES["linux"]).exists())

    def test_missing_platform_assets_are_rejected(self):
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0")
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(UpdateInstallError):
                download_verified_package(release, "windows", Path(temporary_directory))

    def test_stage_update_downloads_extracts_and_preserves_target_path(self):
        content = linux_package(b"staged-new-app")
        release, opener = release_with_package(RELEASE_ASSET_NAMES["linux"], content)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "installed app"
            target.write_bytes(b"old-app")
            plan = stage_update(release, "linux", target, root / "logs" / "update.log", opener)
            try:
                self.assertEqual(plan.target, target.resolve())
                self.assertEqual(plan.source.read_bytes(), b"staged-new-app")
                self.assertEqual(plan.log_path, root / "logs" / "update.log")
            finally:
                shutil.rmtree(plan.work_dir, ignore_errors=True)

    def test_extracts_windows_executable_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "windows.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("PayPamin Flow.exe", b"new-windows-app")
                archive.writestr("../ignored", b"must-not-be-extracted")
            source = extract_update_package(package, "windows", root / "out")
            self.assertEqual(source.read_bytes(), b"new-windows-app")
            self.assertFalse((root / "ignored").exists())

    def test_extracts_macos_bundle_and_executable_mode(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "macos.zip"
            with zipfile.ZipFile(package, "w") as archive:
                info = zipfile.ZipInfo("PayPamin Flow.app/Contents/MacOS/paypamin-flow")
                info.external_attr = 0o100755 << 16
                archive.writestr(info, b"new-macos-app")
                archive.writestr("PayPamin Flow.app/Contents/Info.plist", "synthetic")
            source = extract_update_package(package, "macos", root / "out")
            self.assertEqual((source / "Contents" / "MacOS" / "paypamin-flow").read_bytes(), b"new-macos-app")
            if os.name == "posix":
                self.assertTrue((source / "Contents" / "MacOS" / "paypamin-flow").stat().st_mode & 0o111)

    def test_macos_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "macos.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("PayPamin Flow.app/../outside", b"unsafe")
            with self.assertRaises(UpdateInstallError):
                extract_update_package(package, "macos", root / "out")
            self.assertFalse((root / "outside").exists())

    def test_macos_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "macos.zip"
            with zipfile.ZipFile(package, "w") as archive:
                link = zipfile.ZipInfo("PayPamin Flow.app/Contents/MacOS/link")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, "../../outside")
            with self.assertRaises(UpdateInstallError):
                extract_update_package(package, "macos", root / "out")

    def test_helper_launch_failure_cleans_staging_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            work_dir = root / "work"
            work_dir.mkdir()
            plan = UpdatePlan("linux", work_dir, work_dir / "source", root / "target", root / "update.log")
            with patch("update_installer.subprocess.Popen", side_effect=OSError("unavailable")):
                with self.assertRaises(UpdateInstallError):
                    launch_update(plan, process_id=99_999_999)
            self.assertFalse(work_dir.exists())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux helper integration test")
    def test_linux_helper_replaces_and_restarts_app(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            work_dir = root / "work with spaces"
            work_dir.mkdir()
            updated = b"#!/bin/sh\n# updated\nexit 0\n"
            source = work_dir / "staged app"
            source.write_bytes(updated)
            target = root / "target app"
            target.write_bytes(b"#!/bin/sh\n# old\nexit 0\n")
            target.chmod(0o755)
            log = root / "update.log"
            plan = UpdatePlan("linux", work_dir, source, target, log)
            helper = launch_update(plan, process_id=99_999_999)
            try:
                helper.wait(timeout=10)
            finally:
                if helper.poll() is None:
                    helper.kill()
                    helper.wait()
            self.assertEqual(target.read_bytes(), updated)
            self.assertFalse(work_dir.exists())
            self.assertFalse(Path(str(target) + ".bak").exists())
            self.assertIn("Update installed and application restarted", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
