"""Portable JSON reminder journal and weekly backups for PayPamin Flow.

SQLite remains the live database. The JSON file is an atomic, human-readable
export containing current application data plus an append-only reminder history.
It can be imported after reinstalling the app without creating duplicate
invoices or reminder events.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_info import APP_NAME, APP_VERSION
from i18n import _

JOURNAL_FORMAT = 1
JOURNAL_FILENAME = "reminder_journal.json"
JOURNAL_BACKUP_PREFIX = "reminder-journal-"
MAX_JOURNAL_BYTES = 100 * 1024 * 1024
MAX_JOURNAL_RECORDS = 100_000

INVOICE_COLUMNS = (
    "customer", "invoice_no", "due_date", "invoice_date", "template_vendor",
    "reviewed", "logo_file", "amount", "currency", "paid", "email", "source",
    "source_hash", "ignored", "note", "p1_date", "p2_date", "sent_count",
    "p1_snapshot", "created",
)


class JournalError(RuntimeError):
    """Raised when a journal cannot be safely read, written or imported."""


@dataclass(frozen=True)
class ImportResult:
    invoices_added: int = 0
    invoices_merged: int = 0
    reminders_added: int = 0
    reminders_skipped: int = 0


def _utc(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _timestamp(now: datetime | None = None) -> str:
    return _utc(now).isoformat(timespec="seconds")


def _normalise_invoice_number(value) -> str:
    return "".join(str(value or "").split()).casefold()


def reminder_event_id(invoice_no, level, reminder_date) -> str:
    """Stable identity for one P1/P2, independent of the local SQLite row ID."""
    key = f"{_normalise_invoice_number(invoice_no)}|{level}|{reminder_date}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def ensure_journal_schema(db: sqlite3.Connection) -> None:
    """Create the event table inside the application's normal DB migration."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS reminder_events (
        event_id TEXT PRIMARY KEY,
        invoice_id INTEGER,
        invoice_no TEXT NOT NULL,
        source_hash TEXT NOT NULL DEFAULT '',
        level TEXT NOT NULL,
        reminder_date TEXT NOT NULL,
        created_utc TEXT NOT NULL,
        payload TEXT NOT NULL
        )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminder_events_invoice "
        "ON reminder_events(invoice_id,reminder_date)"
    )


