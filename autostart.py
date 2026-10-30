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

from app_info import APP_DESCRIPTION, APP_DESCRIPTION_SV, APP_ID, APP_NAME, APP_SLUG, MINIMIZED_START_ARG
from i18n import _

SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
LOCAL_DATA_DIR = Path.home() / ".paminnelseapp"
WINDOWS_VALUE_NAME = "PayPaminFlow"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class AutostartError(RuntimeError):
    """Raised when the current user's login entry cannot be updated."""


def launch_command() -> list[str]:
    """Return an argument vector that starts minimized at OS login."""
    if getattr(sys, "frozen", False):
        if not sys.executable:
            raise AutostartError(_("Det går inte att hitta appens programfil."))
        return [str(Path(sys.executable).resolve()), MINIMIZED_START_ARG]

    if not sys.executable:
        raise AutostartError(_("Det går inte att hitta Python-installationen."))
    executable = Path(sys.executable).resolve()
    script = SOURCE_DIR / "paypamin_flow_launcher.py"
    if sys.platform.startswith("win"):
        # Never fall back to python.exe: that would open a console at login.
        pythonw = executable.with_name("pythonw.exe")
        if not pythonw.is_file():
            raise AutostartError(_("Konsolfri start kräver pythonw.exe. Installera Python från python.org."))
        executable = pythonw
    if not script.is_file():
        raise AutostartError(_("Startfilen saknas: {script}", script=script))
    return [str(executable), str(script), MINIMIZED_START_ARG]


def autostart_location() -> str:
    """Return a human-readable location for the current platform's entry."""
    if sys.platform.startswith("win"):
        return str(_windows_shortcut_path())
    if sys.platform == "darwin":
        return str(_macos_agent_path())
    if sys.platform.startswith("linux"):
        return str(_linux_desktop_path())
    return _("Plattformen stöds inte")


def is_autostart_enabled() -> bool:
    if sys.platform.startswith("win"):
        return _windows_shortcut_path().is_file() or _legacy_windows_autostart_exists()
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


def _windows_shortcut_path() -> Path:
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    return (
        base
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / f"{APP_NAME}.lnk"
    )


def _legacy_windows_autostart_exists() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def _remove_legacy_windows_run_value() -> None:
    """Migrate the old pythonw Run value without leaving a duplicate start."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
    except FileNotFoundError:
        pass


def _windows_powershell() -> Path:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    executable = root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise AutostartError(_("Windows PowerShell krävs för den ikonmärkta autostartgenvägen."))
    return executable


def _create_windows_shortcut(shortcut_path: Path, command: list[str]) -> None:
    """Create an icon-branded Startup shortcut through Windows' own COM shell."""
    icon = RESOURCE_DIR / "assets" / "paypamin_flow.ico"
    if not icon.is_file():
        raise AutostartError(_("Programikonen saknas: {path}", path=icon))
    powershell = _windows_powershell()
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = shortcut_path.with_name(f"{shortcut_path.stem}.tmp.lnk")
    environment = os.environ.copy()
    environment.update({
        "PAYPAMIN_FLOW_SHORTCUT": str(temporary_path),
        "PAYPAMIN_FLOW_TARGET": command[0],
        "PAYPAMIN_FLOW_ARGUMENTS": subprocess.list2cmdline(command[1:]),
        "PAYPAMIN_FLOW_WORKDIR": str(SOURCE_DIR),
        "PAYPAMIN_FLOW_ICON": f"{icon},0",
        "PAYPAMIN_FLOW_DESCRIPTION": APP_NAME,
    })
    script = (
        "$ErrorActionPreference='Stop';"
        "$shell=New-Object -ComObject WScript.Shell;"
        "$link=$shell.CreateShortcut($env:PAYPAMIN_FLOW_SHORTCUT);"
        "$link.TargetPath=$env:PAYPAMIN_FLOW_TARGET;"
        "$link.Arguments=$env:PAYPAMIN_FLOW_ARGUMENTS;"
        "$link.WorkingDirectory=$env:PAYPAMIN_FLOW_WORKDIR;"
        "$link.IconLocation=$env:PAYPAMIN_FLOW_ICON;"
        "$link.Description=$env:PAYPAMIN_FLOW_DESCRIPTION;"
        "$link.WindowStyle=1;"
        "$link.Save()"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            env=environment,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0 or not temporary_path.is_file():
            raise AutostartError(_("Windows-genvägen för autostart kunde inte skapas."))
        os.replace(temporary_path, shortcut_path)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutostartError(str(exc)) from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _set_windows_autostart(enabled: bool) -> None:
    shortcut_path = _windows_shortcut_path()
    if not enabled:
        shortcut_path.unlink(missing_ok=True)
        _remove_legacy_windows_run_value()
        return

    _create_windows_shortcut(shortcut_path, launch_command())
    _remove_legacy_windows_run_value()


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
