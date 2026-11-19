"""Failures that used to vanish into ``except ...: pass`` must leave a mark.

The rule the app follows: a swallowed error is still an error. Toolkit noise
from a window that was already closed is a warning in ``app.log``; anything
unexpected is written as an error with its traceback and therefore reaches the
consolidated ``errors.log`` the author reads. Repeating faults are counted, not
reprinted, so a callback that fails on every repaint cannot drown the log.
"""
import ast
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import error_log  # noqa: E402
import quiet_faults  # noqa: E402


class TclError(Exception):
    """Stand-in for ``tkinter.TclError``, which is not installed here."""


class ReportTests(unittest.TestCase):
    def setUp(self):
        quiet_faults.reset()
        self.addCleanup(quiet_faults.reset)
        # Without a handler logging falls back to stderr, which is not a console
        # the app has; the tests would print every expected warning.
        quiet = logging.getLogger(quiet_faults.LOGGER_NAME)
        quiet.addHandler(logging.NullHandler())
        self.addCleanup(quiet.handlers.clear)

    def report(self, error, **kwargs):
        with self.assertLogs(quiet_faults.LOGGER_NAME, level="DEBUG") as captured:
            quiet_faults.report_fault(error, **kwargs)
        return captured.records

    def test_an_unexpected_error_is_an_error_with_a_traceback(self):
        try:
            raise ValueError("bad number")
        except ValueError as error:
            records = self.report(error, site="mod:func")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelno, logging.ERROR)
        self.assertIn("mod:func", records[0].getMessage())
        self.assertIn("bad number", records[0].getMessage())
        self.assertIsNotNone(records[0].exc_info)

    def test_toolkit_teardown_is_only_a_warning(self):
        records = self.report(TclError("window has been destroyed"), site="ui:repaint")
        self.assertEqual(records[0].levelno, logging.WARNING)
        self.assertIsNone(records[0].exc_info, "expected noise should not carry a traceback")

    def test_files_and_permissions_that_are_already_gone_are_warnings(self):
        for error in (FileNotFoundError("gone"), PermissionError("locked"), OSError("busy")):
            with self.subTest(error=type(error).__name__):
                quiet_faults.reset()
                self.assertEqual(self.report(error, site="io:cleanup")[0].levelno, logging.WARNING)

    def test_the_level_can_be_forced_by_the_call_site(self):
        records = self.report(TclError("x"), site="ui:repaint", level=logging.ERROR)
        self.assertEqual(records[0].levelno, logging.ERROR)

    def test_the_same_fault_is_written_once_and_then_counted(self):
        quiet_faults.report_fault(ValueError("same"), site="mod:func")
        for _ in range(4):
            quiet_faults.report_fault(ValueError("same"), site="mod:func")
        self.assertEqual(len(quiet_faults.summary()), 1)
        self.assertIn("x5", quiet_faults.summary()[0])

    def test_a_different_site_or_type_is_a_separate_line(self):
        quiet_faults.report_fault(ValueError("a"), site="mod:one")
        quiet_faults.report_fault(KeyError("b"), site="mod:one")
        quiet_faults.report_fault(ValueError("a"), site="mod:two")
        self.assertEqual(len(quiet_faults.summary()), 3)

    def test_the_site_is_taken_from_the_calling_function(self):
        with self.assertLogs(quiet_faults.LOGGER_NAME, level="DEBUG") as captured:
            quiet_faults.report_fault(ValueError("x"))
        self.assertIn("test_the_site_is_taken_from_the_calling_function", captured.records[0].getMessage())

    def test_the_exception_being_handled_is_used_when_none_is_given(self):
        try:
            raise ValueError("from the except block")
        except ValueError:
            records = self.report(sys.exc_info()[1])
        self.assertIn("from the except block", records[0].getMessage())

    def test_reporting_never_raises(self):
        quiet_faults.report_fault(None)
        quiet_faults.report_fault(ValueError("x"), site="")
        with mock.patch.object(logging, "getLogger", side_effect=RuntimeError("no logging")):
            quiet_faults.reset()
            quiet_faults.report_fault(ValueError("x"), site="mod:func")
        self.assertEqual(quiet_faults.summary(), [], "a failed write is forgotten, not retried")

    def test_an_error_handed_over_without_a_traceback_prints_no_none_type(self):
        """``exc_info=True`` with no active exception writes "NoneType: None"."""
        records = self.report(ValueError("no traceback"), site="mod:func")
        self.assertFalse(records[0].exc_info)

    def test_a_long_message_is_cut_so_one_line_stays_one_line(self):
        records = self.report(ValueError("x" * 5000), site="mod:func")
        message = records[0].getMessage()
        self.assertLessEqual(len(message), quiet_faults._MAX_MESSAGE + 80)

    def test_the_summary_is_written_to_the_app_log(self):
        quiet_faults.report_fault(ValueError("boom"), site="mod:func")
        quiet_faults.report_fault(TclError("closed"), site="ui:repaint")
        logger = logging.getLogger("paypamin-flow")
        with self.assertLogs(logger, level="INFO") as captured:
            lines = quiet_faults.log_summary(logger)
        self.assertEqual(len(lines), 2)
        self.assertIn("Swallowed faults this session: 2 site(s)", captured.output[0])

    def test_an_empty_summary_writes_nothing(self):
        logger = logging.getLogger("paypamin-flow")
        with mock.patch.object(logger, "info") as info:
            self.assertEqual(quiet_faults.log_summary(logger), [])
        info.assert_not_called()


