"""Layout tests for the settings dialog on small and large screens.

The headless test environment has no Tk display, so these tests exercise the
real ``settings()`` code against a recording widget toolkit. That proves the
dialog builds every field, reflows between one and three columns, wraps long
help texts instead of forcing width and keeps its action buttons outside the
scrolling area.
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

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def destroy(self):
        self.destroyed = True

    def bind(self, _sequence, _callback=None, **_kwargs):
        return None

    def winfo_width(self):
        return self.options.get("_width", 900)

    def winfo_screenwidth(self):
        return self.options.get("_screen_width", 1920)

    def winfo_screenheight(self):
        return 1080

    def winfo_reqwidth(self):
        return 900

    def winfo_reqheight(self):
        return 700

    def grid_columnconfigure(self, _index, **_kwargs):
        return None


class FakeCanvas(FakeWidget):
    def bind(self, _sequence, callback=None, **_kwargs):
        self._configure_callback = callback

    def winfo_width(self):
        return self.options.get("_width", 900)

    def itemconfigure(self, *_args, **_kwargs):
        return None


class FakeScrollableForm:
    """Stand-in for accessibility.ScrollableForm used by settings()."""

    def __init__(self, window, _tk, _ttk, padding=16):
        self.window = window
        self.form = FakeWidget("ScrollForm", window.registry, master=window, padding=padding)
        self.canvas = FakeCanvas("Canvas", window.registry, master=window)
        self.canvas.options["_width"] = window.options.get("_canvas_width", 900)
        self.fitted = None

    def fit_to_content(self, max_width=1100, max_height=800):
        self.fitted = (max_width, max_height)
        return (min(max_width, 900), min(max_height, 700))


class FakeWindow(FakeWidget):
    def __init__(self, title, registry, screen_width, canvas_width=900):
        super().__init__("Toplevel", registry, _screen_width=screen_width)
        self.registry = registry
        self.title_text = title
        self.options["_canvas_width"] = canvas_width
        self.geometry_calls = []
        self.minsize_calls = []
        self.grabbed = False
        self.after_jobs = []

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

    def after_idle(self, callback):
        self.after_jobs.append(callback)
        return f"job{len(self.after_jobs)}"

    def after_cancel(self, _job):
        return None

    def winfo_width(self):
        return self.options["_canvas_width"]


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

    def build(self, screen_width=1920, canvas_width=900):
        app = self.app
        window = FakeWindow("Inställningar", self.registry, screen_width, canvas_width)

        def new_toplevel(_title):
            return window

        fake_self = SimpleNamespace(
            _new_toplevel=new_toplevel,
            ui_font_scale=1.0,
            review_learning=lambda _parent=None: None,
            set_font_scale=lambda *_a, **_k: None,
            rebuild_ui=lambda: None,
            refresh=lambda: None,
        )
        with mock.patch.object(app, "setting", side_effect=lambda key: self.values.get(key, "")), \
                mock.patch.object(app, "set_setting"), \
                mock.patch.object(app, "set_autostart"), \
                mock.patch.object(app, "refresh_json_journal"), \
                mock.patch.object(app, "ScrollableForm", FakeScrollableForm), \
                mock.patch.object(app, "fit_window_to_screen"):
            app.ReminderApp.settings(fake_self)
        return window

    def widgets(self, kind):
        return [widget for widget in self.registry if widget.kind == kind]

    def cell_frames(self):
        return [
            widget for widget in self.registry
            if widget.kind == "Frame" and getattr(widget.master, "kind", None) == "ScrollForm"
            and any(child.kind == "Entry" for child in self.registry if child.master is widget)
        ]

    def test_every_setting_field_is_built_with_its_saved_value(self):
        self.build()

        entries = self.widgets("Entry")
        self.assertEqual(len(entries), 7)
        self.assertEqual(sorted(entry.text for entry in entries), ["150", "23", "5", "5", "5", "5", "5"])

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
        window = self.build()

        buttons = [
            widget for widget in self.widgets("Button")
            if widget.options.get("text") in ("Spara inställningar", "Stäng")
        ]
        self.assertEqual(len(buttons), 2)
        footer = buttons[0].master
        self.assertIs(footer.master, window)
        self.assertEqual(footer.pack_calls[0]["side"], "bottom")

    def reflow_to(self, window, width):
        canvas = [w for w in self.registry if w.kind == "Canvas"][0]
        canvas.options["_width"] = width
        canvas._configure_callback(SimpleNamespace(widget=canvas))
        for job in window.after_jobs:
            job()

    def columns_now(self):
        return {
            cell.grid_calls[-1]["column"] for cell in self.cell_frames() if cell.grid_calls
        }

    def test_wide_dialog_packs_fields_in_three_columns(self):
        window = self.build(screen_width=1920, canvas_width=1000)
        self.reflow_to(window, 1000)

        self.assertEqual(self.columns_now(), {0, 1, 2})

    def test_narrow_dialog_falls_back_to_a_single_column(self):
        window = self.build(screen_width=800, canvas_width=420)
        self.reflow_to(window, 420)

        self.assertEqual(self.columns_now(), {0})

    def test_help_texts_wrap_to_the_available_width(self):
        window = self.build(screen_width=1280, canvas_width=760)
        self.reflow_to(window, 760)

        hints = [
            widget for widget in self.widgets("Label")
            if widget.master.kind == "ScrollForm"
            and widget.options.get("style") == "Sub.TLabel"
        ]
        self.assertTrue(hints)
        for hint in hints:
            self.assertLessEqual(hint.options["wraplength"], 760)

    def test_resizing_the_dialog_reflows_without_rebuilding_fields(self):
        window = self.build(screen_width=1920, canvas_width=1000)
        canvas = [w for w in self.registry if w.kind == "Canvas"][0]
        entries_before = list(self.widgets("Entry"))

        self.reflow_to(window, 420)

        self.assertEqual(self.columns_now(), {0})
        self.assertEqual(self.widgets("Entry"), entries_before)

    def test_dialog_width_never_exceeds_the_screen(self):
        window = FakeWindow("x", [], 800)
        self.assertLessEqual(self.app.dialog_available_width(window), 800 - 48)


if __name__ == "__main__":
    unittest.main()
