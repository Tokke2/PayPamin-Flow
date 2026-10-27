import sys
import tempfile
import types
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

    def test_missing_p1_pdf_can_be_recreated_without_new_reminder_history(self):
        row, original_path = self.save_p1()
        snapshot = self.app.capture_p1_snapshot(row, 150.0, self.original_date.isoformat())
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_snapshot=? WHERE id=?", (snapshot, row["id"]))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertFalse(self.app.p1_file_missing(row))
        original_path.unlink()
        self.assertTrue(self.app.p1_file_missing(row))

        self.owner.selected = lambda: row
        self.owner.refresh = Mock()
        self.owner.write_letter = Mock(return_value=original_path)
        self.owner.update_p1_logo = MethodType(self.app.ReminderApp.update_p1_logo, self.owner)
        self.owner.recreate_p1 = MethodType(self.app.ReminderApp.recreate_p1, self.owner)
        with (
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm,
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            result = self.app.ReminderApp.make_reminder(self.owner)

        self.assertEqual(result, original_path)
        self.assertIn("saknas", confirm.call_args.args[1])
        args, kwargs = self.owner.write_letter.call_args
        self.assertEqual(args[1], "P1")
        self.assertEqual(kwargs["reminder_date"], self.original_date)
        self.assertIsNone(kwargs["output_path"])
        with self.app.connect() as db:
            saved = db.execute(
                "SELECT p1_date,p2_date,sent_count,p1_snapshot,logo_file FROM invoices WHERE id=?",
                (row["id"],),
            ).fetchone()
        self.assertEqual(tuple(saved), (self.original_date.isoformat(), "2026-10-10", 2, snapshot, "old.svg"))

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

        with self.app.connect() as db:
            snapshot = db.execute("SELECT p1_snapshot FROM invoices WHERE id=?", (row["id"],)).fetchone()[0]
        self.assertIsNotNone(self.app.read_p1_snapshot(snapshot))

    def test_logo_edit_uses_original_snapshot_terms_row_and_language(self):
        row, original_path = self.save_p1()
        self.app.reminder_file_path(row, "P1", self.original_date, "reminder").write_bytes(b"other language PDF")
        snapshot = self.app.capture_p1_snapshot(row, 150.0, self.original_date.isoformat())
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_snapshot=?,amount=9000,paid=100,customer='Changed after P1' WHERE id=?",
                (snapshot, row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.app.set_setting("fee", "999")
        self.app.set_setting("interest", "99")
        self.app.set_setting("objection_days", "30")
        self.app.set_setting("payment_deadline_days", "30")
        self.app.set_language("en")
        languages = []

        def write_letter(*args, **kwargs):
            languages.append(self.app.get_language())
            return original_path

        self.owner.write_letter = Mock(side_effect=write_letter)
        result = self.app.ReminderApp.update_p1_logo(self.owner, row, "new.svg")

        self.assertEqual(result, original_path)
        args, kwargs = self.owner.write_letter.call_args
        updated, _, fee, _ = args
        self.assertEqual(updated["customer"], "P1 Testkund AB")
        self.assertEqual(updated["amount"], 1000.0)
        self.assertEqual(updated["paid"], 0)
        self.assertEqual(fee, 150.0)
        self.assertEqual(kwargs["reminder_terms"], {
            "fee": 150.0,
            "interest": "23",
            "objection_days": "5",
            "payment_deadline_days": "5",
        })
        self.assertEqual(kwargs["output_path"], original_path)
        self.assertEqual(languages, ["sv"])
        self.assertEqual(self.app.get_language(), "en")
        with self.app.connect() as db:
            saved = db.execute("SELECT amount,paid,customer,p2_date,sent_count,p1_snapshot FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved[:5]), (9000.0, 100.0, "Changed after P1", "2026-10-10", 2))
        self.assertEqual(saved["p1_snapshot"], snapshot)

    def test_failed_p1_regeneration_keeps_previous_logo_and_history(self):
        row, _ = self.save_p1()
        self.owner.write_letter = Mock(return_value=None)

        result = self.app.ReminderApp.update_p1_logo(self.owner, row, "new.svg")

        self.assertIsNone(result)
        with self.app.connect() as db:
            saved = db.execute("SELECT logo_file,p1_date,p2_date,sent_count FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("old.svg", "2026-10-01", "2026-10-10", 2))

    def test_broken_svg_is_a_visible_error_and_preserves_previous_pdf(self):
        row, original_path = self.save_p1()
        fake = SimpleNamespace(
            write_pdf=Mock(side_effect=self.app.LogoEmbedError("SVG kunde inte läsas")),
        )
        with patch.object(self.app, "open_path"), patch.object(self.app.messagebox, "showerror", create=True) as error:
            result = self.app.ReminderApp.write_letter(
                fake, row, "P1", 150.0, self.app.SVG_DIR / "broken.svg",
                reminder_date=self.original_date, output_path=original_path,
            )
        self.assertIsNone(result)
        self.assertEqual(original_path.read_bytes(), b"original P1")
        self.assertEqual(error.call_args.args[0], "Logotypen kunde inte användas")
        self.assertEqual(list(self.app.EXPORT_DIR.glob(".paypamin-reminder-*")), [])

    def test_svg_parser_errors_are_not_silently_ignored(self):
        fake_svglib = types.ModuleType("svglib")
        fake_parser = types.ModuleType("svglib.svglib")
        fake_parser.svg2rlg = Mock(side_effect=ValueError("malformed SVG"))
        fake_svglib.svglib = fake_parser
        with patch.dict(sys.modules, {"svglib": fake_svglib, "svglib.svglib": fake_parser}):
            with self.assertRaises(self.app.LogoEmbedError) as raised:
                self.app.load_svg_drawing(self.app.SVG_DIR / "old.svg")
        self.assertIn("kunde inte läsas", str(raised.exception))
        with self.assertRaises(self.app.LogoEmbedError):
            self.app.load_svg_drawing(self.app.SVG_DIR / "missing.svg")

    def test_write_letter_passes_snapshot_terms_to_pdf_writer(self):
        row, original_path = self.save_p1()
        terms = {"fee": 150.0, "interest": "12", "objection_days": "7", "payment_deadline_days": "9"}
        fake = SimpleNamespace(write_pdf=Mock(side_effect=lambda path, *args: Path(path).write_bytes(b"replacement PDF")))
        with patch.object(self.app, "open_path"):
            result = self.app.ReminderApp.write_letter(
                fake, row, "P1", 150.0, "", reminder_date=self.original_date,
                output_path=original_path, reminder_terms=terms,
            )
        self.assertEqual(result, original_path)
        self.assertEqual(fake.write_pdf.call_args.args[-1], terms)

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
