import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from invoice_parser import InvoiceSection
from test_database import load_headless_app


class PaidInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "paid-invoices.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, *, paid=0.0):
        record = {
            "customer": "Betald Kund AB",
            "invoice_no": "F-3001",
            "invoice_date": "2026-10-01",
            "due_date": "2026-11-01",
            "template_vendor": "",
            "amount": 1250.5,
            "currency": "SEK",
            "paid": paid,
            "email": "",
            "source": "manual-entry",
            "source_hash": "different-source-hash",
            "note": "",
            "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no='F-3001'").fetchone()

    def section(self):
        return InvoiceSection((0,), "Fakturanummer F-3001\nATT BETALA 1 250,50 SEK")

    def test_mark_invoice_paid_completes_invoice(self):
        row = self.save_invoice()
        refreshed = []
        fake = SimpleNamespace(selected=lambda: row, refresh=lambda: refreshed.append(True))

        self.app.ReminderApp.mark_invoice_paid(fake)

        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["paid"], saved["amount"])
        self.assertEqual(saved["paid_before_marking"], 0.0)
        self.assertEqual(saved["paid_marked_source"], "manual")
        self.assertTrue(saved["paid_marked_at"])
        self.assertEqual(self.app.next_stage(saved), "Avslutad")
        self.assertEqual(refreshed, [True])

    def test_undo_paid_marking_restores_partial_payment_and_all_history(self):
        row = self.save_invoice(paid=250.25)
        with self.app.connect() as db:
            db.execute(
                """UPDATE invoices SET p1_date='2026-10-20',p2_date='2026-10-25',
                sent_count=2,p1_draft_date='2026-10-20',p1_sent_date='2026-10-21',
                ledger_first_seen='2026-10-01',ledger_last_seen='2026-10-15' WHERE id=?""",
                (row["id"],),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        owner = SimpleNamespace(selected=lambda: row, refresh=Mock(), current_filter_key="history")
        owner.select_invoice_filter = lambda key: setattr(owner, "current_filter_key", key)
        self.app.ReminderApp.mark_invoice_paid(owner)
        with self.app.connect() as db:
            paid_row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        owner.selected = lambda: paid_row

        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            restored = self.app.ReminderApp.undo_invoice_paid(owner)

        self.assertTrue(restored)
        confirm.assert_called_once()
        self.assertEqual(owner.current_filter_key, "current")
        self.assertEqual(owner.refresh.call_count, 2)
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["paid"], 250.25)
        self.assertIsNone(saved["paid_before_marking"])
        self.assertEqual(saved["paid_marked_at"], "")
        self.assertEqual(saved["paid_marked_source"], "")
        self.assertNotEqual(self.app.next_stage(saved), "Avslutad")
        self.assertEqual(
            (saved["p1_date"], saved["p2_date"], saved["sent_count"]),
            ("2026-10-20", "2026-10-25", 2),
        )
        self.assertEqual(
            (saved["p1_draft_date"], saved["p1_sent_date"]),
            ("2026-10-20", "2026-10-21"),
        )
        self.assertEqual(
            (saved["ledger_first_seen"], saved["ledger_last_seen"]),
            ("2026-10-01", "2026-10-15"),
        )

    def test_undo_paid_marking_can_be_declined_without_changes(self):
        row = self.save_invoice(paid=1250.5)
        with self.app.connect() as db:
            db.execute(
                """UPDATE invoices SET paid_before_marking=300,paid_marked_at='2026-11-01T10:00:00',
                paid_marked_source='manual' WHERE id=?""",
                (row["id"],),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        owner = SimpleNamespace(selected=lambda: row, refresh=Mock())

        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=False):
            restored = self.app.ReminderApp.undo_invoice_paid(owner)

        self.assertFalse(restored)
        owner.refresh.assert_not_called()
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["paid"], 1250.5)
        self.assertEqual(saved["paid_before_marking"], 300.0)
        self.assertEqual(saved["paid_marked_source"], "manual")

    def test_undo_legacy_paid_marking_returns_row_with_zero_previous_payment(self):
        row = self.save_invoice(paid=1250.5)
        owner = SimpleNamespace(selected=lambda: row, refresh=Mock(), current_filter_key="history")
        owner.select_invoice_filter = lambda key: setattr(owner, "current_filter_key", key)

        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.assertTrue(self.app.ReminderApp.undo_invoice_paid(owner))

        self.assertIn("Inget tidigare betalbelopp", confirm.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["paid"], 0.0)
        self.assertEqual(owner.current_filter_key, "current")

    def test_paid_invoice_leaves_active_list_but_remains_in_history(self):
        row = self.save_invoice(paid=1250.5)

        class FakeTree:
            def __init__(self):
                self.rows = {}

            def get_children(self):
                return tuple(self.rows)

            def delete(self, item):
                self.rows.pop(item, None)

            def insert(self, _parent, _position, **options):
                self.rows[options["iid"]] = options["values"]

        tree = FakeTree()
        fake = SimpleNamespace(tree=tree, current_filter_key="current", show_detail=Mock())
        self.app.ReminderApp.refresh(fake)
        self.assertEqual(tree.rows, {})

        fake.current_filter_key = "all"
        self.app.ReminderApp.refresh(fake)
        self.assertEqual(tree.rows[str(row["id"])][0], "F-3001")
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)

    def test_automatic_folder_import_skips_paid_invoice_silently(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "still-in-import.pdf"
        pdf.write_bytes(b"new PDF bytes with the already paid invoice number")
        fake = SimpleNamespace(
            _import_scan_running=False,
            refresh=lambda: None,
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake, automatic=True, paths=[pdf])
        info.assert_not_called()
        self.assertFalse(fake._import_scan_running)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM invoices").fetchone()[0], 1)

    def test_manual_scan_reports_paid_skip_separately(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "still-in-import.pdf"
        pdf.write_bytes(b"new PDF bytes with the already paid invoice number")
        fake = SimpleNamespace(
            _import_scan_running=False,
            refresh=lambda: None,
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
        ):
            self.app.ReminderApp.scan_import_folder(fake, paths=[pdf])
        summary = info.call_args.args[1]
        self.assertIn("Betalda som hoppades över: 1", summary)
        self.assertIn("Dubbletter som inte importerades: 0", summary)

    def test_manual_pdf_import_explains_paid_skip(self):
        self.save_invoice(paid=1250.5)
        pdf = self.workspace / "paid.pdf"
        pdf.write_bytes(b"paid invoice PDF")
        fake = SimpleNamespace(
            preview_invoice=lambda *args, **kwargs: self.fail("Paid invoice must not open preview"),
            add_invoice=lambda **kwargs: self.fail("Paid invoice must not open save dialog"),
        )
        with (
            patch.object(self.app.filedialog, "askopenfilename", create=True, return_value=str(pdf)),
            patch.object(self.app, "extract_invoice_sections", return_value=[self.section()]),
            patch.object(self.app.messagebox, "showinfo", create=True) as info,
            patch.object(self.app.messagebox, "showwarning", create=True) as warning,
        ):
            self.app.ReminderApp.import_invoice(fake)
        warning.assert_not_called()
        self.assertEqual(info.call_args.args[0], "Betald faktura")
        self.assertIn("F-3001", info.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
