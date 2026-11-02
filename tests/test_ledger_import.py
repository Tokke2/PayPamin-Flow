import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date as real_date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ledger_import import (
    LedgerImportError, LedgerPlan, LedgerResult, apply_ledger_import,
    parse_ledger_pages, plan_ledger_import, read_ledger_report,
)
from reminder_journal import export_journal, import_journal
from test_database import load_headless_app


PAGES = [
    """Tadega AB
Kundreskontralista
Per datum 2026-11-02
Kundnr Kund
123800680 Sensor Försäkring Norden AB
1001 2026-10-01 2026-10-31 SEK 1 000,00 1 000,00
1002 2026-10-02 2026-11-01 B 671 SEK 2 000,00 500,00
Antal fakturor 2
Summa i SEK 1 500,00
1/3
""",
    """Tadega AB
Kundreskontralista
Per datum 2026-11-02
19207300 Jonsson Bil & Trailer AB
1003 2026-10-12 2026-10-27 SEK 3 000,00 3 000,00
Antal fakturor 1
Summa i SEK 3 000,00
2/3
""",
    """Tadega AB
Kundreskontralista
Per datum 2026-11-02
50616011 Haga Limo AB / Håkan Andersson
1004 2026-10-19 2026-10-19 SEK 500,00 500,00
Antal fakturor 1
Summa i SEK 500,00
Antal fakturor 4
Totalsumma i SEK 5 000,00
3/3
""",
]


class LedgerParserTests(unittest.TestCase):
    def test_reads_complete_pages_in_any_selection_order(self):
        report = parse_ledger_pages([PAGES[2], PAGES[0], PAGES[1]])

        self.assertEqual(report.list_date, "2026-11-02")
        self.assertEqual(report.expected_count, 4)
        self.assertEqual(report.page_count, 3)
        self.assertEqual(report.expected_total, 5000.0)
        self.assertEqual(report.actual_total, 5000.0)
        self.assertTrue(report.total_verified)
        self.assertEqual([entry.invoice_no for entry in report.entries], ["1001", "1002", "1003", "1004"])
        self.assertEqual(report.entries[0].customer, "Sensor Försäkring Norden AB")
        self.assertEqual(report.entries[0].customer_number, "123800680")
        self.assertEqual(report.entries[1].paid, 1500.0)
        self.assertEqual(report.entries[2].due_date, "2026-10-27")

    def test_reads_text_based_pdf_without_ocr(self):
        import fitz

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.pdf"
            document = fitz.open()
            for text in PAGES:
                page = document.new_page(width=1200, height=800)
                page.insert_text((36, 36), text, fontname="helv", fontsize=8)
            document.save(path)
            document.close()
            report = read_ledger_report(path)

        self.assertEqual(report.expected_count, 4)
        self.assertEqual(report.expected_total, 5000.0)
        self.assertEqual([entry.invoice_no for entry in report.entries], ["1001", "1002", "1003", "1004"])

    def test_accepts_compact_pdf_text_labels(self):
        pages = [
            text.replace("Per datum ", "Perdatum")
            .replace("Antal fakturor ", "Antalfakturor ")
            .replace("Totalsumma i SEK", "TotalsummaiSEK")
            for text in PAGES
        ]
        report = parse_ledger_pages(pages)
        self.assertEqual(report.expected_count, 4)
        self.assertEqual(report.actual_total, 5000.0)

    def test_unreadable_invoice_row_is_named_and_blocks_import(self):
        pages = PAGES[:]
        pages[0] = pages[0].replace("1 000,00 1 000,00", "1 000,00 OLÄSBART", 1)
        with self.assertRaisesRegex(LedgerImportError, "Fakturaraden") as raised:
            parse_ledger_pages(pages)
        self.assertIn("1001", str(raised.exception))

    def test_rejects_missing_page(self):
        with self.assertRaisesRegex(LedgerImportError, "ofullständig"):
            parse_ledger_pages([PAGES[0], PAGES[2]])

    def test_rejects_count_mismatch(self):
        pages = PAGES[:]
        pages[2] = pages[2].replace("Antal fakturor 4\nTotalsumma", "Antal fakturor 5\nTotalsumma")
        with self.assertRaisesRegex(LedgerImportError, "Fakturaantalet"):
            parse_ledger_pages(pages)

    def test_rejects_total_mismatch(self):
        pages = PAGES[:]
        pages[2] = pages[2].replace("Totalsumma i SEK 5 000,00", "Totalsumma i SEK 5 001,00")
        with self.assertRaisesRegex(LedgerImportError, "Totalsumman"):
            parse_ledger_pages(pages)

    def test_non_sek_list_is_importable_but_not_paid_reconciled(self):
        pages = PAGES[:]
        pages[0] = pages[0].replace("B 671 SEK", "B 671 EUR")
        report = parse_ledger_pages(pages)
        self.assertFalse(report.total_verified)


class LedgerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "ledger.sqlite3"
        self.app.init_db()
        self.report = parse_ledger_pages(PAGES)

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_existing(self, invoice_no="1001", amount=1234.0, paid=100.0):
        values = {
            "customer": "Befintlig kund", "invoice_no": invoice_no,
            "invoice_date": "2026-10-01", "due_date": "2026-10-31",
            "template_vendor": "Bevarad mall", "amount": amount, "currency": "SEK",
            "paid": paid, "email": "kund@example.test", "source": "manual",
            "source_hash": "original-source", "note": "Bevarad text", "reviewed": 1,
            "logo_file": "supplier.svg",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='2026-10-20',sent_count=1 WHERE invoice_no=?", (invoice_no,))
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    def test_first_import_builds_history_without_marking_unseen_invoice_paid(self):
        existing = self.save_existing()
        plan = plan_ledger_import(self.app.DB_PATH, self.report)
        self.assertEqual((plan.new_count, plan.existing_count, len(plan.missing)), (3, 1, 0))

        result = apply_ledger_import(self.app.DB_PATH, self.report)

        self.assertEqual((result.imported, result.existing, result.marked_paid), (3, 1, 0))
        with self.app.connect() as db:
            preserved = db.execute("SELECT * FROM invoices WHERE id=?", (existing["id"],)).fetchone()
            new_row = db.execute("SELECT * FROM invoices WHERE invoice_no='1002'").fetchone()
            self.assertEqual(preserved["amount"], 1234.0)
            self.assertEqual(preserved["paid"], 100.0)
            self.assertEqual(preserved["p1_date"], "2026-10-20")
            self.assertEqual(preserved["sent_count"], 1)
            self.assertEqual(preserved["template_vendor"], "Bevarad mall")
            self.assertEqual(preserved["ledger_first_seen"], "2026-11-02")
            self.assertEqual(preserved["ledger_last_seen"], "2026-11-02")
            self.assertEqual(new_row["amount"], 2000.0)
            self.assertEqual(new_row["paid"], 1500.0)
            self.assertEqual(new_row["source"], "")
            self.assertEqual(self.app.setting("ledger_last_list_date"), "2026-11-02")

    def test_second_complete_list_marks_only_previously_seen_missing_rows_paid(self):
        apply_ledger_import(self.app.DB_PATH, self.report)
        self.save_existing("MANUAL-1", amount=900.0, paid=0.0)
        remaining = tuple(entry for entry in self.report.entries if entry.invoice_no in {"1001", "1003"})
        second = replace(
            self.report, list_date="2026-11-09", entries=remaining,
            expected_count=2, expected_total=4000.0, actual_total=4000.0,
        )
        plan = plan_ledger_import(self.app.DB_PATH, second)
        self.assertEqual({row.invoice_no for row in plan.missing}, {"1002", "1004"})

        result = apply_ledger_import(self.app.DB_PATH, second)

        self.assertEqual((result.imported, result.existing, result.marked_paid), (0, 2, 2))
        with self.app.connect() as db:
            for invoice_no in ("1002", "1004"):
                row = db.execute("SELECT amount,paid FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()
                self.assertEqual(row["paid"], row["amount"])
            manual = db.execute("SELECT amount,paid FROM invoices WHERE invoice_no='MANUAL-1'").fetchone()
            self.assertEqual((manual["amount"], manual["paid"]), (900.0, 0.0))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 5)

        repeated = apply_ledger_import(self.app.DB_PATH, second)
        self.assertEqual(repeated.marked_paid, 0)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 5)

    def test_unverified_non_sek_report_never_marks_missing_paid(self):
        apply_ledger_import(self.app.DB_PATH, self.report)
        second = replace(
            self.report, list_date="2026-11-09", entries=self.report.entries[:1],
            expected_count=1, expected_total=1000.0, actual_total=1000.0,
            total_verified=False,
        )
        plan = plan_ledger_import(self.app.DB_PATH, second)
        self.assertEqual(plan.missing, ())

    def test_older_report_is_rejected(self):
        apply_ledger_import(self.app.DB_PATH, self.report)
        older = replace(self.report, list_date="2026-11-01")
        with self.assertRaisesRegex(LedgerImportError, "äldre"):
            plan_ledger_import(self.app.DB_PATH, older)

    def test_json_journal_preserves_ledger_history(self):
        apply_ledger_import(self.app.DB_PATH, self.report)
        journal = self.workspace / "ledger-journal.json"
        export_journal(self.app.DB_PATH, journal)
        payload = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(payload["invoices"][0]["ledger_last_seen"], "2026-11-02")

        restored_db = self.workspace / "restored.sqlite3"
        restored_journal = self.workspace / "restored-journal.json"
        self.app.DB_PATH = restored_db
        self.app.init_db()
        import_journal(restored_db, restored_journal, journal)
        with self.app.connect() as db:
            row = db.execute("SELECT ledger_first_seen,ledger_last_seen FROM invoices WHERE invoice_no='1001'").fetchone()
            self.assertEqual(tuple(row), ("2026-11-02", "2026-11-02"))
            self.assertEqual(self.app.setting("ledger_last_list_date"), "2026-11-02")


class LedgerUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "ledger-ui.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_friday_reminder_offers_import_once_and_keeps_schedule(self):
        class Friday:
            @staticmethod
            def today():
                return real_date(2026, 11, 6)

        scheduled = []
        fake = SimpleNamespace(
            _quitting=False, winfo_viewable=lambda: True,
            import_ledger_list=Mock(), after=lambda delay, callback: scheduled.append((delay, callback)),
            _run_scheduled_ledger_reminder="next-ledger-reminder",
        )
        fake._maybe_show_ledger_reminder = lambda: self.app.ReminderApp._maybe_show_ledger_reminder(fake)
        with patch.object(self.app, "date", Friday), patch.object(
            self.app.messagebox, "askyesno", create=True, return_value=True
        ) as question:
            self.app.ReminderApp._run_scheduled_ledger_reminder(fake)
            fake.import_ledger_list.assert_called_once_with()
            self.assertEqual(self.app.setting("ledger_last_friday_prompt"), "2026-11-06")
            self.app.ReminderApp._maybe_show_ledger_reminder(fake)
            self.assertEqual(question.call_count, 1)
        self.assertEqual(scheduled, [(self.app.LEDGER_REMINDER_INTERVAL_MS, "next-ledger-reminder")])

    def test_hidden_window_does_not_consume_friday_reminder(self):
        class Friday:
            @staticmethod
            def today():
                return real_date(2026, 11, 6)

        fake = SimpleNamespace(_quitting=False, winfo_viewable=lambda: False)
        with patch.object(self.app, "date", Friday), patch.object(
            self.app.messagebox, "askyesno", create=True
        ) as question:
            self.assertFalse(self.app.ReminderApp._maybe_show_ledger_reminder(fake))
        question.assert_not_called()
        self.assertEqual(self.app.setting("ledger_last_friday_prompt"), "")

    def test_import_requires_confirmation_and_refreshes_journal(self):
        report = parse_ledger_pages(PAGES)
        plan = LedgerPlan(4, 0, (), "")
        result = LedgerResult(4, 0, 0)
        fake = SimpleNamespace(refresh=Mock())
        with patch.object(self.app.filedialog, "askopenfilename", create=True, return_value="ledger.pdf"), patch.object(
            self.app, "read_ledger_report", return_value=report
        ), patch.object(self.app, "plan_ledger_import", return_value=plan), patch.object(
            self.app, "apply_ledger_import", return_value=result
        ) as apply_import, patch.object(self.app, "refresh_json_journal", return_value=True) as refresh_journal, patch.object(
            self.app.messagebox, "askyesno", create=True, return_value=True
        ), patch.object(self.app.messagebox, "showinfo", create=True):
            returned = self.app.ReminderApp.import_ledger_list(fake)
        self.assertEqual(returned, result)
        apply_import.assert_called_once_with(self.app.DB_PATH, report)
        refresh_journal.assert_called_once_with(parent=fake)
        fake.refresh.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
