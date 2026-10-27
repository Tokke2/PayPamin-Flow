import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from invoice_parser import InvoiceSection
from test_database import load_headless_app


class MultiInvoiceImportUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "multi-invoice.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def fake_ui(self, previews):
        def preview(path, guess, vendor="", page_indexes=None):
            previews.append(page_indexes)
            return guess

        def add_invoice(source, guess, source_hash):
            record = {
                "customer": guess.get("customer") or "Testkund AB",
                "invoice_no": guess["invoice_no"],
                "invoice_date": guess.get("invoice_date", ""),
                "due_date": guess.get("due_date") or "2026-12-31",
                "template_vendor": guess.get("template_vendor", ""),
                "amount": guess.get("amount", 0),
                "currency": guess.get("currency", "SEK"),
                "paid": 0,
                "email": "",
                "source": source,
                "source_hash": source_hash,
                "note": guess.get("note", ""),
                "reviewed": 1,
            }
            self.assertIsNone(self.app.save_invoice_record(record))

        return SimpleNamespace(
            _import_scan_running=False,
            guess_supplier=lambda text: "",
            apply_saved_zones=lambda path, vendor, guess, page_indexes=None: guess,
            preview_invoice=preview,
            add_invoice=add_invoice,
            refresh=lambda: None,
        )

    def test_manual_import_saves_every_invoice_with_its_own_pages(self):
        pdf = self.workspace / "bundled.pdf"
        pdf.write_bytes(b"synthetic bundled PDF")
        sections = [
            InvoiceSection((0, 1), "Fakturanummer 9001\nFörfallodatum 2026-12-01\nATT BETALA 1 000,00 SEK"),
            InvoiceSection((2,), "Invoice # INV-9002\nDue date: 2026-12-15\nTotal due EUR 250,50"),
        ]
        previews = []
        fake = self.fake_ui(previews)
        with (
            patch.object(self.app.filedialog, "askopenfilename", create=True, return_value=str(pdf)),
            patch.object(self.app, "extract_invoice_sections", return_value=sections),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.import_invoice(fake)

        self.assertEqual(previews, [(0, 1), (2,)])
        with self.app.connect() as db:
            rows = {row["invoice_no"]: row for row in db.execute("SELECT * FROM invoices")}
        self.assertEqual(set(rows), {"9001", "INV-9002"})
        self.assertEqual(rows["9001"]["amount"], 1000.0)
        self.assertEqual(rows["INV-9002"]["amount"], 250.5)
        self.assertEqual(rows["INV-9002"]["currency"], "EUR")
        self.assertNotEqual(rows["9001"]["source_hash"], rows["INV-9002"]["source_hash"])
        self.assertIn("Importerade: 2", info.call_args.args[1])

    def test_folder_reimport_skips_saved_invoice_and_imports_remaining(self):
        import_dir = self.workspace / "import"
        import_dir.mkdir(exist_ok=True)
        pdf = import_dir / "bundled.pdf"
        pdf.write_bytes(b"synthetic bundled PDF revision")
        self.app.IMPORT_DIR = import_dir
        sections = [
            InvoiceSection((0,), "Fakturanummer 9101\nATT BETALA 100,00 SEK"),
            InvoiceSection((1,), "Fakturanummer 9102\nATT BETALA 200,00 SEK"),
        ]
        file_hash = self.app.file_sha256(pdf)
        first_hash = self.app.invoice_section_hash(file_hash, (0,), 2)
        self.app.save_invoice_record({
            "customer": "Befintlig kund",
            "invoice_no": "9101",
            "invoice_date": "",
            "due_date": "2026-12-01",
            "template_vendor": "",
            "amount": 100,
            "currency": "SEK",
            "paid": 0,
            "email": "",
            "source": str(pdf.resolve()),
            "source_hash": first_hash,
            "note": "",
            "reviewed": 1,
        })
        previews = []
        fake = self.fake_ui(previews)
        with (
            patch.object(self.app, "extract_invoice_sections", return_value=sections),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake, paths=[pdf])

        self.assertEqual(previews, [(1,)])
        with self.app.connect() as db:
            numbers = {row[0] for row in db.execute("SELECT invoice_no FROM invoices")}
        self.assertEqual(numbers, {"9101", "9102"})
        self.assertIn("Importerade: 1", info.call_args.args[1])
        self.assertIn("Dubbletter som inte importerades: 1", info.call_args.args[1])
        self.assertFalse(fake._import_scan_running)


if __name__ == "__main__":
    unittest.main()
