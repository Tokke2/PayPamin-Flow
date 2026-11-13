import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


class FeeModelTests(unittest.TestCase):
    """The app charges 60 kr to consumers and 450 kr to businesses, once."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "fees.sqlite3"
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

    def save_invoice(self, customer_type="private", currency="SEK", number="FEE-1001"):
        values = {
            "customer": "Kund AB",
            "invoice_no": number,
            "invoice_date": "2026-09-01",
            "due_date": "2000-01-01",
            "template_vendor": "",
            "amount": 1000.0,
            "currency": currency,
            "paid": 0,
            "email": "",
            "source": "",
            "source_hash": "fee-source",
            "note": "",
            "reviewed": 1,
            "logo_file": "",
            "customer_type": customer_type,
            "fee_agreement": "contract",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (number,)).fetchone()

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
        owner.update_reminder_logo = MethodType(self.app.ReminderApp.update_reminder_logo, owner)
        return owner

    def test_amounts_are_fixed_and_not_settings(self):
        """The two amounts come from the law, so they are not editable settings."""
        row = self.save_invoice()
        self.assertEqual(self.app.REMINDER_FEE_CAP, 60.0)
        self.assertEqual(self.app.LATE_PAYMENT_COMPENSATION, 450.0)
        self.assertEqual(self.app.setting("fee"), "")
        self.assertEqual(self.app.setting("compensation"), "")
        # A value left by an older version, or written by hand, changes nothing.
        self.app.set_setting("fee", "150")
        self.assertEqual(self.app.reminder_fee_for(row), 60.0)

    def test_interest_is_the_statutory_ten_percent(self):
        """Räntelagen 6 §: the reference rate 2,00 % plus eight points."""
        self.assertEqual(self.app.LATE_PAYMENT_INTEREST, 10.0)
        self.assertEqual(self.app.setting("interest"), "")
        with self.app.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('interest','23')")
        self.app.init_db()
        self.assertEqual(self.app.setting("interest"), "")
        self.assertEqual(self.app.current_reminder_terms(60.0, "private", "SEK")["interest"], "10")

    def test_a_consumer_rate_above_the_ceiling_is_refused(self):
        """19 a § konsumentkreditlagen caps a consumer at the reference rate + 20."""
        import fee_rules

        problems = fee_rules.assess_interest("private", 23)
        self.assertEqual([issue.level for issue in problems], ["error"])
        self.assertEqual(fee_rules.assess_interest("private", 10), ())
        self.assertEqual(fee_rules.assess_interest("business", 15, "contract"), ())
        self.assertEqual([issue.level for issue in fee_rules.assess_interest("business", 15)], ["warning"])

    def test_obsolete_fee_settings_are_removed_from_the_database(self):
        with self.app.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('fee','150')")
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('compensation','999')")
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('fee_locked','1')")
        self.app.init_db()
        with self.app.connect() as db:
            left = [row["key"] for row in db.execute(
                "SELECT key FROM settings WHERE key IN ('fee','compensation','fee_locked')"
            )]
            p1_days = db.execute("SELECT value FROM settings WHERE key='p1_days'").fetchone()["value"]
        self.assertEqual(left, [])
        self.assertEqual(p1_days, "5")

    def test_consumer_invoice_gets_sixty_kronor(self):
        row = self.save_invoice()
        self.assertEqual(self.app.reminder_fee_for(row), 60.0)
        assessment = self.app.invoice_fee_assessment(row)
        self.assertFalse(assessment.blocked)
        self.assertEqual(assessment.issues, ())
        self.assertEqual(self.app.charged_fee_for(row), 0.0)

    def test_business_invoice_gets_four_hundred_and_fifty_in_compensation(self):
        row = self.save_invoice(customer_type="business")
        self.assertEqual(self.app.reminder_fee_for(row), 450.0)
        self.assertEqual(self.app.reminder_fee_note(row), "Förseningsersättning enligt 4 a § lagen (1981:739).")
        self.assertEqual(self.app.invoice_fee_assessment(row).issues, ())

    def test_authority_invoice_is_treated_as_business(self):
        row = self.save_invoice(customer_type="authority")
        self.assertEqual(self.app.reminder_fee_for(row), 450.0)

    def test_a_fee_above_the_cap_still_blocks_the_reminder(self):
        """The guard stays in place even though the app itself cannot set the amount."""
        row = self.save_invoice()
        owner = self.owner_for(row, Mock(return_value=self.workspace / "p1.pdf"))
        with (
            patch.object(self.app, "reminder_fee_for", return_value=150.0, create=True),
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm,
            patch.object(self.app.messagebox, "showerror", create=True) as error,
        ):
            result = self.app.ReminderApp.make_reminder(owner)

        self.assertIsNone(result)
        confirm.assert_not_called()
        owner.write_letter.assert_not_called()
        self.assertIn("högre än det lagliga taket", error.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_date FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["p1_date"], "")

    def test_business_reminder_never_adds_a_second_compensation_on_p2(self):
        row = self.save_invoice(customer_type="business")
        self.app.set_setting("p2_days", "0")
        self.app.set_setting("payment_deadline_days", "0")
        pdf = self.workspace / "reminder.pdf"
        owner = self.owner_for(row, Mock(return_value=pdf))
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.make_reminder(owner)

        fees = [call.args[2] for call in owner.write_letter.call_args_list]
        self.assertEqual(fees, [450.0, 450.0])
        with self.app.connect() as db:
            saved = db.execute("SELECT p1_snapshot,p2_snapshot FROM invoices WHERE id=?", (row["id"],)).fetchone()
        p1 = self.app.read_p1_snapshot(saved["p1_snapshot"])
        p2 = self.app.read_reminder_snapshot(saved["p2_snapshot"])
        self.assertEqual(p1["terms"]["fee"], 450.0)
        self.assertEqual(p1["terms"]["customer_type"], "business")
        self.assertEqual(p1["terms"]["fee_kind"], "compensation")
        self.assertEqual(p2["terms"]["fee"], 450.0)

    def test_p2_reuses_the_fee_already_charged_with_p1(self):
        row = self.save_invoice()
        self.app.set_setting("p2_days", "0")
        self.app.set_setting("payment_deadline_days", "0")
        owner = self.owner_for(row, Mock(return_value=self.workspace / "reminder.pdf"))
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.make_reminder(owner)
        # The setting changes after P1 must not change what P2 charges.
        self.app.set_setting("fee", "0")
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(self.app.reminder_fee_for_level(saved, "P2"), 60.0)

    def test_write_letter_charges_the_fee_once_for_p2(self):
        row = self.save_invoice()
        snapshot = self.app.capture_p1_snapshot(row, 60.0, "2026-10-01")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='2026-10-01',p1_snapshot=? WHERE id=?", (snapshot, row["id"]))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        totals = []

        def write_pdf(_path, _row, _level, _fee, _today, remaining, total, *_args, **_kwargs):
            totals.append((remaining, total))

        owner = SimpleNamespace(
            write_pdf=write_pdf,
            invoice_logo=lambda _row: ("", "(Ingen logotyp)"),
        )
        owner.write_letter = MethodType(self.app.ReminderApp.write_letter, owner)
        with patch.object(self.app.messagebox, "showerror", create=True):
            owner.write_letter(row, "P2", 60.0, output_path=self.workspace / "p2.pdf")

        self.assertEqual(totals, [(1000.0, 1060.0)])

    def test_a_second_reminder_pdf_does_not_repeat_the_fee_line(self):
        row = self.save_invoice(customer_type="business")
        pdf = self.workspace / "business-p2.pdf"
        snapshot = self.app.capture_p1_snapshot(row, 450.0, "2026-10-01")
        row = dict(row)
        row["p1_date"] = "2026-10-01"
        row["p1_snapshot"] = snapshot
        owner = SimpleNamespace(
            invoice_logo=lambda _row: ("", ""),
            write_pdf=MethodType(self.app.ReminderApp.write_pdf, SimpleNamespace()),
        )
        owner.write_letter = MethodType(self.app.ReminderApp.write_letter, owner)

        with patch.object(self.app, "open_path", create=True, return_value=None):
            result = owner.write_letter(row, "P2", 450.0, output_path=pdf)

        self.assertEqual(result, pdf)
        import pymupdf

        text = "".join(page.get_text() for page in pymupdf.open(pdf))
        self.assertIn("Förseningsersättning", text)
        self.assertNotIn("Förseningsersättning (påminnelse 2)", text)
        self.assertEqual(text.count("Förseningsersättning (påminnelse 1)"), 1)
        self.assertIn("1 450,00 kr", text)

    def test_legacy_p2_with_a_too_high_p1_fee_is_warned_but_not_blocked(self):
        row = self.save_invoice()
        p1_date = (date.today() - timedelta(days=5)).isoformat()
        # An invoice reminded before the fee rules existed: P1 already carried 150 kr.
        snapshot = self.app.capture_p1_snapshot(row, 150.0, p1_date)
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=?,p1_snapshot=?,sent_count=1 WHERE id=?",
                (p1_date, snapshot, row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.app.reminder_file_path(row, "P1", date.fromisoformat(p1_date)).write_bytes(b"existing P1")
        self.app.set_setting("p2_days", "0")
        self.app.set_setting("payment_deadline_days", "0")
        owner = self.owner_for(row, Mock(return_value=self.workspace / "p2.pdf"))
        with (
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm,
            patch.object(self.app.messagebox, "showerror", create=True) as error,
        ):
            self.app.ReminderApp.make_reminder(owner)

        error.assert_not_called()
        owner.write_letter.assert_called_once()
        self.assertEqual(owner.write_letter.call_args.args[1:3], ("P2", 150.0))
        self.assertIn("ligger över dagens tak", confirm.call_args.args[1])

    def test_a_legacy_zero_fee_prints_no_fee_at_all(self):
        """A historical reminder without a fee still renders without a fee row."""
        row = self.save_invoice(customer_type="business")
        pdf = self.workspace / "no-fee.pdf"
        owner = SimpleNamespace(
            invoice_logo=lambda _row: ("", ""),
            write_pdf=MethodType(self.app.ReminderApp.write_pdf, SimpleNamespace()),
        )
        owner.write_letter = MethodType(self.app.ReminderApp.write_letter, owner)
        with patch.object(self.app, "open_path", create=True, return_value=None):
            result = owner.write_letter(row, "P1", 0.0, output_path=pdf)

        self.assertEqual(result, pdf)
        import pymupdf

        text = "".join(page.get_text() for page in pymupdf.open(pdf))
        self.assertIn("Ingen avgift debiteras", text)
        self.assertNotIn("Förseningsersättning", text)
        self.assertIn("1 000,00 kr", text)

    def test_non_sek_invoice_is_reported_but_not_blocked(self):
        row = self.save_invoice(currency="EUR")
        assessment = self.app.invoice_fee_assessment(row)
        self.assertFalse(assessment.blocked)
        self.assertEqual(len(assessment.warnings), 1)
        self.assertIn("EUR", self.app.fee_issue_text(assessment.warnings[0]))

    def test_older_databases_gain_a_customer_type_column(self):
        legacy = self.workspace / "legacy.sqlite3"
        self.app.DB_PATH = legacy
        with self.app.connect() as db:
            db.execute(
                """CREATE TABLE invoices (
                id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
                due_date TEXT NOT NULL, invoice_date TEXT DEFAULT '', template_vendor TEXT DEFAULT '',
                reviewed INTEGER NOT NULL DEFAULT 1, amount REAL NOT NULL DEFAULT 0,
                paid REAL NOT NULL DEFAULT 0, email TEXT DEFAULT '', source TEXT DEFAULT '',
                ignored INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '', p1_date TEXT DEFAULT '',
                p2_date TEXT DEFAULT '', sent_count INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL
                )"""
            )
            db.execute(
                "INSERT INTO invoices(customer,invoice_no,due_date,amount,paid,created) VALUES(?,?,?,?,?,?)",
                ("Gammal kund", "OLD-1", "2026-01-01", 500.0, 0.0, "2026-01-01"),
            )
        self.app.init_db()
        self.app.init_db()
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE invoice_no='OLD-1'").fetchone()
        self.assertEqual(row["customer_type"], "private")
        self.assertEqual(row["fee_agreement"], "")
        self.assertEqual(self.app.reminder_fee_for(row), 60.0)

    def test_journal_keeps_the_customer_type(self):
        row = self.save_invoice(customer_type="business", number="FEE-JOURNAL")
        self.app.JOURNAL_PATH = self.workspace / "journal.json"
        self.app.refresh_json_journal()
        import json

        payload = json.loads(self.app.JOURNAL_PATH.read_text(encoding="utf-8"))
        saved = [item for item in payload["invoices"] if item["invoice_no"] == "FEE-JOURNAL"][0]
        self.assertEqual(saved["customer_type"], "business")
        self.assertEqual(saved["fee_agreement"], "contract")
        self.assertEqual(row["customer_type"], "business")


if __name__ == "__main__":
    unittest.main()
