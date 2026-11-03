"""Move generated reminder PDFs into non-destructive per-customer archives."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ARCHIVE_FOLDER_NAME = "arkiv"
ARCHIVE_AFTER_DAYS = 1
_REMINDER_FILENAME = re.compile(
    r"^(?:paminnelse|reminder)\([12]\)_.+_(\d{4}-\d{2}-\d{2})\.pdf$",
    re.IGNORECASE,
)
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class ReminderArchiveReport:
    archived: int = 0
    conflicts: int = 0
    errors: int = 0
    unmatched: int = 0


def safe_customer_folder(customer) -> str:
    """Return one readable, portable folder name without path separators."""
    name = re.sub(r"[^\w-]+", "_", str(customer or ""), flags=re.UNICODE).strip("_")[:60] or "kund"
    return "_" + name if name.upper() in _WINDOWS_RESERVED else name


def customer_archive_path(export_dir: str | Path, customer, filename: str | Path) -> Path:
    """Build the customer-specific archive path for one reminder basename."""
    return Path(export_dir) / ARCHIVE_FOLDER_NAME / safe_customer_folder(customer) / Path(filename).name


def reminder_date_from_filename(path: str | Path) -> date | None:
    """Read the original reminder date without trusting file modification time."""
    match = _REMINDER_FILENAME.fullmatch(Path(path).name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def archive_old_reminders(
    export_dir: str | Path,
    customer_by_filename: dict[str, str] | None = None,
    *,
    today: date | None = None,
) -> ReminderArchiveReport:
    """Archive recognized reminders from the first day after their reminder date.

    Only regular files directly inside ``export/`` and the legacy flat
    ``export/arkiv/`` folder are considered. Customer folders are never scanned
    recursively, unrelated PDFs are left alone and existing files are never
    overwritten. A reminder without an exact database-backed customer mapping
    stays in place instead of being assigned to a guessed customer folder.
    """
    root = Path(export_dir)
    if not root.is_dir():
        return ReminderArchiveReport()
    current = today or date.today()
    customers = customer_by_filename or {}
    archived = conflicts = errors = unmatched = 0
    archive_dir = root / ARCHIVE_FOLDER_NAME
    candidates = []
    try:
        candidates.extend(sorted(root.iterdir()))
        if archive_dir.is_dir() and not archive_dir.is_symlink():
            # Migrate eligible reminders from the old flat archive as well.
            candidates.extend(sorted(archive_dir.iterdir()))
    except OSError:
        return ReminderArchiveReport(errors=1)
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            reminder_date = reminder_date_from_filename(path)
            if reminder_date is None or (current - reminder_date).days < ARCHIVE_AFTER_DAYS:
                continue
            customer = str(customers.get(path.name) or "").strip()
            if not customer:
                unmatched += 1
                continue
            destination = customer_archive_path(root, customer, path.name)
            if archive_dir.is_symlink() or destination.parent.is_symlink():
                conflicts += 1
                continue
            if destination.exists() or destination.is_symlink():
                conflicts += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
            archived += 1
        except OSError:
            errors += 1
    return ReminderArchiveReport(
        archived=archived, conflicts=conflicts, errors=errors, unmatched=unmatched,
    )
