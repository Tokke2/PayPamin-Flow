"""Weekly Python maintenance without creating a separate Python environment.

The application owns only its week markers. Runtime updates are performed by
the Windows launcher before the interpreter is started; add-on updates use the
current interpreter and never create a venv or a parallel Python installation.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

MAINTENANCE_WEEKDAY = 0  # Monday
MAINTENANCE_HOUR = 8
MAINTENANCE_MINUTE = 0
MAINTENANCE_POLL_INTERVAL_MS = 60 * 1000

# (import name, requirement used by the existing application environment)
PYTHON_ADDONS = (
    ("fitz", "PyMuPDF>=1.23"),
    ("reportlab", "reportlab>=4.0"),
    ("pytesseract", "pytesseract>=0.3.10"),
    ("pdf2image", "pdf2image>=1.17"),
    ("svglib", "svglib>=1.5"),
    ("PIL", "Pillow>=10.0"),
    ("cv2", "opencv-python-headless>=4.8"),
    ("pystray", "pystray>=0.19.5"),
)


def maintenance_monday(moment: datetime) -> datetime:
    """Return local midnight on the Monday of ``moment``'s week."""
    return (moment - timedelta(days=(moment.weekday() - MAINTENANCE_WEEKDAY) % 7)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


def maintenance_time(moment: datetime) -> datetime:
    """Return the preferred local maintenance time for this week."""
    return maintenance_monday(moment).replace(
        hour=MAINTENANCE_HOUR, minute=MAINTENANCE_MINUTE,
    )


def maintenance_week(moment: datetime) -> str:
    """Return a year-safe Monday date used as the once-per-week marker."""
    return maintenance_monday(moment).date().isoformat()


def maintenance_due(moment: datetime, last_week: str) -> bool:
    """Allow one catch-up after Monday 08:00, never before the scheduled time."""
    return moment >= maintenance_time(moment) and last_week != maintenance_week(moment)


def read_maintenance_week(path: Path) -> str:
    """Read a marker, treating only its absence as an empty history."""
    try:
        return path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return ""


def write_maintenance_week(path: Path, week: str) -> None:
    """Atomically persist a validated Monday marker without following links."""
    datetime.strptime(week, "%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"{week}\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def addon_package_specs() -> tuple[str, ...]:
    """Return every app-owned requirement for a weekly upgrade check."""
    return tuple(requirement for _import_name, requirement in PYTHON_ADDONS)


def missing_addon_package_specs() -> tuple[str, ...]:
    """Return only missing requirements for startup recovery, never upgrades."""
    return tuple(
        requirement
        for import_name, requirement in PYTHON_ADDONS
        if importlib.util.find_spec(import_name) is None
    )


def install_python_addons(
    executable: str | Path,
    packages,
    *,
    upgrade: bool = False,
    runner=None,
    timeout: int = 600,
) -> tuple[bool, str]:
    """Install into the current environment, with the existing user-site fallback.

    ``upgrade`` is intended only for the weekly job. Startup recovery passes
    ``False`` and supplies only missing packages. No environment is created.
    """
    package_list = tuple(str(package) for package in packages if str(package).strip())
    if not package_list:
        return True, ""
    run = runner or subprocess.run
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def command(user_site: bool) -> list[str]:
        args = [str(executable), "-m", "pip", "install"]
        if user_site:
            args.append("--user")
        if upgrade:
            # Upgrade named app requirements, not every unrelated dependency.
            args.extend(["--upgrade", "--upgrade-strategy", "only-if-needed"])
        args.extend(package_list)
        return args

    def invoke(user_site: bool = False):
        return run(
            command(user_site),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=flags,
        )

    try:
        process = invoke()
    except Exception as exc:
        return False, str(exc)
    if process.returncode != 0:
        try:
            process = invoke(user_site=True)
        except Exception as exc:
            return False, str(exc)
    details = (process.stderr or process.stdout or "").strip()
    return process.returncode == 0, details
