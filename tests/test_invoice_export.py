"""CSV export: the file a spreadsheet gets, and the list it mirrors.

The file format is tested on its own, without Tk, by reading the bytes back.
The export command is tested with a real database and a fake window, so both
the "what you see is what you export" rule and the cancelled dialogue are
covered without a display.
"""
import csv
import io
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import invoice_export
from activity_log import ACTIVITY_LOGGER_NAME
from test_database import load_headless_app


def read_rows(path):
    """Read the file the way the app wrote it, BOM and all."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter=";"))


class FileFormatTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_the_header_follows_the_register_and_says_what_each_column_is(self):
        path = self.folder / "empty.csv"
        self.assertEqual(invoice_export.write(path, []), 0)
        rows = read_rows(path)
        self.assertEqual(rows[0], [label for _, label in invoice_export.COLUMNS])
        self.assertEqual(rows[0][:4], ["Fakturanr", "Kund", "Fakturadatum", "Förfallodatum"])
        self.assertEqual(len(rows), 1)

    def test_the_file_opens_in_excel_with_swedish_characters_and_commas(self):
        path = self.folder / "svenskt.csv"
        invoice_export.write(
            path,
            [{
                "invoice_no": "6475", "customer": "Limoeurope Åkersberga AB",
                "invoice_date": "2026-10-01", "due_date": "2026-11-01",
                "amount": 1500.0, "currency": "SEK", "paid": 500.0,
                "balance": 1000.0, "stage": "P2 att skapa", "p1_date": "2026-10-20",
                "p2_date": "", "fee": 150.0, "email_status": "P1 · skickad 2026-10-20",
                "note": "Avser konsult",
            }],
        )
        raw = path.read_bytes()
        # Excel needs the byte-order mark to read Å, Ä and Ö without a question.
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", raw)
        rows = read_rows(path)
        self.assertEqual(rows[1][1], "Limoeurope Åkersberga AB")
        self.assertEqual(rows[1][4], "1500,00")
        self.assertEqual(rows[1][7], "1000,00")
        self.assertEqual(rows[1][11], "150,00")
        # One field holding a semicolon still stays one field.
        self.assertEqual(len(rows[1]), len(invoice_export.COLUMNS))

    def test_a_semicolon_inside_a_name_does_not_become_a_new_column(self):
        path = self.folder / "semikolon.csv"
        invoice_export.write(path, [{"customer": "Kund A; filial B", "invoice_no": "1"}])
        rows = read_rows(path)
        self.assertEqual(rows[1][1], "Kund A; filial B")
        self.assertEqual(len(rows[1]), len(invoice_export.COLUMNS))

    def test_a_name_that_starts_like_a_formula_stays_text(self):
        path = self.folder / "formel.csv"
        invoice_export.write(
            path,
            [
                {"customer": "=SUMMA(A1:A9)", "invoice_no": "1"},
                {"customer": "+46 70 123", "invoice_no": "2"},
                {"customer": "@kund", "invoice_no": "3"},
                {"customer": "-Hemlig kund", "invoice_no": "4"},
            ],
        )
        rows = read_rows(path)
        self.assertEqual([row[1] for row in rows[1:]], ["'=SUMMA(A1:A9)", "'+46 70 123", "'@kund", "'-Hemlig kund"])

    def test_a_negative_amount_keeps_its_minus_without_becoming_text(self):
        path = self.folder / "kredit.csv"
        invoice_export.write(path, [{"invoice_no": "9", "amount": -250.0, "paid": 0, "balance": -250.0}])
        rows = read_rows(path)
        self.assertEqual(rows[1][4], "-250,00")
        self.assertEqual(rows[1][7], "-250,00")

    def test_missing_values_leave_empty_cells_instead_of_words(self):
        path = self.folder / "tomt.csv"
        invoice_export.write(path, [{"invoice_no": "1", "fee": None, "note": ""}])
        rows = read_rows(path)
        self.assertEqual(len(rows[1]), len(invoice_export.COLUMNS))
        self.assertEqual(rows[1][11], "")
        self.assertEqual(rows[1][13], "")

    def test_missing_folders_are_created_and_the_count_is_returned(self):
        path = self.folder / "ny" / "mapp" / "fakturor.csv"
        written = invoice_export.write(path, [{"invoice_no": "1"}, {"invoice_no": "2"}])
        self.assertEqual(written, 2)
        self.assertTrue(path.is_file())

    def test_the_suggested_name_says_what_it_holds_and_when(self):
        self.assertEqual(invoice_export.suggested_name(date(2026, 10, 23)), "fakturor-2026-10-23.csv")
        self.assertTrue(invoice_export.suggested_name().startswith("fakturor-"))


class ExportCommandTests(unittest.TestCase):
    """The menu command exports exactly what the window is showing."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "export.sqlite3"
        self.app.init_db()
        self.addCleanup(self.cleanup)
        self.owner = SimpleNamespace(
            current_filter_key="current",
            invoice_search_var=SimpleNamespace(get=lambda: ""),
            invoice_sort_column="due_date",
            invoice_sort_reverse=False,
        )
        self.owner.export_records = lambda visible: self.app.ReminderApp.export_records(self.owner, visible)

    def cleanup(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()
        self.temporary.cleanup()

    def save(self, invoice_no, *, paid=0.0, customer=None, note=""):
        record = {
            "customer": customer or f"Kund {invoice_no}", "invoice_no": invoice_no,
            "invoice_date": "2026-10-01", "due_date": (date.today() - timedelta(days=10)).isoformat(),
            "template_vendor": "", "amount": 1000.0, "currency": "SEK", "paid": paid,
            "email": "", "source": "manual-entry", "source_hash": f"source-{invoice_no}",
            "note": note, "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        return invoice_no

    def export(self, target):
        chosen = str(Path(target)) if target else ""
        ask = Mock(return_value=chosen)
        filedialog = SimpleNamespace(asksaveasfilename=ask)
        with patch.object(self.app, "filedialog", filedialog), patch.object(
            self.app, "log_activity", create=True
        ) as logged, patch.object(self.app.messagebox, "showinfo", create=True) as showinfo, patch.object(
            self.app.messagebox, "showerror", create=True
        ) as showerror:
            result = self.app.ReminderApp.export_invoices_csv(self.owner)
        return SimpleNamespace(
            result=result, ask=ask, logged=logged, showinfo=showinfo, showerror=showerror,
        )

    def test_only_the_invoices_in_the_open_tab_reach_the_file(self):
        self.save("AKTIV-1", note="Aktiv faktura")
        self.save("BETALD-1", paid=1000.0)
        target = self.workspace / "export" / "lista.csv"
        outcome = self.export(target)

        self.assertEqual(outcome.result, target)
        rows = read_rows(target)
        self.assertEqual([row[0] for row in rows[1:]], ["AKTIV-1"])
        self.assertEqual(rows[1][13], "Aktiv faktura")
        # The dialog suggests the export folder and a dated name.
        self.assertEqual(outcome.ask.call_count, 1)
        suggested = outcome.ask.call_args.kwargs["initialfile"]
        self.assertTrue(suggested.startswith("fakturor-"))
        self.assertTrue(str(outcome.ask.call_args.kwargs["initialdir"]).endswith("export"))
        self.assertIn("1 faktura exporterad", outcome.showinfo.call_args.args[1])
        outcome.logged.assert_called()

    def test_a_search_narrows_the_file_the_same_way_it_narrows_the_list(self):
        self.save("6475", customer="Acme AB")
        self.save("6476", customer="Limoeurope AB")
        self.owner.invoice_search_var = SimpleNamespace(get=lambda: 'kund:"acme ab"')
        target = self.workspace / "sok.csv"
        outcome = self.export(target)

        self.assertEqual(outcome.result, target)
        self.assertEqual([row[0] for row in read_rows(target)[1:]], ["6475"])

    def test_cancelling_the_file_dialogue_writes_nothing_and_says_nothing(self):
        self.save("6475")
        outcome = self.export("")
        self.assertIsNone(outcome.result)
        self.assertEqual(list(self.workspace.glob("*.csv")), [])
        outcome.showinfo.assert_not_called()

    def test_an_empty_list_explains_itself_without_a_file_dialogue(self):
        outcome = self.export(self.workspace / "tomt.csv")
        self.assertIsNone(outcome.result)
        outcome.ask.assert_not_called()
        self.assertIn("ingenting att exportera", outcome.showinfo.call_args.args[1])
        self.assertFalse((self.workspace / "tomt.csv").exists())

    def test_a_file_that_cannot_be_written_is_reported_instead_of_lost(self):
        self.save("6475")
        with patch.object(self.app.invoice_export, "write", side_effect=OSError("disken är full")):
            outcome = self.export(self.workspace / "fel.csv")
        self.assertIsNone(outcome.result)
        self.assertIn("disken är full", outcome.showerror.call_args.args[1])
        outcome.showinfo.assert_not_called()

    def test_the_stage_is_written_in_the_language_the_window_shows(self):
        self.save("AKTIV-1")
        target = self.workspace / "status.csv"
        self.export(target)
        rows = read_rows(target)
        stage = rows[1][8]
        self.assertTrue(stage)
        # An ignored invoice is named as such instead of vanishing silently.
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET ignored=1 WHERE invoice_no='AKTIV-1'")
        self.owner.current_filter_key = "ignored"
        self.export(self.workspace / "ignorerad.csv")
        rows = read_rows(self.workspace / "ignorerad.csv")
        self.assertTrue(rows[1][8].startswith("IGNORERAD"))


if __name__ == "__main__":
    unittest.main()
