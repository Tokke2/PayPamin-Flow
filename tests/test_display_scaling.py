import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_database import load_headless_app


class RecordingStyle:
    """Record ttk style options the way the real Style object accepts them."""

    def __init__(self):
        self.configurations = {}
        self.maps = {}

    def configure(self, name, **options):
        self.configurations.setdefault(name, {}).update(options)

    def map(self, name, **options):
        self.maps.setdefault(name, {}).update(options)

    def options(self, name):
        return self.configurations[name]


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


class DisplayScaleTests(unittest.TestCase):
    """The UI must scale once, from the real display DPI, and never twice."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))
        self.addCleanup(self.temporary.cleanup)

    def scale_for(self, dpi):
        fake = SimpleNamespace(winfo_fpixels=Mock(return_value=dpi))
        return self.app.ReminderApp._display_scale(fake)

    def test_96_dpi_is_the_design_grid(self):
        self.assertEqual(self.scale_for(96), 1.0)

    def test_windows_scaling_levels_map_to_physical_pixel_factors(self):
        for dpi, expected in ((120, 1.25), (144, 1.5), (168, 1.75), (192, 2.0)):
            with self.subTest(dpi=dpi):
                self.assertEqual(self.scale_for(dpi), expected)

    def test_unmeasurable_or_absurd_dpi_falls_back_to_one(self):
        for dpi in (0, -1, "wide"):
            with self.subTest(dpi=dpi):
                self.assertEqual(self.scale_for(dpi), 1.0)
        fake = SimpleNamespace(winfo_fpixels=Mock(side_effect=RuntimeError("no display")))
        self.assertEqual(self.app.ReminderApp._display_scale(fake), 1.0)
        self.assertEqual(self.scale_for(960), 4.0)

    def test_pixel_helper_scales_design_pixels_by_display_and_text_zoom(self):
        fake = SimpleNamespace(dpi_scale=2.0, ui_font_scale=1.5)
        self.assertEqual(self.app.ReminderApp._px(fake, 40), 120)
        fake = SimpleNamespace(dpi_scale=1.25, ui_font_scale=0.8)
        self.assertEqual(self.app.ReminderApp._px(fake, 40), 40)
        fake = SimpleNamespace()
        self.assertEqual(self.app.ReminderApp._px(fake, 40), 40)
        self.assertEqual(self.app.ReminderApp._px(fake, 0), 1)

    def test_style_apply_receives_the_display_scale_but_points_do_not(self):
        style = RecordingStyle()
        accessible = self.app.AccessibleStyle(style, FakeFontModule(), "Test Sans")
        accessible.apply(1.0, pixel_scale=1.5)
        # A pixel metric follows the display: 10 px * 1.5.
        self.assertEqual(style.options("TButton")["padding"], (15, 10))
        # A point size does not: Tk already applies the screen DPI to points.
        self.assertEqual(style.options("TLabel")["font"], ("Test Sans", 10))
        accessible.apply(1.5, pixel_scale=1.0)
        self.assertEqual(style.options("TLabel")["font"], ("Test Sans", 15))


class UiLivenessTests(unittest.TestCase):
    """Background work must stop cleanly when the window is closing."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))
        self.addCleanup(self.temporary.cleanup)

    def test_plain_objects_count_as_alive_so_logic_stays_testable(self):
        self.assertTrue(self.app.ui_is_alive(SimpleNamespace()))

    def test_destroyed_window_is_dead(self):
        self.assertFalse(self.app.ui_is_alive(SimpleNamespace(winfo_exists=lambda: 0)))
        self.assertFalse(self.app.ui_is_alive(SimpleNamespace(winfo_exists=Mock(side_effect=RuntimeError))))

    def test_quitting_application_is_dead_even_before_the_widget_goes(self):
        fake = SimpleNamespace(winfo_exists=lambda: 1, _quitting=True)
        self.assertFalse(self.app.ui_is_alive(fake))

    def test_refresh_skips_a_destroyed_window_instead_of_raising(self):
        class Tree:
            def get_children(self):
                raise AssertionError("a destroyed tree must not be touched")

        fake = SimpleNamespace(winfo_exists=lambda: 0, tree=Tree())
        self.app.ReminderApp.refresh(fake)

    def test_import_scan_is_skipped_when_the_window_is_closing(self):
        fake = SimpleNamespace(winfo_exists=lambda: 0, _import_scan_running=False)
        self.app.ReminderApp.scan_import_folder(fake)
        self.assertFalse(fake._import_scan_running)

    def test_scheduled_scan_stops_rescheduling_after_the_window_closed(self):
        fake = SimpleNamespace(
            winfo_exists=lambda: 0, _quitting=False, _python_addons_ready=False,
            _import_scan_running=False, after=Mock(),
        )
        self.app.ReminderApp._run_scheduled_import_scan(fake)
        fake.after.assert_not_called()


class QuitConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = load_headless_app(Path(self.temporary.name))
        self.addCleanup(self.temporary.cleanup)

    def test_declining_the_question_keeps_the_app_running(self):
        fake = SimpleNamespace(quit_app=Mock())
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=False) as ask:
            self.app.ReminderApp.confirm_quit(fake)
        self.assertTrue(ask.called)
        fake.quit_app.assert_not_called()

    def test_confirming_the_question_quits_completely(self):
        fake = SimpleNamespace(quit_app=Mock())
        with patch.object(self.app.messagebox, "askyesno", create=True, return_value=True):
            self.app.ReminderApp.confirm_quit(fake)
        fake.quit_app.assert_called_once_with()

    def test_footer_defaults_follow_the_saved_settings_and_never_drift(self):
        fake = SimpleNamespace()
        values = {"p1_days": "7", "p2_days": "9", "p3_days": "11"}
        with patch.object(self.app, "setting", side_effect=values.get):
            text = self.app.ReminderApp._defaults_summary_text(fake)
        self.assertIn("+7 dagar", text)
        self.assertIn("+9 dagar", text)
        self.assertIn("+11 dagar", text)
        self.assertIn(self.app.money(self.app.REMINDER_FEE_CAP), text)
        self.assertIn(self.app.money(self.app.LATE_PAYMENT_COMPENSATION), text)
        # The footer states no interest at all.
        self.assertNotIn("ränta", text.casefold())
        self.assertNotIn("interest", text.casefold())
        self.assertNotIn("%", text)
        with patch.object(self.app, "setting", return_value=""):
            fallback = self.app.ReminderApp._defaults_summary_text(fake)
        self.assertIn("+5 dagar", fallback)

    def test_the_foot_bar_shows_both_hide_and_quit(self):
        source = (Path(__file__).resolve().parents[1] / "paypamin_flow.py").read_text(encoding="utf-8")
        self.assertIn("self.confirm_quit", source)
        self.assertIn("self.hide_to_tray", source)
        self.assertIn("Avsluta helt", source)
        # Two rows: the defaults summary must never be squeezed by the buttons.
        self.assertIn("_footer_summary=summary", source)


if __name__ == "__main__":
    unittest.main()
