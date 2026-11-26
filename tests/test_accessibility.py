import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import accessibility
from app_info import PYTHON_PACKAGE_REQUIRED_FILES
from test_database import load_headless_app


class FakeFont:
    def __init__(self, size=10, family="Test Sans"):
        self.size = size
        self.family = family

    def cget(self, key):
        return getattr(self, key)

    def configure(self, **options):
        for key, value in options.items():
            setattr(self, key, value)


class FakeFontModule:
    def __init__(self):
        self.fonts = {name: FakeFont(size=10 + index) for index, name in enumerate(accessibility.NAMED_FONTS)}

    def nametofont(self, name):
        return self.fonts[name]


class FakeStyle:
    def __init__(self):
        self.configurations = {}
        self.maps = {}

    def configure(self, name, **options):
        self.configurations.setdefault(name, {}).update(options)

    def map(self, name, **options):
        self.maps.setdefault(name, {}).update(options)


class FakeWidget:
    def __init__(self, widget_class, *, x=0, y=0, height=1, children=(), mapped=True, state="normal"):
        self.widget_class = widget_class
        self.x = x
        self.y = y
        self.height = height
        self.children = list(children)
        self.mapped = mapped
        self.options = {"state": state, "takefocus": ""}
        self.bindings = {}
        self.focused = False
        self.root = self
        for child in self.children:
            child.root = self.root

    def winfo_class(self):
        return self.widget_class

    def winfo_children(self):
        return self.children

    def winfo_rootx(self):
        return self.x

    def winfo_rooty(self):
        return self.y

    def winfo_height(self):
        return self.height

    def winfo_exists(self):
        return True

    def winfo_ismapped(self):
        return self.mapped

    def winfo_toplevel(self):
        return self.root

    def cget(self, key):
        return self.options.get(key, "")

    def configure(self, **options):
        self.options.update(options)

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def focus_set(self):
        self.focused = True


class BindingWindow:
    def __init__(self):
        self.bindings = {}

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback


class FakeGridWidget:
    """Record grid/configure calls for ResponsiveGrid tests."""

    def __init__(self, kind="widget"):
        self.kind = kind
        self.grid_calls = []
        self.options = {}

    def grid(self, **kwargs):
        self.grid_calls.append(kwargs)

    def configure(self, **kwargs):
        self.options.update(kwargs)

    @property
    def last_grid(self):
        return self.grid_calls[-1] if self.grid_calls else {}


class FakeGridForm(FakeGridWidget):
    def __init__(self):
        super().__init__("form")
        self.column_options = {}

    def grid_columnconfigure(self, index, **kwargs):
        self.column_options[index] = kwargs

    def winfo_width(self):
        return self.options.get("width", 1000)


