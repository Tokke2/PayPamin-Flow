import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


class ReminderWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "workflow.sqlite3"
        self.app.JOURNAL_PATH = self.workspace / "reminder_journal.json"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.init_db()
        self.app.set_language("sv")

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self):
        values = {
            "customer": "Kund AB",
            "invoice_no": "FLOW-1001",
            "invoice_date": "2026-09-01",
            "due_date": "2000-01-01",
            "template_vendor": "",
            "amount": 1250.0,
            "currency": "SEK",
            "paid": 0,
            "email": "first@example.com, second@example.com",
            "source": "",
            "source_hash": "workflow-source",
            "note": "Konsulttjänst",
            "reviewed": 1,
            "logo_file": "",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices").fetchone()

    def owner_for(self, row, write_letter):
        owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=write_letter,
            refresh=Mock(),
            open_reminder_email=Mock(),
            logo_var=SimpleNamespace(get=lambda: ""),
        )
        for name in ("selected_logo_path", "logo_file_path", "invoice_logo"):
            setattr(owner, name, MethodType(getattr(self.app.ReminderApp, name), owner))
        return owner

    def test_one_click_creates_p1_then_due_p2_and_opens_only_latest_draft(self):
        row = self.save_invoice()
        self.app.set_setting("p2_days", "0")
        self.app.set_setting("payment_deadline_days", "0")
        p1 = self.workspace / "new-p1.pdf"
        p2 = self.workspace / "new-p2.pdf"
        owner = self.owner_for(row, Mock(side_effect=[p1, p2]))
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            result = self.app.ReminderApp.make_reminder(owner)

        self.assertEqual(result, p2)
        self.assertEqual([call.args[1] for call in owner.write_letter.call_args_list], ["P1", "P2"])
        self.assertEqual(confirm.call_count, 2)
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,p2_date,sent_count FROM invoices").fetchone()
            events = db.execute("SELECT level FROM reminder_events ORDER BY level").fetchall()
        self.assertEqual(saved["p1_date"], date.today().isoformat())
        self.assertEqual(saved["p2_date"], date.today().isoformat())
        self.assertEqual(saved["sent_count"], 2)
        self.assertEqual([event[0] for event in events], ["P1", "P2"])
        self.assertEqual(owner.open_reminder_email.call_count, 1)
        self.assertEqual(owner.open_reminder_email.call_args.args[1:], ("P2", p2))
        payload = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual({event["level"] for event in payload["reminders"]}, {"P1", "P2"})

    def test_new_p1_does_not_create_p2_before_p2_interval_has_passed(self):
        row = self.save_invoice()
        self.app.set_setting("p2_days", "5")
        p1 = self.workspace / "new-p1.pdf"
        owner = self.owner_for(row, Mock(return_value=p1))
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            result = self.app.ReminderApp.make_reminder(owner)

        self.assertEqual(result, p1)
        owner.write_letter.assert_called_once()
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,p2_date,sent_count FROM invoices").fetchone()
        self.assertEqual(saved["p1_date"], date.today().isoformat())
        self.assertEqual(saved["p2_date"], "")
        self.assertEqual(saved["sent_count"], 1)
        self.assertEqual(owner.open_reminder_email.call_args.args[1:], ("P1", p1))

    def test_p2_waits_for_the_payment_deadline_printed_on_p1(self):
        row = self.save_invoice()
        p1_date = (date.today() - timedelta(days=5)).isoformat()
        self.app.set_setting("payment_deadline_days", "10")
        snapshot = self.app.capture_p1_snapshot(row, 150.0, p1_date)
        self.app.set_setting("payment_deadline_days", "0")
        self.app.set_setting("p2_days", "0")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date=?,p1_snapshot=?", (p1_date, snapshot))
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.next_stage(row), "Väntar P2")
        self.assertEqual(self.app.p2_due_date(row), date.today() + timedelta(days=5))

        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date=?", ((date.today() - timedelta(days=10)).isoformat(),))
            row = db.execute("SELECT * FROM invoices").fetchone()
        self.assertEqual(self.app.p2_due_date(row), date.today())
        self.assertEqual(self.app.next_stage(row), "P2 att skapa")

    def test_missing_p1_pdf_is_recreated_before_due_p2_without_new_p1_event(self):
        row = self.save_invoice()
        p1_date = (date.today() - timedelta(days=5)).isoformat()
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date=?,sent_count=1", (p1_date,))
            row = db.execute("SELECT * FROM invoices").fetchone()
        p1 = self.app.reminder_file_path(row, "P1", date.fromisoformat(p1_date))
        p2 = self.workspace / "new-p2.pdf"

        def write_letter(_record, level, _fee, _logo_path, **_kwargs):
            return p1 if level == "P1" else p2

        owner = self.owner_for(row, Mock(side_effect=write_letter))
        owner.update_p1_logo = MethodType(self.app.ReminderApp.update_p1_logo, owner)
        owner.recreate_p1 = MethodType(self.app.ReminderApp.recreate_p1, owner)
        with (
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm,
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            result = self.app.ReminderApp.make_reminder(owner)

        self.assertEqual(result, p2)
        self.assertEqual([call.args[1] for call in owner.write_letter.call_args_list], ["P1", "P2"])
        self.assertEqual(confirm.call_count, 2)
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,p2_date,sent_count FROM invoices").fetchone()
            events = db.execute("SELECT level FROM reminder_events").fetchall()
        self.assertEqual(saved["p1_date"], p1_date)
        self.assertEqual(saved["p2_date"], date.today().isoformat())
        self.assertEqual(saved["sent_count"], 2)
        self.assertEqual([event[0] for event in events], ["P2"])
        self.assertEqual(owner.open_reminder_email.call_args.args[1:], ("P2", p2))


if __name__ == "__main__":
    unittest.main()
