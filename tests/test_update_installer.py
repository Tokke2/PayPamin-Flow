import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import update_installer
from app_info import PYTHON_PACKAGE_REQUIRED_FILES, PYTHON_RELEASE_ASSET
from update_checker import ReleaseAsset, ReleaseInfo
from update_installer import (
    UpdateInstallError,
    cleanup_update,
    install_update,
    restart_updated_app,
    rollback_update,
    stage_update,
)


PACKAGE_URL = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.7.0/{PYTHON_RELEASE_ASSET}"
CHECKSUM_URL = PACKAGE_URL + ".sha256"


def python_package(version="0.7.0", extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PYTHON_PACKAGE_REQUIRED_FILES:
            if name == "app_info.py":
                content = f'APP_VERSION = "{version}"\n'.encode()
            elif name.endswith((".py", ".pyw")):
                content = f"# updated {name}\n".encode()
            elif name == "requirements.txt":
                content = b"pystray>=0.19.5\n"
            else:
                content = b"icon"
            archive.writestr(name, content)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def release_with_package(package):
    digest = hashlib.sha256(package).hexdigest()
    checksum = f"{digest}  {PYTHON_RELEASE_ASSET}\n".encode("ascii")
    release = ReleaseInfo(
        version="0.7.0",
        tag_name="v0.7.0",
        url="https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0",
        assets=(ReleaseAsset(PYTHON_RELEASE_ASSET, PACKAGE_URL), ReleaseAsset(PYTHON_RELEASE_ASSET + ".sha256", CHECKSUM_URL)),
    )
    return release, {PACKAGE_URL: package, CHECKSUM_URL: checksum}


class FakeResponse:
    def __init__(self, url, content):
        self.url = url
        self.stream = io.BytesIO(content)
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.stream.read(size)

    def geturl(self):
        return self.url


def opener_for(responses):
    def opener(request, timeout):
        return FakeResponse(request.full_url, responses[request.full_url])

    return opener


class UpdateInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "app"
        self.target.mkdir()

    def stage(self, package=None, target=None):
        release, responses = release_with_package(package or python_package())
        plan = stage_update(
            release,
            platform="linux",
            target_path=target or self.target,
            log_path=self.root / "update.log",
            opener=opener_for(responses),
        )
        self.addCleanup(cleanup_update, plan)
        return plan

    def test_stage_downloads_verifies_and_preserves_running_app(self):
        (self.target / "paypamin_flow.py").write_text("old application", encoding="utf-8")
        plan = self.stage()
        self.assertEqual(plan.source_path.joinpath("paypamin_flow.py").read_text(), "# updated paypamin_flow.py\n")
        self.assertEqual(plan.target_path, self.target.resolve())
        self.assertEqual((self.target / "paypamin_flow.py").read_text(), "old application")
        self.assertTrue(plan.work_dir.is_dir())
        cleanup_update(plan)
        self.assertFalse(plan.work_dir.exists())

    def test_checksum_mismatch_is_rejected(self):
        release, responses = release_with_package(python_package())
        responses[CHECKSUM_URL] = f"{'0' * 64}  {PYTHON_RELEASE_ASSET}\n".encode()
        with self.assertRaises(UpdateInstallError):
            stage_update(release, platform="linux", target_path=self.target, opener=opener_for(responses))
        self.assertEqual(list(self.target.iterdir()), [])

    def test_path_traversal_is_rejected(self):
        package = python_package(extra={"../outside.py": "not allowed"})
        with self.assertRaises(UpdateInstallError):
            self.stage(package)
        self.assertFalse((self.root / "outside.py").exists())

    def test_missing_python_assets_are_rejected(self):
        release = ReleaseInfo("0.7.0", "v0.7.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0")
        with self.assertRaises(UpdateInstallError):
            stage_update(release, platform="linux", target_path=self.target)

    def test_package_version_must_match_release(self):
        with self.assertRaises(UpdateInstallError):
            self.stage(python_package(version="0.8.0"))

    def test_install_preserves_user_data_and_rollback_restores_every_file(self):
        (self.target / "paypamin_flow.py").write_text("old application", encoding="utf-8")
        for folder in ("import", "export", "svg"):
            (self.target / folder).mkdir()
            (self.target / folder / "keep.txt").write_text(folder, encoding="utf-8")
        database = self.target / "paminnelseapp.sqlite3"
        database.write_bytes(b"user database")
        plan = self.stage()
        installed = install_update(plan)
        self.assertEqual((self.target / "paypamin_flow.py").read_text(), "# updated paypamin_flow.py\n")
        self.assertTrue((self.target / "tray.py").is_file())
        for folder in ("import", "export", "svg"):
            self.assertEqual((self.target / folder / "keep.txt").read_text(), folder)
        self.assertEqual(database.read_bytes(), b"user database")

        rollback_update(installed)
        self.assertEqual((self.target / "paypamin_flow.py").read_text(), "old application")
        self.assertFalse((self.target / "tray.py").exists())
        self.assertEqual(database.read_bytes(), b"user database")

    def test_failed_installation_rolls_back_and_cleans_staging(self):
        (self.target / "app_info.py").write_text("old info", encoding="utf-8")
        (self.target / "autostart.py").write_text("old autostart", encoding="utf-8")
        plan = self.stage()
        original_replace = update_installer._replace_file

        def fail_once(source, target):
            if target.name == "autostart.py" and source.parent == plan.source_path:
                raise OSError("synthetic write failure")
            return original_replace(source, target)

        with patch.object(update_installer, "_replace_file", side_effect=fail_once):
            with self.assertRaises(UpdateInstallError):
                install_update(plan)
        self.assertEqual((self.target / "app_info.py").read_text(), "old info")
        self.assertEqual((self.target / "autostart.py").read_text(), "old autostart")
        self.assertFalse(plan.work_dir.exists())

    def test_windows_restart_uses_pythonw_and_no_console(self):
        plan = self.stage()
        installed = install_update(plan)
        python_home = self.root / "python"
        python_home.mkdir()
        python = python_home / "python.exe"
        pythonw = python_home / "pythonw.exe"
        python.write_bytes(b"")
        pythonw.write_bytes(b"")
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(pid=4321)

        with patch.object(update_installer.sys, "platform", "win32"), patch.object(
            update_installer.sys, "executable", str(python)
        ), patch.object(update_installer.subprocess, "Popen", side_effect=popen), patch.object(
            update_installer.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True
        ), patch.object(update_installer.subprocess, "DETACHED_PROCESS", 0x00000008, create=True):
            process = restart_updated_app(installed)
        self.assertEqual(process.pid, 4321)
        args, kwargs = calls[0]
        self.assertEqual(args, [str(pythonw.resolve()), str((self.target / "paypamin_flow.pyw").resolve())])
        self.assertEqual(kwargs["creationflags"], 0x08000008)
        self.assertFalse(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdout"], update_installer.subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], update_installer.subprocess.DEVNULL)

    def test_untrusted_download_url_is_rejected(self):
        release, responses = release_with_package(python_package())
        unsafe = ReleaseInfo(
            release.version,
            release.tag_name,
            release.url,
            (ReleaseAsset(PYTHON_RELEASE_ASSET, "http://example.com/update.zip"), release.assets[1]),
        )
        with self.assertRaises(UpdateInstallError):
            stage_update(unsafe, platform="linux", target_path=self.target, opener=opener_for(responses))


if __name__ == "__main__":
    unittest.main()
