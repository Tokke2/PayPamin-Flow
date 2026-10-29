"""Desktop-mail composition integrations that still leave sending to the user."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


USERCHOICE_MAILTO_KEY = (
    r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice"
)
REGISTERED_MAIL_CLIENT_KEY = r"Software\Clients\Mail"
THUNDERBIRD_APP_PATHS_KEY = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\thunderbird.exe"
)


def _registry_value(root_name, key_path, value_name=""):
    """Read one Windows registry value without making non-Windows imports fail."""
    if sys.platform != "win32":
        return ""
    import winreg

    roots = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    root = roots[root_name]
    views = [0]
    for name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        view = getattr(winreg, name, 0)
        if view and view not in views:
            views.append(view)
    for view in views:
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | view) as key:
                value, _value_type = winreg.QueryValueEx(key, value_name)
            return str(value or "")
        except OSError:
            continue
    return ""


def windows_uses_thunderbird():
    """Prefer Windows 11's actual mailto UserChoice over legacy MAPI defaults."""
    if sys.platform != "win32":
        return False
    prog_id = _registry_value("HKCU", USERCHOICE_MAILTO_KEY, "ProgId")
    if prog_id:
        return "thunderbird" in prog_id.casefold()
    client = _registry_value("HKCU", REGISTERED_MAIL_CLIENT_KEY)
    return "thunderbird" in client.casefold()


def _existing_file(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        try:
            path = Path(os.path.expandvars(str(candidate))).expanduser()
            if path.is_file():
                return str(path)
        except (OSError, RuntimeError, ValueError):
            continue
    return None


def _find_thunderbird_executable():
    registered = [
        _registry_value(root, THUNDERBIRD_APP_PATHS_KEY)
        for root in ("HKCU", "HKLM")
    ]
    found = _existing_file(registered)
    if found:
        return found
    found = _existing_file((shutil.which("thunderbird.exe"), shutil.which("thunderbird")))
    if found:
        return found
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "Mozilla Thunderbird" / "thunderbird.exe")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend((
            Path(local) / "Mozilla Thunderbird" / "thunderbird.exe",
            Path(local) / "Programs" / "Mozilla Thunderbird" / "thunderbird.exe",
        ))
    return _existing_file(candidates)


def default_thunderbird_executable():
    """Return Thunderbird only when it is the default mailto app and is installed."""
    if not windows_uses_thunderbird():
        return None
    return _find_thunderbird_executable()


def build_thunderbird_compose(content, pdf_path):
    """Build Thunderbird's -compose value with one fixed, existing PDF attachment.

    Thunderbird percent-decodes unquoted option values after splitting the options.
    Encoding every value therefore preserves commas, quotes, Unicode and newlines.
    """
    attachment = Path(pdf_path).expanduser().resolve().as_uri()
    fields = {
        "to": ",".join(content["recipients"]),
        "bcc": content["bcc"],
        "subject": content["subject"],
        "body": content["body"],
        "attachment": attachment,
    }
    return ",".join(
        f"{name}={quote(str(value), safe='')}" for name, value in fields.items()
    ) + ",format=text"


def open_thunderbird_draft(executable, content, pdf_path):
    """Open a compose window with the PDF attached; never send or use a shell."""
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Reminder PDF does not exist: {pdf_path}")
    command = [str(executable), "-compose", build_thunderbird_compose(content, pdf_path)]
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=no_window,
    )
    return True
