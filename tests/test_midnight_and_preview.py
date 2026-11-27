"""Clock-aware updates and bounded, directly rendered PDF previews."""
import ast
import math
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import accessibility
from update_checker import next_midnight_delay_ms


class MidnightTests(unittest.TestCase):
    def test_one_millisecond_before_midnight(self):
        self.assertEqual(next_midnight_delay_ms(datetime(2026, 11, 25, 23, 59, 59, 999000)), 1)

    def test_midnight_schedules_the_following_midnight(self):
        self.assertEqual(next_midnight_delay_ms(datetime(2026, 11, 25)), 24 * 60 * 60 * 1000)

    def test_end_of_year_rollover(self):
        self.assertEqual(next_midnight_delay_ms(datetime(2026, 12, 31, 23, 30)), 30 * 60 * 1000)

    def test_stockholm_spring_and_autumn_dst_days(self):
        try:
            zone = ZoneInfo("Europe/Stockholm")
        except ZoneInfoNotFoundError:
            self.skipTest("No IANA timezone database on this platform")
        self.assertEqual(next_midnight_delay_ms(datetime(2026, 3, 29, tzinfo=zone)), 23 * 60 * 60 * 1000)
        self.assertEqual(next_midnight_delay_ms(datetime(2026, 10, 25, tzinfo=zone)), 25 * 60 * 60 * 1000)


class PreviewScaleTests(unittest.TestCase):
    def test_small_viewports_fit_without_artificial_minimum_zoom(self):
        scale = accessibility.preview_raster_scale(600, 900, 180, 240)
        self.assertAlmostEqual(scale, 240 / 900)
        self.assertLessEqual(600 * scale, 180)
        self.assertLessEqual(900 * scale, 240)

    def test_dpi_pixels_and_zoom_increase_direct_render_resolution(self):
        normal = accessibility.preview_raster_scale(600, 900, 600, 900)
        hidpi = accessibility.preview_raster_scale(600, 900, 1200, 1800)
        zoomed = accessibility.preview_raster_scale(600, 900, 600, 900, 2)
        self.assertEqual(normal, 1)
        self.assertEqual(hidpi, 2)
        self.assertEqual(zoomed, hidpi)

    def test_huge_and_very_narrow_pages_stay_inside_pixel_and_axis_budgets(self):
        for width, height in ((600, 900), (1e6, 1e6), (10000, 1), (1, 10000), (123.4, 456.7)):
            with self.subTest(width=width, height=height):
                scale = accessibility.preview_raster_scale(width, height, 1e6, 1e6, 3)
                w, h = math.ceil(width * scale), math.ceil(height * scale)
                self.assertLessEqual(w * h, accessibility.MAX_PREVIEW_PIXELS)
                self.assertLessEqual(max(w, h), accessibility.MAX_PREVIEW_AXIS)

    def test_invalid_dimensions_never_reach_the_rasterizer(self):
        for bad in (0, -1, float("nan"), float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    accessibility.preview_raster_scale(bad, 900, 600, 900)


class PreviewRenderTests(unittest.TestCase):
    def environment(self):
        """Exercise the real nested callbacks without a native display."""
        tree = ast.parse((Path(__file__).resolve().parents[1] / "paypamin_flow.py").read_text(encoding="utf-8"))
        preview = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "preview_invoice")
        functions = [node for node in preview.body if isinstance(node, ast.FunctionDef) and node.name in {"render_page", "queue_render", "close_preview"}]
        pix = SimpleNamespace(width=600, height=900, tobytes=Mock(return_value=b"P6\n1 1\n255\n\xff\xff\xff"))
        page = SimpleNamespace(rect=SimpleNamespace(width=600, height=900), get_pixmap=Mock(return_value=pix))
        doc = Mock()
        doc.__getitem__ = Mock(return_value=page)
        doc.__len__ = Mock(return_value=1)
        canvas = Mock()
        canvas.winfo_width.return_value = 612
        canvas.winfo_height.return_value = 912
        win = Mock()
        win.after.return_value = "render-timer"
        state = dict(page=0, scale=1.0, zoom=1.0, photo=object(), image_w=1, image_h=1,
                     closed=False, render_job=None, render_key=None)
        env = dict(state=state, doc=doc, canvas=canvas, win=win,
                   self=SimpleNamespace(_px=lambda value: value, close_invoice_preview=Mock()),
                   fitz=SimpleNamespace(Matrix=lambda x, y: (x, y)),
                   tk=SimpleNamespace(PhotoImage=Mock(), TclError=RuntimeError),
                   zoom_var=Mock(), page_var=Mock(), draw_saved=Mock(), report_fault=Mock(),
                   preview_raster_scale=accessibility.preview_raster_scale,
                   _=lambda text, **values: text.format(**values))
        exec(compile(ast.Module(body=functions, type_ignores=[]), "preview_callbacks", "exec"), env)
        return env, page, pix

    def test_identical_render_reuses_image_but_refreshes_zone_overlays(self):
        env, page, pix = self.environment()
        env["render_page"]()
        env["render_page"]()
        page.get_pixmap.assert_called_once()
        env["draw_saved"].assert_has_calls([unittest.mock.call(), unittest.mock.call()])
        pix.tobytes.assert_called_once_with("ppm")
        env["tk"].PhotoImage.assert_called_once_with(data=pix.tobytes.return_value, format="PPM")

    def test_resize_replaces_pending_timer_and_new_size_rerenders(self):
        env, page, _ = self.environment()
        env["render_page"]()
        env["queue_render"]()
        env["queue_render"]()
        env["win"].after_cancel.assert_called_with("render-timer")
        env["canvas"].winfo_width.return_value = 312
        env["render_page"]()
        self.assertEqual(page.get_pixmap.call_count, 2)
        self.assertEqual(env["state"]["scale"], 0.5)

    def test_close_cancels_resize_and_releases_image_before_closing_pdf(self):
        env, page, _ = self.environment()
        env["queue_render"]()
        env["close_preview"]()
        env["win"].after_cancel.assert_called_once_with("render-timer")
        self.assertIsNone(env["state"]["photo"])
        self.assertIsNone(env["state"]["render_job"])
        env["self"].close_invoice_preview.assert_called_once_with(env["win"], env["doc"])
        env["render_page"]()
        env["queue_render"]()
        page.get_pixmap.assert_not_called()
