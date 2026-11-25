import hashlib
import io
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import update_installer
import update_state
from app_info import PYTHON_PACKAGE_REQUIRED_FILES, PYTHON_RELEASE_ASSET
from update_checker import ReleaseAsset, ReleaseInfo
from update_installer import (
    UpdateInstallError,
    _download_asset,
    _validate_package_build,
    cleanup_update,
    install_update,
    mark_update_ready,
    restart_updated_app,
    rollback_update,
    stage_update,
    update_restart_ready,
    wait_for_update_restart,
)


SOURCE_URL = "https://github.com/Tokke2/PayPamin-Flow/archive/refs/tags/v0.7.0.zip"
# Still used by the download-retry tests, which exercise the transport itself.
PACKAGE_URL = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.7.0/{PYTHON_RELEASE_ASSET}"
SOURCE_COMMIT = "c" * 40


def source_archive(version="0.7.0", extra=None, omit=None, root=None):
    """Build the shape GitHub uses for a tag: one folder wrapping the repo.

    The real archive also carries ``tests/`` and ``.github/``; the update must
    skip them instead of copying a test suite into the user's app folder.
    """
    buffer = io.BytesIO()
    omitted = set(omit or ())
    folder = "PayPamin-Flow-" + version if root is None else root
    prefix = f"{folder}/" if folder else ""
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PYTHON_PACKAGE_REQUIRED_FILES:
            if name in omitted:
                continue
            if name == "app_info.py":
                content = f'APP_VERSION = "{version}"\n'.encode()
            elif name == "build_info.py":
                # The repository's committed stamp is stale; the installer
                # must replace it with the release it actually installed.
                content = b'APP_RELEASE_ID = "440160436"\n'
            elif name.endswith((".py", ".pyw")):
                content = f"# updated {name}\n".encode()
            elif name == "requirements.txt":
                content = b"pystray>=0.19.5\n"
            else:
                content = b"icon"
            archive.writestr(prefix + name, content)
        archive.writestr(prefix + "tests/test_update_installer.py", b"# never installed\n")
        archive.writestr(prefix + ".github/workflows/build.yml", b"name: build\n")
        for name, content in (extra or {}).items():
            archive.writestr(prefix + name, content)
    return buffer.getvalue()


