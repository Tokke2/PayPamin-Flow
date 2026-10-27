import json
import sqlite3
import tempfile
from contextlib import closing
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from reminder_journal import (
    JournalError,
    create_weekly_backup,
    export_journal,
    import_journal,
    record_reminder,
)
from test_database import load_headless_app


class ReminderJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "journal.sqlite3"
        self.app.JOURNAL_PATH = self.workspace / "reminder_journal.json"
        self.app.JOURNAL_BACKUP_DIR = self.workspace / "backups" / "journal"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, invoice_no="JSON-1001"):
        values = {
            "customer": "JSON Testkund AB",
            "invoice_no": invoice_no,
            "invoice_date": "2026-09-01",
            "due_date": "2000-01-01",
            "template_vendor": "Supplier AB",
            "amount": 1250.0,
            "currency": "SEK",
            "paid": 0,
            "email": "kund@example.test",
            "source": "journal-test",
            "source_hash": "journal-source-" + invoice_no,
            "note": "Original fakturatext",
            "reviewed": 1,
            "logo_file": "supplier.svg",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    def owner_for(self, row, result):
        owner = SimpleNamespace(
            logo_var=SimpleNamespace(get=lambda: ""),
            selected=lambda: row,
            write_letter=Mock(return_value=result),
            refresh=lambda: None,
        )
        for name in ("selected_logo_path", "logo_file_path", "invoice_logo"):
            setattr(owner, name, MethodType(getattr(self.app.ReminderApp, name), owner))
        return owner

    def test_successful_p1_writes_json_and_weekly_backup_only_once(self):
        row = self.save_invoice()
        pdf = self.app.EXPORT_DIR / "paminnelse(1)_JSON-1001.pdf"
        owner = self.owner_for(row, pdf)
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.make_reminder(owner)

        payload = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["application"], "PayPamin Flow")
        self.assertEqual(len(payload["invoices"]), 1)
        self.assertEqual(len(payload["reminders"]), 1)
        event = payload["reminders"][0]
        self.assertEqual(event["level"], "P1")
        self.assertEqual(event["invoice_no"], "JSON-1001")
        self.assertEqual(event["pdf_name"], pdf.name)
        self.assertEqual(event["terms"]["fee"], 150.0)
        self.assertEqual(event["invoice"]["note"], "Original fakturatext")

        first = create_weekly_backup(
            self.app.DB_PATH, self.app.JOURNAL_PATH, self.app.JOURNAL_BACKUP_DIR,
            now=datetime(2026, 10, 27, tzinfo=timezone.utc),
        )
        second = create_weekly_backup(
            self.app.DB_PATH, self.app.JOURNAL_PATH, self.app.JOURNAL_BACKUP_DIR,
            now=datetime(2026, 10, 28, tzinfo=timezone.utc),
        )
        next_week = create_weekly_backup(
            self.app.DB_PATH, self.app.JOURNAL_PATH, self.app.JOURNAL_BACKUP_DIR,
            now=datetime(2026, 11, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(first.name, "reminder-journal-2026-W44.json")
        self.assertIsNone(second)
        self.assertEqual(next_week.name, "reminder-journal-2026-W45.json")
        self.assertEqual(len(list(self.app.JOURNAL_BACKUP_DIR.glob("*.json"))), 2)

    def test_failed_pdf_does_not_create_a_reminder_event(self):
        row = self.save_invoice("JSON-FAIL")
        owner = self.owner_for(row, None)
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.make_reminder(owner)
        self.assertFalse(self.app.JOURNAL_PATH.exists())
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 0)

    def test_import_after_reinstall_restores_data_and_repeated_import_is_deduplicated(self):
        row = self.save_invoice()
        self.app.set_setting("fee", "175")
        self.app.set_setting("language", "en")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='2026-10-20',sent_count=1 WHERE id=?", (row["id"],))
            db.execute("INSERT INTO vendor_logos(vendor,logo_file) VALUES('supplier ab','supplier.svg')")
            db.execute("INSERT INTO pdf_zones(vendor,field,page_index,x0,y0,x1,y1,samples) VALUES('supplier ab','amount',0,1,2,3,4,2)")
            db.execute("INSERT INTO pdf_zone_samples(vendor,field,page_index,x0,y0,x1,y1,created) VALUES('supplier ab','amount',0,1,2,3,4,'2026-10-20')")
        record_reminder(
            self.app.DB_PATH, self.app.JOURNAL_PATH, row["id"], "P1", "2026-10-20",
            175.0, {"fee": 175.0, "interest": "23", "objection_days": "5", "payment_deadline_days": "5"},
            "en", "supplier.svg", "reminder-1001.pdf",
        )

        target_db = self.workspace / "reinstalled.sqlite3"
        target_json = self.workspace / "reinstalled.json"
        self.app.DB_PATH = target_db
        self.app.init_db()
        result = import_journal(target_db, target_json, self.app.JOURNAL_PATH)
        self.assertEqual(result.invoices_added, 1)
        self.assertEqual(result.reminders_added, 1)
        again = import_journal(target_db, target_json, self.app.JOURNAL_PATH)
        self.assertEqual(again.invoices_added, 0)
        self.assertEqual(again.invoices_merged, 1)
        self.assertEqual(again.reminders_added, 0)
        self.assertEqual(again.reminders_skipped, 1)

        with closing(sqlite3.connect(target_db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reminder_events").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='fee'").fetchone()[0], "175")
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='language'").fetchone()[0], "en")
            self.assertEqual(db.execute("SELECT p1_date,sent_count FROM invoices").fetchone(), ("2026-10-20", 1))
            self.assertEqual(db.execute("SELECT logo_file FROM vendor_logos").fetchone()[0], "supplier.svg")
            self.assertEqual(db.execute("SELECT samples FROM pdf_zones").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pdf_zone_samples").fetchone()[0], 1)
        restored = json.loads(target_json.read_text(encoding="utf-8"))
        self.assertEqual(len(restored["reminders"]), 1)
        self.assertEqual(restored["reminders"][0]["language"], "en")

    def test_legacy_p1_and_p2_dates_are_included_without_event_rows(self):
        row = self.save_invoice("JSON-LEGACY")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='2026-10-01',p2_date='2026-10-10',sent_count=2 WHERE id=?", (row["id"],))
        export_journal(self.app.DB_PATH, self.app.JOURNAL_PATH)
        payload = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual({event["level"] for event in payload["reminders"]}, {"P1", "P2"})
        self.assertTrue(all(event["origin"] == "legacy" for event in payload["reminders"]))

    def test_invalid_import_does_not_replace_existing_data(self):
        row = self.save_invoice("JSON-SAFE")
        bad = self.workspace / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with self.assertRaises(JournalError):
            import_journal(self.app.DB_PATH, self.workspace / "new.json", bad)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT invoice_no FROM invoices").fetchone()[0], row["invoice_no"])

    def test_scheduler_reschedules_weekly_journal_job(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _run_scheduled_journal_backup="next-journal-backup",
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app, "create_weekly_journal_backup", return_value=None) as backup:
            self.app.ReminderApp._run_scheduled_journal_backup(fake)
        backup.assert_called_once_with(self.app.DB_PATH, self.app.JOURNAL_PATH, self.app.JOURNAL_BACKUP_DIR)
        self.assertEqual(scheduled, [(self.app.JOURNAL_BACKUP_INTERVAL_MS, "next-journal-backup")])


if __name__ == "__main__":
    unittest.main()
