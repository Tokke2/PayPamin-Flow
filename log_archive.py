"""Calendar-day rotation, archiving and retention for application logs.

The log folder is deliberately small and predictable. A running day has
exactly three files:

``app.log``
    Technical events from the application, the console-free launcher and the
    updater.
``activity.log``
    One structured JSON event per line for every traced user action.
``errors.log``
    A consolidated view of the unresolved errors found in the two files above.

At the first record of a new day yesterday's technical logs move into
``logs/arkiv/YYYY-MM-DD/``. Archived days, including resolved-error snapshots,
are deleted after seven days so the folder never grows without a bound.
Today's ``errors.log`` is never archived: an unresolved incident stays visible
until it is explicitly marked as resolved.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from error_log import ERROR_LOG_NAME, RESOLVED_ARCHIVE_FOLDER

LOG_ARCHIVE_FOLDER = "arkiv"
RETENTION_DAYS = 7
_ROTATED_LOG = re.compile(r"^.+\.log\.\d+$")
_DATED_FOLDER = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class LogArchiveReport:
    """Outcome of one archive and retention pass."""

    archived: int = 0
    collisions: int = 0
    errors: int = 0
    pruned_days: int = 0
    pruned_errors: int = 0

    @property
    def changed(self) -> bool:
        return bool(
            self.archived or self.collisions or self.errors
            or self.pruned_days or self.pruned_errors
        )


class DailySizeRotatingFileHandler(RotatingFileHandler):
    """Rotate before the first record on a new local day and retain size rotation."""

    def __init__(self, filename, *args, today=None, **kwargs):
        self._today = today or date.today
        super().__init__(filename, *args, **kwargs)
        current = self._today()
        try:
            modified = datetime.fromtimestamp(Path(self.baseFilename).stat().st_mtime).date()
            self._open_date = modified if modified < current else current
        except OSError:
            self._open_date = current

    def doRollover(self) -> None:
        """Use unique numeric rotations instead of deleting the oldest backup."""
        if self.stream:
            self.stream.close()
            self.stream = None
        source = Path(self.baseFilename)
        if source.exists():
            stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            destination = Path(f"{self.baseFilename}.{stamp}")
            index = 2
            while destination.exists() or destination.is_symlink():
                destination = Path(f"{self.baseFilename}.{stamp}{index}")
                index += 1
            self.rotate(self.baseFilename, str(destination))
        if not self.delay:
            self.stream = self._open()

    def rollover_for_new_day(self) -> bool:
        current = self._today()
        if current <= self._open_date:
            return False
        self.doRollover()
        self._open_date = current
        return True

    def emit(self, record: logging.LogRecord) -> None:
        self.rollover_for_new_day()
        super().emit(record)


def _archive_destination(archive_dir: Path, name: str) -> tuple[Path, bool]:
    """Return a free destination and whether the preferred name collided."""
    destination = archive_dir / name
    if not destination.exists() and not destination.is_symlink():
        return destination, False
    destination = archive_dir / f"legacy-{name}"
    index = 2
    while destination.exists() or destination.is_symlink():
        destination = archive_dir / f"legacy-{index}-{name}"
        index += 1
    return destination, True


def _is_log_file(path: Path) -> bool:
    return path.name.endswith(".log") or bool(_ROTATED_LOG.fullmatch(path.name))


def archive_old_logs(
    log_dir: str | Path,
    *,
    today: date | None = None,
    retention_days: int = RETENTION_DAYS,
) -> LogArchiveReport:
    """Archive whole log files whose last write predates the local calendar day.

    Only regular ``.log`` files and numeric rotations directly inside ``log_dir``
    are considered. The active unresolved ``errors.log`` is never archived.
    Existing archives and symlinks are never overwritten or followed. Archived
    days older than ``retention_days`` are deleted in the same pass.
    """
    root = Path(log_dir)
    if not root.is_dir() or root.is_symlink():
        return LogArchiveReport()
    current = today or date.today()
    archive_root = root / LOG_ARCHIVE_FOLDER
    archived = collisions = errors = 0
    try:
        candidates = sorted(root.iterdir())
    except OSError:
        return LogArchiveReport(errors=1)
    for source in candidates:
        try:
            if source.is_symlink() or not source.is_file() or source.name == ERROR_LOG_NAME:
                continue
            if not _is_log_file(source):
                continue
            modified = datetime.fromtimestamp(source.stat().st_mtime).date()
            if modified >= current:
                continue
            if archive_root.is_symlink():
                errors += 1
                continue
            dated_dir = archive_root / modified.isoformat()
            if dated_dir.is_symlink():
                errors += 1
                continue
            dated_dir.mkdir(parents=True, exist_ok=True)
            destination, collision = _archive_destination(dated_dir, source.name)
            collisions += int(collision)
            source.rename(destination)
            archived += 1
        except OSError:
            errors += 1
    pruned_days, pruned_errors = prune_expired_archives(
        root, today=current, retention_days=retention_days
    )
    return LogArchiveReport(
        archived=archived,
        collisions=collisions,
        errors=errors,
        pruned_days=pruned_days,
        pruned_errors=pruned_errors,
    )


def prune_expired_archives(
    log_dir: str | Path,
    *,
    today: date | None = None,
    retention_days: int = RETENTION_DAYS,
) -> tuple[int, int]:
    """Delete archived days older than the retention window.

    Only directories named ``YYYY-MM-DD`` directly inside ``arkiv/`` and
    ``arkiv/resolved/`` are candidates, so unrelated folders in the log area are
    never touched. Symlinks are skipped instead of followed and deletion happens
    with :func:`shutil.rmtree`, which removes links instead of their targets.

    Returns ``(deleted_days, errors)``.
    """
    root = Path(log_dir)
    if not root.is_dir() or root.is_symlink():
        return 0, 0
    current = today or date.today()
    cutoff = current - timedelta(days=max(0, retention_days))
    archive_root = root / LOG_ARCHIVE_FOLDER
    removed_days = errors = 0
    for parent in (archive_root, archive_root / RESOLVED_ARCHIVE_FOLDER):
        if not parent.is_dir() or parent.is_symlink():
            continue
        try:
            entries = sorted(parent.iterdir())
        except OSError:
            errors += 1
            continue
        for folder in entries:
            if not folder.is_dir() or folder.is_symlink() or not _DATED_FOLDER.fullmatch(folder.name):
                continue
            try:
                archived_day = date.fromisoformat(folder.name)
            except ValueError:
                continue
            if archived_day >= cutoff:
                continue
            try:
                shutil.rmtree(folder)
                removed_days += 1
            except OSError:
                errors += 1
    return removed_days, errors
