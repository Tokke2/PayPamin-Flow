import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from invoice_parser import InvoiceSection
from test_database import load_headless_app


class ReminderSourceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "source-verification.sqlite3"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()
        self.pdf = self.workspace / "original.pdf"
        self.pdf.write_bytes(b"synthetic original invoice")
        self.source_hash = "original-pdf-section-1"

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, **changes):
        values = {
            "customer": "PDF Testkund AB",
            "invoice_no": "PDF-1001",
            "invoice_date": "2026-09-01",
            "due_date": "2000-01-01",
            "template_vendor": "Supplier AB",
            "amount": 1250.0,
            "currency": "SEK",
            "paid": 0,
            "email": "kund@example.test",
            "source": str(self.pdf),
            "source_hash": self.source_hash,
            "note": "Original fakturatext",
            "reviewed": 1,
            "logo_file": "",
        }
        values.update(changes)
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (values["invoice_no"],)).fetchone()

    def candidate(self, row, **changes):
        values = {field: row[field] for field, _label in self.app.INVOICE_PDF_COMPARE_FIELDS}
        values.update(changes)
        return InvoiceSection((0,), "synthetic invoice text"), values, self.source_hash

    def owner_for(self, row):
        owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=Mock(return_value=None),
            refresh=Mock(),
            logo_var=SimpleNamespace(get=lambda: ""),
        )
        for name in ("selected_logo_path", "logo_file_path", "invoice_logo"):
            setattr(owner, name, MethodType(getattr(self.app.ReminderApp, name), owner))
        return owner

    def test_matching_original_pdf_is_checked_before_p1_confirmation(self):
        row = self.save_invoice()
        owner = self.owner_for(row)
        with (
            patch.object(self.app, "read_invoice_candidates", return_value=[self.candidate(row)]) as read,
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm,
        ):
            self.app.ReminderApp.make_reminder(owner)
        read.assert_called_once_with(self.pdf)
        confirm.assert_called_once()
        owner.write_letter.assert_called_once()

    def test_pdf_mismatch_blocks_p1_and_preserves_reminder_history(self):
        row = self.save_invoice()
        owner = self.owner_for(row)
        mismatched = self.candidate(row, amount=999.0, customer="Annans kund AB")
        with (
            patch.object(self.app, "read_invoice_candidates", return_value=[mismatched]),
            patch.object(self.app.messagebox, "askyesno", create=True) as confirm,
            patch.object(self.app.messagebox, "showwarning", create=True) as warning,
        ):
            self.app.ReminderApp.make_reminder(owner)
        confirm.assert_not_called()
        owner.write_letter.assert_not_called()
        self.assertIn("Fakturabelopp", warning.call_args.args[1])
        self.assertIn("Kundnamn", warning.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,p1_snapshot,sent_count FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("", "", 0))

    def test_multi_invoice_pdf_uses_saved_section_identity(self):
        row = self.save_invoice()
        wrong_values = {field: row[field] for field, _label in self.app.INVOICE_PDF_COMPARE_FIELDS}
        wrong_values.update(invoice_no="PDF-OTHER", amount=10.0)
        wrong = (InvoiceSection((0,), "other"), wrong_values, "other-section")
        matching = self.candidate(row)
        with patch.object(self.app, "read_invoice_candidates", return_value=[wrong, matching]):
            self.assertEqual(self.app.verify_invoice_source(row), [])

    def test_p1_verification_reuses_saved_zones_without_changing_logo(self):
        row = self.save_invoice()
        owner = self.owner_for(row)
        calls = []

        def apply_zones(path, vendor, guess, page_indexes=None, update_logo=True):
            calls.append((vendor, page_indexes, update_logo))
            guess["amount"] = row["amount"]
            return guess

        owner.apply_saved_zones = apply_zones
        generic_values = self.candidate(row, amount=1.0)
        with (
            patch.object(self.app, "read_invoice_candidates", return_value=[generic_values]),
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True),
        ):
            self.app.ReminderApp.make_reminder(owner)
        self.assertEqual(calls, [("Supplier AB", (0,), False)])
        owner.write_letter.assert_called_once()

    def test_manual_invoice_without_pdf_keeps_existing_flow(self):
        row = self.save_invoice(source="", source_hash="")
        owner = self.owner_for(row)
        with (
            patch.object(self.app, "read_invoice_candidates") as read,
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True),
        ):
            self.app.ReminderApp.make_reminder(owner)
        read.assert_not_called()
        owner.write_letter.assert_called_once()

    def test_unreadable_original_pdf_blocks_p1(self):
        row = self.save_invoice()
        owner = self.owner_for(row)
        with (
            patch.object(self.app, "read_invoice_candidates", side_effect=ValueError("synthetic PDF error")),
            patch.object(self.app.messagebox, "showerror", create=True) as error,
        ):
            self.app.ReminderApp.make_reminder(owner)
        owner.write_letter.assert_not_called()
        self.assertIn("P1 skapades inte", error.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,sent_count FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("", 0))


if __name__ == "__main__":
    unittest.main()
