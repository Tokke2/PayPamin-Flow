"""Polling helper for stable, newly added invoice PDFs in import/ and subfolders.

No third-party filesystem service is required. Both ``import/`` and any
non-hidden subdirectories inside ``import/`` are scanned recursively using
``os.scandir``. A file must have the same size and modification time on two
consecutive polls before it is offered to the import flow, preventing partially
written downloads or print-to-PDF files from being read too early.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileSignature:
    size: int
    modified_ns: int


def _walk_pdf_entries(root: Path) -> dict[Path, FileSignature]:
    """Recursively scan ``root`` and non-hidden subfolders for ``.pdf`` files."""
    found: dict[Path, FileSignature] = {}
    stack = [root]
    while stack:
        current_dir = stack.pop()
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    name = entry.name
                    if not name or name.startswith("."):
                        continue
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(current_dir / name)
                            continue
                        if not name.lower().endswith(".pdf"):
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        details = entry.stat(follow_symlinks=False)
                    except OSError:
                        # The file or directory may still be moving or being written.
                        continue
                    found[current_dir / name] = FileSignature(details.st_size, details.st_mtime_ns)
        except OSError:
            continue
    return found


def iter_import_pdfs(folder: str | Path) -> list[Path]:
    """Return sorted PDF paths in ``folder`` and all non-hidden subfolders."""
    return sorted(_walk_pdf_entries(Path(folder)))


class ImportFolderMonitor:
    """Track an import folder (including subfolders) and return each stable PDF once."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        self._pending: dict[Path, FileSignature] = {}
        self._handled: dict[Path, FileSignature] = {}

    def _snapshot(self) -> dict[Path, FileSignature]:
        return _walk_pdf_entries(self.folder)

    def poll(self) -> list[Path]:
        """Return stable new/changed PDFs; incomplete files remain pending."""
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
