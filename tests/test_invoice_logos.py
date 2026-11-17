import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

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
        # Logo editing is checked against the statutory amounts.
        self.app.set_setting("fee_model", "statutory")
        for filename in ("invoice.svg", "vendor.svg"):
            (self.app.SVG_DIR / filename).write_text(f"<svg>{filename}</svg>", encoding="utf-8")
        self.owner = SimpleNamespace()
        for name in ("logo_file_path", "invoice_logo", "reminder_logo_files", "reminder_logo_options"):
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

    def test_previous_customer_logo_and_email_are_reused_for_new_invoice(self):
        first = self.record("invoice.svg")
        first["email"] = "economy@example.com"
        self.assertIsNone(self.app.save_invoice_record(first))
        following = self.record(None)
        following.update(
            customer="  logotypkund   ab ", invoice_no="LOGO-1002",
            source_hash="unique-logo-test-source-2", email="",
        )

        values = self.app.apply_saved_customer_contact(following)

        self.assertEqual(values["logo_file"], "invoice.svg")
        self.assertEqual(values["email"], "economy@example.com")
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            saved = db.execute("SELECT logo_file,email FROM invoices WHERE invoice_no='LOGO-1002'").fetchone()
            contact = db.execute("SELECT logo_file FROM customer_contacts WHERE customer_key='logotypkund ab'").fetchone()
        self.assertEqual(tuple(saved), ("invoice.svg", "economy@example.com"))
        self.assertEqual(contact["logo_file"], "invoice.svg")

    def test_new_invoice_save_reuses_contact_without_dialog_prefill(self):
        first = self.record("invoice.svg")
        first["email"] = "saved@example.com"
        self.assertIsNone(self.app.save_invoice_record(first))
        following = self.record(None)
        following.update(invoice_no="LOGO-MANUAL", source_hash="manual-new-source", email="")

        self.assertIsNone(self.app.save_invoice_record(following))

        with self.app.connect() as db:
            saved = db.execute("SELECT logo_file,email FROM invoices WHERE invoice_no='LOGO-MANUAL'").fetchone()
        self.assertEqual(tuple(saved), ("invoice.svg", "saved@example.com"))

    def test_customer_logo_is_used_for_legacy_invoice(self):
        self.assertIsNone(self.app.save_invoice_record(self.record("invoice.svg")))

        path, name = self.owner.invoice_logo({
            "logo_file": None, "template_vendor": "", "customer": "Logotypkund AB",
        })

        self.assertEqual(path, str((self.app.SVG_DIR / "invoice.svg").resolve()))
        self.assertEqual(name, "invoice.svg")

    def test_customer_logo_does_not_override_explicit_invoice_choice(self):
        self.assertIsNone(self.app.save_invoice_record(self.record("invoice.svg")))
        for choice in ("vendor.svg", ""):
            following = self.record(choice)
            following.update(invoice_no="LOGO-NEW", source_hash="unique-new-source")
            values = self.app.apply_saved_customer_contact(following)
            self.assertEqual(values["logo_file"], choice)

    def test_explicit_invoice_logo_wins_over_template_and_customer(self):
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

    def test_missing_explicit_svg_is_kept_for_a_clear_pdf_error(self):
        path, name = self.owner.invoice_logo({"logo_file": "missing.svg", "template_vendor": ""})
        self.assertEqual(path, str((self.app.SVG_DIR / "missing.svg").resolve()))
        self.assertEqual(name, "missing.svg")

    def test_no_stored_choice_means_no_logo(self):
        """Without a global selector there is no hidden default to fall back on."""
        path, name = self.owner.invoice_logo({"logo_file": None, "template_vendor": "", "customer": ""})
        self.assertEqual(path, "")
        self.assertEqual(name, "(Ingen logotyp)")

    def test_reminder_logo_files_lists_the_svg_folder(self):
        (self.app.SVG_DIR / "extra.svg").write_text("<svg/>", encoding="utf-8")
        self.assertEqual(self.owner.reminder_logo_files(), ["extra.svg", "invoice.svg", "vendor.svg"])

    def test_reminder_logo_options_preselect_the_invoice_logo(self):
        choices, suggested, missing = self.owner.reminder_logo_options({"logo_file": "invoice.svg", "template_vendor": ""})
        self.assertEqual(choices, ["(Ingen logotyp)", "invoice.svg", "vendor.svg"])
        self.assertEqual(suggested, "invoice.svg")
        self.assertEqual(missing, "")

    def test_reminder_logo_options_keep_a_missing_file_visible(self):
        choices, suggested, missing = self.owner.reminder_logo_options({"logo_file": "removed.svg", "template_vendor": ""})
        self.assertEqual(choices, ["(Ingen logotyp)", "removed.svg", "invoice.svg", "vendor.svg"])
        self.assertEqual(suggested, "removed.svg")
        self.assertEqual(missing, "removed.svg")

    def test_reminder_logo_options_fall_back_to_no_logo(self):
        choices, suggested, missing = self.owner.reminder_logo_options(
            {"logo_file": None, "template_vendor": "", "customer": ""}
        )
        self.assertEqual(choices, ["(Ingen logotyp)", "invoice.svg", "vendor.svg"])
        self.assertEqual(suggested, "(Ingen logotyp)")
        self.assertEqual(missing, "")

    def test_p1_uses_the_logo_chosen_in_the_dialogue_and_stores_it(self):
        self.map_vendor_logo()
        row = self.save_invoice("invoice.svg")
        calls = []
        chosen = []
        self.owner.selected = lambda: row
        self.owner.write_letter = lambda record, level, fee, logo_path: calls.append((record["id"], level, logo_path))
        self.owner.refresh = lambda: None

        def choose(record, level):
            chosen.append((record["id"], level))
            return "vendor.svg", str((self.app.SVG_DIR / "vendor.svg").resolve()), "vendor.svg", ""

        self.owner.choose_reminder_details = choose
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.app.ReminderApp.make_reminder(self.owner)

        self.assertEqual(chosen, [(row["id"], "P1")])
        self.assertEqual(calls, [(row["id"], "P1", str((self.app.SVG_DIR / "vendor.svg").resolve()))])
        self.assertIn("vendor.svg", confirm.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_snapshot,logo_file FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["logo_file"], "vendor.svg")
        snapshot = self.app.read_p1_snapshot(saved["p1_snapshot"])
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["row"]["logo_file"], "vendor.svg")
        self.assertEqual(snapshot["terms"]["fee"], 60.0)

    def test_cancelled_logo_choice_creates_no_reminder(self):
        row = self.save_invoice(None)
        self.owner.selected = lambda: row
        self.owner.write_letter = Mock()
        self.owner.refresh = lambda: None
        self.owner.choose_reminder_details = lambda record, level: None
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.assertIsNone(self.app.ReminderApp.make_reminder(self.owner))
        confirm.assert_not_called()
        self.owner.write_letter.assert_not_called()
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date,logo_file FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertFalse(saved["p1_date"])
        self.assertIsNone(saved["logo_file"])


if __name__ == "__main__":
    unittest.main()
