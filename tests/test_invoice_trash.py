"""The trash can behind every invoice delete.

The rules are tested against a real SQLite database through the module's own
functions, and the delete/undo/trash dialogue is exercised with recording
widgets, so neither test needs a display.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import invoice_trash
from test_database import load_headless_app


def make_database():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE invoices (
            id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
            due_date TEXT NOT NULL DEFAULT '', amount REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'SEK', paid REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT '', reminder_message TEXT NOT NULL DEFAULT '',
            p1_snapshot TEXT DEFAULT '', ignored INTEGER NOT NULL DEFAULT 0)"""
    )
    return db


def add_invoice(db, invoice_no, customer="Kund AB", amount=1000.0, **extra):
    values = {"customer": customer, "invoice_no": invoice_no, "amount": amount, **extra}
    names = ",".join(values)
    db.execute(
        f"INSERT INTO invoices({names}) VALUES({','.join('?' for _ in values)})",
        list(values.values()),
    )
    return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()


def close_log_handlers(app):
    """Release the log files so a temporary folder can be removed on Windows."""
    for handler in app.logger.handlers[:]:
        app.logger.removeHandler(handler)
        handler.close()


class TrashRulesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_database()
        self.addCleanup(self.db.close)

    def test_a_delete_moves_the_whole_row_instead_of_destroying_it(self):
        row = add_invoice(
            self.db, "6475", note="Avser konsult", reminder_message="Ring gärna.",
            p1_snapshot='{"terms": {"payment_deadline_days": 5}}',
        )
        trash_id = invoice_trash.delete_invoice_to_trash(self.db, row["id"], "2026-10-23 09:00:00")

        self.assertIsNotNone(trash_id)
        self.assertIsNone(self.db.execute("SELECT * FROM invoices WHERE id=?", (row["id"],)).fetchone())
        item = invoice_trash.trash_item(self.db, trash_id)
        self.assertEqual(item["invoice_no"], "6475")
        self.assertEqual(item["deleted_at"], "2026-10-23 09:00:00")
        # Every column travels, including the P1 snapshot and the message line.
        self.assertEqual(item["row"]["note"], "Avser konsult")
        self.assertEqual(item["row"]["reminder_message"], "Ring gärna.")
        self.assertEqual(json.loads(item["row"]["p1_snapshot"])["terms"]["payment_deadline_days"], 5)

    def test_a_trashed_invoice_never_shows_up_in_the_invoice_table(self):
        row = add_invoice(self.db, "1")
        invoice_trash.delete_invoice_to_trash(self.db, row["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 0)
        self.assertEqual(invoice_trash.trash_count(self.db), 1)

    def test_restoring_puts_the_row_back_exactly(self):
        row = add_invoice(self.db, "6475", customer="Limoeurope AB", amount=1500.0, paid=500.0, note="Text")
        trash_id = invoice_trash.delete_invoice_to_trash(self.db, row["id"])
        result = invoice_trash.restore(self.db, trash_id)

        self.assertTrue(result["restored"])
        self.assertFalse(result.get("renumbered"))
        self.assertEqual(result["invoice_no"], "6475")
        restored = self.db.execute("SELECT * FROM invoices WHERE invoice_no='6475'").fetchone()
        for column in ("id", "customer", "amount", "paid", "note", "currency"):
            self.assertEqual(restored[column], row[column], column)
        self.assertEqual(invoice_trash.trash_count(self.db), 0)

    def test_restoring_into_a_taken_id_gives_a_new_id_and_says_so(self):
        row = add_invoice(self.db, "1")
        trash_id = invoice_trash.delete_invoice_to_trash(self.db, row["id"])
        # A new invoice takes the id the trashed row used to have.
        self.db.execute(
            "INSERT INTO invoices(id,customer,invoice_no) VALUES(?,?,?)", (row["id"], "Annan", "2")
        )
        result = invoice_trash.restore(self.db, trash_id)

        self.assertTrue(result["restored"])
        self.assertTrue(result["renumbered"])
        self.assertEqual(result["original_id"], row["id"])
        self.assertNotEqual(result["id"], row["id"])
        numbers = {entry[0] for entry in self.db.execute("SELECT invoice_no FROM invoices")}
        self.assertEqual(numbers, {"1", "2"})

    def test_a_row_deleted_before_a_new_column_still_restores(self):
        """The stored JSON is matched against the columns the table has now."""
        row = add_invoice(self.db, "9")
        trash_id = invoice_trash.delete_invoice_to_trash(self.db, row["id"])
        self.db.execute("ALTER TABLE invoices ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'private'")
        result = invoice_trash.restore(self.db, trash_id)

        self.assertTrue(result["restored"])
        restored = self.db.execute("SELECT * FROM invoices WHERE invoice_no='9'").fetchone()
        self.assertEqual(restored["customer_type"], "private")

    def test_restoring_something_that_is_gone_reports_it(self):
        self.assertEqual(
            invoice_trash.restore(self.db, 999)["reason"], "missing"
        )
        self.assertFalse(invoice_trash.restore(self.db, 999)["restored"])

    def test_only_an_explicit_request_deletes_for_good(self):
        first = add_invoice(self.db, "1")
        second = add_invoice(self.db, "2")
        first_id = invoice_trash.delete_invoice_to_trash(self.db, first["id"])
        invoice_trash.delete_invoice_to_trash(self.db, second["id"])

        self.assertEqual(invoice_trash.purge(self.db, [first_id]), 1)
        self.assertEqual(invoice_trash.trash_count(self.db), 1)
        self.assertEqual(invoice_trash.purge(self.db, []), 0)
        self.assertEqual(invoice_trash.empty_trash(self.db), 1)
        self.assertEqual(invoice_trash.trash_count(self.db), 0)

    def test_nothing_disappears_on_a_timer(self):
        """An old delete is still restorable; there is no silent deadline."""
        row = add_invoice(self.db, "1")
        trash_id = invoice_trash.delete_invoice_to_trash(self.db, row["id"], "2001-01-01 00:00:00")
        self.assertEqual(invoice_trash.trash_count(self.db), 1)
        self.assertTrue(invoice_trash.restore(self.db, trash_id)["restored"])

    def test_the_list_is_newest_first_and_says_how_much_it_holds(self):
        for number in ("1", "2", "3"):
            row = add_invoice(self.db, number)
            invoice_trash.delete_invoice_to_trash(self.db, row["id"], f"2026-10-2{number} 10:00:00")
        items = invoice_trash.trash_items(self.db)
        self.assertEqual([item["invoice_no"] for item in items], ["3", "2", "1"])
        self.assertEqual(invoice_trash.trash_summary(items), "3 fakturor i papperskorgen")
        self.assertEqual(invoice_trash.trash_summary(items[:1]), "1 faktura i papperskorgen")
        self.assertEqual(invoice_trash.trash_summary([]), "Papperskorgen är tom")

    def test_a_missing_invoice_is_reported_instead_of_creating_an_empty_trash_row(self):
        self.assertIsNone(invoice_trash.delete_invoice_to_trash(self.db, 12345))
        self.assertEqual(invoice_trash.trash_count(self.db), 0)


class TrashAppTests(unittest.TestCase):
    """The delete and undo actions in the app, without a display."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "trash.sqlite3"
        self.app.init_db()

        def cleanup():
            close_log_handlers(self.app)
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def save(self, invoice_no="6475", customer="Limoeurope AB"):
        record = {
            "customer": customer, "invoice_no": invoice_no, "invoice_date": "2026-10-01",
            "due_date": "2026-11-01", "template_vendor": "", "amount": 1500.0,
            "currency": "SEK", "paid": 0.0, "email": "", "source": "manual-entry",
            "source_hash": f"hash-{invoice_no}", "note": "", "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            return db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()

    class Bar:
        def __init__(self):
            self.packed = []

        def pack(self, **options):
            self.packed.append(options)

        def pack_forget(self):
            self.packed.append("forgotten")

    class Label:
        def __init__(self):
            self.text = ""

        def configure(self, **options):
            self.text = options.get("text", self.text)

    def owner(self, row):
        owner = SimpleNamespace(
            selected=lambda: row,
            _focus_is_text_input=lambda: False,
            refresh=Mock(),
            _last_deleted=None,
            undo_bar=self.Bar(),
            undo_label=self.Label(),
            _footer="footer-widget",
            after=Mock(return_value="job-1"),
            after_cancel=Mock(),
        )
        owner._hide_undo_delete = lambda: self.app.ReminderApp._hide_undo_delete(owner)
        owner._offer_undo_delete = lambda: self.app.ReminderApp._offer_undo_delete(owner)
        return owner

    def test_deleting_moves_the_row_and_offers_one_visible_undo(self):
        row = self.save()
        owner = self.owner(row)
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ):
            trash_id = self.app.ReminderApp.delete_invoice(owner)

        self.assertIsNotNone(trash_id)
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM invoices WHERE id=?", (row["id"],)).fetchone())
            self.assertEqual(invoice_trash.trash_count(db), 1)
        self.assertEqual(owner._last_deleted["invoice_no"], "6475")
        self.assertEqual(owner.undo_label.text, "Faktura 6475 ligger i papperskorgen.")
        self.assertIn("footer-widget", [options.get("before") for options in owner.undo_bar.packed])
        owner.after.assert_called_once()
        self.assertEqual(owner.after.call_args.args[0], 60000)

    def test_a_refused_delete_keeps_the_invoice(self):
        row = self.save()
        owner = self.owner(row)
        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True):
            self.assertIsNone(self.app.ReminderApp.delete_invoice(owner))
        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 0)
            self.assertIsNotNone(db.execute("SELECT 1 FROM invoices WHERE id=?", (row["id"],)).fetchone())

    def test_undo_restores_the_last_deleted_invoice(self):
        row = self.save()
        owner = self.owner(row)
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ), patch.object(self.app.messagebox, "showinfo", create=True) as showinfo:
            self.app.ReminderApp.delete_invoice(owner)
            self.assertTrue(self.app.ReminderApp.undo_last_delete(owner))

        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 0)
            restored = db.execute("SELECT * FROM invoices WHERE invoice_no='6475'").fetchone()
        self.assertEqual(restored["amount"], 1500.0)
        self.assertIn("tillbaka i listan", showinfo.call_args.args[1])
        self.assertIsNone(owner._last_deleted)

    def test_ctrl_z_inside_a_text_field_stays_in_the_text(self):
        """Typing in search must not restore an invoice instead of undoing text."""
        row = self.save()
        owner = self.owner(row)
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ), patch.object(self.app.messagebox, "showinfo", create=True) as showinfo:
            self.app.ReminderApp.delete_invoice(owner)
            owner._focus_is_text_input = lambda: True
            self.assertFalse(self.app.ReminderApp.undo_last_delete(owner))
        showinfo.assert_not_called()
        with self.app.connect() as db:
            # Still in the trash, ready to be restored from the trash view.
            self.assertEqual(invoice_trash.trash_count(db), 1)

    def test_undo_without_a_delete_explains_itself_instead_of_guessing(self):
        owner = self.owner(None)
        with patch.object(self.app.messagebox, "showinfo", create=True) as showinfo:
            self.assertFalse(self.app.ReminderApp.undo_last_delete(owner))
        self.assertIn("Ingen faktura", showinfo.call_args.args[1])

    def test_the_undo_offer_expires_but_the_trash_keeps_the_invoice(self):
        row = self.save()
        owner = self.owner(row)
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ):
            self.app.ReminderApp.delete_invoice(owner)
        self.app.ReminderApp._hide_undo_delete(owner)

        self.assertIn("forgotten", owner.undo_bar.packed)
        self.assertIsNone(owner._undo_job)
        with self.app.connect() as db:
            # The invoice is still restorable from the trash after the bar is gone.
            self.assertEqual(invoice_trash.trash_count(db), 1)


class RecordingWidget:
    """Record what a dialogue builds, and let a test press its buttons."""

    def __init__(self, kind, registry, master=None, **options):
        self.kind = kind
        self.master = master
        self.options = dict(options)
        self.packed = []
        self.rows = {}
        self.chosen = []
        self.headings = {}
        self.columns = {}
        registry.append(self)

    def pack(self, **kwargs):
        self.packed.append(kwargs)
        return self

    def configure(self, **options):
        self.options.update(options)

    def state(self, states):
        self.options["state"] = tuple(states)

    def heading(self, column, **options):
        self.headings[column] = options

    def column(self, column, **options):
        self.columns[column] = options

    def insert(self, _parent, _index, **options):
        self.rows[options["iid"]] = options["values"]

    def get_children(self):
        return tuple(self.rows)

    def delete(self, item):
        self.rows.pop(item, None)

    def selection(self):
        return tuple(self.chosen)

    def selection_set(self, item):
        self.chosen.append(item)


class RecordingTtk:
    def __init__(self):
        self.widgets = []
        self.by_kind = {}

    def _make(self, kind):
        def build(master=None, **options):
            widget = RecordingWidget(kind, self.widgets, master, **options)
            self.by_kind.setdefault(kind, []).append(widget)
            return widget
        return build

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._make(name)

    def kind(self, name):
        return self.by_kind.get(name, [])

    def find_button(self, text):
        for button in self.kind("Button"):
            if button.options.get("text") == text:
                return button
        raise AssertionError(f"no button named {text!r} in {[b.options.get('text') for b in self.kind('Button')]}")


class RecordingWindow:
    def __init__(self, title):
        self.title_text = title
        self.protocols = {}

    def resizable(self, *_args):
        pass

    def protocol(self, name, handler):
        self.protocols[name] = handler

    def deiconify(self):
        self.shown = True

    def lift(self):
        self.lifted = True

    def focus_force(self):
        self.focused = True

    def destroy(self):
        self.destroyed = True


class ShortcutCallbackTests(unittest.TestCase):
    """The shortcut wrapper leaves the key alone when the action declines."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as temporary_directory:
            cls.module = load_headless_app(Path(temporary_directory))
            close_log_handlers(cls.module)

    def wrapper(self, result):
        app = SimpleNamespace(_shortcut_callback=self.module.ReminderApp._shortcut_callback)
        return app._shortcut_callback(lambda: result)

    def test_a_normal_action_consumes_the_key(self):
        for result in (None, True, object()):
            with self.subTest(result=result):
                self.assertEqual(self.wrapper(result)(), "break")

    def test_a_declined_action_lets_the_widget_keep_the_key(self):
        self.assertIsNone(self.wrapper(False)())


class FocusGuardTests(unittest.TestCase):
    """Ctrl+Z belongs to a text field when the keyboard is in one."""

    class Widget:
        def __init__(self, widget_class):
            self.widget_class = widget_class

        def winfo_class(self):
            return self.widget_class

    def owner(self, widget):
        return SimpleNamespace(
            focus_get=lambda: widget,
            _last_deleted=None,
        )

    def test_a_text_field_keeps_its_own_undo(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            self.addCleanup(close_log_handlers, app)
            for name in ("Entry", "TEntry", "Text", "Spinbox", "TCombobox"):
                with self.subTest(widget=name):
                    owner = self.owner(self.Widget(name))
                    self.assertTrue(app.ReminderApp._focus_is_text_input(owner))
            for name in ("Treeview", "TButton", "Frame", "Toplevel"):
                with self.subTest(widget=name):
                    owner = self.owner(self.Widget(name))
                    self.assertFalse(app.ReminderApp._focus_is_text_input(owner))

    def test_no_focus_means_the_shortcut_works(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = load_headless_app(Path(temporary_directory))
            self.addCleanup(close_log_handlers, app)
            self.assertFalse(app.ReminderApp._focus_is_text_input(self.owner(None)))


class TrashWindowTests(unittest.TestCase):
    """The trash dialogue itself, against a real database."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.app.DB_PATH = self.workspace / "trash-window.sqlite3"
        self.app.init_db()

        def cleanup():
            close_log_handlers(self.app)
            self.temporary.cleanup()

        self.addCleanup(cleanup)
        self.ttk = RecordingTtk()
        self.window = RecordingWindow("Papperskorg")
        self.owner = SimpleNamespace(
            _trash_window=None,
            ttk=self.ttk,
            _new_toplevel=lambda title: self.window,
            _px=lambda value: value,
            refresh=Mock(),
        )
        self.patches = [patch.object(self.app, "ttk", self.ttk)]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def save(self, invoice_no, customer="Kund AB"):
        record = {
            "customer": customer, "invoice_no": invoice_no, "invoice_date": "2026-10-01",
            "due_date": "2026-11-01", "template_vendor": "", "amount": 1000.0,
            "currency": "SEK", "paid": 0.0, "email": "", "source": "manual-entry",
            "source_hash": f"hash-{invoice_no}", "note": "", "reviewed": 1,
        }
        self.assertIsNone(self.app.save_invoice_record(record))
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE invoice_no=?", (invoice_no,)).fetchone()
            invoice_trash.delete_invoice_to_trash(db, row["id"])
        return row

    def open_trash(self):
        self.ttk.widgets.clear()
        self.ttk.by_kind.clear()
        return self.app.ReminderApp.show_trash(self.owner)

    def tree(self):
        return self.ttk.kind("Treeview")[0]

    def summary(self):
        texts = [widget.options.get("text") for widget in self.ttk.kind("Label")]
        return [text for text in texts if text and ("papperskorg" in str(text).casefold() or "faktura" in str(text).casefold())]

    def test_the_dialogue_lists_what_the_trash_holds_and_can_be_reopened(self):
        self.save("6475")
        window = self.open_trash()
        self.assertIs(window, self.window)
        self.assertEqual(list(self.tree().rows.values())[0][0], "6475")
        self.assertIn("1 faktura i papperskorgen", self.summary())
        # A second open raises the same window instead of stacking copies.
        self.assertIs(self.app.ReminderApp.show_trash(self.owner), self.window)
        self.assertIn("WM_DELETE_WINDOW", self.window.protocols)

    def test_an_empty_trash_disables_the_three_actions(self):
        self.open_trash()
        for name in ("Återställ valda", "Ta bort permanent", "Töm papperskorgen"):
            self.assertEqual(self.ttk.find_button(name).options.get("state"), ("disabled",), name)

    def test_restoring_the_selected_invoice_puts_it_back(self):
        self.save("6475")
        self.open_trash()
        self.tree().selection_set("1")
        with patch.object(self.app.messagebox, "showinfo", create=True) as showinfo, patch.object(
            self.app, "refresh_json_journal", return_value=True
        ):
            self.ttk.find_button("Återställ valda").options["command"]()

        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 0)
            self.assertIsNotNone(db.execute("SELECT 1 FROM invoices WHERE invoice_no='6475'").fetchone())
        self.assertIn("1 fakturor återställda", showinfo.call_args.args[1])
        self.assertEqual(self.tree().rows, {})
        self.owner.refresh.assert_called()

    def trash_ids(self):
        with self.app.connect() as db:
            return {item["invoice_no"]: item["id"] for item in invoice_trash.trash_items(db)}

    def test_restoring_the_offered_invoice_takes_the_undo_offer_away(self):
        self.save("6475")
        trash_id = self.trash_ids()["6475"]
        self.owner._last_deleted = {"trash_id": trash_id, "invoice_no": "6475", "customer": "Kund AB", "invoice_id": 1}
        self.owner._hide_undo_delete = Mock()
        self.open_trash()
        self.tree().selection_set(str(trash_id))
        with patch.object(self.app.messagebox, "showinfo", create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ):
            self.ttk.find_button("Återställ valda").options["command"]()

        self.owner._hide_undo_delete.assert_called()
        self.assertIsNone(self.owner._last_deleted)

    def test_restoring_another_invoice_leaves_the_undo_offer_alone(self):
        self.save("6475")
        self.save("6476")
        ids = self.trash_ids()
        self.owner._last_deleted = {"trash_id": ids["6476"], "invoice_no": "6476", "customer": "Kund AB", "invoice_id": 2}
        self.owner._hide_undo_delete = Mock()
        self.open_trash()
        self.tree().selection_set(str(ids["6475"]))
        with patch.object(self.app.messagebox, "showinfo", create=True), patch.object(
            self.app, "refresh_json_journal", return_value=True
        ):
            self.ttk.find_button("Återställ valda").options["command"]()

        self.owner._hide_undo_delete.assert_not_called()
        self.assertIsNotNone(self.owner._last_deleted)

    def test_emptying_the_trash_asks_first_and_keeps_everything_on_no(self):
        self.save("1")
        self.save("2")
        self.open_trash()
        with patch.object(self.app.messagebox, "askyesno", return_value=False, create=True) as ask:
            self.ttk.find_button("Töm papperskorgen").options["command"]()
        self.assertEqual(ask.call_count, 1)
        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 2)

    def test_emptying_the_trash_removes_everything_on_yes(self):
        self.save("1")
        self.save("2")
        self.open_trash()
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True):
            self.ttk.find_button("Töm papperskorgen").options["command"]()
        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 0)
        self.assertEqual(self.tree().rows, {})
        self.assertEqual(self.ttk.find_button("Töm papperskorgen").options.get("state"), ("disabled",))

    def test_permanent_delete_only_touches_the_selected_row(self):
        self.save("1")
        self.save("2")
        self.open_trash()
        first = min(self.tree().rows)
        self.tree().selection_set(first)
        with patch.object(self.app.messagebox, "askyesno", return_value=True, create=True):
            self.ttk.find_button("Ta bort permanent").options["command"]()
        with self.app.connect() as db:
            self.assertEqual(invoice_trash.trash_count(db), 1)


if __name__ == "__main__":
    unittest.main()
