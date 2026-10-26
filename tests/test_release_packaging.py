import importlib.util
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from app_info import RELEASE_ASSET_NAMES


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paypamin_release_packaging", ROOT / "packaging" / "package_release.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class ReleasePackagingTests(unittest.TestCase):
    def assert_checksum(self, asset, checksum):
        self.assertEqual(checksum.read_text(encoding="ascii"), f"{packaging.sha256_file(asset)}  {asset.name}\n")

    def test_windows_package_contains_single_executable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dist = root / "dist"
            dist.mkdir()
            (dist / "PayPamin Flow.exe").write_bytes(b"synthetic-windows-app")
            asset, checksum = packaging.package_release("windows", dist, root / "assets")
            self.assertEqual(asset.name, RELEASE_ASSET_NAMES["windows"])
            with zipfile.ZipFile(asset) as archive:
                self.assertEqual(archive.namelist(), ["PayPamin Flow.exe"])
                self.assertEqual(archive.read("PayPamin Flow.exe"), b"synthetic-windows-app")
            self.assert_checksum(asset, checksum)

    def test_macos_package_contains_app_bundle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "dist" / "PayPamin Flow.app" / "Contents" / "MacOS" / "paypamin-flow"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"synthetic-macos-app")
            executable.chmod(0o755)
            (executable.parents[1] / "Info.plist").write_text("synthetic", encoding="utf-8")
            asset, checksum = packaging.package_release("macos", root / "dist", root / "assets")
            self.assertEqual(asset.name, RELEASE_ASSET_NAMES["macos"])
            with zipfile.ZipFile(asset) as archive:
                self.assertIn("PayPamin Flow.app/Contents/MacOS/paypamin-flow", archive.namelist())
                self.assertIn("PayPamin Flow.app/Contents/Info.plist", archive.namelist())
                if os.name == "posix":
                    mode = (archive.getinfo("PayPamin Flow.app/Contents/MacOS/paypamin-flow").external_attr >> 16) & 0o777
                    self.assertTrue(mode & 0o111)
            self.assert_checksum(asset, checksum)

    def test_linux_package_contains_executable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dist = root / "dist"
            dist.mkdir()
            (dist / "paypamin-flow").write_bytes(b"synthetic-linux-app")
            (dist / "paypamin-flow").chmod(0o755)
            asset, checksum = packaging.package_release("linux", dist, root / "assets")
            self.assertEqual(asset.name, RELEASE_ASSET_NAMES["linux"])
            with tarfile.open(asset, "r:gz") as archive:
                member = archive.getmember("paypamin-flow")
                self.assertTrue(member.isfile())
                self.assertEqual(archive.extractfile(member).read(), b"synthetic-linux-app")
            self.assert_checksum(asset, checksum)


if __name__ == "__main__":
    unittest.main()
