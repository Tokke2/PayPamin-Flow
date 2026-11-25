"""A republished release must be judged by its files, not by its version.

The project keeps 0.6.0 while it is being finished and replaces the files in
the release, so the version and even the release ID stay the same while the
application changes. These tests build real ZIPs and real app directories and
prove that the difference is found - and that a genuine no-op is not offered
as an update.
"""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import update_state
from app_info import PYTHON_PACKAGE_REQUIRED_FILES, PYTHON_RELEASE_ASSET
from update_checker import (
    CONTENT_CURRENT,
    CONTENT_DIFFERS,
    CONTENT_UNAVAILABLE,
    ReleaseAsset,
    ReleaseInfo,
    is_update_available,
    release_package_sha256,
    update_change_kind,
)
from update_installer import (
    cleanup_update,
    evaluate_release,
    install_update,
    read_source_content,
    rollback_update,
    stage_update,
)


PACKAGE_URL = f"https://github.com/Tokke2/PayPamin-Flow/releases/download/v0.6.0/{PYTHON_RELEASE_ASSET}"
CHECKSUM_URL = PACKAGE_URL + ".sha256"
# The release is the tag's source archive, wrapped in one folder by GitHub.
SOURCE_URL = "https://github.com/Tokke2/PayPamin-Flow/archive/refs/tags/v0.6.0.zip"
SOURCE_COMMIT = "c" * 40
ARCHIVE_ROOT = "PayPamin-Flow-0.6.0/"


def package_bytes(version="0.6.0", overrides=None, extra=None):
    """Build a release ZIP whose files are predictable."""
    overrides = overrides or {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PYTHON_PACKAGE_REQUIRED_FILES:
            if name in overrides:
                content = overrides[name]
            elif name == "app_info.py":
                content = f'APP_VERSION = "{version}"\n'.encode()
            elif name.endswith((".py", ".pyw")):
                content = f"# release {name}\n".encode()
            elif name == "requirements.txt":
                content = b"pystray>=0.19.5\n"
            else:
                content = b"icon"
            archive.writestr(ARCHIVE_ROOT + name, content)
        for name, content in (extra or {}).items():
            archive.writestr(ARCHIVE_ROOT + name, content)
    return buffer.getvalue()


def release_for(package, *, version="0.6.0", release_id="444043893", digest=True, assets=True, updated_at=""):
    sha = hashlib.sha256(package).hexdigest()
    checksum = f"{sha}  {PYTHON_RELEASE_ASSET}\n".encode("ascii")
    package_assets = (
        (
            ReleaseAsset(
                PYTHON_RELEASE_ASSET, PACKAGE_URL,
                digest=f"sha256:{sha}" if digest else "", updated_at=updated_at,
            ),
            ReleaseAsset(PYTHON_RELEASE_ASSET + ".sha256", CHECKSUM_URL),
        )
        if assets
        else ()
    )
    release = ReleaseInfo(
        version=version,
        tag_name=f"v{version}",
        url="https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
        assets=package_assets,
        release_id=release_id,
        package_sha256=sha if digest else "",
        package_updated_at=updated_at,
        source_url=SOURCE_URL,
        source_commit=SOURCE_COMMIT,
        source_committed_at=updated_at,
    )
    return release, {PACKAGE_URL: package, CHECKSUM_URL: checksum, SOURCE_URL: package}


class FakeResponse:
    def __init__(self, url, content):
        self.url = url
        self.stream = io.BytesIO(content)
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self, size=-1):
        return self.stream.read(size)

    def geturl(self):
        return self.url


def opener_for(responses):
    requests = []

    def opener(request, timeout):
        requests.append(request.full_url)
        if request.full_url not in responses:
            raise OSError("no such asset in this test")
        return FakeResponse(request.full_url, responses[request.full_url])

    opener.requests = requests
    return opener


