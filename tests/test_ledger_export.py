"""Tests for exporting the customer ledger (reskontra) with reminder counts and dates."""
from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fitz

import ledger_export
from i18n import set_language
from test_database import load_headless_app


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter=";"))


class LedgerExportUnitTests(unittest.TestCase):
    def tearDown(self):
        set_language("sv")

    def test_reminder_count_and_latest_reminder_date_handle_zero_one_and_two_reminders(self):
        unreminded = {"sent_count": 0, "p1_date": "", "p2_date": "", "p1_sent_date": "", "p2_sent_date": ""}
        self.assertEqual(ledger_export.reminder_count_for(unreminded), 0)
        self.assertEqual(ledger_export.latest_reminder_date_for(unreminded), "")

        one = {"sent_count": 1, "p1_date": "2026-11-05", "p1_sent_date": "2026-11-06 09:15:00", "p2_date": ""}
        self.assertEqual(ledger_export.reminder_count_for(one), 1)
        self.assertEqual(ledger_export.latest_reminder_date_for(one), "2026-11-06")

        two = {
            "sent_count": 2,
            "p1_date": "2026-11-05",
            "p1_sent_date": "2026-11-05 10:00:00",
            "p2_date": "2026-11-16",
            "p2_sent_date": "",
        }
        self.assertEqual(ledger_export.reminder_count_for(two), 2)
        self.assertEqual(ledger_export.latest_reminder_date_for(two), "2026-11-16")

    def test_suggested_names_reflect_scope_date_and_format(self):
        day = date(2026, 11, 25)
        self.assertEqual(ledger_export.suggested_name(day, "all", ".csv"), "reskontra-2026-11-25.csv")
        self.assertEqual(ledger_export.suggested_name(day, "open", ".pdf"), "reskontra-oppen-2026-11-25.pdf")
        self.assertEqual(ledger_export.suggested_name(day, "reminded", ".csv"), "reskontra-paminnelser-2026-11-25.csv")


class LedgerExportCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "ledger-export.sqlite3"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.init_db()

        def cleanup():
            set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)
        self.owner = SimpleNamespace(
            current_filter_key="current",
            invoice_search_var=SimpleNamespace(get=lambda: ""),
            invoice_sort_column="due_date",
            invoice_sort_reverse=False,
        )
        self.owner.ledger_export_records = lambda scope="all": self.app.ReminderApp.ledger_export_records(self.owner, scope)

        self._seed_invoices()

    def _seed_invoices(self):
        # 1) Unpaid invoice with 2 reminders (P1 + P2)
        self.assertIsNone(self.app.save_invoice_record({
            "customer": "Nordisk Transport AB",
            "invoice_no": "7001",
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-31",
            "template_vendor": "",
            "amount": 2500.0,
            "currency": "SEK",
            "paid": 500.0,
            "email": "ekonomi@nordisk.test",
            "source": "",
            "source_hash": "h-7001",
            "note": "Frakt oktober",
            "reviewed": 1,
        }))
        # 2) Paid invoice with 1 reminder (P1) and payment date
        self.assertIsNone(self.app.save_invoice_record({
            "customer": "Svensk Glas & Metall AB",
            "invoice_no": "7002",
            "invoice_date": "2026-10-05",
            "due_date": "2026-11-04",
            "template_vendor": "",
            "amount": 1800.0,
            "currency": "SEK",
            "paid": 1800.0,
            "email": "",
            "source": "",
            "source_hash": "h-7002",
            "note": "Glasreparation",
            "reviewed": 1,
        }))
        # 3) Unpaid invoice with 0 reminders
        self.assertIsNone(self.app.save_invoice_record({
            "customer": "Kund Utan Påminnelse AB",
            "invoice_no": "7003",
            "invoice_date": "2026-11-10",
            "due_date": "2026-12-10",
            "template_vendor": "",
            "amount": 950.0,
            "currency": "SEK",
            "paid": 0.0,
            "email": "",
            "source": "",
            "source_hash": "h-7003",
            "note": "",
            "reviewed": 1,
        }))
        with self.app.connect() as db:
            db.execute(
                """UPDATE invoices
                   SET p1_date='2026-11-05', p1_sent_date='2026-11-05 11:20:00',
                       p2_date='2026-11-16', p2_sent_date='2026-11-17 08:30:00',
                       sent_count=2, ledger_last_seen='2026-11-25'
                   WHERE invoice_no='7001'"""
            )
            db.execute(
                """UPDATE invoices
                   SET p1_date='2026-11-08', p1_sent_date='2026-11-08 14:00:00',
                       sent_count=1, paid_marked_at='2026-11-20T15:00:00',
                       paid_marked_source='ledger', ledger_last_seen='2026-11-15'
                   WHERE invoice_no='7002'"""
            )

    def test_csv_export_includes_all_ledger_invoices_reminder_counts_and_dates(self):
        target = self.workspace / "export" / "reskontra-hela.csv"
        with (
            patch.object(self.app, "log_activity", create=True),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            result = self.app.ReminderApp.export_ledger(self.owner, scope="all", target_path=target)

        self.assertEqual(result, target)
        rows = read_csv_rows(target)
        headers = rows[0]
        self.assertIn("Antal påminnelser", headers)
        self.assertIn("P1-datum", headers)
        self.assertIn("P2-datum", headers)
        self.assertIn("Senaste påminnelsedatum", headers)
        self.assertIn("Betaldatum", headers)
        self.assertIn("Reskontradatum", headers)

        idx = {name: i for i, name in enumerate(headers)}
        by_no = {row[idx["Fakturanr"]]: row for row in rows[1:]}
        self.assertEqual(set(by_no), {"7001", "7002", "7003"})

        self.assertEqual(by_no["7001"][idx["Antal påminnelser"]], "2")
        self.assertEqual(by_no["7001"][idx["P1-datum"]], "2026-11-05")
        self.assertEqual(by_no["7001"][idx["P2-datum"]], "2026-11-16")
        self.assertEqual(by_no["7001"][idx["Senaste påminnelsedatum"]], "2026-11-17")
        self.assertEqual(by_no["7001"][idx["Betalstatus"]], "Delbetald")
        self.assertEqual(by_no["7001"][idx["Saldo"]], "2000,00")

        self.assertEqual(by_no["7002"][idx["Antal påminnelser"]], "1")
        self.assertEqual(by_no["7002"][idx["Betaldatum"]], "2026-11-20")
        self.assertEqual(by_no["7002"][idx["Betalstatus"]], "Betald")

        self.assertEqual(by_no["7003"][idx["Antal påminnelser"]], "0")
        self.assertEqual(by_no["7003"][idx["Senaste påminnelsedatum"]], "")
        self.assertEqual(by_no["7003"][idx["Betalstatus"]], "Obetald")

        summary_msg = info.call_args.args[1]
        self.assertIn("Påminda fakturor: 2", summary_msg)
        self.assertIn("Totalt antal påminnelser: 3", summary_msg)

    def test_open_and_reminded_scopes_filter_correctly(self):
        open_csv = self.workspace / "open.csv"
        reminded_csv = self.workspace / "reminded.csv"
        with (
            patch.object(self.app, "log_activity", create=True),
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            self.app.ReminderApp.export_ledger(self.owner, scope="open", target_path=open_csv)
            self.app.ReminderApp.export_ledger(self.owner, scope="reminded", target_path=reminded_csv)

        open_nos = [row[0] for row in read_csv_rows(open_csv)[1:]]
        reminded_nos = [row[0] for row in read_csv_rows(reminded_csv)[1:]]
        self.assertEqual(open_nos, ["7001", "7003"])
        self.assertEqual(reminded_nos, ["7001", "7002"])

    def test_pdf_export_writes_readable_landscape_ledger_report_with_reminders_and_dates(self):
        pdf_target = self.workspace / "export" / "reskontra.pdf"
        with (
            patch.object(self.app, "log_activity", create=True),
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            result = self.app.ReminderApp.export_ledger(self.owner, scope="all", target_path=pdf_target)

        self.assertEqual(result, pdf_target)
        self.assertTrue(pdf_target.is_file())
        with fitz.open(pdf_target) as doc:
            text = "\n".join(page.get_text() for page in doc)
        self.assertIn("Kundreskontra", text)
        self.assertIn("Totalt antal påminnelser: 3", text)
        self.assertIn("7001", text)
        self.assertIn("2026-11-16", text)
        self.assertIn("7002", text)
        self.assertIn("2026-11-20", text)

    def test_english_ui_translates_ledger_export_headers_and_statuses(self):
        set_language("en")
        target = self.workspace / "ledger-en.csv"
        ask = Mock(return_value=str(target))
        with (
            patch.object(self.app, "filedialog", SimpleNamespace(asksaveasfilename=ask)),
            patch.object(self.app, "log_activity", create=True),
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            self.app.ReminderApp.export_ledger(self.owner, scope="all")
        rows = read_csv_rows(target)
        self.assertIn("Reminder count", rows[0])
        self.assertIn("Latest reminder date", rows[0])
        self.assertIn("Payment date", rows[0])


if __name__ == "__main__":
    unittest.main()
