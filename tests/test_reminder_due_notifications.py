import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from invoice_parser import InvoiceSection
from test_database import load_headless_app


class DueReminderDialogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "due-reminders.sqlite3"
        self.app.init_db()
        self.app.set_language("sv")

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(
        self,
        invoice_no,
        *,
        due_date=None,
        p1_date="",
        p2_date="",
        paid=0,
        reviewed=1,
        ignored=0,
        source_hash="",
    ):
        today = date.today()
        record = {
            "customer": f"Kund {invoice_no}",
            "invoice_no": invoice_no,
            "invoice_date": (today - timedelta(days=30)).isoformat(),
            "due_date": (due_date or today + timedelta(days=30)).isoformat(),
            "template_vendor": "",
            "amount": 1000,
            "currency": "SEK",
            "paid": paid,
            "email": "",
            "source": "manual-entry",
            "source_hash": source_hash,
            "note": "",
            "reviewed": reviewed,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=?,p2_date=?,ignored=? WHERE invoice_no=?",
                (p1_date, p2_date, ignored, invoice_no),
            )
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    def save_due_p1(self, invoice_no="P1-100", **kwargs):
        return self.save_invoice(invoice_no, due_date=date.today() - timedelta(days=5), **kwargs)

    def save_due_p2(self, invoice_no="P2-200", **kwargs):
        return self.save_invoice(
            invoice_no,
            due_date=date.today() - timedelta(days=30),
            p1_date=(date.today() - timedelta(days=5)).isoformat(),
            **kwargs,
        )

    def test_only_invoices_ready_for_p1_or_p2_are_included(self):
        self.save_due_p1()
        self.save_due_p2()
        self.save_invoice("WAITING")
        self.save_due_p1("PAID", paid=1000)
        self.save_due_p1("IGNORED", ignored=1)
        self.save_due_p1("UNREVIEWED", reviewed=0)
        self.save_invoice(
            "P2-WAITING",
            due_date=date.today() - timedelta(days=30),
            p1_date=date.today().isoformat(),
        )

        rows = self.app.due_reminder_invoices()

        self.assertEqual({row["invoice_no"] for row in rows}, {"P1-100", "P2-200"})
        by_number = {row["invoice_no"]: row for row in rows}
        self.assertEqual(self.app.next_stage(by_number["P1-100"]), "P1 att skapa")
        self.assertEqual(self.app.next_stage(by_number["P2-200"]), "P2 att skapa")

    def test_dialog_lists_p1_and_p2_in_swedish_and_english(self):
        self.save_due_p1()
        self.save_due_p2()
        self.save_invoice("WAITING")
        with patch.object(self.app.messagebox, "showinfo", create=True) as info:
            self.assertTrue(self.app.show_due_reminder_dialog(parent="parent"))
            self.assertEqual(info.call_args.args[0], "Dags att skapa P1/P2")
            message = info.call_args.args[1]
            self.assertIn("P1: P1-100 – Kund P1-100", message)
            self.assertIn("P2: P2-200 – Kund P2-200", message)
            self.assertNotIn("WAITING", message)
            self.assertEqual(info.call_args.kwargs["parent"], "parent")

            self.app.set_language("en")
            info.reset_mock()
            self.assertTrue(self.app.show_due_reminder_dialog())
            self.assertEqual(info.call_args.args[0], "Time to create P1/P2")
            self.assertIn("Select an invoice in the list and click Create reminder.", info.call_args.args[1])

    def test_rows_are_ordered_by_how_long_the_reminder_has_waited(self):
        """The invoice that has been forgotten longest is the one that costs most."""
        self.save_invoice("P1-SHORT", due_date=date.today() - timedelta(days=5))
        self.save_invoice("P1-LONG", due_date=date.today() - timedelta(days=40))
        self.save_invoice("P1-MID", due_date=date.today() - timedelta(days=12))

        order = [row["invoice_no"] for _days, row, _level in self.app.due_reminder_rows()]

        self.assertEqual(order, ["P1-LONG", "P1-MID", "P1-SHORT"])

    def test_summary_counts_each_level_and_the_outstanding_total(self):
        self.save_due_p1()
        self.save_due_p2()
        self.save_invoice("PARTLY", due_date=date.today() - timedelta(days=9), paid=250)

        summary = self.app.due_reminder_summary(self.app.due_reminder_rows())

        self.assertEqual((summary["p1"], summary["p2"]), (2, 1))
        self.assertAlmostEqual(summary["total"], 2750.0)
        self.assertFalse(summary["mixed"])

    def test_a_summary_with_mixed_currencies_never_adds_them_up(self):
        """Adding kronor and euro would produce a number that means nothing."""
        self.save_due_p1("P1-SEK")
        self.save_invoice("P1-EUR", due_date=date.today() - timedelta(days=9))
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET currency='EUR' WHERE invoice_no='P1-EUR'")

        summary = self.app.due_reminder_summary(self.app.due_reminder_rows())

        self.assertTrue(summary["mixed"])

    def test_a_reminder_whose_draft_was_opened_is_not_offered_again(self):
        """A level already sent or opened in the mail client is not news."""
        self.save_due_p1("OPENED")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_draft_date=? WHERE invoice_no='OPENED'", (date.today().isoformat(),))

        self.assertEqual(self.app.due_reminder_rows(), [])
        self.assertEqual([row["invoice_no"] for _d, row, _l in self.app.due_reminder_rows(include_opened=True)], ["OPENED"])

    def test_a_sent_reminder_is_not_offered_again(self):
        self.save_due_p2("SENT")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p2_sent_date=? WHERE invoice_no='SENT'", (date.today().isoformat(),))

        self.assertEqual(self.app.due_reminder_rows(), [])

    def test_the_dialog_opens_a_working_list_when_a_window_exist(self):
        """With a window available, the list is shown instead of a message box."""
        self.save_due_p1()
        parent = SimpleNamespace(make_reminder=lambda: None, _new_toplevel=lambda title: None,
                                 show_due_reminder_window=lambda rows: ("window", len(rows)))
        with patch.object(self.app.messagebox, "showinfo", create=True) as info:
            result = self.app.show_due_reminder_dialog(parent=parent)
        self.assertEqual(result, ("window", 1))
        info.assert_not_called()

    def test_no_dialog_is_shown_when_no_reminder_is_due(self):
        self.save_invoice("WAITING")
        with patch.object(self.app.messagebox, "showinfo", create=True) as info:
            self.assertFalse(self.app.show_due_reminder_dialog())
        info.assert_not_called()

    def test_folder_scan_shows_due_dialog_after_scan_summary(self):
        import_dir = self.workspace / "import"
        import_dir.mkdir(exist_ok=True)
        pdf = import_dir / "invoice.pdf"
        pdf.write_bytes(b"synthetic invoice")
        self.app.IMPORT_DIR = import_dir
        source_hash = self.app.file_sha256(pdf)
        row = self.save_due_p1(source_hash=source_hash)
        events = []
        fake = SimpleNamespace(_import_scan_running=False, refresh=lambda: events.append("refresh"))
        candidate = (InvoiceSection((0,), "synthetic"), {"invoice_no": row["invoice_no"]}, source_hash)
        with (
            patch.object(self.app, "read_invoice_candidates", return_value=[candidate]),
            patch.object(
                self.app.messagebox,
                "showinfo",
                create=True,
                side_effect=lambda *args, **kwargs: events.append("summary"),
            ) as summary,
            patch.object(
                self.app,
                "show_due_reminder_dialog",
                side_effect=lambda parent=None: events.append("due"),
            ) as due_dialog,
        ):
            self.app.ReminderApp.scan_import_folder(fake)
        summary.assert_called_once()
        due_dialog.assert_called_once_with(parent=fake)
        self.assertEqual(events, ["refresh", "summary", "due"])
        self.assertFalse(fake._import_scan_running)


if __name__ == "__main__":
    unittest.main()
