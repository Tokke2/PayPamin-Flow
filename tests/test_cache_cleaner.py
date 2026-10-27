import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cache_cleaner import CleanupReport, clean_cache
from test_database import load_headless_app


NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


class SmartCacheCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.temp = self.root / "temp"
        self.source.mkdir()
        self.temp.mkdir()

    def age(self, path, hours):
        timestamp = (NOW - timedelta(hours=hours)).timestamp()
        os.utime(path, (timestamp, timestamp))

    def temp_directory(self, name, hours):
        path = self.temp / name
        path.mkdir()
        payload = path / "payload.tmp"
        payload.write_bytes(name.encode())
        self.age(payload, hours)
        self.age(path, hours)
        return path

    def test_only_stale_known_cache_entries_are_removed(self):
        bytecode = self.source / "__pycache__"
        bytecode.mkdir()
        old_pyc = bytecode / "old.pyc"
        recent_pyc = bytecode / "recent.pyc"
        unknown = bytecode / "keep.txt"
        old_pyc.write_bytes(b"old bytecode")
        recent_pyc.write_bytes(b"recent bytecode")
        unknown.write_bytes(b"not a cache candidate")
        self.age(old_pyc, 72)
        self.age(recent_pyc, 1)
        self.age(unknown, 72)

        protected_pdf = self.source / "import" / "invoice.pdf"
        protected_pdf.parent.mkdir()
        protected_pdf.write_bytes(b"invoice")
        self.age(protected_pdf, 72)
        old_update = self.temp_directory("paypamin-flow-python-update-old", 72)
        old_backup = self.temp_directory("paypamin-backup-old", 72)
        recent_update = self.temp_directory("paypamin-flow-python-update-recent", 1)
        unrelated = self.temp_directory("another-program-old", 72)

        report = clean_cache(self.source, temp_dir=self.temp, now=NOW)

        self.assertFalse(old_pyc.exists())
        self.assertTrue(recent_pyc.is_file())
        self.assertTrue(unknown.is_file())
        self.assertTrue(protected_pdf.is_file())
        self.assertFalse(old_update.exists())
        self.assertFalse(old_backup.exists())
        self.assertTrue(recent_update.is_dir())
        self.assertTrue(unrelated.is_dir())
        self.assertGreaterEqual(report.removed_files, 3)
        self.assertGreaterEqual(report.removed_directories, 2)
        self.assertGreater(report.freed_bytes, 0)
        self.assertEqual(report.errors, 0)

    def test_recent_file_protects_whole_temporary_work_directory(self):
        directory = self.temp_directory("paypamin-restore-active", 1)
        self.age(directory, 72)  # A new file must matter more than the parent timestamp.

        report = clean_cache(self.source, temp_dir=self.temp, now=NOW)

        self.assertTrue(directory.is_dir())
        self.assertTrue((directory / "payload.tmp").is_file())
        self.assertEqual(report.removed_directories, 0)

    def test_temporary_symlink_is_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        payload = outside / "keep.pdf"
        payload.write_bytes(b"keep")
        link = self.temp / "paypamin-backup-linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks are unavailable on this platform: {exc}")
        self.age(payload, 72)

        report = clean_cache(self.source, temp_dir=self.temp, now=NOW)

        self.assertTrue(payload.is_file())
        self.assertTrue(link.is_symlink())
        self.assertEqual(report.errors, 0)


class CacheCleanupUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def fake_window(self, scheduled):
        return SimpleNamespace(
            _quitting=False,
            _run_scheduled_cache_cleanup="next-cache-cleanup",
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )

    def test_daily_cleanup_runs_at_most_once_per_date(self):
        scheduled = []
        settings = {"cache_auto": "1", "cache_last_cleanup": ""}
        fake = self.fake_window(scheduled)
        report = CleanupReport(removed_files=2, removed_directories=1, freed_bytes=100)
        with (
            patch.object(self.app, "setting", side_effect=lambda key: settings.get(key, "")),
            patch.object(self.app, "set_setting", side_effect=lambda key, value: settings.__setitem__(key, value)),
            patch.object(self.app, "clean_cache", return_value=report) as cleanup,
        ):
            self.app.ReminderApp._run_scheduled_cache_cleanup(fake)
            self.app.ReminderApp._run_scheduled_cache_cleanup(fake)
        cleanup.assert_called_once_with(self.app.APP_FOLDER)
        self.assertEqual(settings["cache_last_cleanup"], self.app.date.today().isoformat())
        self.assertEqual(scheduled, [
            (self.app.CACHE_CLEANUP_INTERVAL_MS, "next-cache-cleanup"),
            (self.app.CACHE_CLEANUP_INTERVAL_MS, "next-cache-cleanup"),
        ])

    def test_daily_cleanup_respects_disabled_setting(self):
        scheduled = []
        fake = self.fake_window(scheduled)
        with (
            patch.object(self.app, "setting", side_effect=lambda key: "0" if key == "cache_auto" else ""),
            patch.object(self.app, "clean_cache") as cleanup,
        ):
            self.app.ReminderApp._run_scheduled_cache_cleanup(fake)
        cleanup.assert_not_called()
        self.assertEqual(len(scheduled), 1)

    def test_manual_cleanup_reports_result_and_counts_as_daily_run(self):
        report = CleanupReport(removed_files=3, freed_bytes=2048)
        saved = []
        with (
            patch.object(self.app, "clean_cache", return_value=report),
            patch.object(self.app, "set_setting", side_effect=lambda key, value: saved.append((key, value))),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.clear_cache_now(SimpleNamespace())
        self.assertEqual(saved, [("cache_last_cleanup", self.app.date.today().isoformat())])
        self.assertEqual(info.call_args.args[0], "Cache rensad")
        self.assertIn("2 048 byte", info.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
