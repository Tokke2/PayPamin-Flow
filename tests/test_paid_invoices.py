import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from invoice_parser import InvoiceSection
from test_database import load_headless_app


class PaidInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "paid-invoices.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, *, paid=0.0):
        record = {
            "customer": "Betald Kund AB",
            "invoice_no": "F-3001",
            "invoice_date": "2026-10-01",
            "due_date": "2026-11-01",
            "template_vendor": "",
            "amount": 1250.5,
            "currency": "SEK",
            "paid": paid,
            "email": "",
            "source": "manual-entry",
            "source_hash": "different-source-hash",
            "note": "",
            "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no='F-3001'").fetchone()

    def section(self):
        return InvoiceSection((0,), "Fakturanummer F-3001\nATT BETALA 1 250,50 SEK")

    def test_mark_invoice_paid_completes_invoice(self):
        row = self.save_invoice()
        refreshed = []
        fake = SimpleNamespace(selected=lambda: row, refresh=lambda: refreshed.append(True))

        self.app.ReminderApp.mark_invoice_paid(fake)

        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["paid"], saved["amount"])
        self.assertEqual(self.app.next_stage(saved), "Avslutad")
        self.assertEqual(refreshed, [True])

    def test_automatic_folder_import_skips_paid_invoice_silently(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "still-in-import.pdf"
        pdf.write_bytes(b"new PDF bytes with the already paid invoice number")
        fake = SimpleNamespace(
            _import_scan_running=False,
            refresh=lambda: None,
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake, automatic=True, paths=[pdf])
        info.assert_not_called()
        self.assertFalse(fake._import_scan_running)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM invoices").fetchone()[0], 1)

    def test_manual_scan_reports_paid_skip_separately(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "still-in-import.pdf"
        pdf.write_bytes(b"new PDF bytes with the already paid invoice number")
        fake = SimpleNamespace(
            _import_scan_running=False,
            refresh=lambda: None,
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake, paths=[pdf])
        summary = info.call_args.args[1]
        self.assertIn("Betalda som hoppades över: 1", summary)
        self.assertIn("Dubbletter som inte importerades: 0", summary)

    def test_manual_pdf_import_explains_paid_skip(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "paid.pdf"
        pdf.write_bytes(b"paid invoice PDF")
        fake = SimpleNamespace(
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app.filedialog, "askopenfilename", create=True, return_value=str(pdf)),
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
            patch.object(self.app.messagebox, "showwarning", create=True) as warning,
        ):
            self.app.ReminderApp.import_invoice(fake)
        warning.assert_not_called()
        self.assertEqual(info.call_args.args[0], "Betald faktura")
        self.assertIn("F-3001", info.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