def write_directory(root, package):
    """Write the files of an archive into a directory, as an install would."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for name in archive.namelist():
            if not name.startswith(ARCHIVE_ROOT):
                continue
            target = Path(root) / name[len(ARCHIVE_ROOT):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


class StateFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "installed-release.json"

    def test_a_recorded_package_is_read_back(self):
        self.assertTrue(update_state.record_installed_package("a" * 64, release_id="444043893", version="0.6.0", path=self.path))
        self.assertEqual(update_state.installed_package_sha256(self.path), "a" * 64)

    def test_an_impossible_hash_is_never_recorded(self):
        for value in ("", "not-a-hash", "a" * 63, "z" * 64, None):
            with self.subTest(value=value):
                self.assertFalse(update_state.record_installed_package(value, path=self.path))
        self.assertEqual(update_state.read_state(self.path), {})

    def test_a_damaged_file_reads_as_unknown_instead_of_raising(self):
        for content in ("{not json", "[]", '"text"', json.dumps({"package_sha256": "nope"})):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                self.assertEqual(update_state.installed_package_sha256(self.path), "")

    def test_an_oversized_file_is_ignored(self):
        self.path.write_text(json.dumps({"package_sha256": "a" * 64, "padding": "x" * 100_000}), encoding="utf-8")
        self.assertEqual(update_state.read_state(self.path), {})

    def test_a_rollback_restores_the_previous_record(self):
        update_state.record_installed_package("a" * 64, path=self.path)
        previous = update_state.read_state(self.path)
        update_state.record_installed_package("b" * 64, path=self.path)
        update_state.restore_state(previous, self.path)
        self.assertEqual(update_state.installed_package_sha256(self.path), "a" * 64)
        update_state.restore_state({}, self.path)
        self.assertFalse(self.path.exists())


class FileComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_the_files_that_differ_are_named(self):
        package = package_bytes()
        write_directory(self.root, package)
        with zipfile.ZipFile(io.BytesIO(package_bytes(overrides={"paypamin_flow.py": b"# newer\n"}))) as archive:
            hashes = {
                info.filename[len(ARCHIVE_ROOT):]: hashlib.sha256(archive.read(info)).hexdigest()
                for info in archive.infolist()
            }
        difference = update_state.compare_package_files(hashes, self.root)
        self.assertEqual(difference.changed, ("paypamin_flow.py",))

    def test_a_file_the_release_adds_counts_as_a_change(self):
        write_directory(self.root, package_bytes())
        hashes = {"brand_new.py": hashlib.sha256(b"new").hexdigest()}
        self.assertEqual(
            update_state.compare_package_files(hashes, self.root).missing, ("brand_new.py",)
        )

    def test_build_info_never_decides_anything(self):
        write_directory(self.root, package_bytes())
        self.assertEqual(
            update_state.compare_package_files(
                {"build_info.py": hashlib.sha256(b"other identity").hexdigest()}, self.root
            ),
            update_state.PackageDiff(),
        )

    def test_files_that_only_exist_locally_are_none_of_the_releases_business(self):
        write_directory(self.root, package_bytes())
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_local.py").write_text("# mine", encoding="utf-8")
        (self.root / "notes.md").write_text("# notes", encoding="utf-8")
        with zipfile.ZipFile(io.BytesIO(package_bytes())) as archive:
            hashes = {
                info.filename[len(ARCHIVE_ROOT):]: hashlib.sha256(archive.read(info)).hexdigest()
                for info in archive.infolist()
            }
        self.assertEqual(update_state.compare_package_files(hashes, self.root), update_state.PackageDiff())

    def test_a_source_checkout_is_recognised(self):
        self.assertFalse(update_state.is_source_checkout(self.root))
        (self.root / ".git").mkdir()
        self.assertTrue(update_state.is_source_checkout(self.root))

    def test_a_file_list_is_shortened_for_a_dialog(self):
        names = [f"file{index}.py" for index in range(7)]
        self.assertTrue(update_state.describe_files(names).endswith("(+3)"))
        self.assertEqual(update_state.describe_files(["a.py"]), "a.py")
        self.assertEqual(update_state.describe_files([]), "")


class PackageHashTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_the_digest_github_reports_needs_no_download(self):
        release, responses = release_for(package_bytes())
        opener = opener_for(responses)
        self.assertEqual(release_package_sha256(release, opener=opener), release.package_sha256)
        self.assertEqual(opener.requests, [])

    def test_the_sidecar_is_used_when_the_digest_is_missing(self):
        release, responses = release_for(package_bytes(), digest=False)
        opener = opener_for(responses)
        expected = hashlib.sha256(responses[PACKAGE_URL]).hexdigest()
        self.assertEqual(release_package_sha256(release, opener=opener), expected)
        self.assertEqual(opener.requests, [CHECKSUM_URL])

    def test_a_missing_sidecar_is_reported_as_unknown(self):
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0")
        self.assertEqual(release_package_sha256(release, opener=opener_for({})), "")


class EvaluateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        self.state_file = self.root / "installed-release.json"

    def evaluate(self, release, responses, **options):
        return evaluate_release(
            release,
            directory=self.app_dir,
            state_file=self.state_file,
            opener=opener_for(responses),
            **options,
        )

    def test_a_newer_version_is_an_update_without_touching_the_network(self):
        release, responses = release_for(package_bytes(version="0.7.0"), version="0.7.0")
        opener = opener_for(responses)
        result = evaluate_release(release, current_version="0.6.0", directory=self.app_dir, state_file=self.state_file, opener=opener)
        self.assertTrue(is_update_available(result, "0.6.0"))
        self.assertEqual(update_change_kind(result, "0.6.0"), "version")
        self.assertEqual(opener.requests, [])

    def test_the_same_version_with_changed_files_is_an_update(self):
        """This is the bug: version and release ID are unchanged."""
        installed = package_bytes()
        write_directory(self.app_dir, installed)
        release, responses = release_for(package_bytes(overrides={"i18n.py": b"# new text\n"}), release_id="444043893")
        result = self.evaluate(release, responses)
        self.assertEqual(result.content_state, CONTENT_DIFFERS)
        self.assertTrue(is_update_available(result, "0.6.0", "444043893"))
        self.assertEqual(update_change_kind(result, "0.6.0"), "files")
        self.assertIn("i18n.py", result.changed_files)

    def test_identical_files_are_not_offered_even_when_the_release_id_differs(self):
        package = package_bytes()
        write_directory(self.app_dir, package)
        release, responses = release_for(package, release_id="999999999")
        result = self.evaluate(release, responses)
        self.assertEqual(result.content_state, CONTENT_CURRENT)
        self.assertFalse(is_update_available(result, "0.6.0", "111111111"))
        # The next check is free: the release's commit was recorded.
        self.assertEqual(update_state.installed_source_commit(self.state_file), SOURCE_COMMIT)

    def test_a_recorded_package_settles_the_question_without_a_download(self):
        release, responses = release_for(package_bytes(overrides={"tray.py": b"# newer tray\n"}))
        update_state.record_installed_package("f" * 64, path=self.state_file)
        opener = opener_for(responses)
        result = evaluate_release(release, current_version="0.6.0", directory=self.app_dir, state_file=self.state_file, opener=opener)
        self.assertEqual(result.content_state, CONTENT_DIFFERS)
        self.assertEqual(opener.requests, [])
        self.assertTrue(is_update_available(result, "0.6.0"))

    def test_a_recorded_package_equal_to_the_release_is_current(self):
        package = package_bytes()
        release, responses = release_for(package)
        update_state.record_installed_package(hashlib.sha256(package).hexdigest(), path=self.state_file)
        opener = opener_for(responses)
        result = evaluate_release(release, current_version="0.6.0", directory=self.app_dir, state_file=self.state_file, opener=opener)
        self.assertEqual(result.content_state, CONTENT_CURRENT)
        self.assertEqual(opener.requests, [])
        self.assertFalse(is_update_available(result, "0.6.0"))

    def test_a_failed_download_leaves_the_release_undecided(self):
        release, _ = release_for(package_bytes(overrides={"tray.py": b"# newer\n"}))
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener_for({}),
        )
        self.assertEqual(result.content_state, CONTENT_UNAVAILABLE)
        # Unknown falls back to the metadata, never to a false "up to date".
        self.assertTrue(is_update_available(result, "0.6.0", "1", "a" * 40))
        self.assertFalse(is_update_available(result, "0.6.0", "444043893", SOURCE_COMMIT))

    def test_content_comparison_can_be_turned_off(self):
        release, responses = release_for(package_bytes(overrides={"tray.py": b"# newer\n"}))
        result = evaluate_release(release, current_version="0.6.0", directory=self.app_dir, state_file=self.state_file, opener=opener_for(responses), compare_content=False)
        self.assertEqual(result.content_state, "")

    def test_the_probe_reads_the_archive_without_extracting_it(self):
        release, responses = release_for(package_bytes())
        content = read_source_content(release, opener=opener_for(responses))
        self.assertEqual(content.root, ARCHIVE_ROOT.rstrip("/"))
        self.assertEqual(len(content.files), len(PYTHON_PACKAGE_REQUIRED_FILES))
        # Nothing is written next to the app while only comparing.
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["app"])


class OlderReleaseTests(unittest.TestCase):
    """A release older than the installed files must never be installed.

    Content comparison can tell that the files differ, but not which set is
    newer. The ZIP's upload time settles it, so a manual replacement - or a
    checkout - is never quietly rolled back to an older release.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        self.state_file = self.root / "installed-release.json"
        # Old install, new files: exactly the state after a manual replacement.
        write_directory(self.app_dir, package_bytes(overrides={"i18n.py": b"# newer local text\n"}))
        for path in self.app_dir.rglob("*"):
            if path.is_file():
                import os
                os.utime(path, (2_000_000_000, 2_000_000_000))

    def test_a_release_uploaded_before_the_files_is_not_an_update(self):
        release, responses = release_for(
            package_bytes(overrides={"i18n.py": b"# older release text\n"}),
            updated_at="2020-01-01T00:00:00Z",
        )
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener_for(responses),
        )
        self.assertEqual(result.content_state, "stale")
        self.assertIn("i18n.py", result.changed_files)
        self.assertFalse(is_update_available(result, "0.6.0"))

    def test_a_release_uploaded_after_the_files_is_still_an_update(self):
        release, responses = release_for(
            package_bytes(overrides={"i18n.py": b"# really newer text\n"}),
            updated_at="2035-01-01T00:00:00Z",
        )
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener_for(responses),
        )
        self.assertEqual(result.content_state, "differs")
        self.assertTrue(is_update_available(result, "0.6.0"))

    def test_an_unknown_upload_time_is_treated_as_a_normal_update(self):
        release, responses = release_for(package_bytes(overrides={"i18n.py": b"# other text\n"}))
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener_for(responses),
        )
        self.assertEqual(result.content_state, "differs")
        self.assertTrue(is_update_available(result, "0.6.0"))

    def test_the_release_timestamp_is_read_from_the_asset(self):
        asset = ReleaseAsset("PayPamin-Flow-Python.zip", PACKAGE_URL, updated_at="2026-11-13T09:34:17Z")
        release = ReleaseInfo("0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0", assets=(asset,))
        self.assertEqual(release.assets[0].updated_at, "2026-11-13T09:34:17Z")

    def test_a_stale_release_is_explained_in_the_dialog(self):
        from test_database import load_headless_app
        app = load_headless_app(self.root)
        self.addCleanup(lambda: [app.logger.removeHandler(handler) or handler.close() for handler in app.logger.handlers[:]])
        release = ReleaseInfo(
            "0.6.0", "v0.6.0", "https://github.com/Tokke2/PayPamin-Flow/releases/tag/v0.6.0",
            content_state="stale",
        )
        text = app.ReminderApp._no_update_message(SimpleNamespace(), release, "abcdef123456")
        self.assertIn("nyare än releasen", text)


