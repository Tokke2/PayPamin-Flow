"""Customer classification is an explicit, durable choice, not a name guess."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from customer_contacts import (
    ensure_customer_contact_schema, get_customer_type, save_customer_contact,
)
from reminder_journal import import_journal
from test_database import load_headless_app
from test_settings_layout import FakeVariable, FakeWidget, FakeWindow


class CustomerTypeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "types.sqlite3"
        self.app.JOURNAL_PATH = self.workspace / "journal.json"
        self.app.init_db()
        self.app.set_language("sv")
        self.app.set_setting("learning_enabled", "0")
        self.addCleanup(self.app.set_language, "sv")
        # Windows cannot remove a temporary directory while its log is open.
        # Cleanups run in reverse order: close handlers before removing files.
        self.addCleanup(self.close_log_handlers)

    def close_log_handlers(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()

    def record(self, number="TYPE-1", customer="Alex Svensson", customer_type=None):
        result = dict(customer=customer, invoice_no=number, invoice_date="2026-01-01",
                      due_date="2026-01-30", template_vendor="", amount=1000.0,
                      currency="SEK", paid=0.0, email="", source="", source_hash=number,
                      note="", reviewed=1, logo_file=None)
        if customer_type is not None:
            result["customer_type"] = customer_type
        return result

    def test_selected_type_is_saved_and_reused_on_next_invoice(self):
        self.app.save_invoice_record(self.record(customer_type="business"))
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "  ALEX   Svensson  "), "business")
        self.app.save_invoice_record(self.record("TYPE-2", customer="  alex   svensson  "))
        self.app.init_db()
        with self.app.connect() as db:
            rows = db.execute("SELECT customer_type FROM invoices ORDER BY id").fetchall()
        self.assertEqual([row[0] for row in rows], ["business", "business"])
        self.assertEqual(self.app.infer_imported_customer_type("ALEX SVENSSON"), "business")

    def test_private_override_wins_over_company_name_and_old_invoice_history(self):
        self.app.save_invoice_record(self.record(customer="Example AB", customer_type="business"))
        with self.app.connect() as db:
            save_customer_contact(db, "Example AB", "", customer_type="private")
        self.assertEqual(self.app.infer_imported_customer_type("example ab"), "private")
        self.app.save_invoice_record(self.record("TYPE-2", "Example AB"))
        with self.app.connect() as db:
            rows = db.execute("SELECT customer_type FROM invoices ORDER BY id").fetchall()
        self.assertEqual([row[0] for row in rows], ["business", "private"])

    def test_changing_choice_does_not_reclassify_other_invoices_or_p1_history(self):
        self.app.save_invoice_record(self.record(customer_type="private"))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices").fetchone()
            snapshot = self.app.capture_p1_snapshot(row, 60.0, "2026-01-31")
            db.execute("UPDATE invoices SET p1_date='2026-01-31',p1_snapshot=?,paid=200", (snapshot,))
        self.app.save_invoice_record(self.record("TYPE-2", customer_type="business"))
        with self.app.connect() as db:
            old = db.execute("SELECT * FROM invoices WHERE invoice_no='TYPE-1'").fetchone()
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")
        self.assertEqual(old["customer_type"], "private")
        self.assertEqual(old["p1_snapshot"], snapshot)
        self.assertEqual(old["paid"], 200.0)

    def test_email_logo_and_language_edits_preserve_saved_type(self):
        with self.app.connect() as db:
            save_customer_contact(db, "Alex Svensson", "first@example.com", customer_type="business")
            save_customer_contact(db, "Alex Svensson", "new@example.com", "logo.svg", language="en")
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")
            contact = db.execute("SELECT * FROM customer_contacts").fetchone()
        self.assertEqual(contact["emails"], "new@example.com")
        self.assertEqual(contact["language"], "en")
        self.assertEqual(contact["logo_file"], "logo.svg")

    def test_legacy_contacts_migrate_idempotently_without_guessing_a_type(self):
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE customer_contacts(customer_key TEXT PRIMARY KEY,customer_name TEXT,emails TEXT,updated TEXT)")
            db.execute("INSERT INTO customer_contacts VALUES('example ab','Example AB','old@example.com','old')")
            ensure_customer_contact_schema(db)
            ensure_customer_contact_schema(db)
            self.assertEqual(get_customer_type(db, "Example AB"), "")
            self.assertEqual(db.execute("SELECT emails FROM customer_contacts").fetchone()[0], "old@example.com")

    def test_duplicate_and_cancelled_save_do_not_change_customer_choice(self):
        self.app.save_invoice_record(self.record(customer_type="business"))
        duplicate = self.app.save_invoice_record(self.record(customer_type="private"))
        self.assertIsNotNone(duplicate)
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")

    def test_journal_restores_type_but_does_not_overwrite_a_local_choice(self):
        self.app.save_invoice_record(self.record(customer_type="business"))
        self.assertTrue(self.app.refresh_json_journal())
        payload = json.loads(self.app.JOURNAL_PATH.read_text())
        self.assertEqual(payload["customer_contacts"][0]["customer_type"], "business")
        source = self.app.JOURNAL_PATH
        self.app.DB_PATH = self.workspace / "restored.sqlite3"
        self.app.init_db()
        target = self.workspace / "restored.json"
        import_journal(self.app.DB_PATH, target, source)
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")
            save_customer_contact(db, "Alex Svensson", "local@example.com", customer_type="private")
        import_journal(self.app.DB_PATH, target, source)
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "private")

    def dialog(self, interaction, row=None, guess=None, edit_customer=False):
        """Build and interact with the real invoice dialog using recording widgets."""
        registry = []
        window = FakeWindow("Invoice", registry, 1920)
        form = FakeWidget("Form", registry, window)

        class Widget(FakeWidget):
            def __init__(self, kind, master=None, **options):
                super().__init__(kind, registry, master, **options)
                self.bindings = {}

            def bind(self, sequence, callback, **kwargs):
                self.bindings[sequence] = callback

            def delete(self, *_args):
                self.text = ""

            def grid_remove(self):
                return None

        window.wait_window = lambda: interaction(registry, window)
        owner = SimpleNamespace(_new_toplevel=lambda title: window,
                                _dialog_form=lambda *a, **kw: form, refresh=Mock())
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.app, "window_palette", return_value={"background": "white"}))
            stack.enter_context(patch.object(self.app.tk, "StringVar", FakeVariable, create=True))
            stack.enter_context(patch.object(self.app.tk, "BooleanVar", FakeVariable, create=True))
            stack.enter_context(patch.object(self.app, "refresh_json_journal", return_value=True))
            for kind in ("Entry", "Label", "Frame", "Combobox", "Button", "Checkbutton"):
                factory = lambda master=None, _kind=kind, **opts: Widget(_kind, master, **opts)
                stack.enter_context(patch.object(self.app.ttk, kind, factory, create=True))
            if edit_customer:
                owner.selected=lambda: row
                return self.app.ReminderApp.edit_customer(owner)
            return self.app.ReminderApp.invoice_dialog(owner, "Ny faktura", row=row, guess=guess)

    def test_dialog_reuses_typed_customer_and_preserves_manual_override_until_customer_changes(self):
        with self.app.connect() as db:
            save_customer_contact(db, "Alex Svensson", "", customer_type="business")
            save_customer_contact(db, "Other AB", "", customer_type="private")

        def interact(widgets, window):
            customer = next(w for w in widgets if w.kind == "Entry" and w.grid_calls[0]["row"] == 0)
            combo = next(w for w in widgets if w.kind == "Combobox" and w.grid_calls[0]["row"] == 1)
            self.assertIn("Privatperson", combo.options["values"])
            self.assertIn("Företag", combo.options["values"])
            customer.insert(0, "Alex Svensson")
            customer.bindings["<KeyRelease>"]()
            self.assertEqual(combo.get(), "Företag")
            combo.options["textvariable"].set("Privatperson")
            combo.bindings["<<ComboboxSelected>>"]()
            customer.bindings["<FocusOut>"]()
            self.assertEqual(combo.get(), "Privatperson")
            customer.delete(0, "end")
            customer.insert(0, "Other AB")
            customer.bindings["<FocusOut>"]()
            self.assertEqual(combo.get(), "Privatperson")
            # Cancelling the dialog never changes the stored choice.
            window.destroy()

        self.assertFalse(self.dialog(interact))
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")

    def test_dialog_saves_choice_and_next_dialog_preselects_it(self):
        def save_as_business(widgets, window):
            combo = next(w for w in widgets if w.kind == "Combobox" and w.grid_calls[0]["row"] == 1)
            combo.options["textvariable"].set("Företag")
            next(w for w in widgets if w.kind == "Button" and w.options.get("text") == "Spara").options["command"]()

        self.assertTrue(self.dialog(save_as_business, guess=self.record()))
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, "Alex Svensson"), "business")

        def check_default(widgets, window):
            combo = next(w for w in widgets if w.kind == "Combobox" and w.grid_calls[0]["row"] == 1)
            self.assertEqual(combo.get(), "Företag")
            window.destroy()

        self.assertFalse(self.dialog(check_default, guess=self.record("TYPE-2")))

    def customer_edit_row(self, customer_type="private"):
        self.app.save_invoice_record(self.record(customer_type=customer_type))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no='TYPE-1'").fetchone()

    def test_edit_customer_checkbox_saves_business_and_reuses_on_future_invoice(self):
        row = self.customer_edit_row()

        def choose_business(widgets, window):
            checkbox = next(w for w in widgets if w.kind == "Checkbutton")
            self.assertIn("avmarkerad = privatperson", checkbox.options["text"])
            self.assertFalse(checkbox.options["variable"].get())
            checkbox.options["variable"].set(True)
            next(w for w in widgets if w.kind == "Button" and w.options.get("text") == "Spara").options["command"]()
            self.assertTrue(window.destroyed)

        self.dialog(choose_business, row=row, edit_customer=True)
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, row["customer"]), "business")
            self.assertEqual(db.execute("SELECT customer_type FROM invoices WHERE id=?", (row["id"],)).fetchone()[0], "business")
        self.app.save_invoice_record(self.record("TYPE-2"))
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT customer_type FROM invoices WHERE invoice_no='TYPE-2'").fetchone()[0], "business")

        def reopen(widgets, window):
            self.assertTrue(next(w for w in widgets if w.kind == "Checkbutton").options["variable"].get())
            window.destroy()

        self.dialog(reopen, row=row, edit_customer=True)

    def test_edit_customer_unchecked_saves_private_and_keeps_other_invoice_history(self):
        row = self.customer_edit_row("business")
        self.app.save_invoice_record(self.record("TYPE-2", customer_type="business"))
        snapshot = self.app.capture_p1_snapshot(row, 450.0, "2026-02-01")
        with self.app.connect() as db:
            db.execute("UPDATE invoices SET p1_date='2026-02-01',p1_snapshot=?,paid=100 WHERE id=?", (snapshot, row["id"]))
            row = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()

        def choose_private(widgets, window):
            checkbox = next(w for w in widgets if w.kind == "Checkbutton")
            self.assertTrue(checkbox.options["variable"].get())
            checkbox.options["variable"].set(False)
            next(w for w in widgets if w.kind == "Button" and w.options.get("text") == "Spara").options["command"]()

        self.dialog(choose_private, row=row, edit_customer=True)
        with self.app.connect() as db:
            edited = db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone()
            self.assertEqual(edited["customer_type"], "private")
            self.assertEqual(edited["p1_snapshot"], snapshot)
            self.assertEqual(edited["paid"], 100.0)
            self.assertEqual(get_customer_type(db, row["customer"]), "private")
            self.assertEqual(db.execute("SELECT customer_type FROM invoices WHERE invoice_no='TYPE-2'").fetchone()[0], "business")
        self.assertEqual(self.app.infer_imported_customer_type(row["customer"]), "private")

    def test_edit_customer_checkbox_falls_back_to_invoice_type_for_legacy_contact(self):
        row = self.customer_edit_row("business")
        with self.app.connect() as db:
            db.execute("UPDATE customer_contacts SET customer_type=''")

        def inspect(widgets, window):
            self.assertTrue(next(w for w in widgets if w.kind == "Checkbutton").options["variable"].get())
            window.destroy()

        self.dialog(inspect, row=row, edit_customer=True)

    def test_cancel_customer_checkbox_change_does_not_save(self):
        row = self.customer_edit_row("business")

        def cancel(widgets, window):
            next(w for w in widgets if w.kind == "Checkbutton").options["variable"].set(False)
            next(w for w in widgets if w.kind == "Button" and w.options.get("text") == "Stäng").options["command"]()

        self.dialog(cancel, row=row, edit_customer=True)
        with self.app.connect() as db:
            self.assertEqual(get_customer_type(db, row["customer"]), "business")
            self.assertEqual(db.execute("SELECT customer_type FROM invoices WHERE id=?", (row["id"],)).fetchone()[0], "business")

    def test_customer_checkbox_preserves_authority_on_unchanged_save(self):
        row = self.customer_edit_row("authority")

        def save_without_changing_type(widgets, window):
            self.assertTrue(next(w for w in widgets if w.kind == "Checkbutton").options["variable"].get())
            next(w for w in widgets if w.kind == "Entry" and w.grid_calls[0]["row"] == 1).insert(0, "changed@example.com")
            next(w for w in widgets if w.kind == "Combobox").options["textvariable"].set("Engelska (English)")
            next(w for w in widgets if w.kind == "Button" and w.options.get("text") == "Spara").options["command"]()

        self.dialog(save_without_changing_type, row=row, edit_customer=True)
        with self.app.connect() as db:
            contact = self.app.get_customer_contact(db, row["customer"])
            self.assertEqual(contact["customer_type"], "authority")
            self.assertEqual(contact["emails"], "changed@example.com")
            self.assertEqual(contact["language"], "en")
