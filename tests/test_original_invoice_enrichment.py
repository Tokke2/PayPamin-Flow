import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


HISTORY_FIELDS = (
    "invoice_no", "amount", "currency", "paid", "p1_date", "p2_date", "sent_count",
    "p1_snapshot", "p2_snapshot", "p1_draft_date", "p2_draft_date",
    "p1_sent_date", "p2_sent_date", "ledger_first_seen", "ledger_last_seen", "created",
)


class OriginalInvoiceEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "original-enrichment.sqlite3"
        self.app.init_db()
        self.original = self.workspace / "original.pdf"
        self.original.write_bytes(b"original invoice PDF")

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_ledger_invoice(self):
        values = {
            "customer": "Reskontrakund AB", "invoice_no": "1001",
            "invoice_date": "2026-10-01", "due_date": "2026-10-31",
            "template_vendor": "", "amount": 2000.0, "currency": "SEK", "paid": 500.0,
            "email": "kund@example.test", "source": "", "source_hash": "",
            "note": "B 671", "reviewed": 1, "logo_file": None,
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            db.execute(
                """UPDATE invoices SET ledger_first_seen='2026-11-01',ledger_last_seen='2026-11-02',
                p1_date='2026-11-03',p2_date='2026-11-08',sent_count=2,
                p1_snapshot='p1-history',p2_snapshot='p2-history',
                p1_draft_date='2026-11-03 10:00:00',p2_draft_date='2026-11-08 10:00:00',
                p1_sent_date='2026-11-03 11:00:00',p2_sent_date='2026-11-08 11:00:00'
                WHERE invoice_no='1001'"""
            )
            return db.execute("SELECT * FROM invoices WHERE invoice_no='1001'").fetchone()

    def history(self, row):
        return {field: row[field] for field in HISTORY_FIELDS}

    def candidate(self, invoice_no="1001", candidate_hash="a" * 64):
        section = SimpleNamespace(text=f"Faktura {invoice_no}\nAvser Konsulttjänst", page_indexes=[0])
        values = {
            "invoice_no": invoice_no, "customer": "Kund AB med fullständigt namn",
            "invoice_date": "2026-10-01", "due_date": "2026-11-15",
            "amount": 9999.0, "currency": "EUR", "paid": 0.0,
            "email": "faktura@example.test", "note": "Konsulttjänst september",
        }
        return section, values, candidate_hash

    def owner(self, row, invoice_dialog):
        return SimpleNamespace(
            selected=lambda: row,
            guess_supplier=Mock(return_value="Leverantör AB"),
            apply_saved_zones=Mock(side_effect=lambda path, vendor, values, page_indexes: values),
            preview_invoice=Mock(side_effect=lambda path, values, vendor, page_indexes: values),
            invoice_dialog=invoice_dialog,
        )

    def import_pdf(self, owner, candidates):
        with patch.object(self.app.filedialog, "askopenfilename", create=True, return_value=str(self.original)), patch.object(
            self.app, "read_invoice_candidates", return_value=candidates
        ), patch.object(self.app.messagebox, "showinfo", create=True):
            return self.app.ReminderApp.import_original_invoice(owner)

    def test_original_pdf_enriches_same_ledger_row_and_preserves_all_history(self):
        row = self.save_ledger_invoice()
        before = self.history(row)

        def save_reviewed(title, **kwargs):
            self.assertEqual(title, "Komplettera faktura från original-PDF")
            self.assertTrue(kwargs["enrich_original"])
            merged = self.app.merge_original_invoice_values(kwargs["row"], kwargs["guess"])
            merged.update(
                source=kwargs["source"], source_hash=kwargs["source_hash"], reviewed=1,
            )
            self.assertIsNone(self.app.save_invoice_record(merged, kwargs["row"]["id"]))
            return True

        dialog = Mock(side_effect=save_reviewed)
        owner = self.owner(row, dialog)
        result = self.import_pdf(owner, [self.candidate()])

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], row["id"])
        self.assertEqual(result["source"], str(self.original.resolve()))
        self.assertEqual(result["source_hash"], "a" * 64)
        self.assertEqual(result["customer"], "Kund AB med fullständigt namn")
        self.assertEqual(result["due_date"], "2026-11-15")
        self.assertEqual(result["email"], "faktura@example.test")
        self.assertEqual(result["note"], "Konsulttjänst september")
        self.assertEqual(result["template_vendor"], "Leverantör AB")
        self.assertEqual(self.history(result), before)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)
        self.assertEqual(dialog.call_args.kwargs["source_hash"], "a" * 64)
        owner.preview_invoice.assert_called_once()

        later_entry = SimpleNamespace(
            customer=result["customer"], invoice_no="1001", invoice_date=result["invoice_date"],
            due_date=result["due_date"], amount=2000.0, currency="SEK", balance=1500.0,
            paid=500.0, note="B 671",
        )
        later_report = SimpleNamespace(
            list_date="2026-11-03", entries=(later_entry,), total_verified=True,
        )
        self.app.apply_ledger_import(self.app.DB_PATH, later_report)
        with self.app.connect() as db:
            after_ledger = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(after_ledger["source"], str(self.original.resolve()))
        self.assertEqual(after_ledger["source_hash"], "a" * 64)
        self.assertEqual(after_ledger["note"], "Konsulttjänst september")
        self.assertEqual(after_ledger["paid"], 500.0)
        self.assertEqual(after_ledger["p1_snapshot"], "p1-history")
        self.assertEqual(after_ledger["p2_snapshot"], "p2-history")
        self.assertEqual(after_ledger["ledger_last_seen"], "2026-11-03")

    def test_known_different_invoice_number_is_blocked_before_preview(self):
        row = self.save_ledger_invoice()
        before = self.history(row)
        dialog = Mock(return_value=True)
        owner = self.owner(row, dialog)
        with patch.object(self.app.messagebox, "showerror", create=True) as error:
            result = self.import_pdf(owner, [self.candidate("2002")])
        self.assertIsNone(result)
        owner.preview_invoice.assert_not_called()
        dialog.assert_not_called()
        error.assert_called_once()
        with self.app.connect() as db:
            saved = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(self.history(saved), before)
        self.assertEqual(saved["source"], "")

    def test_unreadable_number_is_verified_again_after_preview(self):
        row = self.save_ledger_invoice()
        dialog = Mock(return_value=True)
        owner = self.owner(row, dialog)
        owner.preview_invoice.side_effect = lambda path, values, vendor, page_indexes: {
            **values, "invoice_no": "9999",
        }
        with patch.object(self.app.messagebox, "showerror", create=True) as error:
            result = self.import_pdf(owner, [self.candidate("")])
        self.assertIsNone(result)
        owner.preview_invoice.assert_called_once()
        dialog.assert_not_called()
        error.assert_called_once()
        with self.app.connect() as db:
            source = db.execute("SELECT source FROM invoices WHERE id=?", (row["id"],)).fetchone()[0]
        self.assertEqual(source, "")

    def test_cancelled_review_does_not_change_ledger_row(self):
        row = self.save_ledger_invoice()
        before = dict(row)
        dialog = Mock(return_value=False)
        owner = self.owner(row, dialog)
        result = self.import_pdf(owner, [self.candidate()])
        self.assertIsNone(result)
        dialog.assert_called_once()
        with self.app.connect() as db:
            saved = dict(db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone())
        self.assertEqual(saved, before)

    def test_empty_pdf_fields_do_not_erase_existing_information(self):
        row = self.save_ledger_invoice()
        merged = self.app.merge_original_invoice_values(row, {
            "invoice_no": "9999", "amount": 1.0, "currency": "EUR", "paid": 0.0,
            "customer": "", "invoice_date": "", "due_date": "", "email": "", "note": "",
            "template_vendor": "", "logo_file": "supplier.svg",
        })
        self.assertEqual(merged["customer"], row["customer"])
        self.assertEqual(merged["note"], row["note"])
        self.assertEqual(merged["due_date"], row["due_date"])
        self.assertEqual(merged["logo_file"], "supplier.svg")
        self.assertEqual(self.history(merged), self.history(row))


if __name__ == "__main__":
    unittest.main()
