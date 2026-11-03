import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reminder_archive import (
    ReminderArchiveReport,
    archive_old_reminders,
    customer_archive_path,
)
from test_database import load_headless_app


class ReminderArchiveTests(unittest.TestCase):
    def test_archives_recognized_reminders_after_one_day_to_customer_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            today = date(2026, 10, 28)
            old_p1 = export / "paminnelse(1)_F-1001_Kund_AB_2026-10-26.pdf"
            old_p2 = export / "reminder(2)_F-1002_Customer_AB_2026-09-01.pdf"
            exactly_one = export / "paminnelse(1)_F-1003_Kund_AB_2026-10-27.pdf"
            recent = export / "paminnelse(1)_F-1004_Kund_AB_2026-10-28.pdf"
            unrelated = export / "other_2020-01-01.pdf"
            invalid_date = export / "paminnelse(1)_F-1005_Kund_AB_2026-99-99.pdf"
            no_date = export / "paminnelse(1)_F-1006_Kund_AB.pdf"
            for path in (old_p1, old_p2, exactly_one, recent, unrelated, invalid_date, no_date):
                path.write_bytes(path.name.encode("utf-8"))
            customers = {
                old_p1.name: "Kund AB",
                old_p2.name: "Customer AB",
                exactly_one.name: "Kund AB",
                recent.name: "Kund AB",
            }

            report = archive_old_reminders(export, customers, today=today)

            self.assertEqual(report, ReminderArchiveReport(archived=3))
            kund_archive = export / "arkiv" / "Kund_AB"
            customer_archive = export / "arkiv" / "Customer_AB"
            self.assertEqual(
                {path.name for path in kund_archive.iterdir()},
                {old_p1.name, exactly_one.name},
            )
            self.assertEqual({path.name for path in customer_archive.iterdir()}, {old_p2.name})
            for path in (old_p1, old_p2, exactly_one):
                self.assertFalse(path.exists())
            for path in (recent, unrelated, invalid_date, no_date):
                self.assertTrue(path.is_file(), path.name)

    def test_existing_customer_archive_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            name = "paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf"
            source = export / name
            destination = customer_archive_path(export, "Kund AB", name)
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"current source")
            destination.write_bytes(b"preserved archive")

            report = archive_old_reminders(
                export, {name: "Kund AB"}, today=date(2026, 10, 28),
            )

            self.assertEqual(report, ReminderArchiveReport(conflicts=1))
            self.assertEqual(source.read_bytes(), b"current source")
            self.assertEqual(destination.read_bytes(), b"preserved archive")

    def test_unmatched_customer_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            source = export / "paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf"
            source.write_bytes(b"reminder")

            report = archive_old_reminders(export, today=date(2026, 10, 28))

            self.assertEqual(report, ReminderArchiveReport(unmatched=1))
            self.assertTrue(source.is_file())
            self.assertFalse((export / "arkiv").exists())

    def test_archive_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            export = base / "export"
            outside = base / "outside"
            export.mkdir()
            outside.mkdir()
            (export / "arkiv").symlink_to(outside, target_is_directory=True)
            name = "paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf"
            source = export / name
            source.write_bytes(b"reminder")

            report = archive_old_reminders(
                export, {name: "Kund AB"}, today=date(2026, 10, 28),
            )

            self.assertEqual(report, ReminderArchiveReport(conflicts=1))
            self.assertTrue(source.is_file())
            self.assertEqual(list(outside.iterdir()), [])

    def test_legacy_flat_archive_is_migrated_to_customer_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            export = Path(temporary)
            legacy = export / "arkiv"
            legacy.mkdir()
            name = "paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf"
            source = legacy / name
            source.write_bytes(b"legacy reminder")

            report = archive_old_reminders(
                export, {name: "Kund AB"}, today=date(2026, 10, 28),
            )

            destination = customer_archive_path(export, "Kund AB", name)
            self.assertEqual(report, ReminderArchiveReport(archived=1))
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"legacy reminder")


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

        report = archive_old_reminders(
            self.app.EXPORT_DIR, {original.name: row["customer"]}, today=date(2026, 10, 28),
        )

        archived = customer_archive_path(self.app.EXPORT_DIR, row["customer"], original.name)
        self.assertEqual(report.archived, 1)
        self.assertTrue(archived.is_file())
        self.assertIn(archived, self.app.p1_file_candidates(row))
        self.assertFalse(self.app.p1_file_missing(row))

    def test_customer_map_uses_reminder_snapshot_not_later_customer_edit(self):
        self.app.DB_PATH = self.workspace / "archive-map.sqlite3"
        self.app.init_db()
        record = {
            "customer": "Kund vid P1", "invoice_no": "F-MAP",
            "invoice_date": "2026-10-01", "due_date": "2026-10-20",
            "template_vendor": "", "amount": 1000.0, "currency": "SEK",
            "paid": 0.0, "email": "", "source": "manual", "source_hash": "map-source",
            "note": "", "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE invoice_no='F-MAP'").fetchone()
        snapshot = self.app.capture_p1_snapshot(row, 150.0, "2026-10-25")
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET customer='Ändrat kundnamn',p1_date='2026-10-25',p1_snapshot=? WHERE id=?",
                (snapshot, row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()

        customers = self.app.reminder_archive_customer_map()

        original = next(path for path in self.app.p1_file_candidates(row) if path.parent == self.app.EXPORT_DIR)
        self.assertEqual(customers[original.name], "Kund vid P1")
        self.assertIn(
            customer_archive_path(self.app.EXPORT_DIR, "Kund vid P1", original.name),
            self.app.p1_file_candidates(row),
        )

    def test_archive_runs_automatically_and_reschedules(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _run_scheduled_reminder_archive="next-archive",
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        report = ReminderArchiveReport(archived=2)
        customers = {"paminnelse(1)_F-1001_Kund_AB_2026-10-01.pdf": "Kund AB"}
        with (
            patch.object(self.app, "reminder_archive_customer_map", return_value=customers),
            patch.object(self.app, "archive_old_reminders", return_value=report) as archive,
        ):
            self.app.ReminderApp._run_scheduled_reminder_archive(fake)
        archive.assert_called_once_with(self.app.EXPORT_DIR, customers)
        self.assertEqual(scheduled, [(self.app.REMINDER_ARCHIVE_INTERVAL_MS, "next-archive")])


if __name__ == "__main__":
    unittest.main()
