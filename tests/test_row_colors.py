import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from test_database import load_headless_app


class InvoiceRowColorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "row-colors.sqlite3"
        self.app.init_db()
        self.today = date.today()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def row(self, **changes):
        values = {
            "ignored": 0,
            "reviewed": 1,
            "amount": 1000.0,
            "paid": 0.0,
            "due_date": (self.today + timedelta(days=10)).isoformat(),
            "p1_date": "",
            "p2_date": "",
        }
        values.update(changes)
        return values

    def color(self, row, stage):
        return self.app.invoice_row_color_tag(row, stage=stage, today=self.today)

    def test_not_due_rows_are_green_including_the_due_date(self):
        for due_date in (self.today, self.today + timedelta(days=10)):
            row = self.row(due_date=due_date.isoformat())
            self.assertEqual(self.color(row, "Väntar P1"), "status-not-due")

    def test_overdue_row_waiting_for_p1_has_no_status_color(self):
        row = self.row(due_date=(self.today - timedelta(days=1)).isoformat())
        self.assertEqual(self.color(row, "Väntar P1"), "")

    def test_p1_ready_or_created_is_yellow(self):
        ready = self.row(due_date=(self.today - timedelta(days=10)).isoformat())
        self.assertEqual(self.color(ready, "P1 att skapa"), "status-p1")
        created = self.row(p1_date=self.today.isoformat())
        self.assertEqual(self.color(created, "Väntar P2"), "status-p1")

    def test_p2_ready_or_created_is_red_and_takes_precedence(self):
        ready = self.row(p1_date=(self.today - timedelta(days=10)).isoformat())
        self.assertEqual(self.color(ready, "P2 att skapa"), "status-p2")
        created = self.row(
            p1_date=(self.today - timedelta(days=10)).isoformat(),
            p2_date=self.today.isoformat(),
        )
        self.assertEqual(self.color(created, "Väntar – efter P2"), "status-p2")
        self.assertEqual(self.color(created, "Kronofogden – granska"), "status-p2")

    def test_paid_ignored_unreviewed_and_invalid_dates_are_neutral(self):
        for changes in (
            {"paid": 1000.0},
            {"ignored": 1},
            {"reviewed": 0},
            {"due_date": "not-a-date"},
        ):
            row = self.row(**changes)
            self.assertEqual(self.color(row, "P1 att skapa"), "")

    def test_tree_configuration_defines_all_three_readable_backgrounds(self):
        class FakeTree:
            def __init__(self):
                self.tags = {}

            def tag_configure(self, tag, **options):
                self.tags[tag] = options

        tree = FakeTree()
        self.app.configure_invoice_row_colors(tree)
        self.assertEqual(tree.tags, {
            tag: {"background": background, "foreground": "#1F2A3D"}
            for tag, background in self.app.INVOICE_ROW_COLORS.items()
        })
        self.assertEqual(set(tree.tags), {"status-not-due", "status-p1", "status-p2"})

        self.app.configure_invoice_row_colors(tree, high_contrast=True)
        self.assertEqual(tree.tags, {
            tag: {"background": "#000000", "foreground": "#FFFFFF"}
            for tag in self.app.INVOICE_ROW_COLORS
        })

    def save_invoice(self, invoice_no, due_date):
        values = {
            "customer": "Färgtest AB",
            "invoice_no": invoice_no,
            "invoice_date": self.today.isoformat(),
            "due_date": due_date.isoformat(),
            "template_vendor": "",
            "amount": 1000.0,
            "currency": "SEK",
            "paid": 0.0,
            "email": "",
            "source": "manual",
            "source_hash": "source-" + invoice_no,
            "note": "",
            "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(values))

    def test_refresh_assigns_status_tags_to_inserted_rows(self):
        self.save_invoice("GREEN", self.today + timedelta(days=10))
        self.save_invoice("YELLOW", self.today - timedelta(days=10))
        self.save_invoice("RED", self.today - timedelta(days=20))
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=?,p2_date=? WHERE invoice_no='RED'",
                (
                    (self.today - timedelta(days=10)).isoformat(),
                    self.today.isoformat(),
                ),
            )

        class FakeTree:
            def __init__(self):
                self.rows = {}

            def get_children(self):
                return ()

            def delete(self, item):
                pass

            def insert(self, _parent, _position, **options):
                self.rows[options["values"][0]] = options["tags"]

        tree = FakeTree()
        fake = SimpleNamespace(
            tree=tree,
            current_filter_key="all",
            show_detail=Mock(),
        )
        self.app.ReminderApp.refresh(fake)

        self.assertEqual(tree.rows, {
            "YELLOW": ("status-p1",),
            "RED": ("status-p2",),
            "GREEN": ("status-not-due",),
        })
        fake.show_detail.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