def _table_exists(db, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _rows(db, table: str):
    if not _table_exists(db, table):
        return []
    return [dict(row) for row in db.execute(f"SELECT * FROM {table}").fetchall()]


def _read_json(path: Path) -> dict:
    try:
        if not path.is_file():
            raise JournalError(_("JSON-journalen saknas: {path}", path=path))
        if path.stat().st_size > MAX_JOURNAL_BYTES:
            raise JournalError(_("JSON-journalen är för stor för att läsas säkert."))
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JournalError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise JournalError(_("JSON-journalen kunde inte läsas: {error}", error=exc)) from exc
    if not isinstance(payload, dict):
        raise JournalError(_("JSON-journalen har ett ogiltigt format."))
    if payload.get("application") != APP_NAME or payload.get("format") != JOURNAL_FORMAT:
        raise JournalError(_("Detta är inte en JSON-journal från PayPamin Flow."))
    if not isinstance(payload.get("invoices"), list) or not isinstance(payload.get("settings"), dict):
        raise JournalError(_("JSON-journalen saknar fakturor eller inställningar."))
    if not isinstance(payload.get("reminders"), list):
        raise JournalError(_("JSON-journalen saknar påminnelsehistorik."))
    for key in ("invoices", "reminders", "vendor_logos", "pdf_zones", "pdf_zone_samples"):
        value = payload.get(key, [])
        if not isinstance(value, list) or len(value) > MAX_JOURNAL_RECORDS:
            raise JournalError(_("JSON-journalen innehåller ogiltiga eller för många poster."))
    if len(payload["invoices"]) + len(payload["reminders"]) > MAX_JOURNAL_RECORDS:
        raise JournalError(_("JSON-journalen innehåller för många poster."))
    return payload


def _atomic_text(path: Path, text: str) -> Path:
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path
    except OSError as exc:
        raise JournalError(_("JSON-journalen kunde inte skrivas: {error}", error=exc)) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _write_payload(path: Path, payload: dict) -> Path:
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise JournalError(_("JSON-journalen innehåller data som inte kan sparas: {error}", error=exc)) from exc
    if len(text.encode("utf-8")) > MAX_JOURNAL_BYTES:
        raise JournalError(_("JSON-journalen är för stor för att sparas säkert."))
    return _atomic_text(path, text)


def _float(value, default=0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _legacy_events(invoices, settings):
    """Represent pre-journal P1/P2 dates without changing the old database."""
    default_terms = {
        "fee": _float(settings.get("fee")),
        "interest": str(settings.get("interest") or ""),
        "objection_days": str(settings.get("objection_days") or ""),
        "payment_deadline_days": str(settings.get("payment_deadline_days") or ""),
    }
    for row in invoices:
        for level, column in (("P1", "p1_date"), ("P2", "p2_date")):
            reminder_date = str(row.get(column) or "")
            if not reminder_date:
                continue
            terms = dict(default_terms)
            language = str(settings.get("language") or "sv")
            if level == "P1":
                try:
                    snapshot = json.loads(row.get("p1_snapshot") or "")
                    if isinstance(snapshot.get("terms"), dict):
                        terms.update(snapshot["terms"])
                    language = str(snapshot.get("language") or language)
                except (TypeError, ValueError, AttributeError):
                    pass
            event_id = reminder_event_id(row.get("invoice_no"), level, reminder_date)
            yield {
                "event_id": event_id,
                "invoice_id": row.get("id"),
                "invoice_no": str(row.get("invoice_no") or ""),
                "source_hash": str(row.get("source_hash") or ""),
                "level": level,
                "reminder_date": reminder_date,
                "created_utc": f"{reminder_date}T00:00:00+00:00",
                "fee": _float(terms.get("fee")),
                "currency": str(row.get("currency") or "SEK"),
                "terms": terms,
                "language": language,
                "logo_file": row.get("logo_file"),
                "pdf_name": "",
                "invoice": dict(row),
                "origin": "legacy",
            }


def _stored_events(db):
    for row in _rows(db, "reminder_events"):
        try:
            event = json.loads(row["payload"])
        except (TypeError, ValueError) as exc:
            raise JournalError(_("Påminnelsehistoriken i databasen är skadad: {error}", error=exc)) from exc
        if not isinstance(event, dict) or not event.get("event_id"):
            raise JournalError(_("Påminnelsehistoriken i databasen är skadad."))
        yield event


def export_journal(database_path, journal_path, *, now: datetime | None = None) -> Path:
    """Atomically export current data and all known reminder history."""
    database_path = Path(database_path)
    journal_path = Path(journal_path)
    if not database_path.is_file():
        raise JournalError(_("Databasen saknas: {path}", path=database_path))
    previous = _read_json(journal_path) if journal_path.is_file() else {}
    try:
        with closing(sqlite3.connect(database_path)) as db:
            db.row_factory = sqlite3.Row
            invoices = _rows(db, "invoices")
            settings = {
                str(row["key"]): str(row["value"])
                for row in _rows(db, "settings")
                if "key" in row and "value" in row
            }
            events = {}
            for event in previous.get("reminders", []):
                if isinstance(event, dict) and event.get("event_id"):
                    events[str(event["event_id"])] = event
            for event in _legacy_events(invoices, settings):
                events.setdefault(event["event_id"], event)
            for event in _stored_events(db):
                events[str(event["event_id"])] = event
            payload = {
                "application": APP_NAME,
                "format": JOURNAL_FORMAT,
                "app_version": APP_VERSION,
                "created_utc": previous.get("created_utc") or _timestamp(now),
                "updated_utc": _timestamp(now),
                "invoices": invoices,
                "settings": settings,
                "vendor_logos": _rows(db, "vendor_logos"),
                "pdf_zones": _rows(db, "pdf_zones"),
                "pdf_zone_samples": _rows(db, "pdf_zone_samples"),
                "reminders": sorted(
                    events.values(),
                    key=lambda event: (
                        str(event.get("created_utc") or ""),
                        str(event.get("reminder_date") or ""),
                        str(event.get("event_id") or ""),
                    ),
                ),
            }
    except JournalError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise JournalError(_("JSON-journalen kunde inte exporteras: {error}", error=exc)) from exc
    return _write_payload(journal_path, payload)


def record_reminder(
    database_path,
    journal_path,
    invoice_id,
    level,
    reminder_date,
    fee,
    terms,
    language,
    logo_file,
    pdf_name,
    *,
    now: datetime | None = None,
) -> dict:
    """Persist one successful P1/P2 event, then refresh the portable JSON."""
    if level not in ("P1", "P2"):
        raise JournalError(_("Okänd påminnelsenivå: {level}", level=level))
    moment = _timestamp(now)
    try:
        with closing(sqlite3.connect(database_path)) as db:
            db.row_factory = sqlite3.Row
            ensure_journal_schema(db)
            row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if row is None:
                raise JournalError(_("Fakturan för påminnelsen hittades inte."))
            invoice = dict(row)
            event_id = reminder_event_id(invoice["invoice_no"], level, reminder_date)
            event = {
                "event_id": event_id,
                "invoice_id": int(invoice["id"]),
                "invoice_no": str(invoice["invoice_no"]),
                "source_hash": str(invoice["source_hash"] or ""),
                "level": level,
                "reminder_date": str(reminder_date),
                "created_utc": moment,
                "fee": _float(fee),
                "currency": str(invoice["currency"] or "SEK"),
                "terms": dict(terms or {}),
                "language": str(language or "sv"),
                "logo_file": logo_file,
                "pdf_name": Path(pdf_name).name if pdf_name else "",
                "invoice": invoice,
                "origin": "application",
            }
            db.execute(
                """INSERT OR REPLACE INTO reminder_events
                (event_id,invoice_id,invoice_no,source_hash,level,reminder_date,created_utc,payload)
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    event_id, event["invoice_id"], event["invoice_no"], event["source_hash"],
                    level, str(reminder_date), moment,
                    json.dumps(event, ensure_ascii=False, sort_keys=True),
                ),
            )
            db.commit()
    except JournalError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise JournalError(_("Påminnelsen kunde inte journalföras: {error}", error=exc)) from exc
    export_journal(database_path, journal_path, now=now)
    return event


def create_weekly_backup(database_path, journal_path, backup_dir, *, now: datetime | None = None):
    """Create at most one JSON copy per ISO week; return its path or None."""
    moment = _utc(now)
    year, week, _ = moment.isocalendar()
    backup_dir = Path(backup_dir).expanduser().resolve()
    destination = backup_dir / f"{JOURNAL_BACKUP_PREFIX}{year}-W{week:02d}.json"
    if destination.is_file():
        try:
            _read_json(destination)
            return None
        except JournalError:
            # Replace a damaged copy atomically from the live database.
            pass
    export_journal(database_path, journal_path, now=moment)
    backup_dir.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=backup_dir
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        shutil.copyfile(journal_path, temporary)
        os.replace(temporary, destination)
        temporary = None
        try:
            destination.chmod(0o600)
        except OSError:
            pass
        return destination
    except OSError as exc:
        raise JournalError(_("Veckokopian av JSON-journalen kunde inte skapas: {error}", error=exc)) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _invoice_values(invoice, now):
    if not isinstance(invoice, dict):
        raise JournalError(_("JSON-journalen innehåller en ogiltig faktura."))
    if not str(invoice.get("customer") or "").strip() or not str(invoice.get("invoice_no") or "").strip():
        raise JournalError(_("JSON-journalen innehåller en faktura utan kund eller fakturanummer."))
    values = {column: invoice.get(column) for column in INVOICE_COLUMNS}
    values["created"] = values["created"] or _timestamp(now)
    values["due_date"] = values["due_date"] or ""
    values["currency"] = values["currency"] or "SEK"
    values["source_hash"] = values["source_hash"] or ""
    values["reviewed"] = int(values["reviewed"] if values["reviewed"] is not None else 1)
    values["ignored"] = int(values["ignored"] or 0)
    values["sent_count"] = int(values["sent_count"] or 0)
    values["amount"] = _float(values["amount"])
    values["paid"] = _float(values["paid"])
    return values


def _import_templates(db, payload):
    if _table_exists(db, "vendor_logos"):
        for row in payload.get("vendor_logos", []):
            if not isinstance(row, dict) or not row.get("vendor"):
                raise JournalError(_("JSON-journalen innehåller en ogiltig logotypmall."))
            db.execute(
                "INSERT OR REPLACE INTO vendor_logos(vendor,logo_file) VALUES(?,?)",
                (str(row["vendor"]), str(row.get("logo_file") or "")),
            )
    if _table_exists(db, "pdf_zones"):
        for row in payload.get("pdf_zones", []):
            if not isinstance(row, dict):
                raise JournalError(_("JSON-journalen innehåller ett ogiltigt PDF-fält."))
            db.execute(
                """INSERT OR REPLACE INTO pdf_zones
                (vendor,field,page_index,x0,y0,x1,y1,samples) VALUES(?,?,?,?,?,?,?,?)""",
                tuple(row.get(key) for key in ("vendor", "field", "page_index", "x0", "y0", "x1", "y1")) + (int(row.get("samples") or 1),),
            )
    if _table_exists(db, "pdf_zone_samples"):
        for row in payload.get("pdf_zone_samples", []):
            if not isinstance(row, dict):
                raise JournalError(_("JSON-journalen innehåller ett ogiltigt PDF-fält."))
            values = tuple(row.get(key) for key in ("vendor", "field", "page_index", "x0", "y0", "x1", "y1", "created"))
            exists = db.execute(
                """SELECT 1 FROM pdf_zone_samples
                WHERE vendor=? AND field=? AND page_index=? AND x0=? AND y0=? AND x1=? AND y1=? AND created=?""",
                values,
            ).fetchone()
            if not exists:
                db.execute(
                    """INSERT INTO pdf_zone_samples
                    (vendor,field,page_index,x0,y0,x1,y1,created) VALUES(?,?,?,?,?,?,?,?)""",
                    values,
                )


def import_journal(database_path, journal_path, source_path, *, now: datetime | None = None) -> ImportResult:
    """Merge a validated journal without duplicating invoices or events."""
    payload = _read_json(Path(source_path).expanduser().resolve())
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    result = {"invoices_added": 0, "invoices_merged": 0, "reminders_added": 0, "reminders_skipped": 0}
    try:
        with closing(sqlite3.connect(database_path)) as db:
            db.row_factory = sqlite3.Row
            ensure_journal_schema(db)
            db.execute("BEGIN IMMEDIATE")
            local_rows = db.execute("SELECT * FROM invoices").fetchall()
            by_number = {}
            by_hash = {}
            for row in local_rows:
                by_number.setdefault(_normalise_invoice_number(row["invoice_no"]), int(row["id"]))
                if row["source_hash"]:
                    by_hash.setdefault(row["source_hash"], int(row["id"]))
            for imported in payload["invoices"]:
                values = _invoice_values(imported, now)
                number_key = _normalise_invoice_number(values["invoice_no"])
                local_id = by_number.get(number_key)
                if local_id is None and values["source_hash"]:
                    local_id = by_hash.get(values["source_hash"])
                if local_id is not None:
                    result["invoices_merged"] += 1
                    local = db.execute("SELECT * FROM invoices WHERE id=?", (local_id,)).fetchone()
                    updates = []
                    parameters = []
                    for column in ("p1_date", "p2_date", "p1_snapshot"):
                        if not local[column] and values[column]:
                            updates.append(f"{column}=?")
                            parameters.append(values[column])
                    if not local["sent_count"] and values["sent_count"]:
                        updates.append("sent_count=?")
                        parameters.append(values["sent_count"])
                    if local["logo_file"] is None and imported.get("logo_file") is not None:
                        updates.append("logo_file=?")
                        parameters.append(imported.get("logo_file"))
                    if updates:
                        parameters.append(local_id)
                        db.execute(f"UPDATE invoices SET {','.join(updates)} WHERE id=?", parameters)
                else:
                    columns = ",".join(INVOICE_COLUMNS)
                    placeholders = ",".join("?" for _ in INVOICE_COLUMNS)
                    cursor = db.execute(
                        f"INSERT INTO invoices({columns}) VALUES({placeholders})",
                        tuple(values[column] for column in INVOICE_COLUMNS),
                    )
                    local_id = int(cursor.lastrowid)
                    result["invoices_added"] += 1
                    by_number[number_key] = local_id
                    if values["source_hash"]:
                        by_hash[values["source_hash"]] = local_id
            for key, value in payload["settings"].items():
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (str(key), str(value)))
            _import_templates(db, payload)
            for imported in payload["reminders"]:
                if not isinstance(imported, dict) or not imported.get("event_id"):
                    raise JournalError(_("JSON-journalen innehåller en ogiltig påminnelse."))
                level = str(imported.get("level") or "")
                reminder_date = str(imported.get("reminder_date") or "")
                invoice_no = str(imported.get("invoice_no") or "")
                if level not in ("P1", "P2") or not reminder_date or not invoice_no:
                    raise JournalError(_("JSON-journalen innehåller en ogiltig påminnelse."))
                source_hash = str(imported.get("source_hash") or "")
                local_id = by_number.get(_normalise_invoice_number(invoice_no))
                if local_id is None and source_hash:
                    local_id = by_hash.get(source_hash)
                event = dict(imported)
                event["invoice_id"] = local_id
                created = str(imported.get("created_utc") or _timestamp(now))
                event["created_utc"] = created
                cursor = db.execute(
                    """INSERT OR IGNORE INTO reminder_events
                    (event_id,invoice_id,invoice_no,source_hash,level,reminder_date,created_utc,payload)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        str(imported["event_id"]), local_id, invoice_no, source_hash, level,
                        reminder_date, created, json.dumps(event, ensure_ascii=False, sort_keys=True),
                    ),
                )
                if cursor.rowcount:
                    result["reminders_added"] += 1
                else:
                    result["reminders_skipped"] += 1
            db.commit()
    except JournalError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise JournalError(_("JSON-journalen kunde inte importeras: {error}", error=exc)) from exc
    export_journal(database_path, journal_path, now=now)
    return ImportResult(**result)
