import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import error_log
import paypamin_flow_launcher
from error_log import refresh_error_log
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

    def test_refresh_excludes_itself_and_removes_stale_entries(self):
        (self.log_dir / "errors.log").write_text("ERROR stale synthetic entry\n", encoding="utf-8")
        (self.log_dir / "app.log").write_text(
            "2026-10-30 10:00:00,000 INFO Healthy operation\n", encoding="utf-8"
        )

        report = refresh_error_log(self.log_dir)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertEqual(report.error_count, 0)
        self.assertIn("No errors found", consolidated)
        self.assertNotIn("stale synthetic entry", consolidated)
        self.assertNotIn("Healthy operation", consolidated)

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

        app_dir = home / ".paminnelseapp"
        consolidated = (app_dir / "errors.log").read_text(encoding="utf-8")
        self.assertIn("SOURCE: startup.log", consolidated)
        self.assertIn("RuntimeError: synthetic launcher failure", consolidated)
        message = show_error.call_args.args[0]
        self.assertIn("startup.log", message)
        self.assertIn("errors.log", message)


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
        self.assertIn("Consolidated error log refresh failed", self.app.LOG_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
