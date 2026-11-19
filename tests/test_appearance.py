"""The light and dark themes, the UI font and the window that uses the screen.

The palette rules are checked as colours, the theme detection with injected
platform readers, and the window behaviour against recording widgets, so the
whole appearance layer is testable without a display.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import accessibility
import appearance
from test_database import load_headless_app


class FakeFont:
    def __init__(self, size=10):
        self.options = {"size": size, "family": "Test Sans"}

    def cget(self, key):
        return self.options[key]

    def configure(self, **options):
        self.options.update(options)


class FakeFontModule:
    def __init__(self):
        self.fonts = {name: FakeFont() for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont")}

    def nametofont(self, name):
        return self.fonts.setdefault(name, FakeFont())


class RecordingStyle:
    def __init__(self):
        self.configurations = {}
        self.maps = {}

    def configure(self, name, **options):
        self.configurations.setdefault(name, {}).update(options)

    def map(self, name, **options):
        self.maps.setdefault(name, {}).update(options)

    def options(self, name):
        return self.configurations[name]


class ThemeChoiceTests(unittest.TestCase):
    def test_known_choices_and_their_spellings_normalize(self):
        for value in ("light", "Ljust", " LIGHT "):
            with self.subTest(value=value):
                self.assertEqual(appearance.normalize_theme(value), appearance.THEME_LIGHT)
        for value in ("dark", "Mörkt", "morkt", "DARK"):
            with self.subTest(value=value):
                self.assertEqual(appearance.normalize_theme(value), appearance.THEME_DARK)
        for value in ("system", "Följ systemet", "follow system", "auto"):
            with self.subTest(value=value):
                self.assertEqual(appearance.normalize_theme(value), appearance.THEME_SYSTEM)

    def test_an_unknown_value_falls_back_instead_of_half_applying(self):
        self.assertEqual(appearance.normalize_theme("", appearance.THEME_DARK), appearance.THEME_DARK)
        self.assertEqual(appearance.normalize_theme(None), appearance.THEME_LIGHT)
        self.assertEqual(appearance.normalize_theme("neon"), appearance.THEME_LIGHT)
        self.assertEqual(appearance.normalize_theme("neon", "dark"), appearance.THEME_DARK)

    def test_the_default_theme_is_the_light_one_the_app_always_had(self):
        self.assertEqual(appearance.DEFAULT_THEME, appearance.THEME_LIGHT)
        self.assertEqual(appearance.setting_label("dark"), "Mörkt")
        self.assertEqual(appearance.setting_label(""), "Ljust")


class SystemThemeTests(unittest.TestCase):
    def test_windows_reads_the_apps_theme_and_defaults_to_light(self):
        self.assertEqual(
            appearance.system_theme(platform="win32", environ={}, windows_reader=lambda: False),
            appearance.THEME_DARK,
        )
        self.assertEqual(
            appearance.system_theme(platform="win32", environ={}, windows_reader=lambda: True),
            appearance.THEME_LIGHT,
        )
        def broken():
            raise OSError("registry is locked down")
        self.assertEqual(
            appearance.system_theme(platform="win32", environ={}, windows_reader=broken),
            appearance.THEME_LIGHT,
        )

    def test_macos_reads_the_interface_style(self):
        dark = lambda *_a, **_k: SimpleNamespace(stdout="Dark\n")
        light = lambda *_a, **_k: SimpleNamespace(stdout="")
        self.assertEqual(appearance.system_theme(platform="darwin", environ={}, runner=dark), appearance.THEME_DARK)
        self.assertEqual(appearance.system_theme(platform="darwin", environ={}, runner=light), appearance.THEME_LIGHT)

    def test_linux_reads_the_color_scheme_then_the_theme(self):
        def runner(command, **_kwargs):
            if "color-scheme" in command:
                return SimpleNamespace(stdout="'prefer-dark'\n")
            return SimpleNamespace(stdout="'Adwaita'\n")
        self.assertEqual(appearance.system_theme(platform="linux", environ={}, runner=runner), appearance.THEME_DARK)

        def dark_theme(command, **_kwargs):
            if "gtk-theme" in command:
                return SimpleNamespace(stdout="'Adwaita-dark'\n")
            return SimpleNamespace(stdout="'default'\n")
        self.assertEqual(appearance.system_theme(platform="linux", environ={}, runner=dark_theme), appearance.THEME_DARK)
        self.assertEqual(
            appearance.system_theme(platform="linux", environ={"GTK_THEME": "Adwaita:dark"}, runner=dark_theme),
            appearance.THEME_DARK,
        )
        self.assertEqual(
            appearance.system_theme(platform="linux", environ={}, runner=lambda *_a, **_k: SimpleNamespace(stdout="'default'\n")),
            appearance.THEME_LIGHT,
        )

    def test_the_desktop_answer_only_decides_when_the_user_asked_for_it(self):
        self.assertEqual(appearance.effective_theme("light", "dark"), appearance.THEME_LIGHT)
        self.assertEqual(appearance.effective_theme("dark", "light"), appearance.THEME_DARK)
        self.assertEqual(appearance.effective_theme("system", "dark"), appearance.THEME_DARK)
        self.assertEqual(appearance.effective_theme("system", "light"), appearance.THEME_LIGHT)
        # A desktop that answers with something odd still resolves to a theme.
        self.assertEqual(appearance.effective_theme("system", "sepia"), appearance.THEME_LIGHT)
        with patch.object(appearance, "system_theme", return_value="dark") as reader:
            self.assertEqual(appearance.effective_theme("system"), appearance.THEME_DARK)
            reader.assert_called_once_with()


class PaletteTests(unittest.TestCase):
    def test_both_themes_keep_every_text_pair_readable(self):
        for theme in ("light", "dark"):
            palette = accessibility.contrast_palette(False, theme)
            with self.subTest(theme=theme):
                for text in (palette["text"], palette["muted_text"], palette["title_text"]):
                    self.assertGreaterEqual(accessibility.contrast_ratio(text, palette["background"]), 4.5)
                    self.assertGreaterEqual(accessibility.contrast_ratio(text, palette["surface"]), 4.5)
                self.assertGreaterEqual(
                    accessibility.contrast_ratio(palette["accent_text"], palette["accent"]), 4.5
                )
                self.assertGreaterEqual(
                    accessibility.contrast_ratio(palette["accent_text"], palette["accent_active"]), 4.5
                )
                self.assertGreaterEqual(accessibility.contrast_ratio(palette["focus"], palette["background"]), 4.5)
                self.assertGreaterEqual(
                    accessibility.contrast_ratio(palette["selected_text"], palette["selected_background"]), 4.5
                )
                # A destructive action is marked by red text, so that text has
                # to clear the same bar as everything else.
                self.assertGreaterEqual(
                    accessibility.contrast_ratio(palette["danger_text"], palette["surface"]), 4.5
                )

    def test_the_two_themes_are_really_different_and_flagged(self):
        light = accessibility.contrast_palette(False, "light")
        dark = accessibility.contrast_palette(False, "dark")
        self.assertFalse(light["dark"])
        self.assertTrue(dark["dark"])
        for key in ("background", "surface", "text", "accent", "border", "heading_background"):
            with self.subTest(key=key):
                self.assertNotEqual(light[key], dark[key])

    def test_high_contrast_wins_over_both_themes(self):
        for theme in ("light", "dark"):
            palette = accessibility.contrast_palette(True, theme)
            with self.subTest(theme=theme):
                self.assertEqual(palette["background"], accessibility.HIGH_CONTRAST_BACKGROUND)
                self.assertEqual(palette["text"], accessibility.HIGH_CONTRAST_TEXT)
                self.assertEqual(palette["field_background"], accessibility.HIGH_CONTRAST_FIELD_BACKGROUND)

    def test_an_unknown_theme_name_paints_the_light_palette(self):
        self.assertFalse(accessibility.contrast_palette(False, "sepia")["dark"])
        self.assertEqual(accessibility.contrast_palette(False, "sepia")["background"], accessibility.BACKGROUND)


class FontStackTests(unittest.TestCase):
    def test_each_platform_gets_its_own_order(self):
        self.assertEqual(accessibility.preferred_font_families("win32")[0], "Segoe UI")
        self.assertEqual(accessibility.preferred_font_families("darwin")[0], "SF Pro Text")
        self.assertEqual(accessibility.preferred_font_families("linux")[0], "Inter")

    def test_the_first_family_the_system_really_has_wins(self):
        available = ["DejaVu Sans", "Noto Sans", "sans-serif"]
        self.assertEqual(accessibility.choose_font_family(available, "linux"), "Noto Sans")
        self.assertEqual(accessibility.choose_font_family(["arial"], "win32"), "arial")
        self.assertEqual(accessibility.choose_font_family([], "linux", fallback="TkDefault"), "TkDefault")
        self.assertEqual(accessibility.choose_font_family(None, "linux"), "")


class ThemedStyleTests(unittest.TestCase):
    def apply(self, theme, high_contrast=False):
        style = RecordingStyle()
        accessible = accessibility.AccessibleStyle(style, FakeFontModule(), "Test Sans")
        accessible.apply(1.0, high_contrast=high_contrast, theme=theme)
        return style

    def test_a_dark_style_paints_surfaces_and_text_from_the_dark_palette(self):
        style = self.apply("dark")
        dark = accessibility.contrast_palette(False, "dark")
        self.assertEqual(style.options("TFrame")["background"], dark["background"])
        self.assertEqual(style.options("TLabel")["foreground"], dark["text"])
        self.assertEqual(style.options("Sub.TLabel")["foreground"], dark["muted_text"])
        self.assertEqual(style.options("Treeview")["fieldbackground"], dark["surface"])
        self.assertEqual(style.options("Treeview.Heading")["background"], dark["heading_background"])
        self.assertEqual(style.options("Accent.TButton")["background"], dark["accent"])
        self.assertIn(("selected", dark["selected_background"]), style.maps["Treeview"]["background"])

    def test_the_light_style_is_unchanged_by_the_new_option(self):
        style = self.apply("light")
        self.assertEqual(style.options("TFrame")["background"], accessibility.BACKGROUND)
        self.assertEqual(style.options("TLabel")["foreground"], accessibility.TEXT)

    def test_high_contrast_paints_black_even_when_the_theme_is_dark(self):
        style = self.apply("dark", high_contrast=True)
        self.assertEqual(style.options("TFrame")["background"], accessibility.HIGH_CONTRAST_BACKGROUND)
        self.assertEqual(style.options("TLabel")["foreground"], accessibility.HIGH_CONTRAST_TEXT)

    def test_the_quiet_and_destructive_buttons_keep_their_hierarchy(self):
        for theme in ("light", "dark"):
            style = self.apply(theme)
            palette = accessibility.contrast_palette(False, theme)
            with self.subTest(theme=theme):
                self.assertEqual(style.options("Quiet.TButton")["background"], palette["background"])
                self.assertEqual(style.options("Quiet.TButton")["foreground"], palette["muted_text"])
                self.assertEqual(style.options("Danger.TButton")["background"], palette["surface"])
                self.assertEqual(style.options("Danger.TButton")["foreground"], palette["danger_text"])
                for name in ("Quiet.TButton", "Danger.TButton"):
                    self.assertIn(("focus", palette["focus"]), style.maps[name]["focuscolor"])

    def test_no_style_inherits_clams_warm_greys(self):
        """Every colour a widget can inherit comes from the palette.

        clam paints anything it does not recognise with #dcdad5, #cfcdc8,
        #9e9a91 and #eeebe7, and it maps the notebook tab, the read-only
        combination field and the table heading itself. Those maps beat a
        plain configure call, which is why the window used to look dusty even
        though the palette was correct.
        """
        clam = {"#dcdad5", "#cfcdc8", "#9e9a91", "#eeebe7", "#bab5ab", "#e3dfd9"}
        for theme in ("light", "dark"):
            style = self.apply(theme)
            palette = accessibility.contrast_palette(False, theme)
            with self.subTest(theme=theme):
                defaults = style.options(".")
                self.assertEqual(defaults["background"], palette["background"])
                self.assertEqual(defaults["foreground"], palette["text"])
                self.assertEqual(defaults["bordercolor"], palette["border"])
                self.assertEqual(defaults["darkcolor"], palette["border"])
                self.assertEqual(defaults["troughcolor"], palette["trough_background"])
                for name, options in style.configurations.items():
                    for option, value in options.items():
                        if isinstance(value, str) and value.startswith("#"):
                            self.assertNotIn(value.lower(), clam, f"{name}.{option}")
                # The notebook tab and the read-only field are mapped, not just
                # configured, so the selected tab and the field really take the
                # surface colour in both themes.
                self.assertIn(("selected", palette["surface"]), style.maps["TNotebook.Tab"]["background"])
                self.assertIn(("", palette["background"]), style.maps["TNotebook.Tab"]["background"])
                self.assertEqual(
                    style.maps["TNotebook.Tab"]["background"][0], ("selected", palette["surface"])
                )
                for name in ("TEntry", "TCombobox", "TSpinbox"):
                    self.assertIn(
                        ("readonly", palette["field_background"]),
                        style.maps[name]["fieldbackground"],
                    )
                self.assertEqual(
                    style.options("Treeview.Heading")["lightcolor"], palette["heading_background"]
                )
                self.assertEqual(
                    style.options("Treeview.Heading")["darkcolor"], palette["heading_background"]
                )
                self.assertIn("TScrollbar", style.maps)

    def test_classic_widgets_follow_the_dark_theme(self):
        class Widget:
            def __init__(self, widget_class, **options):
                self.widget_class = widget_class
                self.options = dict(options)
                self.children = []

            def winfo_class(self):
                return self.widget_class

            def winfo_children(self):
                return self.children

            def configure(self, **options):
                self.options.update(options)

        root = Widget("Tk")
        label = Widget("Label")
        menu = Widget("Menu")
        root.children = [label, menu]
        accessibility.apply_widget_contrast(root, False, "dark")
        dark = accessibility.contrast_palette(False, "dark")
        self.assertEqual(label.options["background"], dark["background"])
        self.assertEqual(label.options["foreground"], dark["text"])
        self.assertEqual(menu.options["background"], dark["surface"])


class AppThemeTests(unittest.TestCase):
    """The window itself: palette, theme switch, geometry and column fitting."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.app = load_headless_app(self.workspace)
        self.addCleanup(self.close_handlers)

    def close_handlers(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()
        self.temporary.cleanup()

    def window(self, **extra):
        values = dict(
            _theme="light", _theme_setting="light", _high_contrast=False,
            _accessibility_style=Mock(), ui_font_scale=1.0, dpi_scale=1.0,
            tree=None, _header_backgrounds=[], winfo_children=lambda: [],
            configure=Mock(), after_idle=Mock(), after=Mock(),
        )
        values.update(extra)
        return SimpleNamespace(**values)

    def test_the_window_palette_follows_the_resolved_theme(self):
        dark = self.app.window_palette(SimpleNamespace(_theme="dark"))
        light = self.app.window_palette(SimpleNamespace(_theme="light"))
        self.assertEqual(dark["background"], accessibility.DARK_BACKGROUND)
        self.assertEqual(light["background"], accessibility.BACKGROUND)
        # A dialogue built on a double without theme attributes still paints.
        self.assertEqual(self.app.window_palette(SimpleNamespace())["background"], accessibility.BACKGROUND)

    def test_switching_to_dark_repaints_everything_and_saves_the_choice(self):
        fake = self.window()
        with patch.object(self.app, "set_setting") as save, patch.object(
            self.app, "refresh_json_journal"
        ), patch.object(self.app, "log_activity"):
            resolved = self.app.ReminderApp.set_theme(fake, "dark")

        self.assertEqual(resolved, "dark")
        self.assertEqual(fake._theme, "dark")
        self.assertEqual(fake._theme_setting, "dark")
        save.assert_called_once_with(self.app.appearance.THEME_SETTING, "dark")
        fake._accessibility_style.apply.assert_called_once_with(
            1.0, high_contrast=False, pixel_scale=1.0, theme="dark"
        )
        self.assertEqual(fake.configure.call_args.kwargs["bg"], accessibility.DARK_BACKGROUND)

    def test_follow_the_system_resolves_before_it_is_painted(self):
        fake = self.window()
        with patch.object(self.app, "set_setting"), patch.object(
            self.app, "refresh_json_journal"
        ), patch.object(self.app, "log_activity"), patch.object(
            self.app.appearance, "system_theme", return_value="dark"
        ):
            self.assertEqual(self.app.ReminderApp.set_theme(fake, "system"), "dark")
        self.assertEqual(fake._theme_setting, "system")
        self.assertEqual(fake._theme, "dark")
        self.assertEqual(fake.configure.call_args.kwargs["bg"], accessibility.DARK_BACKGROUND)

    def test_a_theme_can_be_changed_without_saving_it(self):
        fake = self.window()
        with patch.object(self.app, "set_setting") as save, patch.object(self.app, "log_activity"):
            self.app.ReminderApp.set_theme(fake, "Mörkt", persist=False)
        save.assert_not_called()
        self.assertEqual(fake._theme, "dark")

    def test_the_open_windows_and_menus_are_repainted_together(self):
        dialog = Mock()
        dialog.winfo_class.return_value = "Toplevel"
        fake = self.window(
            winfo_children=lambda: [dialog],
            main_menu=Mock(), file_menu=Mock(), help_menu=Mock(), row_menu=Mock(),
        )
        with patch.object(self.app, "set_setting"), patch.object(
            self.app, "refresh_json_journal"
        ), patch.object(self.app, "log_activity"), patch.object(
            self.app, "apply_widget_contrast"
        ) as repaint:
            self.app.ReminderApp.set_theme(fake, "dark", persist=False)

        self.assertEqual(dialog.configure.call_args.kwargs["bg"], accessibility.DARK_BACKGROUND)
        windows = [call.args[0] for call in repaint.call_args_list]
        self.assertIn(dialog, windows)
        self.assertIn(fake.main_menu, windows)
        for call in repaint.call_args_list:
            self.assertEqual(call.args[2], "dark")

    def test_invoice_rows_use_deep_tints_in_the_dark_theme(self):
        class FakeTree:
            def __init__(self):
                self.tags = {}

            def tag_configure(self, tag, **options):
                self.tags[tag] = options

        tree = FakeTree()
        self.app.configure_invoice_row_colors(tree, theme="dark")
        self.assertEqual(tree.tags, {
            tag: {"background": background, "foreground": accessibility.DARK_TEXT}
            for tag, background in self.app.INVOICE_ROW_COLORS_DARK.items()
        })
        self.assertNotEqual(
            self.app.INVOICE_ROW_COLORS_DARK["status-p2"],
            self.app.INVOICE_ROW_COLORS["status-p2"],
        )

    def geometry(self, screen, area, scale=1.0):
        fake = SimpleNamespace(
            dpi_scale=scale,
            winfo_screenwidth=lambda: screen[0],
            winfo_screenheight=lambda: screen[1],
            geometry=Mock(),
            minsize=Mock(),
        )
        with patch.object(self.app, "monitor_work_area", return_value=area):
            self.app.ReminderApp._apply_initial_main_geometry(fake)
        geometry = fake.geometry.call_args.args[0]
        size, x, y = geometry.replace("+", " +").split(" +")
        width, height = (int(value) for value in size.split("x"))
        return width, height, int(x), int(y), fake.minsize.call_args.args

    def test_a_wide_screen_is_actually_used(self):
        width, height, x, y, minimum = self.geometry((2560, 1440), (0, 0, 2560, 1400))
        self.assertGreater(width, 2000)
        self.assertGreater(height, 1100)
        self.assertLessEqual(width, 2560 - 48)
        self.assertLessEqual(height, 1400 - 48)
        self.assertGreater(x, 0)
        self.assertGreater(y, 0)
        self.assertLessEqual(minimum[0], width)
        self.assertLessEqual(minimum[1], height)

    def test_the_window_never_opens_under_the_taskbar_or_off_screen(self):
        area = (1920, 40, 1920, 1000)
        width, height, x, y, _minimum = self.geometry((1920, 1080), area)
        self.assertLessEqual(width, 1920 - 48)
        self.assertLessEqual(height, 1000 - 48)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 40)

    def test_a_small_screen_still_gets_a_usable_window(self):
        width, height, _x, _y, minimum = self.geometry((1024, 700), (0, 0, 1024, 700))
        self.assertGreaterEqual(width, 720)
        self.assertLessEqual(width, 1024)
        self.assertGreaterEqual(height, 480)
        self.assertLessEqual(height, 700)
        # The minimum can never be larger than the window it belongs to.
        self.assertLessEqual(minimum[0], width)
        self.assertLessEqual(minimum[1], height)

    def test_a_high_dpi_screen_scales_the_floor_but_not_beyond_the_screen(self):
        width, height, _x, _y, minimum = self.geometry((1920, 1080), (0, 0, 1920, 1040), scale=1.5)
        self.assertLessEqual(width, 1920)
        self.assertLessEqual(height, 1040)
        self.assertLessEqual(minimum[0], width)


