"""Conservative cleanup of PayPamin Flow's own stale cache files.

Only Python bytecode in the application's __pycache__ and app-named temporary
work directories are eligible. Invoice PDFs, import/export folders, databases,
settings, templates, logos, backups, logs and unrelated programs' caches are
never candidates.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX_AGE_HOURS = 24
TEMP_DIRECTORY_PREFIXES = (
    "paypamin-flow-python-update-",
    "paypamin-backup-",
    "paypamin-restore-",
)
BYTECODE_SUFFIXES = {".pyc", ".pyo"}


@dataclass
class CleanupReport:
    removed_files: int = 0
    removed_directories: int = 0
    freed_bytes: int = 0
    errors: int = 0


def _remove_stale_file(path: Path, cutoff: float, report: CleanupReport) -> None:
    try:
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in BYTECODE_SUFFIXES:
            return
        details = path.stat()
        if details.st_mtime >= cutoff:
            return
        path.unlink()
        report.removed_files += 1
        report.freed_bytes += details.st_size
    except FileNotFoundError:
        pass
    except OSError:
        report.errors += 1


def _stale_directory_contents(directory: Path, cutoff: float) -> tuple[bool, int, int]:
    """Return staleness and size without following links or touching contents."""

    if directory.is_symlink():
        return False, 0, 0
    total_bytes = 0
    file_count = 0
    try:
        for root, directories, files in os.walk(directory, followlinks=False):
            root_path = Path(root)
            if root_path.stat().st_mtime >= cutoff:
                return False, 0, 0
            for name in directories:
                child = root_path / name
                if child.is_symlink() or child.stat().st_mtime >= cutoff:
                    return False, 0, 0
            for name in files:
                child = root_path / name
                if child.is_symlink():
                    return False, 0, 0
                details = child.stat()
                if details.st_mtime >= cutoff:
                    return False, 0, 0
                total_bytes += details.st_size
                file_count += 1
    except FileNotFoundError:
        return False, 0, 0
    return True, total_bytes, file_count


def _remove_stale_temp_directory(path: Path, cutoff: float, report: CleanupReport) -> None:
    try:
        stale, total_bytes, file_count = _stale_directory_contents(path, cutoff)
        if not stale:
            return
        shutil.rmtree(path)
        report.removed_files += file_count
        report.removed_directories += 1
        report.freed_bytes += total_bytes
    except FileNotFoundError:
        pass
    except OSError:
        report.errors += 1


def clean_cache(
    source_dir: str | Path,
    *,
    temp_dir: str | Path | None = None,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> CleanupReport:
    """Remove only known app cache entries older than the conservative cutoff."""

    moment = (now or datetime.now(timezone.utc)).timestamp()
    cutoff = moment - max(0.0, float(max_age_hours)) * 3600
    report = CleanupReport()

    bytecode_dir = Path(source_dir) / "__pycache__"
    try:
        if bytecode_dir.is_dir() and not bytecode_dir.is_symlink():
            for path in bytecode_dir.iterdir():
                _remove_stale_file(path, cutoff, report)
            if not any(bytecode_dir.iterdir()):
                bytecode_dir.rmdir()
                report.removed_directories += 1
    except FileNotFoundError:
        pass
    except OSError:
        report.errors += 1

    temp_root = Path(temp_dir) if temp_dir is not None else Path(tempfile.gettempdir())
    try:
        candidates = list(temp_root.iterdir())
    except FileNotFoundError:
        candidates = []
    except OSError:
        candidates = []
        report.errors += 1
    for candidate in candidates:
        try:
            if (
                candidate.name.startswith(TEMP_DIRECTORY_PREFIXES)
                and candidate.is_dir()
                and not candidate.is_symlink()
            ):
                _remove_stale_temp_directory(candidate, cutoff, report)
        except OSError:
            report.errors += 1
    return report
