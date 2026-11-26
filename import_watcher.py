"""Polling and year/month archiving helpers for invoice PDFs in ``import/``.

Active, unpaid invoice PDFs sit directly inside ``import/``. Only top-level
regular ``.pdf`` files in ``import/`` are polled and imported; subdirectories
under ``import/`` (such as ``import/YYYY/MM/`` where ledger-paid invoices are
archived) are never scanned or imported.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class FileSignature:
    size: int
    modified_ns: int


def _parse_archive_date(value: date | datetime | str | None) -> date:
    """Resolve an archive year/month date, falling back to today's local date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return date.today()
    return date.today()


def _safe_invoice_token(invoice_no: str) -> str:
    return re.sub(r"[^\w-]+", "_", str(invoice_no or ""), flags=re.UNICODE).strip("_")[:40]


def is_archived_import_pdf(path: str | Path, import_dir: str | Path) -> bool:
    """Return True when ``path`` lives inside any subdirectory under ``import_dir``."""
    try:
        candidate = Path(path).expanduser()
        root = Path(import_dir).expanduser().resolve()
        resolved = candidate.resolve()
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    # Top-level files in import/ have len(relative.parts) == 1; any subfolder
    # under import/ (such as import/2026/11/faktura.pdf) has >= 2 parts.
    return len(relative.parts) >= 2


def _collision_free_destination(target_dir: Path, filename: str, invoice_no: str = "") -> Path:
    preferred = target_dir / filename
    if not preferred.exists() and not preferred.is_symlink():
        return preferred
    stem = Path(filename).stem or "faktura"
    suffix = Path(filename).suffix or ".pdf"
    token = _safe_invoice_token(invoice_no)
    if token and token.casefold() not in stem.casefold():
        with_no = target_dir / f"{stem}_{token}{suffix}"
        if not with_no.exists() and not with_no.is_symlink():
            return with_no
        stem = f"{stem}_{token}"
    index = 2
    while True:
        candidate = target_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        index += 1


def archive_import_pdf(
    source_path: str | Path,
    import_dir: str | Path,
    *,
    archive_date: date | datetime | str | None = None,
    invoice_no: str = "",
) -> Path | None:
    """Move a top-level ``import/`` PDF into ``import/YYYY/MM/`` when paid.

    Returns the resolved archived ``Path`` if moved, ``source_path`` resolved if
    it is already archived inside ``import/YYYY/MM/``, or ``None`` if the file
    does not sit in ``import_dir`` or cannot be archived safely.
    """
    raw_source = str(source_path or "").strip()
    if not raw_source:
        return None
    source = Path(raw_source).expanduser()
    root = Path(import_dir).expanduser()
    if root.is_symlink() or source.is_symlink() or not source.is_file():
        return None
    try:
        resolved_root = root.resolve()
        resolved_source = source.resolve()
    except OSError:
        return None
    if is_archived_import_pdf(resolved_source, resolved_root):
        return resolved_source
    if resolved_source.parent != resolved_root:
        return None
    day = _parse_archive_date(archive_date)
    year_dir = resolved_root / f"{day.year:04d}"
    month_dir = year_dir / f"{day.month:02d}"
    if (year_dir.exists() and year_dir.is_symlink()) or (month_dir.exists() and month_dir.is_symlink()):
        return None
    month_dir.mkdir(parents=True, exist_ok=True)
    destination = _collision_free_destination(month_dir, resolved_source.name, invoice_no=invoice_no)
    shutil.move(str(resolved_source), str(destination))
    return destination.resolve()


def restore_archived_import_pdf(archived_path: str | Path, import_dir: str | Path) -> Path | None:
    """Move an archived ``import/YYYY/MM/`` PDF back to ``import/`` upon undo."""
    raw_path = str(archived_path or "").strip()
    if not raw_path:
        return None
    source = Path(raw_path).expanduser()
    root = Path(import_dir).expanduser()
    if root.is_symlink() or source.is_symlink() or not source.is_file():
        return None
    try:
        resolved_root = root.resolve()
        resolved_source = source.resolve()
    except OSError:
        return None
    if not is_archived_import_pdf(resolved_source, resolved_root):
        return None
    resolved_root.mkdir(parents=True, exist_ok=True)
    destination = _collision_free_destination(resolved_root, resolved_source.name)
    shutil.move(str(resolved_source), str(destination))
    return destination.resolve()


