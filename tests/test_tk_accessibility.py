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
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("1000x800")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_real_widgets_follow_visual_tab_order_and_show_focus(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True)
        first = ttk.Entry(frame)
        second = ttk.Button(frame, text="Next")
        text = tk.Text(frame, height=3)
        # Creation order deliberately differs from visual order.
        second.grid(row=0, column=1, padx=8, pady=8)
        first.grid(row=0, column=0, padx=8, pady=8)
        text.grid(row=1, column=0, columnspan=2, padx=8, pady=8)
        self.root.update()

        order = prepare_focus_tree(self.root)
        self.assertEqual(order, [first, second, text])
        focus_first(self.root)
        self.assertIs(self.root.focus_get(), first)
        move_focus(first)
        self.assertIs(self.root.focus_get(), second)
        self.assertEqual(text.cget("highlightcolor"), FOCUS)
        self.assertEqual(int(text.cget("highlightthickness")), 2)

    def test_real_two_hundred_percent_form_fits_and_reveals_last_field(self):
        style = AccessibleStyle(ttk.Style(self.root), tkfont)
        style.apply(2.0)
        dialog = tk.Toplevel(self.root)
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
        surface = ScrollableForm(self.root, tk, ttk, padding=8)
        for index in range(60):
            ttk.Label(surface.form, text=f"Row {index + 1}").grid(
                row=index, column=0, sticky="w", pady=2,
            )
        self.root.update()
        surface.window.geometry("420x260+40+40")
        self.root.update()

        target = surface.form.winfo_children()[5]
        before = surface.canvas.yview()
        target.event_generate("<Button-5>", x=2, y=2)
        self.root.update()
        after_scroll = surface.canvas.yview()
        self.assertGreater(after_scroll[0], before[0])

        surface.canvas.yview_moveto(1.0)
        self.root.update()
        at_bottom = surface.canvas.yview()
        target.event_generate("<Button-5>", x=2, y=2)
        self.root.update()
        self.assertEqual(surface.canvas.yview(), at_bottom)

        other = ttk.Frame()
        self.assertIsNone(surface._on_mousewheel(type("Event", (), {"widget": other, "delta": -120, "num": None})()))

    def test_real_work_area_is_a_usable_rectangle_inside_the_screen(self):
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        left, top, width, height = monitor_work_area(self.root)
        self.assertGreaterEqual(width, 240)
        self.assertGreaterEqual(height, 200)
        self.assertLessEqual(width, screen_width + 1)
        self.assertLessEqual(height, screen_height + 1)
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)

    def test_real_dialog_stays_inside_the_work_area_with_large_text(self):
        style = AccessibleStyle(ttk.Style(self.root), tkfont)
        style.apply(2.0)
        dialog = tk.Toplevel(self.root)
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
