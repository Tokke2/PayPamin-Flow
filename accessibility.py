"""Keyboard, focus, contrast and scalable-text helpers for PayPamin Flow.

The module deliberately has no Tkinter imports.  Application objects are passed
in, which keeps the behavior testable without a display and avoids any native
accessibility dependency.  Standard Tk widget text remains the accessible name;
these helpers make every action reachable and visible from the keyboard.
"""
from __future__ import annotations

import math

FONT_SCALE_SETTING = "ui_font_scale"
FONT_SCALE_MIN = 0.8
FONT_SCALE_MAX = 2.0
FONT_SCALE_CHOICES = (0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)

BACKGROUND = "#F3F5F8"
TEXT = "#1F2A3D"
MUTED_TEXT = "#475467"
TITLE_TEXT = "#263A62"
ACCENT = "#304B79"
ACCENT_ACTIVE = "#263D64"
FOCUS = "#005A9C"
FOCUS_BACKGROUND = "#DCEAFF"
SELECTED_BACKGROUND = "#C7DDF5"
SELECTED_TEXT = "#102A43"
FIELD_BACKGROUND = "#FFFFFF"
CLASSIC_FOCUS_BACKGROUND = "#B8C4D2"

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

    def apply(self, scale):
        scale = normalize_font_scale(scale)
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
        configure("TFrame", background=BACKGROUND)
        configure("TLabel", background=BACKGROUND, foreground=TEXT, font=font(10))
        configure("Title.TLabel", background=BACKGROUND, foreground=TITLE_TEXT, font=font(19, "bold"))
        configure("Heading.TLabel", background=BACKGROUND, foreground=TEXT, font=font(11, "bold"))
        configure("BodyBold.TLabel", background=BACKGROUND, foreground=TEXT, font=font(9, "bold"))
        configure("Sub.TLabel", background=BACKGROUND, foreground=MUTED_TEXT, font=font(9))
        configure(
            "TButton", font=font(9), padding=(size(10), size(7)),
            foreground=TEXT, background=FIELD_BACKGROUND,
            focusthickness=max(2, size(2)), focuscolor=FOCUS,
        )
        configure(
            "Accent.TButton", background=ACCENT, foreground="#FFFFFF",
            font=font(9, "bold"), padding=(size(10), size(7)),
            focusthickness=max(2, size(2)), focuscolor=FOCUS,
        )
        for name in ("TEntry", "TCombobox"):
            configure(
                name, font=font(10), foreground=TEXT, fieldbackground=FIELD_BACKGROUND,
                background=FIELD_BACKGROUND, borderwidth=1,
                focusthickness=max(2, size(2)), focuscolor=FOCUS,
            )
        configure("TCheckbutton", background=BACKGROUND, foreground=TEXT, font=font(10), focuscolor=FOCUS)
        configure("TRadiobutton", background=BACKGROUND, foreground=TEXT, font=font(10), focuscolor=FOCUS)
        configure(
            "Treeview", font=font(9), rowheight=size(30), background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND, foreground=TEXT, borderwidth=1,
            focusthickness=max(2, size(2)), focuscolor=FOCUS,
        )
        configure(
            "Treeview.Heading", font=font(9, "bold"), background="#E8EDF4",
            foreground="#344054", focusthickness=max(2, size(2)), focuscolor=FOCUS,
        )
        configure("TNotebook", background=BACKGROUND, borderwidth=0, focuscolor=FOCUS)
        configure("TNotebook.Tab", font=font(9), padding=(size(10), size(6)), focuscolor=FOCUS)
        configure("TProgressbar", background=ACCENT, troughcolor="#E8EDF4")

        focus_map = {
            "focuscolor": [("focus", FOCUS)],
            "bordercolor": [("focus", FOCUS)],
            "lightcolor": [("focus", FOCUS)],
            "darkcolor": [("focus", FOCUS)],
        }
        for name in ("TButton", "Accent.TButton", "TEntry", "TCombobox", "TCheckbutton", "TRadiobutton", "Treeview"):
            self.style.map(name, **focus_map)
        self.style.map("Accent.TButton", background=[("active", ACCENT_ACTIVE), ("pressed", ACCENT_ACTIVE), ("focus", ACCENT_ACTIVE)])
        self.style.map("Treeview", background=[("selected", SELECTED_BACKGROUND)], foreground=[("selected", SELECTED_TEXT)])
        self.style.map("TNotebook.Tab", background=[("focus", FOCUS_BACKGROUND), ("selected", FIELD_BACKGROUND)], foreground=[("focus", TEXT)])
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


def _visual_key(item):
    index, widget = item
    try:
        return int(widget.winfo_rooty()), int(widget.winfo_rootx()), index
    except Exception:
        return 0, 0, index


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
            candidate.focus_set()
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
            widget.focus_set()
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


def prepare_focus_tree(root):
    """Apply visible classic-widget focus and logical Tab/Shift-Tab traversal.

    The order is based on mapped visual coordinates, so right-packed controls
    and grid dialogs follow what the user sees rather than incidental creation
    order.  Handlers are installed once and always consult the latest order.
    """
    focusable = []

    def visit(widget):
        widget_class = _widget_class(widget)
        # A root's winfo_children includes its Toplevel dialogs.  Each dialog
        # gets its own traversal ring; never leak its controls into the parent.
        if widget is not root and widget_class in {"Tk", "Toplevel"}:
            return
        if widget_class in FOCUSABLE_CLASSES:
            try:
                widget.configure(takefocus=1)
            except Exception:
                pass
            focusable.append(widget)
        if widget_class in CLASSIC_FOCUS_CLASSES:
            try:
                widget.configure(
                    highlightthickness=2,
                    highlightcolor=FOCUS,
                    highlightbackground=CLASSIC_FOCUS_BACKGROUND,
                )
            except Exception:
                pass
        for child in _children(widget):
            visit(child)

    visit(root)
    order = [widget for _index, widget in sorted(enumerate(focusable), key=_visual_key)]
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