class ErrorLogTests(unittest.TestCase):
    """The promise is that a swallowed defect reaches ``errors.log``."""

    def setUp(self):
        quiet_faults.reset()
        self.addCleanup(quiet_faults.reset)
        # A plain TemporaryDirectory cannot be removed while the handler still
        # holds the file open, which Windows reports as WinError 32. The folder
        # is therefore cleaned up last, after the handler has been closed.
        self.folder = Path(tempfile.mkdtemp(prefix="quiet-faults-"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        record = logging.getLogger(quiet_faults.LOGGER_NAME)
        patcher = mock.patch.object(record, "propagate", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.handler = logging.FileHandler(self.folder / "app.log", encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        record.addHandler(self.handler)
        self.addCleanup(record.removeHandler, self.handler)
        self.addCleanup(self.handler.close)

    def flush(self):
        self.handler.flush()

    def test_an_unexpected_fault_ends_up_in_the_consolidated_error_log(self):
        quiet_faults.report_fault(ValueError("fee is not a number"), site="paypamin_flow:reminder_fee")
        self.flush()
        self.assertIn("ERROR", (self.folder / "app.log").read_text(encoding="utf-8"))

        error_log.refresh_error_log(self.folder)
        consolidated = (self.folder / error_log.ERROR_LOG_NAME).read_text(encoding="utf-8")
        self.assertIn("paypamin_flow:reminder_fee", consolidated)

    def test_expected_noise_does_not_claim_to_be_an_unresolved_error(self):
        quiet_faults.report_fault(TclError("window has been destroyed"), site="ui:repaint")
        self.flush()
        self.assertIn("WARNING", (self.folder / "app.log").read_text(encoding="utf-8"))

        error_log.refresh_error_log(self.folder)
        consolidated = self.folder / error_log.ERROR_LOG_NAME
        text = consolidated.read_text(encoding="utf-8") if consolidated.exists() else ""
        self.assertNotIn("ui:repaint", text)


class NoSilentHandlerTests(unittest.TestCase):
    """Keeps the fix from eroding: a new silent handler fails the suite."""

    ALLOWED = {"quiet_faults.py"}

    def test_no_module_swallows_an_exception_without_a_trace(self):
        offenders = []
        for path in sorted(ROOT.glob("*.py")):
            if path.name in self.ALLOWED:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    body = node.body
                    if len(body) == 1 and isinstance(body[0], ast.Pass):
                        offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(
            offenders, [],
            "these handlers swallow the error silently; use quiet_faults.report_fault(): "
            + ", ".join(offenders),
        )

    def test_every_module_that_reports_a_fault_imports_the_helper(self):
        for path in sorted(ROOT.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "report_fault()" not in text:
                continue
            with self.subTest(module=path.name):
                self.assertIn("from quiet_faults import", text)


if __name__ == "__main__":
    unittest.main()