class ResponsiveGridTests(unittest.TestCase):
    def build(self, width):
        form = FakeGridForm()
        grid = accessibility.ResponsiveGrid(form)
        heading = FakeGridWidget("heading")
        cells = []
        hints = []
        checks = []
        grid.add_heading(heading)
        for index in range(7):
            label = FakeGridWidget("label")
            entry = FakeGridWidget("entry")
            cell = FakeGridWidget("cell")
            grid.add_cell(cell, label=label, entry=entry)
            cells.append((cell, label, entry))
        grid.add_full(check := FakeGridWidget("check"))
        checks.append(check)
        hint = FakeGridWidget("hint")
        grid.add_hint(hint)
        hints.append(hint)
        grid.apply(width)
        return grid, form, heading, cells, hints, checks

    def test_column_count_uses_one_shared_rule(self):
        cases = {1200: 3, 750: 3, 700: 2, 500: 2, 480: 1, 0: 1, None: 1, "wide": 1}
        for width, expected in cases.items():
            self.assertEqual(accessibility.ResponsiveGrid.columns_for(width), expected)

    def test_fields_flow_into_the_widest_fitting_column_count(self):
        grid, _form, _heading, cells, _hints, _checks = self.build(1000)

        self.assertEqual(grid.columns, 3)
        columns = [cell.last_grid["column"] for cell, _label, _entry in cells]
        self.assertEqual(columns, [0, 1, 2, 0, 1, 2, 0])
        rows = [cell.last_grid["row"] for cell, _label, _entry in cells]
        self.assertEqual(rows, [1, 1, 1, 2, 2, 2, 3])

    def test_narrow_width_puts_every_field_in_one_column(self):
        grid, _form, _heading, cells, _hints, _checks = self.build(400)

        self.assertEqual(grid.columns, 1)
        self.assertEqual({cell.last_grid["column"] for cell, _label, _entry in cells}, {0})
        self.assertEqual(len({cell.last_grid["row"] for cell, _label, _entry in cells}), 7)

    def test_full_width_items_break_the_field_flow(self):
        grid, _form, heading, cells, hints, checks = self.build(1000)

        self.assertEqual(heading.last_grid["columnspan"], 3)
        self.assertEqual(checks[0].last_grid["columnspan"], 3)
        self.assertEqual(hints[0].last_grid["columnspan"], 3)
        self.assertGreater(checks[0].last_grid["row"], max(
            cell.last_grid["row"] for cell, _label, _entry in cells
        ))

    def test_help_text_and_labels_wrap_to_the_available_width(self):
        _grid, _form, _heading, cells, hints, _checks = self.build(620)

        self.assertEqual(hints[0].options["wraplength"], 612)
        for _cell, label, _entry in cells:
            self.assertLessEqual(label.options["wraplength"], 620)
            self.assertGreaterEqual(label.options["wraplength"], 120)

    def test_entries_shrink_but_stay_usable_in_narrow_columns(self):
        _grid, _form, _heading, cells, _hints, _checks = self.build(400)

        for _cell, _label, entry in cells:
            self.assertGreaterEqual(entry.options["width"], 8)
            self.assertLessEqual(entry.options["width"], 16)

    def test_reapplying_the_same_width_does_no_work(self):
        grid, _form, _heading, _cells, _hints, _checks = self.build(1000)

        self.assertFalse(grid.apply(1000))

    def test_resizing_reflows_existing_widgets_without_replacing_them(self):
        grid, _form, _heading, cells, _hints, _checks = self.build(1000)
        before = [id(cell) for cell, _label, _entry in cells]

        self.assertTrue(grid.apply(420))

        self.assertEqual([id(cell) for cell, _label, _entry in cells], before)
        self.assertEqual({cell.last_grid["column"] for cell, _label, _entry in cells}, {0})
        self.assertEqual(grid.columns, 1)

    def test_compact_mode_halves_spacing_without_hiding_anything(self):
        grid, _form, _heading, cells, _hints, _checks = self.build(1000)
        roomy = cells[0][0].last_grid["pady"]

        grid.compact = True
        grid.apply(900)

        self.assertEqual(len(grid.items), 10)
        compact = cells[0][0].last_grid["pady"]
        self.assertLessEqual(sum(compact), sum(roomy))


