"""Layout tests for the settings dialog on small and large screens.

The headless test environment has no Tk display, so these tests exercise the
real ``settings()`` code against a recording widget toolkit. That proves the
dialog builds every field, reflows between one and two columns and keeps its
action buttons outside the scrolling area.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_database import load_headless_app


class FakeVariable:
    def __init__(self, value=None, **_kwargs):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    """Record grid/pack calls and text like the Tk widgets used by settings()."""

    def __init__(self, kind, registry, master=None, **options):
        self.kind = kind
        self.master = master
        self.options = dict(options)
        self.grid_calls = []
        self.pack_calls = []
        self.text = ""
        self.destroyed = False
        registry.append(self)

    def grid(self, **kwargs):
        self.grid_calls.append(kwargs)
        return self

    def pack(self, **kwargs):
        self.pack_calls.append(kwargs)
        return self

    def insert(self, _index, value):
        self.text = str(value)

    def get(self):
        if self.text:
            return self.text
        variable = self.options.get("textvariable")
        if variable is not None:
            value = variable.get()
            return "" if value is None else str(value)
        return ""

    def grid_columnconfigure(self, _index, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def destroy(self):
        self.destroyed = True

    def winfo_screenwidth(self):
        return self.options.get("_screen_width", 1920)


class FakeWindow(FakeWidget):
    def __init__(self, title, registry, screen_width):
        super().__init__("Toplevel", registry, _screen_width=screen_width)
        self.title_text = title
        self.geometry_calls = []
        self.minsize_calls = []
        self.grabbed = False

    def winfo_screenwidth(self):
        return self.options["_screen_width"]

    def grab_set(self):
        self.grabbed = True

    def grab_release(self):
        self.grabbed = False

    def resizable(self, *_args):
        return (True, True)

    def geometry(self, value=None):
        if value is not None:
            self.geometry_calls.append(value)
        return value

    def minsize(self, width=None, height=None):
        if width is not None:
            self.minsize_calls.append((width, height))

    def protocol(self, *_args):
        return None

    def transient(self, *_args):
        return None

    def focus_force(self):
        return None

    def wait_window(self):
        return None


class FakeTtk:
    """Minimal ttk stand-in that records every control the dialog builds."""

    def __init__(self, registry):
        self.registry = registry

    def _factory(self, kind):
        registry = self.registry

        def create(master=None, **options):
            return FakeWidget(kind, registry, master=master, **options)

        return create

    def __getattr__(self, name):
        # Frame, Label, Entry, Checkbutton, Combobox, Button, Separator ...
        return self._factory(name)


class SettingsDialogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = load_headless_app(Path(self.temporary.name))
        self.addCleanup(self._close_handlers)
        self.registry = []
        self.app.tk = SimpleNamespace(
            StringVar=FakeVariable,
            BooleanVar=FakeVariable,
            Toplevel=lambda *_a, **_k: FakeWindow("", self.registry, 1920),
        )
        self.app.ttk = FakeTtk(self.registry)
        self.values = {
            "p1_days": "5", "p2_days": "5", "p3_days": "5", "fee": "150",
            "interest": "23", "objection_days": "5", "payment_deadline_days": "5",
            "autostart": "1", "update_auto": "1", "auto_import": "1",
            "ledger_friday_reminder": "1", "cache_auto": "1", "language": "sv",
            "start_minimized": "1", "learning_enabled": "1", "fee_locked": "0",
        }

    def _close_handlers(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()

    def build(self, screen_width=1920):
        app = self.app
        window = FakeWindow("Inställningar", self.registry, screen_width)
        surface = FakeWidget("ScrollForm", self.registry)

        def new_toplevel(_title):
            return window

        def dialog_form(_window, padding=20):
            surface.options["padding"] = padding
            return surface

        fake_self = SimpleNamespace(
            _new_toplevel=new_toplevel,
            _dialog_form=dialog_form,
            ui_font_scale=1.0,
            review_learning=lambda _parent=None: None,
            set_font_scale=lambda *_a, **_k: None,
            rebuild_ui=lambda: None,
            refresh=lambda: None,
        )
        with mock.patch.object(app, "setting", side_effect=lambda key: self.values.get(key, "")), \
                mock.patch.object(app, "set_setting"), \
                mock.patch.object(app, "set_autostart"), \
                mock.patch.object(app, "refresh_json_journal"):
            app.ReminderApp.settings(fake_self)
        return window, surface

    def widgets(self, kind):
        return [widget for widget in self.registry if widget.kind == kind]

    def test_every_setting_field_is_built_with_its_saved_value(self):
        self.build()

        entries = self.widgets("Entry")
        values = sorted(entry.text for entry in entries)
        self.assertEqual(
            values, ["150", "23", "5", "5", "5", "5", "5"]
        )
        self.assertEqual(len(entries), 7)

    def test_all_checkboxes_and_the_learning_button_are_present(self):
        self.build()

        texts = [widget.options.get("text") for widget in self.widgets("Checkbutton")]
        for expected in (
            "Starta PayPamin Flow automatiskt när jag loggar in",
            "Sök efter och installera uppdateringar automatiskt två gånger per dygn",
            "Starta alltid minimerad i systemfältet",
            "Bevaka importmappen och importera nya PDF:er automatiskt",
            "Påminn om att importera kundreskontralista varje fredag",
            "Rensa appcache automatiskt en gång per dygn samt vid avslut",
            "Lås påminnelseavgiften (förhindra oavsiktlig ändring)",
            "Lär sig av sparade fakturor och leverantörsval (endast lokalt)",
        ):
            self.assertIn(expected, texts)
        button_texts = [widget.options.get("text") for widget in self.widgets("Button")]
        self.assertIn("Granska inlärning", button_texts)

    def test_action_buttons_live_in_a_pinned_footer(self):
        window, _surface = self.build()

        buttons = [
            widget for widget in self.widgets("Button")
            if widget.options.get("text") in ("Spara inställningar", "Stäng")
        ]
        self.assertEqual(len(buttons), 2)
        footer = buttons[0].master
        self.assertIsInstance(footer, FakeWidget)
        # The footer is attached to the window, not to the scrolling form.
        self.assertIs(footer.master, window)
        self.assertEqual(footer.pack_calls[0]["side"], "bottom")

    def test_wide_screen_uses_two_columns_and_narrow_uses_one(self):
        self.build(screen_width=1920)
        wide_columns = {
            call["column"]
            for entry in self.widgets("Entry")
            for call in entry.master.grid_calls
        }
        self.assertEqual(wide_columns, {0, 2})

        self.registry.clear()
        self.build(screen_width=640)
        narrow_columns = {
            call["column"]
            for entry in self.widgets("Entry")
            for call in entry.master.grid_calls
        }
        self.assertEqual(narrow_columns, {0})

    def test_long_help_texts_wrap_instead_of_forcing_width(self):
        _window, surface = self.build(screen_width=1280)

        hints = [
            label for label in self.widgets("Label")
            if label.options.get("style") == "Sub.TLabel" and label.master is surface
        ]
        self.assertTrue(hints)
        for label in hints:
            self.assertIn("wraplength", label.options)
            self.assertGreater(label.options["wraplength"], 200)

    def test_form_columns_helper_boundary(self):
        self.assertEqual(self.app.form_columns(1100), 2)
        self.assertEqual(self.app.form_columns(700), 2)
        self.assertEqual(self.app.form_columns(699), 1)
        self.assertEqual(self.app.form_columns(None), 1)


if __name__ == "__main__":
    unittest.main()
