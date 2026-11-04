"""Calendar-day rotation and non-destructive archiving for application logs."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from error_log import ERROR_LOG_NAME

LOG_ARCHIVE_FOLDER = "arkiv"
_ROTATED_LOG = re.compile(r"^.+\.log\.\d+$")


@dataclass(frozen=True)
class LogArchiveReport:
    archived: int = 0
    collisions: int = 0
    errors: int = 0


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


def archive_old_logs(log_dir: str | Path, *, today: date | None = None) -> LogArchiveReport:
    """Archive whole log files whose last write predates the local calendar day.

    Only regular ``.log`` files and numeric rotations directly inside ``log_dir``
    are considered. The active unresolved ``errors.log`` is never archived.
    Existing archives and symlinks are never overwritten or followed.
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
            if not (source.name.endswith(".log") or _ROTATED_LOG.fullmatch(source.name)):
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
    return LogArchiveReport(archived=archived, collisions=collisions, errors=errors)