def can_split_pdf_pages(path: str | Path) -> bool:
    """Return True when ``path`` is a valid multi-page PDF readable by PyMuPDF."""
    try:
        import fitz
        with fitz.open(path) as doc:
            return doc.page_count > 1
    except Exception:
        return False


def extract_section_pdf_to_import(
    source_pdf: str | Path,
    import_dir: str | Path,
    page_indexes: tuple[int, ...] | list[int],
    *,
    invoice_no: str = "",
) -> Path | None:
    """Extract ``page_indexes`` from a batch PDF into its own PDF in ``import_dir``."""
    if not page_indexes:
        return None
    source = Path(source_pdf).expanduser()
    root = Path(import_dir).expanduser()
    if root.is_symlink() or source.is_symlink() or not source.is_file():
        return None
    try:
        resolved_root = root.resolve()
        resolved_source = source.resolve()
    except OSError:
        return None
    resolved_root.mkdir(parents=True, exist_ok=True)
    token = _safe_invoice_token(invoice_no)
    if token:
        preferred_name = f"faktura_{token}.pdf"
    else:
        stem = resolved_source.stem or "faktura"
        preferred_name = f"{stem}_sida_{int(page_indexes[0]) + 1}.pdf"
    destination = _collision_free_destination(resolved_root, preferred_name)
    if destination.resolve() == resolved_source:
        destination = _collision_free_destination(resolved_root, f"faktura_{token or 'del'}_1.pdf")
    try:
        import fitz
        with fitz.open(resolved_source) as src_doc:
            out_doc = fitz.open()
            try:
                for page_idx in page_indexes:
                    idx = int(page_idx)
                    if 0 <= idx < src_doc.page_count:
                        out_doc.insert_pdf(src_doc, from_page=idx, to_page=idx)
                if out_doc.page_count == 0:
                    return None
                out_doc.save(str(destination), garbage=3, deflate=True)
            finally:
                out_doc.close()
    except Exception:
        return None
    return destination.resolve()


def _top_level_pdf_entries(root: Path) -> dict[Path, FileSignature]:
    """Scan only direct regular ``.pdf`` files inside ``root`` (never subfolders)."""
    found: dict[Path, FileSignature] = {}
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                name = entry.name
                if not name or name.startswith(".") or not name.lower().endswith(".pdf"):
                    continue
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    details = entry.stat(follow_symlinks=False)
                except OSError:
                    # The file may still be moving or being written.
                    continue
                found[root / name] = FileSignature(details.st_size, details.st_mtime_ns)
    except OSError:
        return found
    return found


def iter_import_pdfs(folder: str | Path) -> list[Path]:
    """Return sorted top-level PDF paths directly inside ``folder``."""
    return sorted(_top_level_pdf_entries(Path(folder)))


class ImportFolderMonitor:
    """Track top-level ``import/`` PDFs and return each stable file once."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        self._pending: dict[Path, FileSignature] = {}
        self._handled: dict[Path, FileSignature] = {}

    def _snapshot(self) -> dict[Path, FileSignature]:
        return _top_level_pdf_entries(self.folder)

    def poll(self) -> list[Path]:
        """Return stable new/changed PDFs; archived subfolders are never scanned."""
        current = self._snapshot()
        active = set(current)
        self._pending = {path: signature for path, signature in self._pending.items() if path in active}
        self._handled = {path: signature for path, signature in self._handled.items() if path in active}
        ready: list[Path] = []
        for path, signature in current.items():
            if self._handled.get(path) == signature:
                continue
            if self._pending.get(path) == signature:
                ready.append(path)
            else:
                self._pending[path] = signature
        for path in ready:
            self._handled[path] = current[path]
            self._pending.pop(path, None)
        return sorted(ready)

    def mark_handled(self, path: str | Path) -> None:
        """Mark a newly split per-invoice PDF as handled so it is not re-polled."""
        target = Path(path)
        try:
            if target.is_symlink() or not target.is_file():
                return
            details = target.stat()
        except OSError:
            return
        signature = FileSignature(details.st_size, details.st_mtime_ns)
        self._handled[target] = signature
        self._pending.pop(target, None)
        try:
            resolved = target.resolve()
            self._handled[resolved] = signature
            self._pending.pop(resolved, None)
        except OSError:
            return
