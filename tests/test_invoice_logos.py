import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

from test_database import load_headless_app


class InvoiceLogoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "invoice-logos.sqlite3"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()
        for filename in ("invoice.svg", "vendor.svg", "global.svg"):
            (self.app.SVG_DIR / filename).write_text(f"<svg>{filename}</svg>", encoding="utf-8")
        self.app.set_setting("logo_file", "global.svg")
        self.app.set_setting("logo_path", str(self.app.SVG_DIR / "global.svg"))
        self.owner = SimpleNamespace(logo_var=SimpleNamespace(get=lambda: "global.svg"))
        for name in ("selected_logo_path", "logo_file_path", "invoice_logo"):
            setattr(self.owner, name, MethodType(getattr(self.app.ReminderApp, name), self.owner))

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def record(self, logo_file=None):
        return {
            "customer": "Logotypkund AB",
            "invoice_no": "LOGO-1001",
            "invoice_date": "2026-01-01",
            "due_date": "2026-01-10",
            "template_vendor": "Supplier AB",
            "amount": 1250.0,
            "currency": "SEK",
            "paid": 0,
            "email": "",
            "source": "logo-test",
            "source_hash": "unique-logo-test-source",
            "note": "",
            "reviewed": 1,
            "logo_file": logo_file,
        }

    def save_invoice(self, logo_file=None):
        values = self.record(logo_file)
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no='LOGO-1001'").fetchone()

    def map_vendor_logo(self):
        with self.app.connect() as db:
            db.execute("INSERT INTO vendor_logos(vendor,logo_file) VALUES(?,?)", ("supplier ab", "vendor.svg"))

    def test_invoice_logo_is_stored_and_preserved_on_edit(self):
        row = self.save_invoice("invoice.svg")
        self.assertEqual(row["logo_file"], "invoice.svg")
        edited = dict(row)
        edited["customer"] = "Redigerad kund AB"
        self.assertIsNone(self.app.save_invoice_record(edited, row["id"]))
        with self.app.connect() as db:
            saved = db.execute("SELECT customer,logo_file FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["customer"], "Redigerad kund AB")
        self.assertEqual(saved["logo_file"], "invoice.svg")

    def test_explicit_invoice_logo_wins_over_template_and_global(self):
        self.map_vendor_logo()
        path, name = self.owner.invoice_logo({"logo_file": "invoice.svg", "template_vendor": "Supplier AB"})
        self.assertEqual(path, str((self.app.SVG_DIR / "invoice.svg").resolve()))
        self.assertEqual(name, "invoice.svg")

    def test_template_logo_is_used_when_invoice_choice_is_inherited(self):
        self.map_vendor_logo()
        path, name = self.owner.invoice_logo({"logo_file": None, "template_vendor": "Supplier AB"})
        self.assertEqual(path, str((self.app.SVG_DIR / "vendor.svg").resolve()))
        self.assertEqual(name, "vendor.svg")

    def test_explicit_no_logo_does_not_fall_back(self):
        self.map_vendor_logo()
        path, name = self.owner.invoice_logo({"logo_file": "", "template_vendor": "Supplier AB"})
        self.assertEqual(path, "")
        self.assertEqual(name, "(Ingen logotyp)")

    def test_global_logo_is_only_the_last_fallback(self):
        path, name = self.owner.invoice_logo({"logo_file": None, "template_vendor": ""})
        self.assertEqual(path, str((self.app.SVG_DIR / "global.svg").resolve()))
        self.assertEqual(name, "global.svg")

    def test_global_fallback_uses_the_canonical_logo_path(self):
        canonical = self.workspace / "canonical-global.svg"
        with patch.object(Path, "resolve", return_value=canonical):
            path, name = self.owner.invoice_logo({"logo_file": None, "template_vendor": ""})
        self.assertEqual(path, str(canonical))
        self.assertEqual(name, "global.svg")

    def test_p1_export_keeps_invoice_logo_after_global_choice_changes(self):
        self.map_vendor_logo()
        row = self.save_invoice("invoice.svg")
        calls = []
        self.owner.selected = lambda: row
        self.owner.write_letter = lambda record, level, fee, logo_path: calls.append((record["id"], level, logo_path))
        self.owner.refresh = lambda: None
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.app.ReminderApp.make_reminder(self.owner)
        self.assertEqual(calls, [(row["id"], "P1", str((self.app.SVG_DIR / "invoice.svg").resolve()))])
        self.assertIn("invoice.svg", confirm.call_args.args[1])
        self.assertNotIn("global.svg", confirm.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
