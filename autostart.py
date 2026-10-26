"""Per-user login autostart for Windows, macOS and Linux.

No administrator rights or third-party packages are required. The module has no
side effects on import; entries are only changed when set_autostart() is called.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from app_info import APP_DESCRIPTION, APP_DESCRIPTION_SV, APP_ID, APP_NAME, APP_SLUG
from i18n import _

SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
LOCAL_DATA_DIR = Path.home() / ".paminnelseapp"
WINDOWS_VALUE_NAME = "PayPaminFlow"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class AutostartError(RuntimeError):
    """Raised when the current user's login entry cannot be updated."""


def launch_command() -> list[str]:
    """Return an argument vector that starts this source tree or frozen app."""
    if getattr(sys, "frozen", False):
        if not sys.executable:
            raise AutostartError(_("Det går inte att hitta appens programfil."))
        return [str(Path(sys.executable).resolve())]

    if not sys.executable:
        raise AutostartError(_("Det går inte att hitta Python-installationen."))
    executable = Path(sys.executable).resolve()
    script = SOURCE_DIR / "paypamin_flow.py"
    if sys.platform.startswith("win"):
        # Never fall back to python.exe: that would open a console at login.
        pythonw = executable.with_name("pythonw.exe")
        if not pythonw.is_file():
            raise AutostartError(_("Konsolfri start kräver pythonw.exe. Installera Python från python.org."))
        executable = pythonw
        script = SOURCE_DIR / "paypamin_flow.pyw"
    if not script.is_file():
        raise AutostartError(_("Startfilen saknas: {script}", script=script))
    return [str(executable), str(script)]


def autostart_location() -> str:
    """Return a human-readable location for the current platform's entry."""
    if sys.platform.startswith("win"):
        return f"HKCU\\{WINDOWS_RUN_KEY}\\{WINDOWS_VALUE_NAME}"
    if sys.platform == "darwin":
        return str(_macos_agent_path())
    if sys.platform.startswith("linux"):
        return str(_linux_desktop_path())
    return _("Plattformen stöds inte")


def is_autostart_enabled() -> bool:
    if sys.platform.startswith("win"):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
    if sys.platform == "darwin":
        return _macos_agent_path().is_file()
    if sys.platform.startswith("linux"):
        return _linux_desktop_path().is_file()
    return False


def set_autostart(enabled: bool) -> None:
    """Enable or disable login start for the current user only."""
    try:
        if sys.platform.startswith("win"):
            _set_windows_autostart(enabled)
        elif sys.platform == "darwin":
            _set_macos_autostart(enabled)
        elif sys.platform.startswith("linux"):
            _set_linux_autostart(enabled)
        else:
            raise AutostartError(_("Autostart stöds inte på {platform}.", platform=sys.platform))
    except AutostartError:
        raise
    except (OSError, ValueError) as exc:
        raise AutostartError(str(exc)) from exc


def _set_windows_autostart(enabled: bool) -> None:
    import winreg

    if not enabled:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
        except FileNotFoundError:
            pass
        return

    command = subprocess.list2cmdline(launch_command())
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, command)


def _macos_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def _set_macos_autostart(enabled: bool) -> None:
    path = _macos_agent_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return

    payload = {
        "Label": APP_ID,
        "ProgramArguments": launch_command(),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(payload, sort_keys=True))


def _linux_desktop_path() -> Path:
    configured_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(configured_home) if configured_home else Path.home() / ".config"
    return config_home / "autostart" / f"{APP_SLUG}.desktop"


def _desktop_argument(argument: str) -> str:
    """Quote one argument according to the freedesktop Exec key rules."""
    escaped = argument.replace("%", "%%")
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("`", "\\`"), ("$", "\\$")):
        escaped = escaped.replace(old, new)
    return f'"{escaped}"'


def _linux_icon_path() -> Path:
    """Keep an icon outside one-file build temporary directories."""
    source = RESOURCE_DIR / "assets" / "paypamin_flow.png"
    target = LOCAL_DATA_DIR / "paypamin_flow.png"
    if source.is_file():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.read_bytes() != source.read_bytes():
                target.write_bytes(source.read_bytes())
            return target
        except OSError:
            # The desktop entry still works without a copied application icon.
            return source
    return source


def _set_linux_autostart(enabled: bool) -> None:
    path = _linux_desktop_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return

    command = " ".join(_desktop_argument(part) for part in launch_command())
    content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        f"Comment={APP_DESCRIPTION}",
        f"Comment[sv]={APP_DESCRIPTION_SV}",
        f"Exec={command}",
        f"Icon={_linux_icon_path()}",
        "Terminal=false",
        "Categories=Office;Finance;",
        "StartupNotify=false",
        "X-GNOME-Autostart-enabled=true",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