class InvoiceColumnFitTests(unittest.TestCase):
    """The table uses the width it is given instead of ending mid-screen."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))
        self.addCleanup(self.close_handlers)

    def close_handlers(self):
        for handler in self.app.logger.handlers[:]:
            self.app.logger.removeHandler(handler)
            handler.close()
        self.temporary.cleanup()

    class Tree:
        def __init__(self, width=0):
            self.width = width
            self.columns = {}

        def winfo_width(self):
            return self.width

        def column(self, column, **options):
            if "width" in options:
                self.columns[column] = options["width"]
            return self.columns.get(column, 0)

    def owner(self, tree, widths=None):
        return SimpleNamespace(
            tree=tree,
            _invoice_column_widths=widths or {
                "invoice_no": 110, "customer": 170, "due_date": 105, "amount": 115,
                "remaining": 120, "p1_date": 105, "p2_send_date": 125,
                "email_status": 190, "stage": 180, "fee": 120,
            },
            _px=lambda value: value,
            after_idle=lambda callback: callback(),
            after=Mock(),
        )

    def test_extra_width_goes_to_the_text_columns_only(self):
        tree = self.Tree()
        owner = self.owner(tree)
        fitted = self.app.ReminderApp._fit_invoice_columns(owner, 2000)

        self.assertEqual(sum(fitted.values()), 2000)
        base = owner._invoice_column_widths
        self.assertGreater(fitted["customer"], base["customer"])
        self.assertGreater(fitted["stage"], base["stage"])
        self.assertGreater(fitted["email_status"], base["email_status"])
        for fixed in ("invoice_no", "due_date", "amount", "remaining", "p1_date", "p2_send_date", "fee"):
            with self.subTest(column=fixed):
                self.assertEqual(fitted[fixed], base[fixed])
        # What was asked for is what the table got.
        self.assertEqual(tree.columns, fitted)

    def test_a_narrow_window_keeps_the_readable_base_widths(self):
        tree = self.Tree()
        owner = self.owner(tree)
        fitted = self.app.ReminderApp._fit_invoice_columns(owner, 900)
        self.assertEqual(fitted, owner._invoice_column_widths)
        self.assertEqual(sum(fitted.values()), 1340)

    def test_an_unmeasured_window_changes_nothing(self):
        tree = self.Tree(width=0)
        owner = self.owner(tree)
        self.assertEqual(self.app.ReminderApp._fit_invoice_columns(owner), {})
        self.assertEqual(tree.columns, {})

    def test_the_configure_event_refits_only_when_the_width_changed(self):
        tree = self.Tree(width=1600)
        owner = self.owner(tree)
        job = []
        owner.after_idle = lambda callback: job.append(callback)
        event = SimpleNamespace(width=1600)
        with patch.object(self.app, "log_activity"):
            self.app.ReminderApp._on_invoice_tree_configure(owner, event)
        self.assertEqual(len(job), 1)
        job[0]()
        self.assertEqual(sum(tree.columns.values()), 1600)

        # The same width again does not queue another layout pass.
        self.app.ReminderApp._on_invoice_tree_configure(owner, event)
        self.assertEqual(len(job), 1)

        # A new width does.
        tree.width = 1800
        self.app.ReminderApp._on_invoice_tree_configure(owner, SimpleNamespace(width=1800))
        self.assertEqual(len(job), 2)


if __name__ == "__main__":
    unittest.main()
