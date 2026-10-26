import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_database import load_headless_app


class DuplicateInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "duplicates.sqlite3"
        self.app.init_db()

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary_directory.cleanup()

        self.addCleanup(cleanup)

    def record(self, invoice_no="F-1001", source="first.pdf", source_hash="a" * 64, customer="Exempelkund AB"):
        return {
            "customer": customer,
            "invoice_no": invoice_no,
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-31",
            "template_vendor": "",
            "amount": 1250.5,
            "currency": "SEK",
            "paid": 0.0,
            "email": "",
            "source": source,
            "source_hash": source_hash,
            "note": "",
            "reviewed": 1,
        }

    def invoice_count(self):
        with self.app.connect() as db:
            return db.execute("SELECT count(*) FROM invoices").fetchone()[0]

    def test_connection_closes_after_with_block(self):
        with self.app.connect() as connection:
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_invoice_number_is_unique_despite_case_and_whitespace(self):
        self.assertIsNone(self.app.save_invoice_record(self.record()))

        duplicate = self.record(invoice_no="  f - 1001  ", source="other.pdf", source_hash="b" * 64)
        result = self.app.save_invoice_record(duplicate)
        self.assertIsNotNone(result)
        self.assertEqual(result["invoice_no"], "F-1001")
        self.assertEqual(self.invoice_count(), 1)

        self.assertIsNone(self.app.save_invoice_record(self.record("F-1002", "second.pdf", "c" * 64)))
        self.assertEqual(self.invoice_count(), 2)

    def test_identical_pdf_content_is_rejected_even_when_renamed(self):
        self.assertIsNone(self.app.save_invoice_record(self.record()))
        renamed = self.record(invoice_no="F-9999", source="renamed.pdf", source_hash="a" * 64)

        result = self.app.save_invoice_record(renamed)
        self.assertIsNotNone(result)
        self.assertEqual(result["invoice_no"], "F-1001")
        self.assertEqual(self.invoice_count(), 1)

    def test_file_hash_depends_on_content_not_filename(self):
        first = self.workspace / "first.pdf"
        renamed = self.workspace / "renamed.pdf"
        first.write_bytes(b"same synthetic PDF bytes")
        renamed.write_bytes(first.read_bytes())
        self.assertEqual(self.app.file_sha256(first), self.app.file_sha256(renamed))
        renamed.write_bytes(b"different synthetic PDF bytes")
        self.assertNotEqual(self.app.file_sha256(first), self.app.file_sha256(renamed))

    def test_editing_allows_self_but_not_another_invoices_number(self):
        self.app.save_invoice_record(self.record())
        self.app.save_invoice_record(self.record("F-1002", "second.pdf", "b" * 64))
        with self.app.connect() as db:
            first_id = db.execute("SELECT id FROM invoices WHERE invoice_no='F-1001'").fetchone()[0]
            second_id = db.execute("SELECT id FROM invoices WHERE invoice_no='F-1002'").fetchone()[0]

        own_edit = self.record(customer="Uppdaterad kund")
        self.assertIsNone(self.app.save_invoice_record(own_edit, first_id))

        collision = self.record(" f-1001 ", "second.pdf", "b" * 64)
        self.assertIsNotNone(self.app.save_invoice_record(collision, second_id))
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT customer FROM invoices WHERE id=?", (first_id,)).fetchone()[0], "Uppdaterad kund")
            self.assertEqual(db.execute("SELECT invoice_no FROM invoices WHERE id=?", (second_id,)).fetchone()[0], "F-1002")

    def test_single_duplicate_import_warns_without_opening_preview(self):
        self.app.save_invoice_record(self.record())
        pdf = self.workspace / "duplicate.pdf"
        pdf.write_bytes(b"different bytes but the same invoice number")
        fake = SimpleNamespace(
            preview_invoice=lambda *args: self.fail("Duplicate must not open the preview"),
            add_invoice=lambda **kwargs: self.fail("Duplicate must not open the save dialog"),
        )
        with (
            patch.object(self.app.filedialog, "askopenfilename", create=True, return_value=str(pdf)),
            patch.object(self.app, "extract_pdf", return_value="synthetic text"),
            patch.object(self.app, "parse_invoice_text", return_value={"invoice_no": " f-1001 "}),
            patch.object(self.app.messagebox, "showwarning", create=True) as warning,
        ):
            self.app.ReminderApp.import_invoice(fake)
        self.assertEqual(warning.call_args.args[0], "Dubblettfaktura")
        self.assertEqual(self.invoice_count(), 1)

    def test_folder_scan_reports_duplicates_not_imported(self):
        import_dir = self.workspace / "import"
        import_dir.mkdir(exist_ok=True)
        pdf = import_dir / "renamed.pdf"
        pdf.write_bytes(b"same PDF content")
        self.app.IMPORT_DIR = import_dir
        self.app.save_invoice_record(self.record(source_hash=self.app.file_sha256(pdf)))
        fake = SimpleNamespace(
            refresh=lambda: None,
            preview_invoice=lambda *args: self.fail("Duplicate must not open the preview"),
            add_invoice=lambda **kwargs: self.fail("Duplicate must not open the save dialog"),
        )
        with (
            patch.object(self.app, "extract_pdf", return_value="synthetic text"),
            patch.object(self.app, "parse_invoice_text", return_value={"invoice_no": "F-9999"}),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake)
        self.assertIn("Dubbletter som inte importerades: 1", info.call_args.args[1])
        self.assertEqual(self.invoice_count(), 1)

    def test_duplicate_warning_is_swedish_and_english(self):
        duplicate = {"invoice_no": "F-1001", "customer": "Exempelkund AB"}
        with patch.object(self.app.messagebox, "showwarning", create=True) as warning:
            self.app.show_duplicate_invoice(duplicate, parent="parent")
            self.assertEqual(warning.call_args.args[0], "Dubblettfaktura")
            self.assertIn("har inte importerats eller sparats igen", warning.call_args.args[1])

            warning.reset_mock()
            self.app.set_language("en")
            self.app.show_duplicate_invoice(duplicate, parent="parent")
            self.assertEqual(warning.call_args.args[0], "Duplicate invoice")
            self.assertIn("was not imported or saved again", warning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
