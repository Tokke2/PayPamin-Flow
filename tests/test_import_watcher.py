import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from import_watcher import ImportFolderMonitor
from test_database import load_headless_app


class ImportFolderMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.monitor = ImportFolderMonitor(self.folder)

    def test_pdf_is_offered_once_after_two_stable_polls(self):
        pdf = self.folder / "invoice.pdf"
        pdf.write_bytes(b"complete")
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [pdf])
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [])

    def test_growing_file_waits_for_a_stable_revision(self):
        pdf = self.folder / "invoice.pdf"
        pdf.write_bytes(b"first")
        self.assertEqual(self.monitor.poll(), [])
        pdf.write_bytes(b"second revision")
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [pdf])
        self.assertEqual(self.monitor.poll(), [])

    def test_changed_file_is_offered_again(self):
        pdf = self.folder / "invoice.pdf"
        pdf.write_bytes(b"one")
        self.monitor.poll()
        self.assertEqual(self.monitor.poll(), [pdf])
        pdf.write_bytes(b"a different size")
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [pdf])

    def test_removed_pending_file_is_not_offered_and_readdition_is_detected(self):
        pdf = self.folder / "invoice.pdf"
        pdf.write_bytes(b"content")
        self.monitor.poll()
        pdf.unlink()
        self.assertEqual(self.monitor.poll(), [])
        pdf.write_bytes(b"content")
        self.assertEqual(self.monitor.poll(), [])
        self.assertEqual(self.monitor.poll(), [pdf])

    def test_uppercase_pdf_suffix_is_included_and_other_files_ignored(self):
        pdf = self.folder / "FORTNOX.PDF"
        pdf.write_bytes(b"invoice")
        (self.folder / "notes.txt").write_text("not an invoice", encoding="utf-8")
        self.monitor.poll()
        self.assertEqual(self.monitor.poll(), [pdf])

    def test_missing_folder_is_safe(self):
        monitor = ImportFolderMonitor(self.folder / "missing")
        self.assertEqual(monitor.poll(), [])


class AutomaticImportUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_scheduler_scans_only_stable_files_and_reopens_hidden_window(self):
        pdf = Path(self.temporary.name) / "invoice.pdf"
        scheduled, scans, shown = [], [], []
        fake = SimpleNamespace(
            _quitting=False,
            _import_scan_running=False,
            _python_addons_ready=True,
            _run_scheduled_import_scan="next-import-scan",
            _import_monitor=SimpleNamespace(poll=lambda: [pdf]),
            state=lambda: "withdrawn",
            deiconify=lambda: shown.append(True),
            scan_import_folder=lambda **kwargs: scans.append(kwargs),
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._run_scheduled_import_scan(fake)
        self.assertEqual(scans, [{"automatic": True, "paths": [pdf]}])
        self.assertEqual(shown, [True])
        self.assertEqual(scheduled, [(self.app.IMPORT_WATCH_INTERVAL_MS, "next-import-scan")])

    def test_scheduler_respects_disabled_setting(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _import_scan_running=False,
            _python_addons_ready=True,
            _run_scheduled_import_scan="next-import-scan",
            _import_monitor=SimpleNamespace(poll=lambda: self.fail("Disabled watcher must not poll")),
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app, "setting", return_value="0"):
            self.app.ReminderApp._run_scheduled_import_scan(fake)
        self.assertEqual(len(scheduled), 1)

    def test_scheduler_waits_until_python_addons_are_ready(self):
        fake = SimpleNamespace(
            _quitting=False,
            _import_scan_running=False,
            _python_addons_ready=False,
            _run_scheduled_import_scan="next-import-scan",
            _import_monitor=SimpleNamespace(poll=lambda: self.fail("Watcher must wait for PDF add-ons")),
            after=lambda delay, callback: None,
        )
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._run_scheduled_import_scan(fake)

    def test_scheduler_does_not_overlap_an_active_scan(self):
        fake = SimpleNamespace(
            _quitting=False,
            _import_scan_running=True,
            _python_addons_ready=True,
            _run_scheduled_import_scan="next-import-scan",
            _import_monitor=SimpleNamespace(poll=lambda: self.fail("Active scan must not overlap")),
            after=lambda delay, callback: None,
        )
        with patch.object(self.app, "setting", return_value="1"):
            self.app.ReminderApp._run_scheduled_import_scan(fake)


if __name__ == "__main__":
    unittest.main()
