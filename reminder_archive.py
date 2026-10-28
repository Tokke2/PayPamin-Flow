"""Move old generated reminder PDFs into a non-destructive export archive."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ARCHIVE_FOLDER_NAME = "arkiv"
ARCHIVE_AFTER_DAYS = 7
_REMINDER_FILENAME = re.compile(
    r"^(?:paminnelse|reminder)\([12]\)_.+_(\d{4}-\d{2}-\d{2})\.pdf$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReminderArchiveReport:
    archived: int = 0
    conflicts: int = 0
    errors: int = 0


def reminder_date_from_filename(path: str | Path) -> date | None:
    """Read the original reminder date without trusting file modification time."""
    match = _REMINDER_FILENAME.fullmatch(Path(path).name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def archive_old_reminders(export_dir: str | Path, *, today: date | None = None) -> ReminderArchiveReport:
    """Archive recognized P1/P2 PDFs strictly older than seven calendar days.

    Only regular files directly inside the export folder are considered. The
    archive is never scanned recursively, unrelated PDFs are left alone and an
    existing archive member is never overwritten.
    """
    root = Path(export_dir)
    if not root.is_dir():
        return ReminderArchiveReport()
    current = today or date.today()
    archived = conflicts = errors = 0
    archive_dir = root / ARCHIVE_FOLDER_NAME
    try:
        candidates = sorted(root.iterdir())
    except OSError:
        return ReminderArchiveReport(errors=1)
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            reminder_date = reminder_date_from_filename(path)
            if reminder_date is None or (current - reminder_date).days <= ARCHIVE_AFTER_DAYS:
                continue
            archive_dir.mkdir(parents=True, exist_ok=True)
            destination = archive_dir / path.name
            if destination.exists() or destination.is_symlink():
                conflicts += 1
                continue
            path.rename(destination)
            archived += 1
        except OSError:
            errors += 1
    return ReminderArchiveReport(archived=archived, conflicts=conflicts, errors=errors)
