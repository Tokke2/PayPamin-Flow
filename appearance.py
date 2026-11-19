"""Light, dark and follow-the-desktop appearance for PayPamin Flow.

The module answers two questions and nothing else: which theme did the user
choose, and which theme is the desktop asking for right now. Both answers are
plain strings, so the logic can be tested without a display, a theme engine or
a running app, and the Tk layer only has to paint what it is told.
"""
from __future__ import annotations

import os
import subprocess
import sys

THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SYSTEM = "system"

# The app opens in the light theme, exactly as it always has; the dark theme is
# a choice, never a surprise after an update.
DEFAULT_THEME = THEME_LIGHT
THEME_SETTING = "ui_theme"
THEME_CHOICES = (THEME_LIGHT, THEME_DARK, THEME_SYSTEM)

# Swedish UI labels. The app translates them; the module never depends on i18n.
THEME_LABELS = {
    THEME_LIGHT: "Ljust",
    THEME_DARK: "Mörkt",
    THEME_SYSTEM: "Följ systemet",
}

_ALIASES = {
    "light": THEME_LIGHT,
    "ljust": THEME_LIGHT,
    "bright": THEME_LIGHT,
    "dark": THEME_DARK,
    "mörkt": THEME_DARK,
    "morkt": THEME_DARK,
    "night": THEME_DARK,
    "system": THEME_SYSTEM,
    "auto": THEME_SYSTEM,
    "automatic": THEME_SYSTEM,
    "follow system": THEME_SYSTEM,
    "följ systemet": THEME_SYSTEM,
    "folj systemet": THEME_SYSTEM,
}


def normalize_theme(value, default: str = DEFAULT_THEME) -> str:
    """Return a known theme name for a stored or typed value.

    Older settings files and hand-edited values may say ``dark``, ``Mörkt`` or
    nothing at all; a value nobody recognises falls back to the default rather
    than to a half-applied theme.
    """
    text = " ".join(str(value or "").strip().casefold().split())
    if text in _ALIASES:
        return _ALIASES[text]
    fallback = _ALIASES.get(str(default or "").strip().casefold(), DEFAULT_THEME)
    return fallback if fallback != THEME_SYSTEM else THEME_SYSTEM


def _output(command, runner=None) -> str:
    """Read a desktop setting without a shell or a persistent subprocess."""
    try:
        result = (runner or subprocess.run)(
            command, capture_output=True, text=True, timeout=1, check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    return str(getattr(result, "stdout", "") or "").strip()


def _windows_apps_use_light() -> bool:
    """Read the Windows app theme; the default is light when it is unknown."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(int(value))
    except Exception:
        return True


def system_theme(platform=None, environ=None, runner=None, windows_reader=None) -> str:
    """Return ``light`` or ``dark`` as the desktop currently asks for.

    Every platform query is read-only and fails towards the light theme, so a
    locked-down desktop or a missing command can never leave the app with a
    half-painted window.
    """
    platform = str(platform or sys.platform).casefold()
    environ = os.environ if environ is None else environ
    if platform.startswith("win"):
        reader = windows_reader or _windows_apps_use_light
        try:
            return THEME_LIGHT if reader() else THEME_DARK
        except Exception:
            return THEME_LIGHT
    if platform == "darwin":
        output = _output(["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"], runner)
        return THEME_DARK if "dark" in output.casefold() else THEME_LIGHT
    # GNOME, KDE and the GTK desktops all answer at least one of these.
    gtk_theme = str(environ.get("GTK_THEME", "") or "").casefold()
    if "dark" in gtk_theme:
        return THEME_DARK
    scheme = _output(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"], runner)
    if "dark" in scheme.casefold():
        return THEME_DARK
    theme = _output(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"], runner)
    return THEME_DARK if "dark" in theme.casefold() else THEME_LIGHT


def effective_theme(value, system=None) -> str:
    """Resolve a chosen theme to the one that is actually painted.

    ``system`` is the desktop's answer, already read by :func:`system_theme`.
    It is passed in so the same value is used to paint and to log, and so a
    test never has to start a subprocess.
    """
    choice = normalize_theme(value)
    if choice == THEME_DARK:
        return THEME_DARK
    if choice == THEME_LIGHT:
        return THEME_LIGHT
    answer = normalize_theme(system if system is not None else system_theme())
    return THEME_LIGHT if answer == THEME_SYSTEM else answer


def is_dark(value) -> bool:
    """True when a resolved or chosen theme ends up dark."""
    return normalize_theme(value) == THEME_DARK


def setting_label(value) -> str:
    """Return the Swedish label a theme choice shows in Settings."""
    return THEME_LABELS[normalize_theme(value)]
