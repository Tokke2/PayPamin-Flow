"""Console-free PayPamin Flow launcher with visible startup diagnostics.

Keep this entry point free of application and Tkinter imports at module load:
if Python or Tkinter is broken, the error must still be logged and shown.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "PayPamin Flow"


def _write_startup_log(details: str) -> Path | None:
    """Write import/start failures before the application logger exists."""
    path = Path.home() / ".paminnelseapp" / "startup.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{datetime.now(timezone.utc).isoformat()}]\n{details.rstrip()}\n")
        return path
    except OSError:
        return None


def _startup_message(details: str, log_path: Path | None) -> str:
    lines = details.strip().splitlines()
    summary = lines[-1][:700] if lines else "Unknown startup error"
    log_text = f"{log_path}\n{log_path.parent / 'errors.log'}" if log_path else "Log file could not be written"
    return (
        "PayPamin Flow kunde inte starta. / PayPamin Flow could not start.\n\n"
        "Kontrollera att Python 3.10 eller senare är installerat med Tkinter.\n"
        "Check that Python 3.10 or later is installed with Tkinter.\n\n"
        f"Fel / Error: {summary}\n\nLogg / Log: {log_text}"
    )


def _show_startup_error(message: str) -> bool:
    """Use Tk when possible, then a native fallback without opening a console."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        try:
            root.withdraw()
            messagebox.showerror(APP_NAME, message, parent=root)
        finally:
            root.destroy()
        return True
    except Exception:
        pass

    try:
        if sys.platform.startswith("win"):
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
            return True
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = (
                f"display dialog {json.dumps(message)} with title {json.dumps(APP_NAME)} "
                'buttons {"OK"} default button "OK" with icon stop'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        if sys.platform.startswith("linux"):
            for command in (
                ["zenity", "--error", "--title", APP_NAME, "--text", message],
                ["notify-send", APP_NAME, message],
            ):
                if not shutil.which(command[0]):
                    continue
                result = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if result.returncode == 0:
                    return True
    except Exception:
        pass
    return False


def _report_startup_failure(details: str) -> None:
    log_path = _write_startup_log(details)
    if log_path is not None:
        try:
            from error_log import refresh_error_log

            refresh_error_log(log_path.parent)
        except Exception:
            # The original startup.log remains available even if aggregation fails.
            pass
    message = _startup_message(details, log_path)
    if not _show_startup_error(message):
        print(message, file=sys.stderr)


def run() -> int:
    """Import and run the app while keeping console-free failures diagnosable."""
    try:
        from paypamin_flow import main

        main()
        return 0
    except Exception:
        _report_startup_failure(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
