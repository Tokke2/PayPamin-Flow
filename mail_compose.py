"""Desktop-mail composition integrations that still leave sending to the user."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path


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
    if client:
        return "thunderbird" in client.casefold()
    system_client = _registry_value("HKLM", REGISTERED_MAIL_CLIENT_KEY)
    return "thunderbird" in system_client.casefold()


def _executable_from_command(command):
    """Extract a quoted or unquoted Thunderbird path from a registered command."""
    match = re.search(
        r'((?:[A-Za-z]:[\\/]|\\\\)[^\r\n\"]*?thunderbird\.exe)',
        str(command or ''), re.IGNORECASE,
    )
    return match.group(1) if match else ''


def _existing_file(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        try:
            text = os.path.expandvars(str(candidate)).strip().strip('"')
            path = Path(text).expanduser()
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
    registered = []
    for root in ("HKCU", "HKLM"):
        command_keys = [r"SOFTWARE\Classes\Thunderbird.Url.mailto\shell\open\command"]
        command_keys.extend(
            rf"SOFTWARE\Clients\Mail\{client}\shell\open\command"
            for client in ("Mozilla Thunderbird", "Thunderbird")
        )
        registered.extend(
            _executable_from_command(_registry_value(root, key)) for key in command_keys
        )
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


DRAFT_PREFIX = "paypamin-flow-draft-"
DRAFT_MAX_AGE_SECONDS = 24 * 60 * 60


def build_thunderbird_draft(content, pdf_path):
    """Return an unsent MIME draft with the PDF embedded as a real attachment.

    Thunderbird 91 and later opens an .eml file with X-Unsent: 1 directly in
    its compose window. Embedding the attachment avoids the separate -compose
    attachment parser, including its URI, comma and Windows-path edge cases.
    """
    pdf_path = Path(pdf_path).expanduser().resolve()
    pdf_data = pdf_path.read_bytes()
    if not pdf_data:
        raise ValueError(f"Reminder PDF is empty: {pdf_path}")

    message = EmailMessage(policy=SMTP)
    message["X-Unsent"] = "1"
    message["To"] = ", ".join(content["recipients"])
    message["Bcc"] = content["bcc"]
    message["Subject"] = content["subject"]
    message.set_content(content["body"], subtype="plain", charset="utf-8")
    message.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    return message.as_bytes(policy=SMTP)


def cleanup_stale_thunderbird_drafts(directory=None, now=None):
    """Remove only our own day-old temporary drafts, never arbitrary files."""
    directory = Path(directory) if directory is not None else Path(tempfile.gettempdir())
    cutoff = (time.time() if now is None else now) - DRAFT_MAX_AGE_SECONDS
    try:
        candidates = directory.iterdir()
        for path in candidates:
            if not path.name.startswith(DRAFT_PREFIX) or path.suffix != ".eml":
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                # A draft may still be open. Leave it for a later cleanup.
                continue
    except OSError:
        return


def write_thunderbird_draft(content, pdf_path, directory=None):
    """Write a complete unsent draft and close it before Thunderbird opens it."""
    draft_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=DRAFT_PREFIX,
            suffix=".eml",
            dir=directory,
            delete=False,
        ) as draft:
            draft_path = Path(draft.name)
            draft.write(build_thunderbird_draft(content, pdf_path))
    except Exception:
        if draft_path is not None:
            try:
                draft_path.unlink()
            except OSError:
                pass
        raise
    return draft_path


def open_thunderbird_draft(executable, content, pdf_path):
    """Open an unsent .eml draft in Thunderbird; never send or use a shell."""
    cleanup_stale_thunderbird_drafts()
    draft_path = write_thunderbird_draft(content, pdf_path)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        # Thunderbird detects X-Unsent: 1 and opens this file as an editable
        # draft. Keep the file available for its asynchronous reader; stale
        # PayPamin drafts are removed on later launches.
        process = subprocess.Popen(
            [str(executable), str(draft_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=no_window,
        )
        return_code = process.poll()
        if return_code not in (None, 0):
            raise RuntimeError(f"Thunderbird exited immediately with code {return_code}")
    except Exception:
        try:
            draft_path.unlink()
        except OSError:
            pass
        raise
    return True
