import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


class ReminderMessageTests(unittest.TestCase):
    """The optional sender line on a reminder PDF.

    The rule the user asked for: a line that is filled in is printed, and an
    empty line leaves nothing at all behind on the customer's page.
    """

    MESSAGE = "Ring gärna om du vill dela upp betalningen."

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "reminder-message.sqlite3"
        self.app.EXPORT_DIR = self.workspace / "export"
        self.app.SVG_DIR = self.workspace / "svg"
        self.app.EXPORT_DIR.mkdir(exist_ok=True)
        self.app.SVG_DIR.mkdir(exist_ok=True)
        self.app.set_language("sv")
        self.app.init_db()
        self.app.set_setting("fee_model", "statutory")

        def cleanup():
            self.app.set_language("sv")
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save_invoice(self, reminder_message=""):
        values = {
            "customer": "Meddelandekund AB",
            "invoice_no": "MSG-1001",
            "invoice_date": "2026-09-01",
            "due_date": "2026-09-15",
            "template_vendor": "",
            "amount": 1000.0,
            "currency": "SEK",
            "paid": 0,
            "email": "",
            "source": "reminder-message-test",
            "source_hash": "unique-reminder-message-source",
            "note": "",
            "reviewed": 1,
            "logo_file": "",
        }
        self.assertIsNone(self.app.save_invoice_record(values))
        with self.app.connect() as db:
            if reminder_message:
                # The line belongs to the reminder, not to the invoice form, so
                # it is written straight to its own column.
                db.execute(
                    "UPDATE invoices SET reminder_message=? WHERE invoice_no='MSG-1001'",
                    (reminder_message,),
                )
            return db.execute("SELECT * FROM invoices WHERE invoice_no='MSG-1001'").fetchone()

    def pdf_text(self, path):
        import pymupdf

        with pymupdf.open(path) as document:
            return "".join(page.get_text() for page in document)

    def render(self, row, output, level="P1", fee=60.0):
        owner = SimpleNamespace()
        owner.write_pdf = MethodType(self.app.ReminderApp.write_pdf, owner)
        owner.write_letter = MethodType(self.app.ReminderApp.write_letter, owner)
        with patch.object(self.app, "open_path", create=True, return_value=None):
            return owner.write_letter(dict(row), level, fee, output_path=output)

    def test_an_empty_message_leaves_no_line_on_the_pdf(self):
        row = self.save_invoice("")
        pdf = self.workspace / "empty-message.pdf"

        self.assertEqual(self.render(row, pdf), pdf)

        text = self.pdf_text(pdf)
        self.assertIn("Betalningspåminnelse", text)
        self.assertNotIn("dela upp betalningen", text)

    def test_a_filled_in_message_is_printed_on_the_pdf(self):
        row = self.save_invoice(self.MESSAGE)
        pdf = self.workspace / "message.pdf"

        self.render(row, pdf)

        self.assertIn("Ring gärna om du vill dela upp betalningen.", self.pdf_text(pdf))

    def test_a_whitespace_only_message_is_treated_as_empty(self):
        row = self.save_invoice("   \n\t  ")
        pdf = self.workspace / "blank-message.pdf"

        self.render(row, pdf)

        text = self.pdf_text(pdf)
        self.assertNotIn("dela upp", text)
        self.assertEqual(self.app.reminder_message_text("  \n "), "")

    def test_the_message_is_cleaned_and_kept_short(self):
        self.assertEqual(
            self.app.reminder_message_text("  Ring   gärna\nom du vill.  "),
            "Ring gärna om du vill.",
        )
        long_text = "a" * (self.app.REMINDER_MESSAGE_MAX_LENGTH + 40)
        shortened = self.app.reminder_message_text(long_text)
        self.assertEqual(len(shortened), self.app.REMINDER_MESSAGE_MAX_LENGTH)
        self.assertTrue(shortened.endswith("…"))

    def test_make_reminder_stores_the_chosen_line_with_the_reminder(self):
        row = self.save_invoice("")
        calls = []
        self.owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=lambda record, level, fee, logo_path: calls.append(
                (record["id"], level, logo_path, record.get("reminder_message"))
            ),
            refresh=lambda: None,
        )
        for name in ("logo_file_path", "invoice_logo", "reminder_logo_files"):
            setattr(self.owner, name, MethodType(getattr(self.app.ReminderApp, name), self.owner))
        self.owner.choose_reminder_details = lambda record, level: ("", "", "(Ingen logotyp)", self.MESSAGE)

        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.app.ReminderApp.make_reminder(self.owner)

        self.assertEqual(calls, [(row["id"], "P1", "", self.MESSAGE)])
        self.assertIn(self.MESSAGE, confirm.call_args.args[1])
        with self.app.connect() as db:
            saved = db.execute("SELECT reminder_message,p1_snapshot FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["reminder_message"], self.MESSAGE)
        snapshot = self.app.read_p1_snapshot(saved["p1_snapshot"])
        self.assertEqual(snapshot["row"]["reminder_message"], self.MESSAGE)

    def test_cancelling_the_dialogue_stores_no_message(self):
        row = self.save_invoice("")
        self.owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=Mock(),
            refresh=lambda: None,
        )
        self.owner.choose_reminder_details = lambda record, level: None
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True) as confirm:
            self.assertIsNone(self.app.ReminderApp.make_reminder(self.owner))
        confirm.assert_not_called()
        self.owner.write_letter.assert_not_called()
        with self.app.connect() as db:
            saved = db.execute("SELECT reminder_message,p1_date FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(tuple(saved), ("", ""))

    def test_an_empty_choice_removes_a_message_stored_earlier(self):
        row = self.save_invoice(self.MESSAGE)
        calls = []
        self.owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=lambda record, level, fee, logo_path: calls.append(record.get("reminder_message")),
            refresh=lambda: None,
        )
        for name in ("logo_file_path", "invoice_logo", "reminder_logo_files"):
            setattr(self.owner, name, MethodType(getattr(self.app.ReminderApp, name), self.owner))
        # The dialogue opens with the stored line and the user clears it.
        self.assertEqual(self.app.reminder_message_text(row["reminder_message"]), self.MESSAGE)
        self.owner.choose_reminder_details = lambda record, level: ("", "", "(Ingen logotyp)", "")

        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.make_reminder(self.owner)

        self.assertEqual(calls, [""])
        with self.app.connect() as db:
            saved = db.execute("SELECT reminder_message FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["reminder_message"], "")

    def test_editing_the_line_rewrites_the_pdf_and_removes_it_when_cleared(self):
        row = self.save_invoice(self.MESSAGE)
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=? WHERE id=?",
                ("2026-10-01", row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        owner = SimpleNamespace(write_letter=Mock(return_value=self.workspace / "p1.pdf"))
        for name in ("logo_file_path", "invoice_logo"):
            setattr(owner, name, MethodType(getattr(self.app.ReminderApp, name), owner))

        result = self.app.ReminderApp.update_reminder_logo(owner, row, "P1", "", message="Ny rad i påminnelsen.")

        self.assertEqual(result, self.workspace / "p1.pdf")
        updated = owner.write_letter.call_args.args[0]
        self.assertEqual(updated["reminder_message"], "Ny rad i påminnelsen.")
        with self.app.connect() as db:
            saved = db.execute("SELECT reminder_message,p1_snapshot FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.assertEqual(saved["reminder_message"], "Ny rad i påminnelsen.")
        self.assertEqual(self.app.read_p1_snapshot(saved["p1_snapshot"])["row"]["reminder_message"], "Ny rad i påminnelsen.")

    def test_editing_without_a_new_line_keeps_the_one_already_printed(self):
        row = self.save_invoice(self.MESSAGE)
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date=? WHERE id=?", ("2026-10-01", row["id"]))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        owner = SimpleNamespace(write_letter=Mock(return_value=self.workspace / "p1.pdf"))
        for name in ("logo_file_path", "invoice_logo"):
            setattr(owner, name, MethodType(getattr(self.app.ReminderApp, name), owner))

        self.app.ReminderApp.update_reminder_logo(owner, row, "P1", "")

        self.assertEqual(owner.write_letter.call_args.args[0]["reminder_message"], self.MESSAGE)

    def test_recreated_p1_keeps_the_message_of_its_own_snapshot(self):
        row = self.save_invoice("")
        snapshot = self.app.capture_p1_snapshot(dict(row, reminder_message="Raden från P1."), 60.0, "2026-10-01")
        with self.app.connect() as db:
            db.execute(
                "UPDATE invoices SET p1_date=?,p1_snapshot=?,reminder_message=? WHERE id=?",
                ("2026-10-01", snapshot, "En senare rad.", row["id"]),
            )
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
        self.app.reminder_file_path(row, "P1", date(2026, 10, 1)).unlink(missing_ok=True)
        self.owner = SimpleNamespace(
            selected=lambda: row,
            write_letter=Mock(return_value=self.workspace / "recreated.pdf"),
            refresh=Mock(),
        )
        for name in ("logo_file_path", "invoice_logo", "update_reminder_logo", "update_p1_logo", "recreate_p1"):
            setattr(self.owner, name, MethodType(getattr(self.app.ReminderApp, name), self.owner))
        # Stop after the recreation: this test is about the recreated P1 only.
        self.owner.choose_reminder_details = lambda record, level: None
        with (
            patch.object(self.app.messagebox, "askyesno", create=True, return_value=True),
            patch.object(self.app.messagebox, "showinfo", create=True),
        ):
            self.app.ReminderApp.make_reminder(self.owner)

        recreated = self.owner.write_letter.call_args.args[0]
        self.assertEqual(recreated["reminder_message"], "Raden från P1.")

    def test_the_stored_line_is_offered_again_for_the_next_reminder(self):
        row = self.save_invoice(self.MESSAGE)
        self.assertEqual(self.app.reminder_level_message(row, "P1"), self.MESSAGE)
        snapshot = self.app.capture_p1_snapshot(dict(row), 60.0, "2026-10-01")
        row = dict(row)
        row["p1_snapshot"] = snapshot
        self.assertEqual(self.app.reminder_level_message(row, "P1"), self.MESSAGE)


if __name__ == "__main__":
    unittest.main()
