"""Prevent Windows console windows from the app and its child processes.

PayPamin Flow is a window app in the system tray; a black console window must
never appear, not at start and not while the import folder is scanned. That is
achieved in three places, all of them here:

* the launcher restarts itself under ``pythonw.exe`` when it was started with
  ``python.exe``, so no console is ever created;
* ``hide_own_console_window()`` hides the console of the current process as a
  last resort, for a start that happened through a console interpreter anyway;
* ``subprocess.Popen`` is patched to add ``CREATE_NO_WINDOW`` on Windows, which
  covers the console programs that PDF and OCR work starts (``pdftoppm``,
  ``tesseract``, ``pip``). The patch is installed when this module is imported,
  before those libraries are loaded.

Everything is a no-op on macOS and Linux, where a child process cannot open a
window of its own.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_installed = False

# Set in the environment of the relaunched interpreter so a start can never
# bounce between python.exe and pythonw.exe in a loop.
CONSOLE_FREE_GUARD = "PAYPAMIN_CONSOLE_FREE_LAUNCH"

SW_HIDE = 0


def configure_console_free_subprocesses() -> None:
    """Add CREATE_NO_WINDOW to child processes on Windows, once per process."""

    global _installed
    if _installed or not sys.platform.startswith("win"):
        return
    original_popen = subprocess.Popen
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def popen_without_console(*args, **kwargs):
        kwargs["creationflags"] = (kwargs.get("creationflags") or 0) | no_window
        return original_popen(*args, **kwargs)

    subprocess.Popen = popen_without_console
    _installed = True


def hide_own_console_window() -> bool:
    """Hide the console window of this process, if it owns one.

    Only Windows has per-process console windows, and a window may legitimately
    be absent (``pythonw.exe``, a frozen build, a redirected start). The call is
    therefore silent about every failure: not being able to hide a window that
    does not exist is not an error.

    A console shared with another process - somebody running the app from an
    open terminal - is deliberately left alone. Hiding that window would hide
    the user's own terminal, and a start from a terminal is a deliberate
    diagnostic start, not the desktop start this function exists for. A console
    created for this process alone has exactly one attached process.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetConsoleWindow()
        if not handle:
            return False
        attached = (ctypes.c_uint32 * 8)()
        count = kernel32.GetConsoleProcessList(attached, len(attached))
        if count and count > 1:
            return False
        ctypes.windll.user32.ShowWindow(handle, SW_HIDE)
        return True
    except Exception:
        return False


def console_free_python(executable: str | None = None) -> Path | None:
    """Return ``pythonw.exe`` beside this interpreter, when it exists.

    ``python.exe`` owns a console window; ``pythonw.exe`` in the same folder is
    the same interpreter without one. Nothing is downloaded or installed - a
    missing file simply means the caller keeps the interpreter it has and hides
    the console instead.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        path = Path(executable or sys.executable)
    except TypeError:
        return None
    if path.name.lower() != "python.exe":
        return None
    candidate = path.with_name("pythonw.exe")
    return candidate if candidate.is_file() else None


def relaunch_console_free(script: str | Path, arguments: list[str] | None = None) -> int | None:
    """Restart ``script`` under ``pythonw.exe`` when this start has a console.

    Returns ``0`` when a console-free copy was started and the caller should
    exit, otherwise ``None`` and the caller continues in this process. The guard
    variable in the child's environment makes the restart happen at most once.
    """
    if not sys.platform.startswith("win") or getattr(sys, "frozen", False):
        return None
    if os.environ.get(CONSOLE_FREE_GUARD) == "1":
        return None
    pythonw = console_free_python(sys.executable)
    if pythonw is None:
        return None
    command = [str(pythonw), str(script)] + list(arguments or [])
    environment = dict(os.environ)
    environment[CONSOLE_FREE_GUARD] = "1"
    try:
        subprocess.Popen(command, env=environment, close_fds=True)
    except OSError:
        return None
    return 0


configure_console_free_subprocesses()
