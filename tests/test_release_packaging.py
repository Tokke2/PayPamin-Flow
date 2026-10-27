import hashlib
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

from app_info import (
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    RELEASE_ASSET_NAMES,
    is_python_package_file,
)
from update_installer import _extract_python_package


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paypamin_release_packaging", ROOT / "packaging" / "package_release.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class ReleasePackagingTests(unittest.TestCase):
    def test_all_platforms_use_one_python_package(self):
        self.assertEqual(set(RELEASE_ASSET_NAMES.values()), {PYTHON_RELEASE_ASSET})
        self.assertEqual(PYTHON_RELEASE_ASSET, "PayPamin-Flow-Python.zip")

    def test_official_release_stamp_accepts_only_numeric_release_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory)
            build_info = packaging.stamp_release_build(source, "424038701")
            self.assertEqual(build_info.read_text(encoding="utf-8"), '"""Official GitHub release identity for same-version update checks."""\n\nAPP_RELEASE_ID = "424038701"\n')
            for invalid in ("main", "arena/cae09411-paypamin-flow", "0", "12x"):
                with self.assertRaises(ValueError):
                    packaging.stamp_release_build(source, invalid)

    def test_package_contains_python_sources_icons_and_no_native_binaries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            asset, checksum = packaging.build_python_package(ROOT, output)
            self.assertEqual(asset.name, PYTHON_RELEASE_ASSET)
            self.assertEqual(checksum.name, PYTHON_RELEASE_ASSET + ".sha256")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text(encoding="ascii"), f"{digest}  {PYTHON_RELEASE_ASSET}\n")
            with zipfile.ZipFile(asset) as archive:
                names = set(archive.namelist())
                self.assertTrue(set(PYTHON_PACKAGE_REQUIRED_FILES).issubset(names))
                self.assertIn("paypamin_flow.py", names)
                self.assertIn("app_backup.py", names)
                self.assertIn("build_info.py", names)
                self.assertIn("tray.py", names)
                self.assertIn("assets/paypamin_flow.ico", names)
                self.assertIn("assets/paypamin_flow.icns", names)
                self.assertTrue(all(is_python_package_file(name) for name in names))
                self.assertFalse(any(name.lower().endswith((".exe", ".dll", ".so", ".dylib", ".spec")) for name in names))
                self.assertFalse(any(name.startswith(("tests/", ".git/", "import/", "export/", "svg/")) for name in names))
                self.assertNotIn("start_paypamin_flow.command", names)
                self.assertNotIn("paypaminn_flow.py", names)
                self.assertNotIn("paypaminn_flow.pyw", names)
            validated = output / "validated"
            _extract_python_package(asset, validated, APP_VERSION)
            self.assertTrue((validated / "paypamin_flow.py").is_file())
            self.assertTrue((validated / "tray.py").is_file())


if __name__ == "__main__":
    unittest.main()
