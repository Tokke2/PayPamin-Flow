"""Keep a consolidated local log of unresolved errors from PayPamin Flow."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ERROR_LOG_NAME = "errors.log"
RESOLVED_ERROR_STATE = "resolved-errors.json"
RESOLVED_ARCHIVE_FOLDER = "resolved"
_SEPARATOR = "=" * 72
_APP_RECORD = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>[A-Z]+)\s+"
)
_ISO_RECORD = re.compile(r"^(?P<time>\d{4}-\d{2}-\d{2}T[^\s]+)\s+")
_STARTUP_RECORD = re.compile(r"^\[(?P<time>\d{4}-\d{2}-\d{2}T[^\]]+)\]\s*$")
_ROTATED_LOG = re.compile(r"^.+\.log\.\d+$")
_CONSOLIDATED_ENTRY = re.compile(
    r"^={72}\nSOURCE: (?P<source>[^\n]+)\nTIME: (?P<time>[^\n]+)\n"
    r"-{72}\n(?P<text>.*?)(?=^={72}\nSOURCE: |\Z)",
    re.MULTILINE | re.DOTALL,
)


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


@dataclass(frozen=True)
class ErrorResolutionReport:
    path: Path
    archive_path: Path | None
    resolved_count: int


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


def _entries_from_consolidated(content: str) -> list[ErrorEntry]:
    return [
        ErrorEntry(
            _timestamp(match.group("time")),
            match.group("source"),
            match.group("text").strip("\n"),
        )
        for match in _CONSOLIDATED_ENTRY.finditer(content)
        if match.group("text").strip("\n")
    ]


def _previous_entries(output_path: Path) -> list[ErrorEntry]:
    try:
        content = output_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    if "# PayPamin Flow consolidated error log" in content:
        return _entries_from_consolidated(content)
    # Preserve error lines from pre-consolidation or manually copied error logs.
    return _entries_from_text(ERROR_LOG_NAME, content)


def _fingerprint(entry: ErrorEntry) -> str:
    timestamp = entry.timestamp.isoformat() if entry.timestamp else ""
    return hashlib.sha256(f"{timestamp}\n{entry.text}".encode("utf-8")).hexdigest()


def _resolved_path(log_dir: Path) -> Path:
    return log_dir / RESOLVED_ERROR_STATE


def _load_resolved(log_dir: Path) -> dict[str, str]:
    path = _resolved_path(log_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict) or payload.get("format") != 1 or not isinstance(payload.get("resolved"), dict):
        raise ValueError("Invalid resolved-error state")
    resolved = payload["resolved"]
    if not all(re.fullmatch(r"[0-9a-f]{64}", key) and isinstance(value, str) for key, value in resolved.items()):
        raise ValueError("Invalid resolved-error state entries")
    return dict(resolved)


def _atomic_write(path: Path, payload: str, *, prefix: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _source_logs(log_dir: Path, output_path: Path) -> list[Path]:
    sources = []
    for path in log_dir.iterdir():
        if not path.is_file() or path.is_symlink() or path == output_path:
            continue
        if path.name.endswith(".log") or _ROTATED_LOG.fullmatch(path.name):
            sources.append(path)
    return sorted(sources, key=lambda path: path.name)


def refresh_error_log(log_dir: str | Path) -> ErrorLogReport:
    """Atomically refresh unresolved errors without discarding archived sources."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    output_path = log_dir / ERROR_LOG_NAME
    resolved = _load_resolved(log_dir)
    entries = _previous_entries(output_path)
    sources = _source_logs(log_dir, output_path)
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
        fingerprint = _fingerprint(entry)
        if fingerprint in resolved or fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(entry)
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    unique.sort(key=lambda entry: entry.timestamp or minimum, reverse=True)

    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "# PayPamin Flow consolidated error log",
        f"# Generated UTC: {generated}",
        "# Unresolved errors are retained until explicitly marked as resolved.",
        "# Original source logs are unchanged.",
        f"# Sources scanned: {len(sources)}",
        f"# Errors: {len(unique)}",
    ]
    if not unique:
        lines.append("# No unresolved errors.")
    for entry in unique:
        timestamp = entry.timestamp.isoformat() if entry.timestamp else "unknown time"
        lines.extend([
            "",
            _SEPARATOR,
            f"SOURCE: {entry.source}",
            f"TIME: {timestamp}",
            "-" * 72,
            entry.text,
        ])
    _atomic_write(output_path, "\n".join(lines) + "\n", prefix=".errors-")
    return ErrorLogReport(output_path, len(unique), len(sources))


def resolve_errors(
    log_dir: str | Path,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> ErrorResolutionReport:
    """Archive and resolve every error currently shown in errors.log.

    Resolved fingerprints prevent the unchanged technical source logs from
    reintroducing old incidents. A new incident has a new timestamp and remains.
    """
    log_dir = Path(log_dir)
    output_path = log_dir / ERROR_LOG_NAME
    entries = _previous_entries(output_path)
    resolved = _load_resolved(log_dir)
    entries = [entry for entry in entries if _fingerprint(entry) not in resolved]
    if not entries:
        return ErrorResolutionReport(output_path, None, 0)

    resolved_at = now or datetime.now(timezone.utc)
    archive_day = today or date.today()
    archive_dir = log_dir / "arkiv" / RESOLVED_ARCHIVE_FOLDER / archive_day.isoformat()
    if (log_dir / "arkiv").is_symlink() or archive_dir.is_symlink() or archive_dir.parent.is_symlink():
        raise OSError("Resolved-error archive must not be a symbolic link")
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = resolved_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = archive_dir / f"errors-{stamp}.log"
    index = 2
    while archive_path.exists() or archive_path.is_symlink():
        archive_path = archive_dir / f"errors-{stamp}-{index}.log"
        index += 1
    try:
        with output_path.open("rb") as source, archive_path.open("xb") as destination:
            shutil.copyfileobj(source, destination)
    except Exception:
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    timestamp = resolved_at.isoformat()
    for entry in entries:
        resolved[_fingerprint(entry)] = timestamp
    payload = json.dumps(
        {"format": 1, "resolved": dict(sorted(resolved.items()))},
        ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n"
    _atomic_write(_resolved_path(log_dir), payload, prefix=".resolved-errors-")
    refresh_error_log(log_dir)
    return ErrorResolutionReport(output_path, archive_path, len(entries))
