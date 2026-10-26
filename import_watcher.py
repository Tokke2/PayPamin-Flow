"""Polling helper for stable, newly added invoice PDFs.

No third-party filesystem service is required. A file must have the same size
and modification time on two consecutive polls before it is offered to the
existing reviewed import flow. Files are offered again if their signature
changes or if they are removed and later added back.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileSignature:
    size: int
    modified_ns: int


class ImportFolderMonitor:
    """Track a single import folder and return each stable PDF revision once."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        self._pending: dict[Path, FileSignature] = {}
        self._handled: dict[Path, FileSignature] = {}

    def _snapshot(self) -> dict[Path, FileSignature]:
        try:
            candidates = sorted(
                path
                for path in self.folder.iterdir()
                if path.is_file() and path.suffix.lower() == ".pdf"
            )
        except (FileNotFoundError, NotADirectoryError):
            return {}
        current: dict[Path, FileSignature] = {}
        for path in candidates:
            try:
                details = path.stat()
                current[path] = FileSignature(details.st_size, details.st_mtime_ns)
            except OSError:
                # The file may still be moving or being replaced by the export.
                continue
        return current

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