class AccessibilityTests(unittest.TestCase):
    def test_scale_is_bounded_and_accepts_percentages(self):
        self.assertEqual(accessibility.normalize_font_scale("125 %"), 1.25)
        self.assertEqual(accessibility.normalize_font_scale("1,5"), 1.5)
        self.assertEqual(accessibility.normalize_font_scale("not-a-number"), 1.0)
        self.assertEqual(accessibility.normalize_font_scale(100), 2.0)
        self.assertEqual(accessibility.normalize_font_scale(-4), 0.8)
        self.assertEqual(accessibility.normalize_font_scale(99), 2.0)
        self.assertEqual(accessibility.stepped_font_scale(1.0, 1), 1.1)
        self.assertEqual(accessibility.stepped_font_scale(1.0, -1), 0.9)
        self.assertEqual(accessibility.font_scale_storage(1.25), "1.25")

    def test_palette_has_readable_text_and_focus_contrast(self):
        for foreground in (accessibility.TEXT, accessibility.MUTED_TEXT, accessibility.TITLE_TEXT, accessibility.FOCUS):
            with self.subTest(foreground=foreground):
                self.assertGreaterEqual(accessibility.contrast_ratio(foreground, accessibility.BACKGROUND), 4.5)
        self.assertGreaterEqual(accessibility.contrast_ratio(accessibility.SELECTED_TEXT, accessibility.SELECTED_BACKGROUND), 4.5)
        high = accessibility.contrast_palette(True)
        self.assertGreaterEqual(accessibility.contrast_ratio(high['text'], high['background']), 4.5)
        self.assertGreaterEqual(accessibility.contrast_ratio(high['focus'], high['background']), 4.5)
        self.assertGreaterEqual(accessibility.contrast_ratio(high['selected_text'], high['selected_background']), 4.5)

    def test_system_high_contrast_detection_has_safe_platform_fallbacks(self):
        def runner(command, **_kwargs):
            output = 'true\n' if 'high-contrast' in command else 'Adwaita\n'
            return SimpleNamespace(stdout=output)

        self.assertTrue(accessibility.system_high_contrast(platform='linux', environ={}, runner=runner))
        self.assertTrue(accessibility.system_high_contrast(platform='linux', environ={'GTK_THEME': 'HighContrast'}, runner=runner))
        self.assertTrue(accessibility.system_high_contrast(platform='darwin', environ={}, runner=lambda *_a, **_k: SimpleNamespace(stdout='1\n')))
        with patch.object(accessibility, '_windows_high_contrast', return_value=True):
            self.assertTrue(accessibility.system_high_contrast(platform='win32', environ={}))
        self.assertFalse(accessibility.system_high_contrast(platform='linux', environ={}, runner=lambda *_a, **_k: SimpleNamespace(stdout='false\n')))

    def test_fit_window_to_screen_enables_resize_and_bounds_geometry(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 800
        window.winfo_screenheight.return_value = 600
        window.winfo_reqwidth.return_value = 1200
        window.winfo_reqheight.return_value = 1000
        window.winfo_x.return_value = 0
        window.winfo_y.return_value = 0
        result = accessibility.fit_window_to_screen(window)
        self.assertEqual(result, (752, 552))
        window.resizable.assert_called_once_with(True, True)
        window.minsize.assert_called_once_with(360, 240)
        geometry = window.geometry.call_args.args[0]
        self.assertTrue(geometry.startswith('752x552+'))

    def test_window_is_bounded_by_the_monitor_work_area(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 1920
        window.winfo_screenheight.return_value = 1080
        window.winfo_reqwidth.return_value = 1000
        window.winfo_reqheight.return_value = 900
        window.winfo_x.return_value = 0
        window.winfo_y.return_value = 0
        # A 1080p screen with a taskbar leaves 1040 usable pixels.
        with patch.object(accessibility, "monitor_work_area", return_value=(0, 0, 1920, 1040)):
            result = accessibility.fit_window_to_screen(window)
        self.assertEqual(result, (1000, 900))
        self.assertTrue(window.geometry.call_args.args[0].startswith("1000x900+"))

    def test_window_never_extends_below_a_short_work_area(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 1366
        window.winfo_screenheight.return_value = 768
        window.winfo_reqwidth.return_value = 1200
        window.winfo_reqheight.return_value = 1200
        window.winfo_x.return_value = 100
        window.winfo_y.return_value = 700
        with patch.object(accessibility, "monitor_work_area", return_value=(0, 0, 1366, 728)):
            width, height = accessibility.fit_window_to_screen(window)
        self.assertEqual((width, height), (1200, 680))
        geometry = window.geometry.call_args.args[0]
        x, y = (int(part) for part in geometry.split("+")[1:])
        self.assertLessEqual(y + height, 728)
        self.assertLessEqual(x + width, 1366)

    def test_work_area_falls_back_to_the_screen_when_windows_apis_fail(self):
        window = Mock()
        window.winfo_screenwidth.return_value = 1024
        window.winfo_screenheight.return_value = 700
        with patch.object(accessibility.sys, "platform", "linux"):
            self.assertEqual(accessibility.monitor_work_area(window), (0, 0, 1024, 700))
        with patch.object(accessibility.sys, "platform", "win32"), patch.object(
            window, "winfo_id", side_effect=RuntimeError("no native handle"), create=True
        ):
            self.assertEqual(accessibility.monitor_work_area(window), (0, 0, 1024, 700))

    def test_high_contrast_is_applied_to_classic_widgets_and_focus(self):
        root = FakeWidget('Tk')
        text = FakeWidget('Text')
        root.children = [text]
        text.root = root
        accessibility.apply_widget_contrast(root, True)
        self.assertEqual(text.options['background'], accessibility.HIGH_CONTRAST_FIELD_BACKGROUND)
        self.assertEqual(text.options['foreground'], accessibility.HIGH_CONTRAST_TEXT)
        accessibility.prepare_focus_tree(root, True)
        self.assertEqual(text.options['highlightcolor'], accessibility.HIGH_CONTRAST_FOCUS)

    def test_style_scales_from_fixed_base_sizes_and_maps_focus(self):
        fonts = FakeFontModule()
        style = FakeStyle()
        accessible = accessibility.AccessibleStyle(style, fonts)
        accessible.apply(1.5)
        self.assertEqual(fonts.fonts["TkDefaultFont"].size, 15)
        self.assertEqual(style.configurations["Treeview"]["rowheight"], 48)
        self.assertEqual(style.configurations["Sub.TLabel"]["foreground"], accessibility.MUTED_TEXT)
        self.assertIn(("focus", accessibility.FOCUS), style.maps["TButton"]["focuscolor"])
        accessible.apply(1.0)
        self.assertEqual(fonts.fonts["TkDefaultFont"].size, 10)
        self.assertEqual(style.configurations["Treeview"]["rowheight"], 32)

    def test_donation_styles_keep_white_text_readable_in_both_palettes(self):
        """A channel keeps its colour, but the text must stay readable.

        The three donation colours are decorative: each one is checked against
        white, and high contrast replaces them with the palette accent so no
        meaning ever depends on the colour alone.
        """
        for high_contrast in (False, True):
            fonts = FakeFontModule()
            style = FakeStyle()
            accessible = accessibility.AccessibleStyle(style, fonts)
            accessible.apply(1.0, high_contrast=high_contrast)
            for name in ("Swish.TButton", "PayPal.TButton", "Kofi.TButton"):
                with self.subTest(style=name, high_contrast=high_contrast):
                    colour = style.configurations[name]["background"]
                    self.assertEqual(style.configurations[name]["foreground"], "#FFFFFF")
                    self.assertGreaterEqual(accessibility.contrast_ratio("#FFFFFF", colour), 4.5)
                    self.assertIn("background", style.maps[name])
            for name in ("Card.TFrame", "CardBody.TLabel", "CardSub.TLabel", "CardHeading.TLabel", "CardKicker.TLabel"):
                self.assertIn(name, style.configurations)

    def test_focus_tree_uses_visual_order_and_classic_focus_outline(self):
        root = FakeWidget("Tk")
        later = FakeWidget("TButton", x=300, y=10, height=30)
        first = FakeWidget("TEntry", x=20, y=20, height=10)
        text = FakeWidget("Text", x=20, y=100)
        root.children = [later, first, text]
        for child in root.children:
            child.root = root
        order = accessibility.prepare_focus_tree(root)
        self.assertEqual(order, [first, later, text])
        self.assertEqual(text.options["highlightthickness"], 2)
        self.assertEqual(text.options["highlightcolor"], accessibility.FOCUS)
        accessibility.focus_first(root)
        self.assertTrue(first.focused)
        accessibility.move_focus(first)
        self.assertTrue(later.focused)
        accessibility.move_focus(later)
        self.assertTrue(text.focused)
        accessibility.move_focus(text, reverse=True)
        self.assertTrue(later.focused)

    def test_control_tab_inserts_a_real_tab_in_text_widgets(self):
        widget = Mock()
        self.assertEqual(accessibility._insert_text_tab(widget), "break")
        widget.insert.assert_called_once_with("insert", "\t")

    def test_parent_focus_tree_does_not_enter_toplevel_dialogs(self):
        root = FakeWidget("Tk")
        main_button = FakeWidget("TButton", x=0, y=0)
        dialog = FakeWidget("Toplevel", x=0, y=100)
        dialog_button = FakeWidget("TButton", x=0, y=0)
        dialog.children = [dialog_button]
        dialog_button.root = dialog
        root.children = [main_button, dialog]
        main_button.root = root
        dialog.root = root
        order = accessibility.prepare_focus_tree(root)
        self.assertEqual(order, [main_button])
        dialog_order = accessibility.prepare_focus_tree(dialog)
        self.assertEqual(dialog_order, [dialog_button])

    def test_focus_skips_disabled_and_unmapped_controls(self):
        root = FakeWidget("Tk")
        first = FakeWidget("TButton", x=0, y=0)
        disabled = FakeWidget("TButton", x=100, y=0, state="disabled")
        hidden = FakeWidget("TButton", x=200, y=0, mapped=False)
        last = FakeWidget("TButton", x=300, y=0)
        root.children = [first, disabled, hidden, last]
        for child in root.children:
            child.root = root
        accessibility.prepare_focus_tree(root)
        accessibility.move_focus(first)
        self.assertTrue(last.focused)
        self.assertFalse(disabled.focused)
        self.assertFalse(hidden.focused)


class AccessibilityAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))
        self.app.DB_PATH = Path(self.temporary.name) / "accessibility.sqlite3"
        self.app.init_db()

        def cleanup():
            for handler in self.app.logger.handlers[:]:
                self.app.logger.removeHandler(handler)
                handler.close()
            self.temporary.cleanup()

        self.addCleanup(cleanup)

    def test_font_scale_setting_is_migrated(self):
        self.assertEqual(self.app.setting(self.app.FONT_SCALE_SETTING), "1.0")
        self.assertIn("accessibility.py", PYTHON_PACKAGE_REQUIRED_FILES)

    def test_main_shortcuts_are_idempotent_and_call_real_actions(self):
        window = BindingWindow()
        fake = SimpleNamespace(
            _shortcut_modifier=lambda: "Control",
            _shortcut_callback=self.app.ReminderApp._shortcut_callback,
            show_keyboard_help=Mock(), change_font_scale=Mock(), reset_font_scale=Mock(),
            focus_invoice_search=Mock(), add_invoice=Mock(), import_invoice=Mock(),
            edit_invoice=Mock(), settings=Mock(), scan_import_folder=Mock(),
            cycle_invoice_filter=Mock(), open_selected_invoice_pdf=Mock(),
            show_file_menu=Mock(), show_help_menu=Mock(), undo_last_delete=Mock(),
        )
        self.app.ReminderApp._install_accessibility_shortcuts(fake, window, main_window=True)
        self.assertIn("<Control-f>", window.bindings)
        self.assertIn("<Control-z>", window.bindings)
        self.assertIn("<Control-plus>", window.bindings)
        self.assertIn("<F5>", window.bindings)
        self.assertIn("<F10>", window.bindings)
        self.assertIn("<Alt-h>", window.bindings)
        self.assertEqual(window.bindings["<Control-f>"](), "break")
        fake.focus_invoice_search.assert_called_once_with()
        # Undo is a real action on the main window, not a placeholder.
        self.assertEqual(window.bindings["<Control-z>"](), "break")
        fake.undo_last_delete.assert_called_once_with()
        binding_count = len(window.bindings)
        self.app.ReminderApp._install_accessibility_shortcuts(fake, window, main_window=True)
        self.assertEqual(len(window.bindings), binding_count)

    def test_system_contrast_poll_applies_changes_and_reschedules(self):
        class ImmediateThread:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _contrast_check_running=False,
            _high_contrast=False,
            _apply_accessibility_palette=Mock(),
            _poll_system_contrast=Mock(),
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app.threading, 'Thread', ImmediateThread), patch.object(
            self.app, 'system_high_contrast', return_value=True,
        ):
            self.app.ReminderApp._poll_system_contrast(fake)
        self.assertTrue(fake._high_contrast)
        fake._apply_accessibility_palette.assert_called_once_with()
        self.assertEqual(scheduled[-1][0], self.app.SYSTEM_CONTRAST_POLL_INTERVAL_MS)

    def test_hidden_tray_window_skips_system_contrast_subprocess_poll(self):
        scheduled = []
        fake = SimpleNamespace(
            _quitting=False,
            _contrast_check_running=False,
            _window_hidden=True,
            _poll_system_contrast=Mock(),
            after=lambda delay, callback: scheduled.append((delay, callback)),
        )
        with patch.object(self.app, "system_high_contrast") as query:
            self.app.ReminderApp._poll_system_contrast(fake)
        query.assert_not_called()
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], self.app.SYSTEM_CONTRAST_POLL_INTERVAL_MS)

    def test_set_font_scale_persists_and_reuses_style(self):
        fake = SimpleNamespace(
            ui_font_scale=1.0,
            _accessibility_style=Mock(),
            tree=None,
            _font_scale_var=None,
            winfo_children=lambda: [],
        )
        with patch.object(self.app, "set_setting") as save, patch.object(self.app, "refresh_json_journal") as journal:
            result = self.app.ReminderApp.set_font_scale(fake, 1.5)
        self.assertEqual(result, 1.5)
        fake._accessibility_style.apply.assert_called_once_with(
            1.5, high_contrast=False, pixel_scale=1.0, theme="light"
        )
        save.assert_called_once_with(self.app.FONT_SCALE_SETTING, "1.5")
        journal.assert_called_once_with(parent=fake)

    def test_fit_window_to_screen_centers_unmapped_dialog_on_master_monitor_away_from_seam(self):
        master = SimpleNamespace(
            winfo_ismapped=lambda: 1,
            winfo_rootx=lambda: 2100,
            winfo_rooty=lambda: 120,
            winfo_width=lambda: 1400,
            winfo_height=lambda: 900,
        )
        dialog = Mock()
        dialog.master = master
        dialog.winfo_ismapped.return_value = 0
        dialog.winfo_screenwidth.return_value = 3840
        dialog.winfo_screenheight.return_value = 1080
        dialog.winfo_reqwidth.return_value = 480
        dialog.winfo_reqheight.return_value = 460
        # Windows cascades unmapped Toplevels at (26, 26) on the primary screen
        dialog.winfo_x.return_value = 26
        dialog.winfo_y.return_value = 26
        with patch.object(accessibility, "monitor_work_area", return_value=(1920, 0, 3840, 1040)):
            size = accessibility.fit_window_to_screen(dialog)
        self.assertEqual(size, (480, 460))
        geom = dialog.geometry.call_args.args[0]
        parts = geom.replace("x", "+").split("+")
        x, y = int(parts[2]), int(parts[3])
        # Must be centered on Monitor 2 (around x=2560), never clamped to the x=1920 DPI seam!
        self.assertGreater(x, 2200)
        self.assertLess(x + 480, 3800)
        self.assertGreater(y, 100)

    def test_scrollable_form_prevents_configure_feedback_loop_and_scrollbar_ping_pong(self):
        tk_mod = SimpleNamespace(
            Canvas=lambda master, **kw: FakeCanvas(master, **kw),
        )

        class FakeGridWidget:
            def __init__(self, master=None, **kw):
                self.master = master
                self.kw = kw
                self.mapped = False
                self.grid_calls = 0
                self.remove_calls = 0
                self.bindings = {}
                self.req_w = 420
                self.req_h = 400

            def grid(self, **_kw):
                self.mapped = True
                self.grid_calls += 1

            def grid_remove(self):
                self.mapped = False
                self.remove_calls += 1

            def set(self, *_a):
                pass

            def columnconfigure(self, *_a, **_kw):
                pass

            def rowconfigure(self, *_a, **_kw):
                pass

            def bind(self, seq, fn, add=None):
                self.bindings[seq] = fn

            def pack(self, **_kw):
                pass

            def update_idletasks(self):
                pass

            def winfo_reqwidth(self):
                return self.req_w

            def winfo_reqheight(self):
                return self.req_h

        class FakeCanvas(FakeGridWidget):
            def __init__(self, master=None, **kw):
                super().__init__(master, **kw)
                self.width = 428
                self.height = 400
                self.scrollregion_calls = 0
                self.itemconfigure_calls = 0

            def create_window(self, *_a, **_kw):
                return 1

            def configure(self, **kw):
                if "width" in kw:
                    self.width = kw["width"]
                if "height" in kw:
                    self.height = kw["height"]
                if "scrollregion" in kw:
                    self.scrollregion_calls += 1

            def itemconfigure(self, _item, **kw):
                self.itemconfigure_calls += 1

            def bbox(self, _tag):
                return (0, 0, self.req_w, self.req_h)

            def winfo_width(self):
                return self.width

            def winfo_height(self):
                return self.height

            def yview(self, *_a):
                pass

            def xview(self, *_a):
                pass

            def yview_moveto(self, *_a):
                pass

            def xview_moveto(self, *_a):
                pass

            def cget(self, _key):
                return (0, 0, self.req_w, self.req_h)

        ttk_mod = SimpleNamespace(
            Frame=lambda master=None, **kw: FakeGridWidget(master, **kw),
            Scrollbar=lambda master=None, **kw: FakeGridWidget(master, **kw),
        )
        win = SimpleNamespace(
            bind=lambda *_a, **_kw: None,
            winfo_width=lambda: 460,
            winfo_height=lambda: 440,
            cget=lambda _k: "#ffffff",
        )
        sf = accessibility.ScrollableForm(win, tk_mod, ttk_mod, padding=20)
        sf.form.req_w = 420
        sf.form.req_h = 400
        fitted = sf.fit_to_content(max_width=600, max_height=600)
        # Headroom (+8px) prevents exact-pixel boundary oscillation
        self.assertEqual(fitted, (428, 408))
        self.assertFalse(sf.vertical.mapped)
        self.assertFalse(sf.horizontal.mapped)

        # Simulate pathological Configure ping-pong where hiding vertical scrollbar
        # makes content 5px taller and showing it makes content 5px shorter at fixed outer size
        for step in range(30):
            sf.form.req_h = 415 if not sf.vertical.mapped else 400
            sf._canvas_changed(SimpleNamespace(width=428))
        # Toggle latch stops oscillation after at most 3 toggles!
        self.assertLessEqual(sf.vertical.grid_calls + sf.vertical.remove_calls, 5)
        # Repeated identical Configure events emit zero redundant scrollregion/itemconfigure calls
        sr_before = sf.canvas.scrollregion_calls
        ic_before = sf.canvas.itemconfigure_calls
        for _ in range(10):
            sf._canvas_changed(SimpleNamespace(width=428))
        self.assertEqual(sf.canvas.scrollregion_calls, sr_before)
        self.assertEqual(sf.canvas.itemconfigure_calls, ic_before)

    def test_modal_dialog_finalizes_before_grab_and_skips_duplicate_idle_finalize(self):
        events = []
        window = SimpleNamespace(
            grab_set=lambda: events.append("grab_set"),
        )
        fake = SimpleNamespace()
        fake._set_window_icon = lambda _w: events.append("icon")
        fake._finalize_window_actions = lambda _w: events.append("actions")
        fake._finalize_toplevel = lambda w, _from_idle=False: self.app.ReminderApp._finalize_toplevel(
            fake, w, _from_idle=_from_idle
        )
        with patch.object(self.app, "fit_window_to_screen", side_effect=lambda _w: events.append("fit")):
            self.app.ReminderApp._prepare_modal_toplevel(fake, window)
            # Deferred after_idle callback firing later must be a no-op
            self.app.ReminderApp._finalize_toplevel(fake, window, _from_idle=True)
        self.assertEqual(events, ["icon", "actions", "fit", "grab_set"])


if __name__ == "__main__":
    unittest.main()