def release_with_source(archive, *, source_url=SOURCE_URL, commit=SOURCE_COMMIT):
    release = ReleaseInfo(
        version="0.7.0",
        tag_name="v0.7.0",
        url="https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0",
        source_url=source_url,
        source_commit=commit,
    )
    return release, {source_url: archive}


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
        # The install record belongs to the test, never to the machine running
        # the suite.
        self.state_file = self.root / "installed-release.json"
        patcher = patch.object(update_state, "state_path", lambda directory=None: self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stage(self, package=None, target=None):
        release, responses = release_with_source(package if package is not None else source_archive())
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

    def test_the_build_stamp_must_match_the_release(self):
        """The stamp names the commit, so a tampered stamp is caught."""
        source = self.root / "stamp-source"
        source.mkdir()
        (source / "app_info.py").write_text('APP_VERSION = "0.7.0"\n', encoding="utf-8")
        release = ReleaseInfo(
            "0.7.0", "v0.7.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.7.0",
            release_id="200", source_commit="c" * 40,
        )
        update_installer.stamp_package_build(source, release)
        _validate_package_build(source, release)

        (source / "app_info.py").write_text('APP_VERSION = "0.7.0"\n# changed\n', encoding="utf-8")
        with self.assertRaisesRegex(UpdateInstallError, "byggidentitet"):
            _validate_package_build(source, release)

        update_installer.stamp_package_build(source, release)
        with self.assertRaisesRegex(UpdateInstallError, "byggidentitet"):
            _validate_package_build(source, ReleaseInfo("0.7.0", "v0.7.0", release.url, source_commit="d" * 40))

    def test_only_application_files_are_taken_from_the_archive(self):
        """The archive is the repository; tests and CI stay out of the install."""
        plan = self.stage()
        names = {path.relative_to(plan.source_path).as_posix() for path in plan.source_path.rglob("*") if path.is_file()}
        self.assertIn("paypamin_flow.py", names)
        self.assertNotIn("tests/test_update_installer.py", names)
        self.assertNotIn(".github/workflows/build.yml", names)
        self.assertFalse((plan.source_path / "tests").exists())

    def test_the_archive_root_folder_is_stripped(self):
        plan = self.stage(source_archive(version="0.7.0"))
        self.assertTrue((plan.source_path / "app_info.py").is_file())
        self.assertFalse((plan.source_path / "PayPamin-Flow-0.7.0").exists())

    def test_path_traversal_never_reaches_the_disk(self):
        """A path outside the app folder is dropped, not written."""
        plan = self.stage(source_archive(extra={"../outside.py": "not allowed"}))
        self.assertFalse((self.root / "outside.py").exists())
        self.assertFalse((plan.source_path.parent / "outside.py").exists())

    def test_a_release_without_an_archive_address_is_rejected(self):
        release = ReleaseInfo("0.7.0", "", "https://github.com/Tokke2/PayPamin-Flow/releases")
        with self.assertRaises(UpdateInstallError):
            stage_update(release, platform="linux", target_path=self.target)

    def test_missing_windows_icon_is_rejected(self):
        with self.assertRaisesRegex(UpdateInstallError, "paypamin_flow.ico"):
            self.stage(source_archive(omit={"assets/paypamin_flow.ico"}))

    def test_package_version_must_match_release(self):
        with self.assertRaises(UpdateInstallError):
            self.stage(source_archive(version="0.8.0"))

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
        self.assertEqual(args, [str(pythonw.resolve()), str((self.target / "paypamin_flow_launcher.py").resolve())])
        self.assertEqual(kwargs["creationflags"], 0x08000008)
        self.assertFalse(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdout"], update_installer.subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], update_installer.subprocess.DEVNULL)
        self.assertEqual(kwargs["env"][update_installer.UPDATE_READY_FILE_ENV], str(installed.ready_file))
        self.assertEqual(kwargs["env"][update_installer.UPDATE_READY_TOKEN_ENV], installed.ready_token)

    def test_unix_restart_uses_the_same_diagnostic_gui_launcher(self):
        plan = self.stage()
        installed = install_update(plan)
        python = self.root / "python"
        python.write_bytes(b"")
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(pid=4322)

        with patch.object(update_installer.sys, "platform", "linux"), patch.object(
            update_installer.sys, "executable", str(python)
        ), patch.object(update_installer.subprocess, "Popen", side_effect=popen):
            process = restart_updated_app(installed)
        self.assertEqual(process.pid, 4322)
        args, kwargs = calls[0]
        self.assertEqual(args, [str(python.resolve()), str((self.target / "paypamin_flow_launcher.py").resolve())])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["creationflags"], 0)
        self.assertEqual(kwargs["env"][update_installer.UPDATE_READY_FILE_ENV], str(installed.ready_file))

    def test_ready_handshake_requires_matching_token_and_pid(self):
        plan = self.stage()
        installed = install_update(plan)
        installed.ready_file = self.root / "ready.json"
        installed.ready_token = "one-off-token"
        process = SimpleNamespace(pid=update_installer.os.getpid())
        environment = {
            update_installer.UPDATE_READY_FILE_ENV: str(installed.ready_file),
            update_installer.UPDATE_READY_TOKEN_ENV: installed.ready_token,
        }
        with patch.dict(update_installer.os.environ, environment):
            self.assertTrue(mark_update_ready())
        self.assertTrue(update_restart_ready(installed, process))
        self.assertFalse(update_restart_ready(installed, SimpleNamespace(pid=process.pid + 1)))
        installed.ready_token = "wrong-token"
        self.assertFalse(update_restart_ready(installed, process))

    def test_failed_ready_handshake_stops_child_and_raises(self):
        plan = self.stage()
        installed = install_update(plan)
        process = Mock(pid=999)
        process.poll.return_value = None
        with self.assertRaises(UpdateInstallError):
            wait_for_update_restart(installed, process, timeout=0)
        process.terminate.assert_called_once_with()

    def test_early_child_exit_is_a_readiness_failure(self):
        plan = self.stage()
        installed = install_update(plan)
        process = Mock(pid=999)
        process.poll.return_value = 1
        with self.assertRaises(UpdateInstallError) as raised:
            wait_for_update_restart(installed, process)
        self.assertIn("kod 1", str(raised.exception))
        process.terminate.assert_not_called()

    def test_untrusted_download_url_is_rejected(self):
        release, responses = release_with_source(
            source_archive(), source_url="http://example.com/source.zip"
        )
        with self.assertRaises(UpdateInstallError):
            stage_update(release, platform="linux", target_path=self.target, opener=opener_for(responses))


class DownloadRetryTests(unittest.TestCase):
    """GitHub answers 504 until a freshly uploaded asset is ready to serve."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.destination = Path(self.temporary.name) / "asset.zip"
        self.asset = ReleaseAsset(PYTHON_RELEASE_ASSET, PACKAGE_URL)
        self.waits = []

    def download(self, opener, retries=None):
        kwargs = {"sleep": self.waits.append}
        if retries is not None:
            kwargs["retries"] = retries
        return _download_asset(self.asset, self.destination, opener=opener, **kwargs)

    def test_repeated_gateway_timeouts_are_retried_until_the_asset_arrives(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) < 3:
                raise urllib.error.HTTPError(request.full_url, 504, "Gateway Timeout", {}, None)
            return FakeResponse(request.full_url, b"package bytes")

        digest = self.download(opener)
        self.assertEqual(digest, hashlib.sha256(b"package bytes").hexdigest())
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.waits, [1.5, 3.0])
        self.assertEqual(self.destination.read_bytes(), b"package bytes")

    def test_gateway_timeout_reported_as_a_response_status_is_also_retried(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                class Timeout(FakeResponse):
                    pass
                response = Timeout(request.full_url, b"")
                response.status = 504
                return response
            return FakeResponse(request.full_url, b"package bytes")

        self.download(opener)
        self.assertEqual(len(calls), 2)

    def test_permanent_http_errors_are_reported_without_retrying(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        with self.assertRaisesRegex(UpdateInstallError, "HTTP 404"):
            self.download(opener)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.waits, [])

    def test_a_network_outage_is_retried_then_reported(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.URLError("timed out")

        with self.assertRaises(UpdateInstallError) as raised:
            self.download(opener, retries=2)
        self.assertIn("timed out", str(raised.exception))
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.waits, [1.5])

    def test_ready_handshake_removes_backup_immediately_and_startup_cleans_completed_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "paypamin-flow-python-update-test"
            backup = staging / "backup"
            backup.mkdir(parents=True)
            (backup / "old.py").write_text("# backup\n", encoding="utf-8")
            (root / "leftover.py.bak").write_text("# bak\n", encoding="utf-8")
            ready = staging / "ready.json"
            env = {
                update_installer.UPDATE_READY_FILE_ENV: str(ready),
                update_installer.UPDATE_READY_TOKEN_ENV: "token-123",
            }
            with patch.dict(update_installer.os.environ, env):
                self.assertTrue(mark_update_ready())
            self.assertFalse(backup.exists())
            self.assertTrue((staging / "update-completed.json").is_file())
            removed = update_installer.cleanup_completed_update_backups(
                temp_root=root, target_path=root
            )
            self.assertEqual(removed, 1)
            self.assertFalse(staging.exists())
            self.assertFalse((root / "leftover.py.bak").exists())


if __name__ == "__main__":
    unittest.main()
