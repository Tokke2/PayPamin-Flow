"""A running day must write exactly three log files.

``app.log`` holds technical events (including launcher and updater records),
``activity.log`` holds structured UI/activity events and ``errors.log`` is the
consolidated view built from the other two.
"""
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from activity_log import ACTIVITY_LOGGER_NAME, log_activity
from app_info import APP_SLUG
from error_log import refresh_error_log
from test_database import load_headless_app


class DailyLogSetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        # The loggers are process-wide, so a handler left by an earlier test
        # module would otherwise keep writing to another temporary folder.
        self._detach(APP_SLUG)
        self._detach(ACTIVITY_LOGGER_NAME)
        self.app = load_headless_app(self.workspace)
        self.addCleanup(self._close)

    @staticmethod
    def _detach(name):
        logger = logging.getLogger(name)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    def _close(self):
        self._detach(APP_SLUG)
        self._detach(ACTIVITY_LOGGER_NAME)

    def _written_names(self):
        return sorted(path.name for path in self.app.LOG_DIR.iterdir() if path.name.endswith(".log"))

    def test_a_running_day_writes_exactly_three_named_logs(self):
        self.app.logger.info("technical event")
        with patch.object(self.app.logger, "handlers", self.app.logger.handlers):
            for handler in self.app.logger.handlers:
                handler.flush()
        log_activity("test", "activity_event", "completed")
        for handler in logging.getLogger(ACTIVITY_LOGGER_NAME).handlers:
            handler.flush()
        refresh_error_log(self.app.LOG_DIR)

        self.assertEqual(self.app.DAILY_LOG_NAMES, ("app.log", "activity.log", "errors.log"))
        self.assertEqual(self._written_names(), ["activity.log", "app.log", "errors.log"])

    def test_activity_events_go_to_their_own_file_and_not_app_log(self):
        self.app.logger.info("technical only")
        log_activity("test", "activity_only", "completed")
        for logger in (self.app.logger, logging.getLogger(ACTIVITY_LOGGER_NAME)):
            for handler in logger.handlers:
                handler.flush()

        self.assertIn("technical only", self.app.LOG_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("activity_only", self.app.LOG_PATH.read_text(encoding="utf-8"))
        activity_text = self.app.ACTIVITY_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("Activity:", activity_text)
        self.assertIn("activity_only", activity_text)
        self.assertNotIn("technical only", activity_text)

    def test_consolidated_error_log_collects_failures_from_both_sources(self):
        self.app.logger.error("Technical failure in app.log")
        try:
            raise RuntimeError("activity failure")
        except RuntimeError:
            log_activity("test", "failing_action", "error", level=logging.ERROR, exc_info=True)
        for logger in (self.app.logger, logging.getLogger(ACTIVITY_LOGGER_NAME)):
            for handler in logger.handlers:
                handler.flush()

        report = refresh_error_log(self.app.LOG_DIR)
        consolidated = report.path.read_text(encoding="utf-8")

        self.assertIn("SOURCE: app.log", consolidated)
        self.assertIn("SOURCE: activity.log", consolidated)
        self.assertIn("Technical failure in app.log", consolidated)
        self.assertIn("RuntimeError: activity failure", consolidated)
        # Healthy activity events never leak into the error view.
        self.assertNotIn("activity_only", consolidated)

    def test_archiving_keeps_the_consolidated_error_log_active(self):
        self.app.logger.error("Unresolved failure")
        for handler in self.app.logger.handlers:
            handler.flush()
        refresh_error_log(self.app.LOG_DIR)

        with patch.object(self.app, "date") as fake_date:
            fake_date.today.return_value = self.app.date(2026, 11, 3)
            self.app._archive_previous_day_logs()

        self.assertTrue(self.app.ERROR_LOG_PATH.is_file())
        self.assertIn("Unresolved failure", self.app.ERROR_LOG_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
