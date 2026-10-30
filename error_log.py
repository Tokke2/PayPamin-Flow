"""Build one consolidated, local error log from PayPamin Flow's other logs."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ERROR_LOG_NAME = "errors.log"
_APP_RECORD = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>[A-Z]+)\s+"
)
_ISO_RECORD = re.compile(r"^(?P<time>\d{4}-\d{2}-\d{2}T[^\s]+)\s+")
_STARTUP_RECORD = re.compile(r"^\[(?P<time>\d{4}-\d{2}-\d{2}T[^\]]+)\]\s*$")
_ROTATED_LOG = re.compile(r"^.+\.log\.\d+$")


@dataclass(frozen=True)
class ErrorEntry:
    timestamp: datetime | None
    source: str
    text: str


@dataclass(frozen=True)
class ErrorLogReport:
    path: Path
    error_count: int
    source_count: int


def _timestamp(value: str) -> datetime | None:
    try:
        if "," in value and "T" not in value:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # logging.Formatter uses local time without a zone; ISO updater records
        # normally include their zone. astimezone handles both consistently.
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _record_start(line: str) -> tuple[str, str, str] | None:
    match = _APP_RECORD.match(line)
    if match:
        return "app", match.group("time"), match.group("level")
    match = _STARTUP_RECORD.match(line)
    if match:
        return "startup", match.group("time"), ""
    match = _ISO_RECORD.match(line)
    if match:
        return "iso", match.group("time"), ""
    return None


def _looks_like_error(text: str) -> bool:
    normalized = text.casefold()
    markers = (
        "error", "exception", "traceback", "failed", "failure", "could not",
        "kunde inte", "misslyck", "rollback", "rolled back",
    )
    return any(marker in normalized for marker in markers) or bool(re.search(r"\bfel\b", normalized))


def _entries_from_text(source: str, content: str) -> list[ErrorEntry]:
    blocks = []
    current = None
    for line in content.splitlines():
        start = _record_start(line)
        if start is not None:
            if current is not None:
                blocks.append(current)
            current = (start, [line])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        blocks.append(current)

    if not blocks:
        return [ErrorEntry(None, source, line) for line in content.splitlines() if _looks_like_error(line)]

    entries = []
    for (kind, timestamp_text, level), lines in blocks:
        text = "\n".join(lines).strip("\n")
        if kind == "app":
            include = level in {"ERROR", "CRITICAL"}
        elif kind == "startup":
            # startup.log is only written when console-free startup fails.
            include = True
        else:
            include = _looks_like_error(text)
        if include and text:
            entries.append(ErrorEntry(_timestamp(timestamp_text), source, text))
    return entries


def _source_logs(log_dir: Path, output_path: Path) -> list[Path]:
    sources = []
    for path in log_dir.iterdir():
        if not path.is_file() or path.is_symlink() or path == output_path:
            continue
        if path.name.endswith(".log") or _ROTATED_LOG.fullmatch(path.name):
            sources.append(path)
    return sorted(sources, key=lambda path: path.name)


def refresh_error_log(log_dir: str | Path) -> ErrorLogReport:
    """Rebuild errors.log atomically while leaving every source log untouched."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / ERROR_LOG_NAME
    sources = _source_logs(log_dir, output_path)
    entries = []
    for path in sources:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            entries.append(ErrorEntry(None, path.name, f"ERROR Could not read source log: {exc}"))
            continue
        entries.extend(_entries_from_text(path.name, content))

    # Rotated/copied logs can contain the same record. Keep distinct incidents
    # with different timestamps, but collapse byte-identical duplicate blocks.
    unique = []
    seen = set()
    for entry in entries:
        timestamp = entry.timestamp.isoformat() if entry.timestamp else ""
        fingerprint = hashlib.sha256(f"{timestamp}\n{entry.text}".encode("utf-8")).digest()
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(entry)
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    unique.sort(key=lambda entry: entry.timestamp or minimum, reverse=True)

    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "# PayPamin Flow consolidated error log",
        f"# Generated UTC: {generated}",
        "# Newest errors first. Original source logs are unchanged.",
        f"# Sources scanned: {len(sources)}",
        f"# Errors: {len(unique)}",
    ]
    if not unique:
        lines.append("# No errors found in the current source logs.")
    for entry in unique:
        timestamp = entry.timestamp.isoformat() if entry.timestamp else "unknown time"
        lines.extend([
            "",
            "=" * 72,
            f"SOURCE: {entry.source}",
            f"TIME: {timestamp}",
            "-" * 72,
            entry.text,
        ])
    payload = "\n".join(lines) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(prefix=".errors-", suffix=".tmp", dir=log_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, output_path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return ErrorLogReport(output_path, len(unique), len(sources))
