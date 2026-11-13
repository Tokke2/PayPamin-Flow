"""Keyboard, focus, contrast and scalable-text helpers for PayPamin Flow.

The module deliberately has no Tkinter imports.  Application objects are passed
in, which keeps the behavior testable without a display and avoids any native
accessibility dependency.  Standard Tk widget text remains the accessible name;
these helpers make every action reachable and visible from the keyboard.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys

FONT_SCALE_SETTING = "ui_font_scale"
FONT_SCALE_MIN = 0.8
FONT_SCALE_MAX = 2.0
FONT_SCALE_CHOICES = (0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)

BACKGROUND = "#F3F5F8"
TEXT = "#1F2A3D"
MUTED_TEXT = "#475467"
# The UI ink is the exact navy of the brand mark (#0B2447), and the pressed
# state goes one step darker (#06152C), so a button, a heading and the icon
# read as one design instead of three slightly different dark blues.
TITLE_TEXT = "#0B2447"
ACCENT = "#0B2447"
ACCENT_ACTIVE = "#06152C"
FOCUS = "#005A9C"
FOCUS_BACKGROUND = "#DCEAFF"
SELECTED_BACKGROUND = "#C7DDF5"
SELECTED_TEXT = "#102A43"
FIELD_BACKGROUND = "#FFFFFF"
CLASSIC_FOCUS_BACKGROUND = "#B8C4D2"
CANVAS_BACKGROUND = "#E4E9F0"

# A deliberate, platform-independent high-contrast palette.  It is used when
# the operating system reports that high contrast is enabled; normal app
# colors remain unchanged otherwise.
HIGH_CONTRAST_BACKGROUND = "#000000"
HIGH_CONTRAST_TEXT = "#FFFFFF"
HIGH_CONTRAST_MUTED_TEXT = "#FFFFFF"
HIGH_CONTRAST_TITLE_TEXT = "#FFFFFF"
HIGH_CONTRAST_ACCENT = "#000080"
HIGH_CONTRAST_ACCENT_ACTIVE = "#000000"
HIGH_CONTRAST_FOCUS = "#FFFF00"
HIGH_CONTRAST_FOCUS_BACKGROUND = "#000000"
HIGH_CONTRAST_SELECTED_BACKGROUND = "#000080"
HIGH_CONTRAST_SELECTED_TEXT = "#FFFFFF"
HIGH_CONTRAST_FIELD_BACKGROUND = "#000000"
HIGH_CONTRAST_CLASSIC_FOCUS_BACKGROUND = "#808080"
HIGH_CONTRAST_CANVAS_BACKGROUND = "#000000"
SYSTEM_CONTRAST_POLL_INTERVAL_MS = 5000

NAMED_FONTS = (
    "TkDefaultFont",
    "TkTextFont",
    "TkMenuFont",
    "TkHeadingFont",
    "TkFixedFont",
    "TkTooltipFont",
)

FOCUSABLE_CLASSES = frozenset({
    "Button", "TButton", "Entry", "TEntry", "Combobox", "TCombobox",
    "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton",
    "Spinbox", "TSpinbox", "Listbox", "Treeview", "Text", "Canvas",
    "Scale", "TScale", "Notebook", "TNotebook",
})
CLASSIC_FOCUS_CLASSES = frozenset({
    "Button", "Entry", "Checkbutton", "Radiobutton", "Spinbox",
    "Listbox", "Text", "Canvas", "Scale",
})


def normalize_font_scale(value, default: float = 1.0) -> float:
    """Return a finite, bounded scale; accept stored numbers and percentages."""
    try:
        if isinstance(value, str):
            text = value.strip().replace(",", ".")
            is_percent = text.endswith("%")
            number = float(text.rstrip("%").strip())
            if is_percent or number > 10:
                number /= 100.0
        else:
            number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite font scale")
    except (TypeError, ValueError):
        number = float(default)
    return round(min(FONT_SCALE_MAX, max(FONT_SCALE_MIN, number)), 2)


def stepped_font_scale(current, direction: int) -> float:
    """Move through the same choices offered in Settings, with clamped ends."""
    scale = normalize_font_scale(current)
    if direction > 0:
        return next((choice for choice in FONT_SCALE_CHOICES if choice > scale + 0.001), FONT_SCALE_MAX)
    if direction < 0:
        return next((choice for choice in reversed(FONT_SCALE_CHOICES) if choice < scale - 0.001), FONT_SCALE_MIN)
    return scale


def font_scale_label(value) -> str:
    return f"{round(normalize_font_scale(value) * 100):d} %"


def font_scale_storage(value) -> str:
    return f"{normalize_font_scale(value):.2f}".rstrip("0").rstrip(".")


def scaled_number(value, scale, *, minimum: int = 1) -> int:
    """Scale point/pixel sizes without compounding and preserve Tk's negative sizes."""
    number = int(round(abs(float(value)) * normalize_font_scale(scale)))
    number = max(minimum, number)
    return -number if float(value) < 0 else number


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError("Expected a six-digit RGB color")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def contrast_ratio(first: str, second: str) -> float:
    """Return WCAG relative-luminance contrast for two #RRGGBB colors."""
    def luminance(color):
        channels = []
        for channel in _rgb(color):
            normalized = channel / 255.0
            channels.append(normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def contrast_palette(high_contrast=False):
    """Return one complete UI palette, including classic Tk widget colors."""
    if high_contrast:
        return {
            "background": HIGH_CONTRAST_BACKGROUND,
            "text": HIGH_CONTRAST_TEXT,
            "muted_text": HIGH_CONTRAST_MUTED_TEXT,
            "title_text": HIGH_CONTRAST_TITLE_TEXT,
            "accent": HIGH_CONTRAST_ACCENT,
            "accent_active": HIGH_CONTRAST_ACCENT_ACTIVE,
            "focus": HIGH_CONTRAST_FOCUS,
            "focus_background": HIGH_CONTRAST_FOCUS_BACKGROUND,
            "selected_background": HIGH_CONTRAST_SELECTED_BACKGROUND,
            "selected_text": HIGH_CONTRAST_SELECTED_TEXT,
            "field_background": HIGH_CONTRAST_FIELD_BACKGROUND,
            "classic_focus_background": HIGH_CONTRAST_CLASSIC_FOCUS_BACKGROUND,
            "canvas_background": HIGH_CONTRAST_CANVAS_BACKGROUND,
            "heading_background": HIGH_CONTRAST_BACKGROUND,
            "heading_text": HIGH_CONTRAST_TEXT,
            "trough_background": HIGH_CONTRAST_BACKGROUND,
        }
    return {
        "background": BACKGROUND,
        "text": TEXT,
        "muted_text": MUTED_TEXT,
        "title_text": TITLE_TEXT,
        "accent": ACCENT,
        "accent_active": ACCENT_ACTIVE,
        "focus": FOCUS,
        "focus_background": FOCUS_BACKGROUND,
        "selected_background": SELECTED_BACKGROUND,
        "selected_text": SELECTED_TEXT,
        "field_background": FIELD_BACKGROUND,
        "classic_focus_background": CLASSIC_FOCUS_BACKGROUND,
        "canvas_background": CANVAS_BACKGROUND,
        "heading_background": "#E3E9F2",
        "heading_text": "#0B2447",
        "trough_background": "#E6EBF3",
    }


def _setting_output(command, runner=None):
    """Read a desktop setting without a shell or a persistent subprocess."""
    try:
        result = (runner or subprocess.run)(
            command, capture_output=True, text=True, timeout=1, check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    return str(getattr(result, "stdout", "") or "").strip()


def _enabled_setting(value):
    return str(value).strip().strip("'\"").casefold() in {"1", "true", "yes", "on", "enabled"}


def _windows_high_contrast():
    """Query Windows itself; no registry or third-party package is required."""
    try:
        import ctypes
        from ctypes import wintypes

        class HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwFlags", wintypes.DWORD),
                ("lpszDefaultScheme", wintypes.LPWSTR),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        info = HIGHCONTRASTW()
        info.cbSize = ctypes.sizeof(info)
        # SPI_GETHIGHCONTRAST and HCF_HIGHCONTRASTON from the Windows SDK.
        if not user32.SystemParametersInfoW(0x0042, info.cbSize, ctypes.byref(info), 0):
            return False
        return bool(info.dwFlags & 0x0001)
    except Exception:
        return False


def system_high_contrast(platform=None, environ=None, runner=None):
    """Return whether the current desktop requests high-contrast UI.

    The optional arguments make platform detection deterministic in tests.  A
    failed or unavailable desktop query deliberately falls back to the normal
    palette rather than preventing the app from starting.
    """
    platform = str(platform or sys.platform).casefold()
    environ = os.environ if environ is None else environ
    if platform.startswith("win"):
        return _windows_high_contrast()
    if platform == "darwin":
        if runner is None:
            try:
                from AppKit import NSWorkspace
                return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldIncreaseContrast())
            except Exception:
                pass
        output = _setting_output(
            ["/usr/bin/defaults", "read", "NSGlobalDomain", "accessibilityDisplayShouldIncreaseContrast"],
            runner,
        )
        return _enabled_setting(output)
    theme = str(environ.get("GTK_THEME", "") or "")
    if "highcontrast" in theme.casefold().replace(" ", ""):
        return True
    output = _setting_output(
        ["gsettings", "get", "org.gnome.desktop.a11y.interface", "high-contrast"], runner,
    )
    if _enabled_setting(output):
        return True
    # Some GTK desktops expose the choice as a theme rather than the a11y key.
    theme_output = _setting_output(
        ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"], runner,
    )
    return "highcontrast" in theme_output.casefold().replace(" ", "")


class AccessibleStyle:
    """Own fixed base sizes so repeated zoom operations never compound."""

    def __init__(self, style, font_module, font_family: str | None = None):
        self.style = style
        self.fonts = {}
        self.base_sizes = {}
        for name in NAMED_FONTS:
            try:
                font = font_module.nametofont(name)
                self.fonts[name] = font
                self.base_sizes[name] = int(font.cget("size"))
            except Exception:
                # A minimal/embedded Tk can lack an optional named font.
                continue
        if font_family:
            self.font_family = font_family
        elif "TkDefaultFont" in self.fonts:
            self.font_family = self.fonts["TkDefaultFont"].cget("family")
        else:
            self.font_family = "TkDefaultFont"

    def apply(self, scale, high_contrast=False):
        scale = normalize_font_scale(scale)
        self.high_contrast = bool(high_contrast)
        palette = contrast_palette(self.high_contrast)
        for name, font in self.fonts.items():
            try:
                font.configure(size=scaled_number(self.base_sizes[name], scale))
            except Exception:
                continue
        size = lambda value: scaled_number(value, scale)
        font = lambda points, weight=None: (
            (self.font_family, size(points)) if weight is None
            else (self.font_family, size(points), weight)
        )
        configure = self.style.configure
        configure("TFrame", background=palette["background"])
        configure("TLabel", background=palette["background"], foreground=palette["text"], font=font(10))
        configure("Title.TLabel", background=palette["background"], foreground=palette["title_text"], font=font(19, "bold"))
        configure("Heading.TLabel", background=palette["background"], foreground=palette["text"], font=font(11, "bold"))
        configure("BodyBold.TLabel", background=palette["background"], foreground=palette["text"], font=font(9, "bold"))
        configure("Sub.TLabel", background=palette["background"], foreground=palette["muted_text"], font=font(9))
        configure(
            "TButton", font=font(9), padding=(size(10), size(7)),
            foreground=palette["text"], background=palette["field_background"],
            focusthickness=max(2, size(2)), focuscolor=palette["focus"],
        )
        configure(
            "Accent.TButton", background=palette["accent"], foreground="#FFFFFF",
            font=font(9, "bold"), padding=(size(10), size(7)),
            focusthickness=max(2, size(2)), focuscolor=palette["focus"],
        )
        for name in ("TEntry", "TCombobox", "TSpinbox"):
            configure(
                name, font=font(10), foreground=palette["text"], fieldbackground=palette["field_background"],
                background=palette["field_background"], borderwidth=1,
                focusthickness=max(2, size(2)), focuscolor=palette["focus"],
            )
        configure("TCheckbutton", background=palette["background"], foreground=palette["text"], font=font(10), focuscolor=palette["focus"])
        configure("TRadiobutton", background=palette["background"], foreground=palette["text"], font=font(10), focuscolor=palette["focus"])
        configure(
            "Treeview", font=font(9), rowheight=size(30), background=palette["field_background"],
            fieldbackground=palette["field_background"], foreground=palette["text"], borderwidth=1,
            focusthickness=max(2, size(2)), focuscolor=palette["focus"],
        )
        configure(
            "Treeview.Heading", font=font(9, "bold"), background=palette["heading_background"],
            foreground=palette["heading_text"], focusthickness=max(2, size(2)), focuscolor=palette["focus"],
        )
        configure("TNotebook", background=palette["background"], borderwidth=0, focuscolor=palette["focus"])
        configure("TNotebook.Tab", font=font(9), padding=(size(10), size(6)), focuscolor=palette["focus"])
        configure("TProgressbar", background=palette["accent"], troughcolor=palette["trough_background"])
        configure("TScrollbar", background=palette["field_background"], troughcolor=palette["background"], arrowcolor=palette["text"])

        focus_map = {
            "focuscolor": [("focus", palette["focus"])],
            "bordercolor": [("focus", palette["focus"])],
            "lightcolor": [("focus", palette["focus"])],
            "darkcolor": [("focus", palette["focus"])],
        }
        for name in ("TButton", "Accent.TButton", "TEntry", "TCombobox", "TSpinbox", "TCheckbutton", "TRadiobutton", "Treeview"):
            self.style.map(name, **focus_map)
        self.style.map("Accent.TButton", background=[("active", palette["accent_active"]), ("pressed", palette["accent_active"]), ("focus", palette["accent_active"])])
        self.style.map("Treeview", background=[("selected", palette["selected_background"])], foreground=[("selected", palette["selected_text"])])
        self.style.map("TNotebook.Tab", background=[("focus", palette["focus_background"]), ("selected", palette["field_background"])], foreground=[("focus", palette["text"]), ("selected", palette["text"])])
        return scale


def _widget_class(widget) -> str:
    try:
        return str(widget.winfo_class())
    except Exception:
        return ""


def _children(widget):
    try:
        return tuple(widget.winfo_children())
    except Exception:
        return ()


def _configure_if_supported(widget, **options):
    for key, value in options.items():
        try:
            widget.configure(**{key: value})
        except Exception:
            # Classic Tk widgets expose different options across platforms.
            continue


def apply_widget_contrast(root, high_contrast=False):
    """Apply the same palette to classic Tk widgets and open menus.

    ttk widgets are styled by AccessibleStyle.  This companion handles the
    classic Label/Text/Canvas/Menu widgets that otherwise keep hard-coded
    colors when the desktop contrast mode changes.
    """
    palette = contrast_palette(high_contrast)

    def visit(widget):
        widget_class = _widget_class(widget)
        if widget is not root and widget_class in {"Tk", "Toplevel"}:
            return
        if widget_class in {"Tk", "Toplevel", "Frame", "Label", "Button", "Checkbutton", "Radiobutton", "Menubutton"}:
            _configure_if_supported(
                widget, background=palette["background"], foreground=palette["text"],
                activebackground=palette["focus_background"], activeforeground=palette["text"],
            )
        elif widget_class in {"Entry", "Spinbox", "Listbox", "Text"}:
            _configure_if_supported(
                widget, background=palette["field_background"], foreground=palette["text"],
                insertbackground=palette["text"], selectbackground=palette["selected_background"],
                selectforeground=palette["selected_text"], highlightcolor=palette["focus"],
                highlightbackground=palette["classic_focus_background"],
            )
        elif widget_class == "Canvas":
            _configure_if_supported(
                widget, background=palette["canvas_background"], highlightcolor=palette["focus"],
                highlightbackground=palette["classic_focus_background"],
            )
        elif widget_class == "Menu":
            _configure_if_supported(
                widget, background=palette["field_background"], foreground=palette["text"],
                activebackground=palette["selected_background"], activeforeground=palette["selected_text"],
                selectcolor=palette["selected_text"], disabledforeground=palette["muted_text"],
            )
        for child in _children(widget):
            visit(child)

    visit(root)
    try:
        root._accessibility_high_contrast = bool(high_contrast)
    except Exception:
        pass
    return palette


def monitor_work_area(window):
    """Return the usable desktop area as ``(left, top, width, height)``.

    On Windows the taskbar is excluded and the monitor containing the window is
    used, so a dialog on a small secondary screen is not sized for the primary
    one. Other platforms use Tk's reported screen size. The result is always in
    Tk's own pixel units; any failure falls back to the full screen.
    """
    try:
        screen_width = max(1, int(window.winfo_screenwidth()))
        screen_height = max(1, int(window.winfo_screenheight()))
    except Exception:
        return (0, 0, 0, 0)
    fallback = (0, 0, screen_width, screen_height)
    if not sys.platform.startswith("win"):
        return fallback
    try:
        import ctypes
        from ctypes import wintypes

        class _Rect(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG),
            ]

        class _MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        source = int(window.winfo_id())
        hwnd = int(user32.GetAncestor(source, 2) or 0) or source  # GA_ROOT
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return fallback
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return fallback
        # GetMonitorInfo reports physical pixels. Tk may report virtualized
        # pixels on a DPI-unaware build, so convert with the primary monitor.
        primary = _MonitorInfo()
        primary.cbSize = ctypes.sizeof(_MonitorInfo)
        primary_monitor = user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
        scale_x = scale_y = 1.0
        if primary_monitor and user32.GetMonitorInfoW(primary_monitor, ctypes.byref(primary)):
            primary_width = int(primary.rcMonitor.right) - int(primary.rcMonitor.left)
            primary_height = int(primary.rcMonitor.bottom) - int(primary.rcMonitor.top)
            if primary_width > 0 and primary_height > 0:
                scale_x = screen_width / primary_width
                scale_y = screen_height / primary_height
        left = int(round(int(info.rcWork.left) * scale_x))
        top = int(round(int(info.rcWork.top) * scale_y))
        width = int(round((int(info.rcWork.right) - int(info.rcWork.left)) * scale_x))
        height = int(round((int(info.rcWork.bottom) - int(info.rcWork.top)) * scale_y))
        if width < 240 or height < 200 or width > screen_width * 2 or height > screen_height * 2:
            return fallback
        return (left, top, width, height)
    except Exception:
        return fallback


