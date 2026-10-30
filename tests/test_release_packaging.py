import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from app_info import (
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    PYTHON_RELEASE_MANIFEST,
    RELEASE_ASSET_NAMES,
    fingerprint_package_files,
    is_python_package_file,
)
from update_checker import ReleaseInfo
from update_installer import _extract_python_package, _validate_package_build


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paypamin_release_packaging", ROOT / "packaging" / "package_release.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class ReleasePackagingTests(unittest.TestCase):
    def test_all_platforms_use_one_python_package(self):
        self.assertEqual(set(RELEASE_ASSET_NAMES.values()), {PYTHON_RELEASE_ASSET})
        self.assertEqual(PYTHON_RELEASE_ASSET, "PayPamin-Flow-Python.zip")

    def test_official_release_stamp_contains_id_commit_and_file_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory)
            commit = "a" * 40
            fingerprint = "b" * 64
            build_info = packaging.stamp_release_build(source, "424038701", commit, fingerprint)
            self.assertEqual(
                build_info.read_text(encoding="utf-8"),
                '"""Official release identity for same-version commit and file checks."""\n\n'
                'APP_RELEASE_ID = "424038701"\n'
                f'APP_RELEASE_COMMIT = "{commit}"\n'
                f'APP_PACKAGE_FINGERPRINT = "{fingerprint}"\n',
            )
            for invalid in ("main", "arena/cae09411-paypamin-flow", "0", "12x"):
                with self.assertRaises(ValueError):
                    packaging.stamp_release_build(source, invalid, commit, fingerprint)
            with self.assertRaises(ValueError):
                packaging.stamp_release_build(source, "424038701", "main", fingerprint)
            with self.assertRaises(ValueError):
                packaging.stamp_release_build(source, "424038701", commit, "not-a-hash")

    def test_official_package_embeds_matching_commit_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            for path in packaging.package_files(ROOT):
                relative = path.relative_to(ROOT)
                (source / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, source / relative)
            (source / "test-results.txt").write_text("transient CI test output", encoding="utf-8")
            commit = "c" * 40
            asset, _, manifest_path = packaging.build_python_package(
                source, output, release_id="424038701", release_commit=commit
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            with zipfile.ZipFile(asset) as archive:
                names = set(archive.namelist())
                build_info = archive.read("build_info.py").decode("utf-8")
            self.assertNotIn("test-results.txt", names)
            self.assertNotIn("test-results.txt", manifest["files"])
            self.assertFalse(is_python_package_file("test-results.txt"))
            self.assertIn('APP_RELEASE_ID = "424038701"', build_info)
            self.assertIn(f'APP_RELEASE_COMMIT = "{commit}"', build_info)
            self.assertIn(f'APP_PACKAGE_FINGERPRINT = "{manifest["package_fingerprint"]}"', build_info)
            self.assertEqual(manifest["commit"], commit)
            validated = output / "validated"
            _extract_python_package(asset, validated, APP_VERSION)
            _validate_package_build(validated, ReleaseInfo(
                APP_VERSION,
                f"v{APP_VERSION}",
                "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
                release_id="424038701",
                release_commit=commit,
                package_fingerprint=manifest["package_fingerprint"],
            ))

    def test_package_contains_python_sources_icons_and_no_native_binaries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            asset, checksum, manifest_path = packaging.build_python_package(ROOT, output)
            self.assertEqual(asset.name, PYTHON_RELEASE_ASSET)
            self.assertEqual(checksum.name, PYTHON_RELEASE_ASSET + ".sha256")
            self.assertEqual(manifest_path.name, PYTHON_RELEASE_MANIFEST)
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text(encoding="ascii"), f"{digest}  {PYTHON_RELEASE_ASSET}\n")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], 1)
            self.assertEqual(manifest["version"], APP_VERSION)
            self.assertEqual(manifest["release_id"], "")
            self.assertEqual(manifest["commit"], "")
            self.assertNotIn("build_info.py", manifest["files"])
            self.assertEqual(manifest["package_fingerprint"], fingerprint_package_files(manifest["files"]))
            for name, expected_hash in manifest["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected_hash)
            with zipfile.ZipFile(asset) as archive:
                names = set(archive.namelist())
                self.assertTrue(set(PYTHON_PACKAGE_REQUIRED_FILES).issubset(names))
                self.assertIn("paypamin_flow.py", names)
                self.assertIn("paypamin_flow_launcher.py", names)
                self.assertIn("paypamin_flow.pyw", names)
                self.assertIn("app_backup.py", names)
                self.assertIn("build_info.py", names)
                self.assertIn("tray.py", names)
                self.assertIn("reminder_journal.py", names)
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
