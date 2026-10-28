import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reminder_archive import ReminderArchiveReport, archive_old_reminders
from test_database import load_headless_app


class ReminderArchiveTests(unittest.TestCase):
    def test_archives_only_recognized_reminders_older_than_seven_days(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            today = date(2026, 10, 28)
            old_p1 = export / "paminnelse(1)_F-1001_Kund_AB_2026-10-20.pdf"
            old_p2 = export / "reminder(2)_F-1002_Customer_AB_2026-09-01.pdf"
            exactly_seven = export / "paminnelse(1)_F-1003_Kund_AB_2026-10-21.pdf"
            recent = export / "paminnelse(1)_F-1004_Kund_AB_2026-10-25.pdf"
            unrelated = export / "other_2020-01-01.pdf"
            invalid_date = export / "paminnelse(1)_F-1005_Kund_AB_2026-99-99.pdf"
            no_date = export / "paminnelse(1)_F-1006_Kund_AB.pdf"
            for path in (old_p1, old_p2, exactly_seven, recent, unrelated, invalid_date, no_date):
                path.write_bytes(path.name.encode("utf-8"))

            report = archive_old_reminders(export, today=today)

            archive = export / "arkiv"
            self.assertEqual(report, ReminderArchiveReport(archived=2))
            self.assertEqual({path.name for path in archive.iterdir()}, {old_p1.name, old_p2.name})
            self.assertFalse(old_p1.exists())
            self.assertFalse(old_p2.exists())
            for path in (exactly_seven, recent, unrelated, invalid_date, no_date):
                self.assertTrue(path.is_file(), path.name)

    def test_existing_archive_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            archive = export / "arkiv"
            archive.mkdir()
            name = "paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf"
            source = export / name
            destination = archive / name
            source.write_bytes(b"current source")
            destination.write_bytes(b"preserved archive")

            report = archive_old_reminders(export, today=date(2026, 10, 28))

            self.assertEqual(report, ReminderArchiveReport(conflicts=1))
            self.assertEqual(source.read_bytes(), b"current source")
            self.assertEqual(destination.read_bytes(), b"preserved archive")


class ArchivedP1Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_archived_p1_is_found_and_is_not_recreated_as_missing(self):
        row = {
            "invoice_no": "F-1001",
            "customer": "Kund AB",
            "p1_date": "2026-10-01",
            "p1_snapshot": "",
        }
        original = self.app.reminder_file_path(row, "P1", date(2026, 10, 1), "paminnelse")
        original.write_bytes(b"original P1")

        report = archive_old_reminders(self.app.EXPORT_DIR, today=date(2026, 10, 28))

        archived = self.app.EXPORT_DIR / "arkiv" / original.name
        self.assertEqual(report.archived, 1)
        self.assertTrue(archived.is_file())
        self.assertIn(archived, self.app.p1_file_candidates(row))
        self.assertFalse(self.app.p1_file_missing(row))

    def test_archive_runs_automatically_and_reschedules(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _run_scheduled_reminder_archive="next-archive",
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        report = ReminderArchiveReport(archived=2)
        with patch.object(self.app, "archive_old_reminders", return_value=report) as archive:
            self.app.ReminderApp._run_scheduled_reminder_archive(fake)
        archive.assert_called_once_with(self.app.EXPORT_DIR)
        self.assertEqual(scheduled, [(self.app.REMINDER_ARCHIVE_INTERVAL_MS, "next-archive")])


if __name__ == "__main__":
    unittest.main()