def fit_window_to_screen(window, margin=24, min_width=360, min_height=240):
    """Make a dialog resizable and keep its requested geometry usable.

    The monitor work area (excluding the Windows taskbar) bounds the dialog, so
    every field stays reachable on small screens, secondary monitors and with
    200% text. ScrollableForm provides overflow for long forms. The main
    window's geometry and all application data are left untouched.
    """
    try:
        window.resizable(True, True)
        window.update_idletasks()
        screen_width = max(1, int(window.winfo_screenwidth()))
        screen_height = max(1, int(window.winfo_screenheight()))
        area_left, area_top, area_width, area_height = monitor_work_area(window)
        if area_width < 240 or area_height < 200:
            area_left, area_top = 0, 0
            area_width, area_height = screen_width, screen_height
        max_width = max(240, area_width - 2 * int(margin))
        max_height = max(200, area_height - 2 * int(margin))
        width = min(max(int(min_width), int(window.winfo_reqwidth())), max_width)
        height = min(max(int(min_height), int(window.winfo_reqheight())), max_height)
        minimum_width = min(int(min_width), max_width)
        minimum_height = min(int(min_height), max_height)
        window.minsize(minimum_width, minimum_height)
        try:
            x, y = int(window.winfo_x()), int(window.winfo_y())
        except Exception:
            x = y = 0
        if x <= 0 and y <= 0:
            x = area_left + max(0, (area_width - width) // 2)
            y = area_top + max(0, (area_height - height) // 2)
        x = min(max(area_left, x), max(area_left, area_left + area_width - width))
        y = min(max(area_top, y), max(area_top, area_top + area_height - height))
        window.geometry(f"{width}x{height}+{x}+{y}")
        return width, height
    except Exception:
        return None


class ResponsiveGrid:
    """Reflow a dialog form into as many columns as actually fit.

    The form is built once and only re-gridded when the available width
    changes, so no value is lost and nothing is ever hidden. Headings,
    check boxes and help texts keep the full width; label/field cells share a
    row when the dialogue is wide enough. Labels wrap and entries shrink, so
    the form never needs horizontal scrolling.
    """

    HEADING_GAP = 14
    MIN_LABEL_WRAP = 120

    def __init__(self, form, min_cell_width=250, max_columns=3, gap=18):
        self.form = form
        self.min_cell_width = max(120, int(min_cell_width))
        self.max_columns = max(1, int(max_columns))
        self.gap = max(0, int(gap))
        self.items = []
        self.columns = 0
        self.width = 0
        self.compact = False

    def add_heading(self, widget, pady=None):
        self.items.append({"kind": "heading", "widget": widget, "pady": pady})
        return widget

    def add_full(self, widget, pady=(2, 2)):
        self.items.append({"kind": "full", "widget": widget, "pady": pady})
        return widget

    def add_hint(self, widget, pady=(0, 0)):
        self.items.append({"kind": "hint", "widget": widget, "pady": pady})
        return widget

    def add_cell(self, widget, label=None, entry=None, pady=(2, 8)):
        self.items.append({
            "kind": "cell", "widget": widget, "label": label,
            "entry": entry, "pady": pady,
        })
        return widget

    @staticmethod
    def columns_for(width, min_cell_width=250, max_columns=3):
        """Return how many field columns fit into ``width`` pixels."""
        try:
            width = int(width)
        except (TypeError, ValueError):
            return 1
        if width <= 0:
            return 1
        return max(1, min(max(1, int(max_columns)), width // max(120, int(min_cell_width))))

    def _pady(self, item, row):
        pady = item["pady"]
        if pady is None:
            pady = (0 if row == 0 else self.HEADING_GAP, 6)
        pady = (int(pady[0]), int(pady[1]))
        if self.compact and item["kind"] in ("cell", "full", "hint"):
            pady = (max(0, pady[0] // 2), max(1, pady[1] // 2))
        return pady

    def _cell_width(self, columns, width):
        if columns <= 1 or width <= 0:
            return max(0, width)
        return max(0, (width - self.gap * (columns - 1)) // columns)

    def apply(self, width=None):
        """Lay the form out for ``width``; returns True when it changed."""
        try:
            width = int(width if width is not None else self.form.winfo_width())
        except Exception:
            width = 0
        columns = self.columns_for(width, self.min_cell_width, self.max_columns)
        if columns == self.columns and width == self.width:
            return False
        self.columns = columns
        self.width = width
        for column in range(self.max_columns):
            try:
                self.form.grid_columnconfigure(
                    column, weight=1 if column < columns else 0,
                )
            except Exception:
                pass
        cell_width = self._cell_width(columns, width)
        row = 0
        column = 0
        for item in self.items:
            widget = item["widget"]
            pady = self._pady(item, row)
            try:
                if item["kind"] == "cell":
                    widget.grid(
                        row=row, column=column, sticky="nw",
                        padx=(0, self.gap if column < columns - 1 else 0),
                        pady=pady,
                    )
                    column += 1
                    if column >= columns:
                        column = 0
                        row += 1
                else:
                    if column:
                        row += 1
                        column = 0
                    widget.grid(
                        row=row, column=0, columnspan=columns,
                        sticky="w", padx=0, pady=pady,
                    )
                    row += 1
            except Exception:
                continue
            self._resize_content(item, cell_width)
        return True

    def _resize_content(self, item, cell_width):
        if item["kind"] == "hint":
            if self.width > 0:
                try:
                    item["widget"].configure(
                        wraplength=max(self.MIN_LABEL_WRAP, self.width - 8),
                    )
                except Exception:
                    pass
            return
        if item["kind"] != "cell":
            return
        label = item.get("label")
        if label is not None and self.width > 0:
            try:
                label.configure(
                    wraplength=max(self.MIN_LABEL_WRAP, cell_width - 8),
                )
            except Exception:
                pass
        entry = item.get("entry")
        if entry is not None and cell_width > 0:
            try:
                entry.configure(width=max(8, min(16, (cell_width - 16) // 9)))
            except Exception:
                pass


class ScrollableForm:
    """A two-direction scrolling surface for a dialog's ordinary ttk form.

    The canvas itself is deliberately not in the Tab ring.  Form controls keep
    their normal keyboard behavior, while prepare_focus_tree reveals a focused
    control even when it is below or beside the visible viewport.
    """

    def __init__(self, window, tk_module, ttk_module, padding=20):
        self.window = window
        self.tk = tk_module
        self.ttk = ttk_module
        self.container = ttk_module.Frame(window)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        self.canvas = tk_module.Canvas(
            self.container, highlightthickness=0, borderwidth=0, takefocus=0,
        )
        self.vertical = ttk_module.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        self.horizontal = ttk_module.Scrollbar(self.container, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.horizontal.grid_remove()
        self.form = ttk_module.Frame(self.canvas, padding=padding)
        self.item = self.canvas.create_window((0, 0), window=self.form, anchor="nw")
        self.form._accessibility_scroll_canvas = self.canvas
        self.canvas._accessibility_scroll_form = self.form
        self.window._accessibility_scrollable_form = self
        self._syncing = False
        self.form.bind("<Configure>", self._content_changed, add="+")
        self.canvas.bind("<Configure>", self._canvas_changed, add="+")
        # The toplevel is the last stop in Tk's binding order, so the wheel
        # works over every field without stealing wheel handling from other
        # widgets. Only this form's own surface scrolls.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.window.bind(sequence, self._on_mousewheel, add="+")
            except Exception:
                continue
        self._content_changed()

    def fit_to_content(self, max_width=1100, max_height=800):
        """Request a canvas size that matches the content, capped to a maximum.

        The dialogue then opens at the size its content needs, and scrolling is
        only used for the part that genuinely does not fit.
        """
        self._content_changed()
        try:
            content_width = max(1, int(self.form.winfo_reqwidth()))
            content_height = max(1, int(self.form.winfo_reqheight()))
            self.canvas.configure(
                width=min(int(max_width), content_width),
                height=min(int(max_height), content_height),
            )
            return (
                min(int(max_width), content_width),
                min(int(max_height), content_height),
            )
        except Exception:
            return None

    def _owns(self, widget):
        """Return whether ``widget`` belongs to this form's scrolling surface."""
        try:
            current = widget
            while current is not None:
                if current is self.container or current is self.canvas or current is self.form:
                    return True
                current = getattr(current, "master", None)
        except Exception:
            return False
        return False

    def _on_mousewheel(self, event):
        """Scroll the form with the mouse wheel, trackpad and Linux buttons."""
        if not self._owns(getattr(event, "widget", None)):
            return None
        try:
            raw = self.canvas.cget("scrollregion")
            values = raw if isinstance(raw, (tuple, list)) else str(raw).split()
            if len(values) != 4:
                return None
            content_height = float(values[3]) - float(values[1])
            if content_height <= int(self.canvas.winfo_height()) + 1:
                return None
        except Exception:
            return None
        delta = getattr(event, "delta", 0) or 0
        number = getattr(event, "num", None)
        if delta:
            step = -1 if delta > 0 else 1
        elif number == 4:
            step = -1
        elif number == 5:
            step = 1
        else:
            return None
        try:
            self.canvas.yview_scroll(step * 3, "units")
        except Exception:
            return None
        return "break"

    def _content_changed(self, _event=None):
        if self._syncing:
            return
        self._syncing = True
        try:
            bounds = self.canvas.bbox("all")
            if bounds:
                self.canvas.configure(scrollregion=bounds)
            self._sync_horizontal_scrollbar()
        finally:
            self._syncing = False

    def _canvas_changed(self, event=None):
        try:
            viewport_width = int(getattr(event, "width", 0) or self.canvas.winfo_width())
            if viewport_width > 1:
                requested = max(viewport_width, int(self.form.winfo_reqwidth()))
                self.canvas.itemconfigure(self.item, width=requested)
        except Exception:
            pass
        self._content_changed()

    def _sync_horizontal_scrollbar(self):
        try:
            viewport_width = int(self.canvas.winfo_width())
            required_width = int(self.form.winfo_reqwidth())
            if viewport_width > 1 and required_width > viewport_width + 1:
                self.horizontal.grid()
            else:
                self.horizontal.grid_remove()
        except Exception:
            pass


def _visual_geometry(item):
    index, widget = item
    try:
        top = int(widget.winfo_rooty())
    except Exception:
        top = 0
    try:
        left = int(widget.winfo_rootx())
    except Exception:
        left = 0
    try:
        height = max(1, int(widget.winfo_height()))
    except Exception:
        height = 1
    return {"index": index, "widget": widget, "top": top, "bottom": top + height, "left": left}


def _visual_order(focusable):
    """Sort controls by visual rows, tolerating different heights in one row."""
    items = sorted(
        (_visual_geometry(item) for item in enumerate(focusable)),
        key=lambda item: (item["top"], item["left"], item["index"]),
    )
    rows = []
    for item in items:
        overlapping = []
        for row in rows:
            overlap = min(item["bottom"], row["bottom"]) - max(item["top"], row["top"])
            if overlap > 0:
                overlapping.append((overlap, row))
        if overlapping:
            row = max(overlapping, key=lambda candidate: candidate[0])[1]
            row["items"].append(item)
            row["top"] = min(row["top"], item["top"])
            row["bottom"] = max(row["bottom"], item["bottom"])
        else:
            rows.append({"top": item["top"], "bottom": item["bottom"], "items": [item]})
    ordered = []
    for row in sorted(rows, key=lambda value: (value["top"], min(item["left"] for item in value["items"]))):
        ordered.extend(sorted(row["items"], key=lambda item: (item["left"], item["index"])))
    return [item["widget"] for item in ordered]


def _usable_focus_widget(widget) -> bool:
    try:
        if not widget.winfo_exists() or not widget.winfo_ismapped():
            return False
    except Exception:
        return False
    try:
        if str(widget.cget("state")).lower() == "disabled":
            return False
    except Exception:
        pass
    try:
        takefocus = str(widget.cget("takefocus")).lower()
        if takefocus in {"0", "false", "no", "off"}:
            return False
    except Exception:
        pass
    return True


def _scroll_canvas_for(widget):
    parent = getattr(widget, "master", None)
    while parent is not None:
        canvas = getattr(parent, "_accessibility_scroll_canvas", None)
        if canvas is not None:
            return canvas
        parent = getattr(parent, "master", None)
    return None


def reveal_widget(widget):
    """Scroll a focused control into its dialog viewport when necessary."""
    canvas = _scroll_canvas_for(widget)
    if canvas is None:
        return
    try:
        canvas.update_idletasks()
        raw_region = canvas.cget("scrollregion")
        values = raw_region if isinstance(raw_region, (tuple, list)) else str(raw_region).split()
        region = [float(value) for value in values]
        if len(region) != 4:
            return
        for axis, viewport_size, widget_start, widget_end in (
            (
                "x", int(canvas.winfo_width()),
                canvas.canvasx(widget.winfo_rootx() - canvas.winfo_rootx()),
                canvas.canvasx(widget.winfo_rootx() - canvas.winfo_rootx() + widget.winfo_width()),
            ),
            (
                "y", int(canvas.winfo_height()),
                canvas.canvasy(widget.winfo_rooty() - canvas.winfo_rooty()),
                canvas.canvasy(widget.winfo_rooty() - canvas.winfo_rooty() + widget.winfo_height()),
            ),
        ):
            if viewport_size <= 1:
                continue
            region_start, region_end = (region[0], region[2]) if axis == "x" else (region[1], region[3])
            span = region_end - region_start
            if span <= viewport_size:
                continue
            visible_start = canvas.canvasx(0) if axis == "x" else canvas.canvasy(0)
            visible_end = visible_start + viewport_size
            destination = None
            if widget_start < visible_start:
                destination = widget_start - 12
            elif widget_end > visible_end:
                destination = widget_end - viewport_size + 12
            if destination is None:
                continue
            fraction = (destination - region_start) / span
            if axis == "x":
                canvas.xview_moveto(min(1.0, max(0.0, fraction)))
            else:
                canvas.yview_moveto(min(1.0, max(0.0, fraction)))
    except Exception:
        return


def _focus_and_reveal(widget):
    widget.focus_set()
    reveal_widget(widget)


def move_focus(widget, reverse: bool = False):
    """Move within the current top-level's visual order and keep Tab in the app."""
    try:
        root = widget.winfo_toplevel()
    except Exception:
        return "break"
    order = list(getattr(root, "_accessibility_focus_order", ()))
    if widget not in order:
        order = prepare_focus_tree(root)
    if not order:
        return "break"
    try:
        start = order.index(widget)
    except ValueError:
        start = -1 if not reverse else 0
    step = -1 if reverse else 1
    for offset in range(1, len(order) + 1):
        candidate = order[(start + step * offset) % len(order)]
        if candidate is widget or not _usable_focus_widget(candidate):
            continue
        try:
            _focus_and_reveal(candidate)
        except Exception:
            continue
        return "break"
    return "break"


def focus_first(root):
    """Focus the first usable widget in visual order; return it for testability."""
    order = prepare_focus_tree(root)
    for widget in order:
        if not _usable_focus_widget(widget):
            continue
        try:
            _focus_and_reveal(widget)
            return widget
        except Exception:
            continue
    return None


def _insert_text_tab(widget):
    try:
        widget.insert("insert", "\t")
    except Exception:
        pass
    return "break"


def prepare_focus_tree(root, high_contrast=None):
    """Apply visible classic-widget focus and logical Tab/Shift-Tab traversal.

    The order is based on mapped visual coordinates, so right-packed controls
    and grid dialogs follow what the user sees rather than incidental creation
    order.  Handlers are installed once and always consult the latest order.
    """
    if high_contrast is None:
        high_contrast = getattr(root, "_accessibility_high_contrast", False)
    palette = contrast_palette(high_contrast)
    try:
        root._accessibility_high_contrast = bool(high_contrast)
    except Exception:
        pass
    focusable = []

    def visit(widget):
        widget_class = _widget_class(widget)
        # A root's winfo_children includes its Toplevel dialogs.  Each dialog
        # gets its own traversal ring; never leak its controls into the parent.
        if widget is not root and widget_class in {"Tk", "Toplevel"}:
            return
        is_scroll_surface = widget_class == "Canvas" and getattr(widget, "_accessibility_scroll_form", None) is not None
        if widget_class in FOCUSABLE_CLASSES and not is_scroll_surface:
            try:
                widget.configure(takefocus=1)
            except Exception:
                pass
            focusable.append(widget)
        if widget_class in CLASSIC_FOCUS_CLASSES:
            try:
                widget.configure(
                    highlightthickness=2,
                    highlightcolor=palette["focus"],
                    highlightbackground=palette["classic_focus_background"],
                )
            except Exception:
                pass
        for child in _children(widget):
            visit(child)

    visit(root)
    order = _visual_order(focusable)
    try:
        root._accessibility_focus_order = order
    except Exception:
        return order
    for widget in order:
        if getattr(widget, "_accessibility_focus_bindings", False):
            continue
        installed = False
        for sequence, reverse in (("<Tab>", False), ("<ISO_Left_Tab>", True), ("<Shift-Tab>", True)):
            try:
                widget.bind(
                    sequence,
                    lambda _event, current=widget, backwards=reverse: move_focus(current, backwards),
                    add="+",
                )
                installed = True
            except Exception:
                continue
        try:
            widget.bind("<FocusIn>", lambda _event, current=widget: reveal_widget(current), add="+")
        except Exception:
            pass
        if _widget_class(widget) == "Text":
            try:
                widget.bind("<Control-Tab>", lambda _event, current=widget: _insert_text_tab(current), add="+")
            except Exception:
                pass
        if installed:
            try:
                widget._accessibility_focus_bindings = True
            except Exception:
                pass
    return order
