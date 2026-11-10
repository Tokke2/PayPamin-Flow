"""Real Tk integration tests for the accessibility layer.

These tests intentionally use actual widgets.  They are skipped on headless
machines without Tk/display; the Linux CI job runs them under Xvfb.
"""
import os
import sys
import unittest

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk
except Exception:  # pragma: no cover - exercised on minimal Python installs
    tk = None
    tkfont = None
    ttk = None

from accessibility import (
    AccessibleStyle,
    FOCUS,
    HIGH_CONTRAST_FIELD_BACKGROUND,
    HIGH_CONTRAST_FOCUS,
    HIGH_CONTRAST_TEXT,
    ResponsiveGrid,
    ScrollableForm,
    apply_widget_contrast,
    fit_window_to_screen,
    focus_first,
    monitor_work_area,
    move_focus,
    prepare_focus_tree,
    reveal_widget,
)


def _tk_display_available():
    if tk is None:
        return False
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
        return True
    except Exception:
        return False


TK_DISPLAY_AVAILABLE = _tk_display_available()


@unittest.skipUnless(TK_DISPLAY_AVAILABLE, "real Tk/display is not available")
class RealTkAccessibilityTests(unittest.TestCase):
    """Real widgets on one shared root.

    Tk is not designed for repeated interpreter creation in one process; on
    macOS that aborts the interpreter. One root for the class and one
    destroyed Toplevel per test keeps the suite stable on every platform.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("1000x800")
        cls.root.deiconify()
        cls.root.lift()
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.root.focus_force()
        self.root.update()
        self._dialogs = []

    def tearDown(self):
        for dialog in self._dialogs:
            try:
                dialog.destroy()
            except Exception:
                pass
        self._dialogs.clear()
        try:
            self.root.geometry("1000x800+0+0")
            self.root.update()
        except Exception:
            pass

    def track(self, dialog):
        self._dialogs.append(dialog)
        return dialog

    def test_real_widgets_follow_visual_tab_order_and_show_focus(self):
        dialog = self.track(tk.Toplevel(self.root))
        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True)
        first = ttk.Entry(frame)
        second = ttk.Button(frame, text="Next")
        text = tk.Text(frame, height=3)
        # Creation order deliberately differs from visual order.
        second.grid(row=0, column=1, padx=8, pady=8)
        first.grid(row=0, column=0, padx=8, pady=8)
        text.grid(row=1, column=0, columnspan=2, padx=8, pady=8)
        dialog.update()

        order = prepare_focus_tree(dialog)
        self.assertEqual(order, [first, second, text])
        focus_first(dialog)
        self.assertIs(dialog.focus_get(), first)
        move_focus(first)
        self.assertIs(dialog.focus_get(), second)
        self.assertEqual(text.cget("highlightcolor"), FOCUS)
        self.assertEqual(int(text.cget("highlightthickness")), 2)

    def test_real_two_hundred_percent_form_fits_and_reveals_last_field(self):
        style = AccessibleStyle(ttk.Style(self.root), tkfont)
        style.apply(2.0)
        dialog = self.track(tk.Toplevel(self.root))
        dialog.title("200 % accessibility test")
        surface = ScrollableForm(dialog, tk, ttk, padding=12)
        entries = []
        for index in range(50):
            ttk.Label(surface.form, text=f"Field {index + 1}").grid(
                row=index, column=0, sticky="w", padx=(0, 10), pady=4,
            )
            entry = ttk.Entry(surface.form, width=32)
            entry.grid(row=index, column=1, sticky="ew", pady=4)
            entries.append(entry)
        surface.form.columnconfigure(1, weight=1)
        dialog.update()
        fit_window_to_screen(dialog, min_width=320, min_height=200)
        dialog.update()

        self.assertEqual(tuple(bool(value) for value in dialog.resizable()), (True, True))
        self.assertLessEqual(dialog.winfo_width(), dialog.winfo_screenwidth())
        self.assertLessEqual(dialog.winfo_height(), dialog.winfo_screenheight())
        order = prepare_focus_tree(dialog)
        self.assertNotIn(surface.canvas, order)
        before = surface.canvas.yview()
        entries[-1].focus_set()
        reveal_widget(entries[-1])
        dialog.update()
        after = surface.canvas.yview()
        self.assertNotEqual(before, after)
        self.assertGreater(after[1], before[1])

    def test_real_mouse_wheel_scrolls_the_form_but_not_foreign_widgets(self):
        dialog = self.track(tk.Toplevel(self.root))
        surface = ScrollableForm(dialog, tk, ttk, padding=8)
        for index in range(60):
            ttk.Label(surface.form, text=f"Row {index + 1}").grid(
                row=index, column=0, sticky="w", pady=2,
            )
        dialog.geometry("420x260+40+40")
        dialog.update()

        target = surface.form.winfo_children()[5]
        before = surface.canvas.yview()
        target.event_generate("<Button-5>", x=2, y=2)
        dialog.update()
        after_scroll = surface.canvas.yview()
        self.assertGreater(after_scroll[0], before[0])

        surface.canvas.yview_moveto(1.0)
        dialog.update()
        at_bottom = surface.canvas.yview()
        target.event_generate("<Button-5>", x=2, y=2)
        dialog.update()
        self.assertEqual(surface.canvas.yview(), at_bottom)

        other = ttk.Frame()
        self.assertIsNone(surface._on_mousewheel(type("Event", (), {"widget": other, "delta": -120, "num": None})()))

    def test_real_work_area_is_a_usable_rectangle_inside_the_screen(self):
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        left, top, width, height = monitor_work_area(self.root)
        self.assertGreaterEqual(width, 240)
        self.assertGreaterEqual(height, 200)
        self.assertLessEqual(width, screen_width + 2)
        self.assertLessEqual(height, screen_height + 2)
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)

    def test_real_dialog_stays_inside_the_work_area_with_large_text(self):
        style = AccessibleStyle(ttk.Style(self.root), tkfont)
        style.apply(2.0)
        dialog = self.track(tk.Toplevel(self.root))
        surface = ScrollableForm(dialog, tk, ttk, padding=12)
        for index in range(40):
            ttk.Label(surface.form, text=f"Field {index + 1}").grid(
                row=index, column=0, sticky="w", pady=4,
            )
        dialog.update()
        fit_window_to_screen(dialog, min_width=320, min_height=200)
        dialog.update()
        left, top, width, height = monitor_work_area(dialog)
        self.assertLessEqual(dialog.winfo_y() + dialog.winfo_height(), top + height + 1)
        self.assertLessEqual(dialog.winfo_x() + dialog.winfo_width(), left + width + 1)

    def test_real_form_reflows_between_three_and_one_column_on_resize(self):
        dialog = self.track(tk.Toplevel(self.root))
        surface = ScrollableForm(dialog, tk, ttk, padding=8)
        form = surface.form
        grid = ResponsiveGrid(form)
        cells = []
        for index in range(6):
            frame = ttk.Frame(form)
            label = ttk.Label(frame, text=f"Field {index + 1}")
            label.grid(row=0, column=0, sticky="w")
            entry = ttk.Entry(frame, width=14)
            entry.grid(row=1, column=0, sticky="w")
            grid.add_cell(frame, label=label, entry=entry)
            cells.append(frame)
        dialog.geometry("960x420+40+40")
        dialog.update()
        grid.apply(940)
        dialog.update()

        self.assertEqual({cell.grid_info()["column"] for cell in cells}, {0, 1, 2})
        self.assertFalse(surface.horizontal.winfo_ismapped())

        dialog.geometry("420x420+40+40")
        dialog.update()
        grid.apply(390)
        dialog.update()

        self.assertEqual({cell.grid_info()["column"] for cell in cells}, {0})
        self.assertFalse(surface.horizontal.winfo_ismapped())
        for cell in cells:
            self.assertTrue(cell.winfo_ismapped())

    def test_real_fit_to_content_keeps_the_requested_size_inside_the_cap(self):
        dialog = self.track(tk.Toplevel(self.root))
        surface = ScrollableForm(dialog, tk, ttk, padding=8)
        for index in range(30):
            ttk.Label(surface.form, text=f"Row {index + 1}").grid(
                row=index, column=0, sticky="w", pady=2,
            )
        dialog.update()

        size = surface.fit_to_content(max_width=520, max_height=240)

        self.assertIsNotNone(size)
        self.assertLessEqual(size[0], 520)
        self.assertLessEqual(size[1], 240)
        self.assertLessEqual(int(surface.canvas.cget("width")), 520)
        self.assertLessEqual(int(surface.canvas.cget("height")), 240)

    def test_real_high_contrast_changes_ttk_and_classic_widgets(self):
        style = AccessibleStyle(ttk.Style(self.root), tkfont)
        style.apply(2.0, high_contrast=True)
        label = ttk.Label(self.root, text="High contrast")
        label.pack()
        text = tk.Text(self.root, height=3)
        text.pack()
        apply_widget_contrast(self.root, True)
        prepare_focus_tree(self.root, True)
        self.root.update()

        self.assertEqual(style.style.lookup("TLabel", "foreground").lower(), HIGH_CONTRAST_TEXT.lower())
        self.assertEqual(text.cget("background"), HIGH_CONTRAST_FIELD_BACKGROUND)
        self.assertEqual(text.cget("foreground"), HIGH_CONTRAST_TEXT)
        self.assertEqual(text.cget("highlightcolor"), HIGH_CONTRAST_FOCUS)

        style.apply(1.0, high_contrast=False)
        apply_widget_contrast(self.root, False)
        self.assertEqual(text.cget("background"), "#FFFFFF")
        self.assertEqual(text.cget("highlightcolor"), FOCUS)


if __name__ == "__main__":
    unittest.main()
