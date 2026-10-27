"""Prevent Windows console windows from application child processes.

The GUI itself is launched with pythonw.exe. Some PDF/OCR libraries start
console executables of their own, so the app also adds CREATE_NO_WINDOW to
those subprocess calls while preserving any flags already supplied.
"""
from __future__ import annotations

import subprocess
import sys

_installed = False


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
