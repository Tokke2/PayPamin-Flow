import json
import tempfile
import unittest
from datetime import date as real_date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from activity_log import ACTIVITY_LOGGER_NAME
from test_database import load_headless_app


class FakeTree:
    def __init__(self):
        self.rows = {}

    def get_children(self):
        return tuple(self.rows)

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, _parent, _position, **options):
        self.rows[options["iid"]] = options["values"]


class FakeNotebook:
    def __init__(self, selected=""):
        self.selected = str(selected)

    def select(self, tab=None):
        if tab is None:
            return self.selected
        self.selected = str(tab)
        return self.selected


class InvoiceViewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "invoice-views.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, invoice_no, *, paid=0.0, ignored=0, amount=1000.0):
        record = {
            "customer": f"Kund {invoice_no}",
            "invoice_no": invoice_no,
            "invoice_date": "2026-10-01",
            "due_date": "2026-11-01",
            "template_vendor": "",
            "amount": amount,
            "currency": "SEK",
            "paid": paid,
            "email": "",
            "source": "manual-entry",
            "source_hash": f"source-{invoice_no}",
            "note": "Bevarad fakturatext",
            "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET ignored=?,p1_date=?,p2_date=?,sent_count=? WHERE invoice_no=?",
                (ignored, "2026-11-06", "2026-11-11", 2, invoice_no),
            )
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    def render(self, filter_key, *, query="", sort_column="due_date", reverse=False):
        tree = FakeTree()
        fake = SimpleNamespace(
            tree=tree, current_filter_key=filter_key, show_detail=Mock(),
            invoice_search_var=SimpleNamespace(get=lambda: query),
            invoice_sort_column=sort_column, invoice_sort_reverse=reverse,
        )
        self.app.ReminderApp.refresh(fake)
        return {values[0]: values for values in tree.rows.values()}

    def test_history_view_contains_paid_and_archived_without_active_rows(self):
        active = self.save_invoice("ACTIVE-1")
        paid = self.save_invoice("PAID-1", paid=1000.0)
        archived = self.save_invoice("ARCHIVED-1", ignored=1)

        self.assertEqual(set(self.render("current")), {"ACTIVE-1"})
        history = self.render("history")
        self.assertEqual(set(history), {"PAID-1", "ARCHIVED-1"})
        self.assertEqual(set(self.render("all")), {"ACTIVE-1", "PAID-1", "ARCHIVED-1"})
        self.assertEqual(set(self.render("ignored")), {"ARCHIVED-1"})

        # The history tab renders the same stored P1/P2 history; it is not a new archive.
        self.assertEqual(history["PAID-1"][5], "2026-11-06")
        self.assertIn("Avslutad", history["PAID-1"][8])
        self.assertIn("IGNORERAD", history["ARCHIVED-1"][8])
        with self.app.connect() as db:
            rows = db.execute("SELECT * FROM invoices ORDER BY invoice_no").fetchall()
            self.assertEqual(len(rows), 3)
            for row in rows:
                self.assertEqual((row["p1_date"], row["p2_date"], row["sent_count"]), ("2026-11-06", "2026-11-11", 2))
            self.assertEqual(db.execute("SELECT paid FROM invoices WHERE id=?", (paid["id"],)).fetchone()[0], 1000.0)
            self.assertEqual(db.execute("SELECT paid FROM invoices WHERE id=?", (active["id"],)).fetchone()[0], 0.0)
            self.assertEqual(db.execute("SELECT ignored FROM invoices WHERE id=?", (archived["id"],)).fetchone()[0], 1)

    def test_history_search_matches_customer_or_invoice_without_editing_rows(self):
        self.save_invoice("PAID-SEARCH", paid=1000.0)
        self.save_invoice("OTHER-PAID", paid=1000.0)

        by_customer = self.render("history", query="  kund   paid-search ")
        by_invoice = self.render("history", query="other-paid")
        no_match = self.render("history", query="saknas")

        self.assertEqual(set(by_customer), {"PAID-SEARCH"})
        self.assertEqual(set(by_invoice), {"OTHER-PAID"})
        self.assertEqual(no_match, {})
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT SUM(paid) FROM invoices").fetchone()[0], 2000.0)

    def test_sort_is_numeric_for_invoice_numbers_and_reversible_for_amounts(self):
        self.save_invoice("10", paid=1000.0, amount=1000.0)
        self.save_invoice("2", paid=300.0, amount=300.0)
        self.save_invoice("1", paid=500.0, amount=500.0)

        by_number = self.render("history", sort_column="invoice_no")
        by_amount = self.render("history", sort_column="amount")
        by_amount_desc = self.render("history", sort_column="amount", reverse=True)

        self.assertEqual(list(by_number), ["1", "2", "10"])
        self.assertEqual(list(by_amount), ["2", "1", "10"])
        self.assertEqual(list(by_amount_desc), ["10", "1", "2"])

    def test_sort_heading_action_toggles_direction_and_refreshes(self):
        fake = SimpleNamespace(
            invoice_sort_column="amount", invoice_sort_reverse=False, refresh=Mock(),
        )
        self.app.ReminderApp.sort_invoice_column(fake, "amount")
        self.assertEqual((fake.invoice_sort_column, fake.invoice_sort_reverse), ("amount", True))
        self.app.ReminderApp.sort_invoice_column(fake, "customer")
        self.assertEqual((fake.invoice_sort_column, fake.invoice_sort_reverse), ("customer", False))
        self.assertEqual(fake.refresh.call_count, 2)

    def test_open_original_and_latest_archived_reminder_pdf(self):
        row = self.save_invoice("PDF-HISTORY", paid=1000.0)
        original = self.workspace / "original-invoice.pdf"
        original.write_bytes(b"original invoice")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET source=? WHERE id=?", (str(original), row["id"]))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        p1 = self.app.reminder_file_path(row, "P1", real_date(2026, 11, 6))
        p1.write_bytes(b"P1")
        p2 = self.app.reminder_file_path(row, "P2", real_date(2026, 11, 11))
        archived_p2 = p2.parent / self.app.ARCHIVE_FOLDER_NAME / p2.name
        archived_p2.parent.mkdir(parents=True, exist_ok=True)
        archived_p2.write_bytes(b"archived P2")
        fake = SimpleNamespace(selected=lambda: row)

        with patch.object(self.app, "open_path") as open_pdf:
            self.assertEqual(self.app.ReminderApp.open_selected_invoice_pdf(fake), original)
            self.assertEqual(self.app.ReminderApp.open_selected_reminder_pdf(fake), archived_p2)

        self.assertEqual(open_pdf.call_args_list, [call(original), call(archived_p2)])

    def test_select_invoice_filter_selects_real_tab_and_defaults_safely(self):
        tabs = FakeNotebook("tab-history")
        fake = SimpleNamespace(
            filter_options={"current": "Aktuella", "history": "Historik / arkiverade / betalda"},
            filter_tabs={"current": "tab-current", "history": "tab-history"},
            view_tabs=tabs,
            current_filter_key="history",
        )

        self.app.ReminderApp.select_invoice_filter(fake, "current")
        self.assertEqual(fake.current_filter_key, "current")
        self.assertEqual(tabs.select(), "tab-current")

        self.app.ReminderApp.select_invoice_filter(fake, "unknown")
        self.assertEqual(fake.current_filter_key, "current")
        self.assertEqual(tabs.select(), "tab-current")

    def test_tab_change_refreshes_and_logs_without_editing_invoice_data(self):
        row = self.save_invoice("PAID-LOG", paid=1000.0)
        tabs = FakeNotebook("tab-history")
        fake = SimpleNamespace(
            view_tabs=tabs,
            filter_tab_ids={"tab-current": "current", "tab-history": "history"},
            current_filter_key="current",
            refresh=Mock(),
        )
        with self.assertLogs(ACTIVITY_LOGGER_NAME, level="INFO") as captured:
            self.app.ReminderApp.on_filter_select(fake)

        self.assertEqual(fake.current_filter_key, "history")
        fake.refresh.assert_called_once_with()
        activities = [
            json.loads(record.getMessage().split("Activity: ", 1)[1])
            for record in captured.records if record.getMessage().startswith("Activity: ")
        ]
        self.assertEqual(activities[-1]["action"], "invoice_filter_changed")
        self.assertEqual(activities[-1]["details"]["filter"], "history")

        self.app.ReminderApp.on_filter_select(fake)
        fake.refresh.assert_called_once_with()
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
            self.assertEqual((saved["paid"], saved["p1_date"], saved["p2_date"]), (1000.0, "2026-11-06", "2026-11-11"))


if __name__ == "__main__":
    unittest.main()
