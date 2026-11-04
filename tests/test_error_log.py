import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import error_log
import paypamin_flow_launcher
from error_log import refresh_error_log, resolve_errors
from test_database import load_headless_app


class ConsolidatedErrorLogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.log_dir = Path(self.temporary.name)

    def test_app_errors_keep_tracebacks_and_source_logs_are_unchanged(self):
        source = (
            "2026-10-30 10:00:00,000 INFO Application started\n"
            "2026-10-30 10:01:00,000 WARNING Invoice logo is missing\n"
            "2026-10-30 10:02:00,000 ERROR PDF generation failed\n"
            "Traceback (most recent call last):\n"
            "  File \"paypamin_flow.py\", line 1, in main\n"
            "RuntimeError: synthetic PDF failure\n"
            "2026-10-30 10:03:00,000 INFO Later information\n"
        )
        source_path = self.log_dir / "app.log"
        source_path.write_text(source, encoding="utf-8")

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 1)
        self.assertIn("SOURCE: app.log", consolidated)
        self.assertIn("PDF generation failed", consolidated)
        self.assertIn("RuntimeError: synthetic PDF failure", consolidated)
        self.assertIn("Traceback (most recent call last)", consolidated)
        self.assertNotIn("Application started", consolidated)
        self.assertNotIn("Invoice logo is missing", consolidated)
        self.assertNotIn("Later information", consolidated)
        self.assertEqual(source_path.read_text(encoding="utf-8"), source)

    def test_rotated_duplicates_collapse_and_distinct_incidents_are_newest_first(self):
        older = "2026-10-29 10:00:00,000 ERROR Repeated failure\n"
        (self.log_dir / "app.log.1").write_text(older, encoding="utf-8")
        (self.log_dir / "app.log").write_text(
            older + "2026-10-30 11:00:00,000 ERROR Repeated failure\n",
            encoding="utf-8",
        )

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 2)
        self.assertEqual(consolidated.count("ERROR Repeated failure"), 2)
        self.assertLess(consolidated.index("2026-10-30 11:00:00,000"), consolidated.index("2026-10-29 10:00:00,000"))

        # Reopening the view rebuilds it instead of appending the same incidents.
        refreshed = refresh_error_log(self.log_dir)
        self.assertEqual(refreshed.error_count, 2)
        self.assertEqual(refreshed.path.read_text(encoding="utf-8").count("ERROR Repeated failure"), 2)

    def test_startup_tracebacks_and_update_failures_are_included(self):
        (self.log_dir / "startup.log").write_text(
            "\n[2026-10-30T09:00:00+00:00]\n"
            "Traceback (most recent call last):\n"
            "  File \"launcher.py\", line 1, in run\n"
            "ImportError: synthetic startup failure\n",
            encoding="utf-8",
        )
        (self.log_dir / "update.log").write_text(
            "2026-10-30T09:10:00+00:00 Validated Python update 0.6.0\n"
            "2026-10-30T09:11:00+00:00 Download failed: synthetic network error\n"
            "2026-10-30T09:12:00+00:00 Rolled back Python update\n",
            encoding="utf-8",
        )

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 3)
        self.assertIn("SOURCE: startup.log", consolidated)
        self.assertIn("ImportError: synthetic startup failure", consolidated)
        self.assertIn("Download failed: synthetic network error", consolidated)
        self.assertIn("Rolled back Python update", consolidated)
        self.assertNotIn("Validated Python update", consolidated)

    def test_refresh_preserves_unresolved_entries_without_duplicating_them(self):
        (self.log_dir / "errors.log").write_text("ERROR unresolved synthetic entry\n", encoding="utf-8")
        (self.log_dir / "app.log").write_text(
            "2026-10-30 10:00:00,000 INFO Healthy operation\n", encoding="utf-8"
        )

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 1)
        self.assertIn("unresolved synthetic entry", consolidated)
        self.assertNotIn("Healthy operation", consolidated)
        refreshed = refresh_error_log(self.log_dir)
        self.assertEqual(refreshed.error_count, 1)
        self.assertEqual(refreshed.path.read_text(encoding="utf-8").count("unresolved synthetic entry"), 1)

    def test_unresolved_error_survives_source_archiving(self):
        source = self.log_dir / "app.log"
        source.write_text(
            "2026-10-30 10:02:00,000 ERROR Failure that remains unresolved\n", encoding="utf-8"
        )
        self.assertEqual(refresh_error_log(self.log_dir).error_count, 1)
        archive = self.log_dir / "arkiv" / "2026-10-30"
        archive.mkdir(parents=True)
        source.rename(archive / "app.log")

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.source_count, 0)
        self.assertIn("Failure that remains unresolved", consolidated)

    def test_resolved_errors_archive_and_do_not_return_from_unchanged_source(self):
        source = self.log_dir / "app.log"
        original = "2026-10-30 10:02:00,000 ERROR Resolved synthetic failure\n"
        source.write_text(original, encoding="utf-8")
        refresh_error_log(self.log_dir)

        resolved = resolve_errors(
            self.log_dir, today=date(2026, 11, 3),
            now=datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(resolved.resolved_count, 1)
        self.assertIn("Resolved synthetic failure", resolved.archive_path.read_text(encoding="utf-8"))
        self.assertEqual(resolved.archive_path.parent, self.log_dir / "arkiv" / "resolved" / "2026-11-03")
        self.assertIn("No unresolved errors", resolved.path.read_text(encoding="utf-8"))
        self.assertTrue((self.log_dir / "resolved-errors.json").is_file())
        self.assertEqual(refresh_error_log(self.log_dir).error_count, 0)

        source.write_text(original + "2026-11-03 09:00:00,000 ERROR New distinct failure\n", encoding="utf-8")
        refreshed = refresh_error_log(self.log_dir)
        consolidated = refreshed.path.read_text(encoding="utf-8")
        self.assertEqual(refreshed.error_count, 1)
        self.assertIn("New distinct failure", consolidated)
        self.assertNotIn("Resolved synthetic failure", consolidated)

    def test_failed_resolved_archive_preserves_active_error_and_state(self):
        (self.log_dir / "app.log").write_text(
            "2026-10-30 10:02:00,000 ERROR Keep after archive failure\n", encoding="utf-8"
        )
        refresh_error_log(self.log_dir)
        before = (self.log_dir / "errors.log").read_text(encoding="utf-8")

        with patch.object(error_log.shutil, "copyfileobj", side_effect=OSError("synthetic archive failure")):
            with self.assertRaisesRegex(OSError, "synthetic archive failure"):
                resolve_errors(self.log_dir)

        self.assertEqual((self.log_dir / "errors.log").read_text(encoding="utf-8"), before)
        self.assertFalse((self.log_dir / "resolved-errors.json").exists())

    def test_failed_atomic_replace_preserves_previous_consolidated_log(self):
        output = self.log_dir / "errors.log"
        output.write_text("previous consolidated log\n", encoding="utf-8")
        (self.log_dir / "app.log").write_text(
            "2026-10-30 10:00:00,000 ERROR New failure\n", encoding="utf-8"
        )

        with patch.object(error_log.os, "replace", side_effect=OSError("synthetic disk failure")):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                refresh_error_log(self.log_dir)

        self.assertEqual(output.read_text(encoding="utf-8"), "previous consolidated log\n")
        self.assertEqual(list(self.log_dir.glob(".errors-*.tmp")), [])

    def test_launcher_failure_is_aggregated_and_message_names_both_logs(self):
        home = self.log_dir / "home"
        with patch.object(paypamin_flow_launcher.Path, "home", return_value=home), patch.object(
            paypamin_flow_launcher, "_show_startup_error", return_value=True
        ) as show_error:
            paypamin_flow_launcher._report_startup_failure(
                "Traceback (most recent call last):\nRuntimeError: synthetic launcher failure"
            )

        app_dir = home / ".paminnelseapp" / "logs"
        consolidated = (app_dir / "errors.log").read_text(encoding="utf-8")
        self.assertIn("SOURCE: startup.log", consolidated)
        self.assertIn("RuntimeError: synthetic launcher failure", consolidated)
        message = show_error.call_args.args[0]
        self.assertIn("startup.log", message)
        self.assertIn("errors.log", message)


class LogFolderTests(unittest.TestCase):
    def test_known_legacy_logs_move_to_own_subfolder_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app_dir = workspace / ".paminnelseapp"
            log_dir = app_dir / "logs"
            log_dir.mkdir(parents=True)
            legacy = {
                "app.log": "old active app log\n",
                "app.log.1": "old rotated app log\n",
                "errors.log": "old consolidated errors\n",
                "startup.log": "old startup failure\n",
                "update.log": "old update failure\n",
            }
            for name, content in legacy.items():
                (app_dir / name).write_text(content, encoding="utf-8")
            (log_dir / "app.log").write_text("current app log\n", encoding="utf-8")
            journal = app_dir / "reminder_journal.json"
            journal.write_text("keep outside logs", encoding="utf-8")

            app = load_headless_app(workspace)
            try:
                self.assertEqual(app.LOG_DIR, log_dir)
                self.assertEqual(app.LOG_PATH, log_dir / "app.log")
                self.assertEqual(app.ERROR_LOG_PATH, log_dir / "errors.log")
                self.assertTrue((log_dir / "app.log").read_text(encoding="utf-8").startswith("current app log\n"))
                self.assertEqual((log_dir / "legacy-app.log").read_text(encoding="utf-8"), legacy["app.log"])
                for name in ("app.log.1", "errors.log", "startup.log", "update.log"):
                    self.assertEqual((log_dir / name).read_text(encoding="utf-8"), legacy[name])
                for name in legacy:
                    self.assertFalse((app_dir / name).exists())
                self.assertEqual(journal.read_text(encoding="utf-8"), "keep outside logs")
            finally:
                for handler in app.logger.handlers[:]:
                    app.logger.removeHandler(handler)
                    handler.close()


class ConsolidatedErrorLogUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_open_log_refreshes_and_opens_consolidated_file(self):
        self.app.logger.error("Synthetic UI failure")

        with patch.object(self.app, "open_path") as open_path:
            self.app.ReminderApp.open_log(SimpleNamespace())

        open_path.assert_called_once_with(self.app.ERROR_LOG_PATH)
        consolidated = self.app.ERROR_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("Synthetic UI failure", consolidated)
        self.assertIn("SOURCE: app.log", consolidated)

    def test_resolve_error_log_archives_after_confirmation(self):
        self.app.logger.error("Synthetic error awaiting resolution")

        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True) as confirm, patch.object(
            self.app.messagebox, "showinfo", create=True
        ) as info:
            self.app.ReminderApp.resolve_error_log(SimpleNamespace())

        confirm.assert_called_once()
        info.assert_called_once()
        self.assertNotIn("Synthetic error awaiting resolution", self.app.ERROR_LOG_PATH.read_text(encoding="utf-8"))
        archived = list((self.app.LOG_DIR / "arkiv" / "resolved").glob("*/*.log"))
        self.assertEqual(len(archived), 1)
        self.assertIn("Synthetic error awaiting resolution", archived[0].read_text(encoding="utf-8"))

    def test_cancelled_error_resolution_keeps_unresolved_error(self):
        self.app.logger.error("Synthetic error must remain")

        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True), patch.object(
            self.app.messagebox, "showinfo", create=True
        ) as info:
            self.app.ReminderApp.resolve_error_log(SimpleNamespace())

        info.assert_not_called()
        self.assertIn("Synthetic error must remain", self.app.ERROR_LOG_PATH.read_text(encoding="utf-8"))
        self.assertFalse((self.app.LOG_DIR / "resolved-errors.json").exists())

    def test_open_technical_log_opens_complete_app_log_with_info_records(self):
        self.app.logger.info("Synthetic customer ledger row detail")

        with patch.object(self.app, "open_path") as open_path:
            self.app.ReminderApp.open_technical_log(SimpleNamespace())

        open_path.assert_called_once_with(self.app.LOG_PATH)
        technical = self.app.LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("Synthetic customer ledger row detail", technical)
        self.assertIn("User opened technical diagnostic log", technical)

    def test_scheduled_refresh_keeps_running_after_an_aggregation_failure(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _run_scheduled_error_log_refresh="next-error-log-refresh",
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app, "refresh_error_log", side_effect=OSError("synthetic refresh failure")):
            self.app.ReminderApp._run_scheduled_error_log_refresh(fake)

        self.assertEqual(scheduled, [
            (self.app.ERROR_LOG_REFRESH_INTERVAL_MS, "next-error-log-refresh")
        ])
        self.assertIn("Consolidated error log refresh or daily archive failed", self.app.LOG_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