class SourceCommitTests(unittest.TestCase):
    """The release is the tag's source archive, so its commit is the identity."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app_dir = self.root / "app"
        self.app_dir.mkdir()
        self.state_file = self.root / "installed-release.json"
        # Installing writes the record through the module's own path, so that
        # path belongs to the test too.
        patcher = patch.object(update_state, "state_path", lambda directory=None: self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_recorded_commit_settles_the_question_without_a_download(self):
        release, responses = release_for(package_bytes())
        update_state.record_installed_package(source_commit=SOURCE_COMMIT, path=self.state_file)
        opener = opener_for(responses)
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener,
        )
        self.assertEqual(result.content_state, CONTENT_CURRENT)
        self.assertEqual(opener.requests, [], "the same commit must not download anything")
        self.assertFalse(is_update_available(result, "0.6.0"))

    def test_a_different_commit_is_an_update_without_a_download(self):
        release, responses = release_for(package_bytes())
        update_state.record_installed_package(source_commit="d" * 40, path=self.state_file)
        opener = opener_for(responses)
        result = evaluate_release(
            release, current_version="0.6.0", directory=self.app_dir,
            state_file=self.state_file, opener=opener,
        )
        self.assertEqual(result.content_state, "source_differs")
        self.assertEqual(opener.requests, [])
        self.assertTrue(is_update_available(result, "0.6.0"))
        self.assertEqual(update_change_kind(result, "0.6.0", "d" * 40), "source")

    def test_the_installed_copy_records_the_commit_it_came_from(self):
        """The next check must be a comparison, not another download."""
        release, responses = release_for(package_bytes())
        plan = stage_update(
            release, platform="linux", target_path=self.app_dir,
            log_path=self.root / "update.log", opener=opener_for(responses),
        )
        self.addCleanup(cleanup_update, plan)
        installed = install_update(plan)
        self.addCleanup(cleanup_update, installed)
        self.assertEqual(update_state.installed_source_commit(self.state_file), SOURCE_COMMIT)
        stamp = (self.app_dir / "build_info.py").read_text(encoding="utf-8")
        self.assertIn(f'APP_RELEASE_COMMIT = "{SOURCE_COMMIT}"', stamp)


class InstalledRecordTests(unittest.TestCase):
    """Installing records the package; a rollback puts the old record back."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "app"
        self.target.mkdir()
        self.state_file = self.root / "installed-release.json"
        patcher = patch.object(update_state, "state_path", lambda directory=None: self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stage(self, package):
        release, responses = release_for(package)
        plan = stage_update(
            release,
            platform="linux",
            target_path=self.target,
            log_path=self.root / "update.log",
            opener=opener_for(responses),
        )
        self.addCleanup(cleanup_update, plan)
        return plan

    def test_installing_records_the_verified_package(self):
        package = package_bytes()
        plan = self.stage(package)
        self.assertEqual(plan.package_sha256, hashlib.sha256(package).hexdigest())
        installed = install_update(plan)
        self.addCleanup(cleanup_update, installed)
        self.assertEqual(
            update_state.installed_package_sha256(self.state_file),
            hashlib.sha256(package).hexdigest(),
        )

    def test_rollback_restores_the_record_of_the_old_files(self):
        update_state.record_installed_package("a" * 64, version="0.5.0", path=self.state_file)
        plan = self.stage(package_bytes())
        installed = install_update(plan)
        self.assertNotEqual(update_state.installed_package_sha256(self.state_file), "a" * 64)
        rollback_update(installed)
        self.assertEqual(update_state.installed_package_sha256(self.state_file), "a" * 64)

    def test_corrupted_local_file_is_detected_even_when_package_digest_matches(self):
        package = package_bytes()
        plan = self.stage(package)
        installed = install_update(plan)
        self.addCleanup(cleanup_update, installed)
        # Corrupt a local tracked file after installation: the updater must
        # detect the mismatch against installed_files_fingerprint and offer repair.
        (self.target / "tray.py").write_bytes(b"# locally damaged\n")
        release, responses = release_for(package)
        result = evaluate_release(
            release,
            current_version="0.6.0",
            directory=self.target,
            state_file=self.state_file,
            opener=opener_for(responses),
        )
        self.assertEqual(result.content_state, CONTENT_DIFFERS)
        self.assertTrue(is_update_available(result, "0.6.0"))


if __name__ == "__main__":
    unittest.main()
