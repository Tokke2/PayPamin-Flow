import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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

    def render(self, filter_key):
        tree = FakeTree()
        fake = SimpleNamespace(tree=tree, current_filter_key=filter_key, show_detail=Mock())
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
        with self.assertLogs(self.app.logger, level="INFO") as captured:
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
