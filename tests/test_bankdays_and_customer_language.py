"""Tests for Swedish banking-day calendar (#4) and per-customer bilingual reminders (#6)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import bankdays
import learning
from customer_contacts import (
    ensure_customer_contact_schema,
    get_customer_language,
    normalize_customer_language,
    save_customer_contact,
)
from test_database import load_headless_app


class SwedishBankdayCalendarTests(unittest.TestCase):
    def test_easter_sunday_known_years(self):
        self.assertEqual(bankdays.easter_sunday(2024), date(2024, 3, 31))
        self.assertEqual(bankdays.easter_sunday(2025), date(2025, 4, 20))
        self.assertEqual(bankdays.easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(bankdays.easter_sunday(2027), date(2027, 3, 28))

    def test_midsummer_eve_and_weekend_advance_to_monday(self):
        # 2026-06-19 is Midsommarafton (Friday) -> Sat Jun 20 (Midsommardagen) -> Sun Jun 21 -> Mon Jun 22.
        self.assertFalse(bankdays.is_swedish_banking_day(date(2026, 6, 19)))
        self.assertEqual(bankdays.non_banking_reason(date(2026, 6, 19), "sv"), "Midsommarafton")
        self.assertEqual(bankdays.non_banking_reason(date(2026, 6, 19), "en"), "Midsummer Eve")
        adjusted, raw, reasons = bankdays.adjusted_deadline_date(date(2026, 6, 14), 5, language="sv")
        self.assertEqual(raw, date(2026, 6, 19))
        self.assertEqual(adjusted, date(2026, 6, 22))
        self.assertEqual(reasons, ("Midsommarafton", "Midsommardagen", "Söndag"))

    def test_christmas_and_new_year_eves_advance_to_next_banking_day(self):
        # 2026-12-24 (Thu Julafton) -> Dec 25 (Juldagen) -> Dec 26 (Annandag jul) -> Dec 27 (Sun) -> Mon Dec 28.
        self.assertEqual(bankdays.next_swedish_banking_day(date(2026, 12, 24)), date(2026, 12, 28))
        # 2026-12-31 (Thu Nyårsafton) -> 2027-01-01 (Nyårsdagen) -> Jan 2 (Sat) -> Jan 3 (Sun) -> Mon Jan 4.
        self.assertEqual(bankdays.next_swedish_banking_day(date(2026, 12, 31)), date(2027, 1, 4))

    def test_movable_red_days_are_non_banking_days(self):
        # 2026 Easter = Apr 5 -> Good Friday Apr 3, Easter Monday Apr 6, Ascension Day May 14.
        self.assertEqual(bankdays.next_swedish_banking_day(date(2026, 4, 3)), date(2026, 4, 7))
        self.assertFalse(bankdays.is_swedish_banking_day(date(2026, 5, 14)))
        self.assertEqual(bankdays.next_swedish_banking_day(date(2026, 5, 14)), date(2026, 5, 15))
        # Ordinary Wednesday is a banking day and stays unchanged.
        self.assertTrue(bankdays.is_swedish_banking_day(date(2026, 11, 25)))
        self.assertEqual(bankdays.next_swedish_banking_day(date(2026, 11, 25)), date(2026, 11, 25))


class BilingualAndBankdayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "bilingual-bankdays.sqlite3"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()
        self.app.set_setting("fee_model", "statutory")
        self.app.set_setting("payment_deadline_days", "5")

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def _pdf_text(self, path: Path) -> str:
        import pymupdf

        with pymupdf.open(path) as document:
            return "".join(page.get_text() for page in document)

    def _save_invoice(self, customer="International Client Ltd", invoice_no="INV-7001", email="ap@client.co.uk"):
        values = {
            "customer": customer,
            "invoice_no": invoice_no,
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-10",
            "template_vendor": "",
            "amount": 2500.0,
            "currency": "EUR",
            "paid": 0.0,
            "email": email,
            "source": f"src-{invoice_no}",
            "source_hash": f"hash-{invoice_no}",
            "note": "Consulting services",
            "reviewed": 1,
            "logo_file": "",
            "customer_type": "business",
            "fee_agreement": "invoice",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    def _render_pdf(self, row, output: Path, level="P1", fee=0.0, reminder_date=date(2026, 6, 14)):
        owner = SimpleNamespace()
        owner.write_pdf = MethodType(self.app.ReminderApp.write_pdf, owner)
        owner.write_letter = MethodType(self.app.ReminderApp.write_letter, owner)
        with patch.object(self.app, "open_path", create=True, return_value=None):
            return owner.write_letter(dict(row), level, fee, reminder_date=reminder_date, output_path=output)

    def test_customer_language_persists_across_invoice_edits(self):
        self.assertEqual(normalize_customer_language("EN"), "en")
        self.assertEqual(normalize_customer_language("sv"), "sv")
        self.assertEqual(normalize_customer_language("de"), "")
        row = self._save_invoice()
        with self.app.connect() as db:
            ensure_customer_contact_schema(db)
            save_customer_contact(db, row["customer"], row["email"], language="en")
            self.assertEqual(get_customer_language(db, row["customer"]), "en")

        # Editing the invoice without specifying language must keep 'en' on the customer card.
        updated = dict(row)
        updated["note"] = "Updated consulting note"
        self.assertIsNone(self.app.save_invoice_record(updated, row["id"]))
        with self.app.connect() as db:
            self.assertEqual(get_customer_language(db, row["customer"]), "en")

    def test_english_customer_gets_english_pdf_and_email_while_app_stays_swedish(self):
        en_row = self._save_invoice("Global Corp Ltd", "INV-EN-1", "billing@global.example")
        sv_row = self._save_invoice("Svensk Kund AB", "INV-SV-1", "ekonomi@svensk.example")
        with self.app.connect() as db:
            save_customer_contact(db, en_row["customer"], en_row["email"], language="en")

        self.assertEqual(self.app.get_language(), "sv")
        en_pdf = self.workspace / "p1-en.pdf"
        sv_pdf = self.workspace / "p1-sv.pdf"
        # 2026-06-14 + 5 days = 2026-06-19 (Midsommarafton) -> adjusted to Monday 2026-06-22!
        self.assertEqual(self._render_pdf(en_row, en_pdf, level="P1", reminder_date=date(2026, 6, 14)), en_pdf)
        self.assertEqual(self.app.get_language(), "sv")
        self.assertEqual(self._render_pdf(sv_row, sv_pdf, level="P1", reminder_date=date(2026, 6, 14)), sv_pdf)

        en_text = self._pdf_text(en_pdf)
        sv_text = self._pdf_text(sv_pdf)
        self.assertIn("Payment reminder number 1", en_text)
        self.assertIn("22 June 2026", en_text)
        self.assertNotIn("19 June 2026", en_text)

        self.assertIn("Betalningspåminnelse nummer 1", sv_text)
        self.assertIn("22 juni 2026", sv_text)
        self.assertNotIn("19 juni 2026", sv_text)

        # Email draft for the English customer is also in English while UI stays Swedish.
        en_mail_row = dict(en_row)
        en_mail_row["p1_date"] = "2026-06-14"
        email = self.app.build_reminder_email_content(en_mail_row, "P1", ["billing@global.example"])
        self.assertEqual(self.app.get_language(), "sv")
        self.assertIn("Invoice INV-EN-1", email["subject"])
        self.assertIn("22 June 2026", email["body"])
        self.assertIn("first reminder", email["body"])

        snapshot = json.loads(self.app.capture_reminder_snapshot(en_row, 0.0, "2026-06-14", "P1"))
        self.assertEqual(snapshot["language"], "en")

    def test_learned_payment_term_shifts_weekend_due_date_to_banking_day(self):
        learned = learning.LearnedValue(
            kind=learning.KIND_SUPPLIER,
            scope="lev",
            scope_label="Lev AB",
            field="payment_term_days",
            value="10",
            observations=5,
            total=5,
        )
        # 2026-10-01 + 10 days = 2026-10-11 (Sunday) -> Monday 2026-10-12.
        vals = {"invoice_date": "2026-10-01", "due_date": ""}
        self.app.apply_learned_value(vals, learned)
        self.assertEqual(vals["due_date"], "2026-10-12")


if __name__ == "__main__":
    unittest.main()
