import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


class ReminderEditingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "reminder-editing.sqlite3"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()
        for filename in ("old.svg", "new.svg"):
            (self.app.SVG_DIR / filename).write_text(f"<svg>{filename}</svg>", encoding="utf-8")
        self.owner = SimpleNamespace(logo_var=SimpleNamespace(get=lambda: "old.svg"))
        for name in ("selected_logo_path", "logo_file_path", "invoice_logo"):
            setattr(self.owner, name, MethodType(getattr(self.app.ReminderApp, name), self.owner))
        self.original_date = date(2026, 10, 1)

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_p1(self):
        values = {
            "customer": "P1 Testkund AB",
            "invoice_no": "P1-1001",
            "invoice_date": "2026-09-01",
            "due_date": "2026-09-15",
            "template_vendor": "Supplier AB",
            "amount": 1000.0,
            "currency": "SEK",
            "paid": 0,
            "email": "",
            "source": "p1-edit-test",
            "source_hash": "unique-p1-edit-source",
            "note": "",
            "reviewed": 1,
            "logo_file": "old.svg",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=?,p2_date=?,sent_count=2 WHERE invoice_no=?",
                (self.original_date.isoformat(), "2026-10-10", "P1-1001"),
            )
            row = db.execute("SELECT * FROM invoices WHERE invoice_no='P1-1001'").fetchone()
        original_path = self.app.reminder_file_path(row, "P1", self.original_date, "paminnelse")
        original_path.write_bytes(b"original P1")
        return row, original_path

    def test_replacement_logo_regenerates_original_p1_without_changing_history(self):
        row, original_path = self.save_p1()
        self.app.set_language("en")
        self.owner.write_letter = Mock(return_value=original_path)

        result = self.app.ReminderApp.update_p1_logo(self.owner, row, "new.svg")

        self.assertEqual(result, original_path)
        args, kwargs = self.owner.write_letter.call_args
        updated, level, fee, logo_path = args
        self.assertEqual(updated["logo_file"], "new.svg")
        self.assertEqual((level, fee), ("P1", 150.0))
        self.assertEqual(logo_path, str((self.app.SVG_DIR / "new.svg").resolve()))
        self.assertEqual(kwargs["reminder_date"], self.original_date)
        self.assertEqual(kwargs["output_path"], original_path)
        with self.app.connect() as db:
            saved = db.execute("SELECT logo_file,p1_date,p2_date,sent_count FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("new.svg", "2026-10-01", "2026-10-10", 2))

    def test_failed_p1_regeneration_keeps_previous_logo_and_history(self):
        row, _ = self.save_p1()
        self.owner.write_letter = Mock(return_value=None)

        result = self.app.ReminderApp.update_p1_logo(self.owner, row, "new.svg")

        self.assertIsNone(result)
        with self.app.connect() as db:
            saved = db.execute("SELECT logo_file,p1_date,p2_date,sent_count FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("old.svg", "2026-10-01", "2026-10-10", 2))

    def test_invoice_without_p1_is_not_regenerated(self):
        row, _ = self.save_p1()
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='' WHERE id=?", (row["id"],))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.owner.write_letter = Mock()
        self.assertIsNone(self.app.ReminderApp.update_p1_logo(self.owner, row, "new.svg"))
        self.owner.write_letter.assert_not_called()

    def test_atomic_p1_replacement_uses_original_date_and_filename(self):
        row, original_path = self.save_p1()
        written = []

        def write_pdf(path, *args):
            written.append((path, args[3]))
            Path(path).write_bytes(b"replacement P1")

        fake = SimpleNamespace(write_pdf=write_pdf)
        with patch.object(self.app, "open_path", return_value=True):
            result = self.app.ReminderApp.write_letter(
                fake, row, "P1", 150.0, "old.svg",
                reminder_date=self.original_date, output_path=original_path,
            )
        self.assertEqual(result, original_path)
        self.assertEqual(original_path.read_bytes(), b"replacement P1")
        self.assertEqual(written[0][1], self.original_date)
        self.assertNotEqual(written[0][0], original_path)
        self.assertFalse(written[0][0].exists())

    def test_failed_pdf_write_preserves_original_file_and_removes_temporary_file(self):
        row, original_path = self.save_p1()
        fake = SimpleNamespace(write_pdf=Mock(side_effect=RuntimeError("synthetic PDF failure")))
        with patch.object(self.app.messagebox, "showerror", create=True) as error:
            result = self.app.ReminderApp.write_letter(
                fake, row, "P1", 150.0, "old.svg",
                reminder_date=self.original_date, output_path=original_path,
            )
        self.assertIsNone(result)
        self.assertEqual(original_path.read_bytes(), b"original P1")
        self.assertEqual(list(self.app.EXPORT_DIR.glob(".paypamin-reminder-*.pdf")), [])
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
