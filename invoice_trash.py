"""A trash can for invoices, so a delete can be undone.

Deleting an invoice used to run ``DELETE FROM invoices`` and the row was gone.
Here a delete instead moves the whole row - every column, including the P1/P2
snapshots - into ``invoice_trash`` as JSON together with the moment it was
deleted. Nothing reads that table except the trash view, so a trashed invoice
can never reappear in the list, in a reminder, in the journal or in an import.

Restoring puts the row back exactly as it was. The stored JSON is matched
against the columns the current database actually has, so a row deleted before
an update that added a column is restored without guessing: the columns that
still exist are restored, the ones the row never had keep their defaults.

Only an explicit "Ta bort permanent" or "Töm papperskorgen" removes a row for
good. Nothing is purged on a timer, because a delete that becomes permanent
after a silent deadline is exactly the surprise a trash can exists to avoid.
"""
from __future__ import annotations

import json
from datetime import datetime

from i18n import _

TRASH_TABLE = "invoice_trash"

TRASH_SCHEMA = f"""CREATE TABLE IF NOT EXISTS {TRASH_TABLE} (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER,
    invoice_no TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'SEK',
    deleted_at TEXT NOT NULL,
    payload TEXT NOT NULL
)"""


def ensure_trash_schema(db) -> None:
    """Create the trash table. Safe to call on every start."""
    db.execute(TRASH_SCHEMA)


def _row_to_dict(row) -> dict:
    """Return a plain dict of one invoice row, whatever column layout it has."""
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def move_to_trash(db, row, deleted_at: str | None = None) -> int:
    """Copy one invoice into the trash and return the trash id.

    The caller deletes the invoice itself in the same transaction, so a crash
    between the two can never lose the row: either both changes commit or
    neither does.
    """
    ensure_trash_schema(db)
    payload = _row_to_dict(row)
    stamp = deleted_at or datetime.now().replace(microsecond=0).isoformat(sep=" ")
    cursor = db.execute(
        f"INSERT INTO {TRASH_TABLE}(invoice_id,invoice_no,customer,amount,currency,deleted_at,payload)"
        " VALUES(?,?,?,?,?,?,?)",
        (
            payload.get("id"),
            str(payload.get("invoice_no") or ""),
            str(payload.get("customer") or ""),
            float(payload.get("amount") or 0),
            str(payload.get("currency") or "SEK"),
            stamp,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cursor.lastrowid)


def delete_invoice_to_trash(db, invoice_id: int, deleted_at: str | None = None) -> int | None:
    """Move one invoice to the trash in one transaction; None when it is gone."""
    row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if row is None:
        return None
    trash_id = move_to_trash(db, row, deleted_at)
    db.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    return trash_id


def trash_count(db) -> int:
    ensure_trash_schema(db)
    row = db.execute(f"SELECT COUNT(*) AS count FROM {TRASH_TABLE}").fetchone()
    return int(row[0] if row else 0)


def trash_items(db) -> list[dict]:
    """Return every trashed invoice, newest first, without the JSON payload."""
    ensure_trash_schema(db)
    rows = db.execute(
        f"SELECT id,invoice_id,invoice_no,customer,amount,currency,deleted_at"
        f" FROM {TRASH_TABLE} ORDER BY deleted_at DESC,id DESC"
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def trash_item(db, trash_id: int) -> dict | None:
    """Return one trashed invoice including its stored row."""
    ensure_trash_schema(db)
    row = db.execute(f"SELECT * FROM {TRASH_TABLE} WHERE id=?", (trash_id,)).fetchone()
    if row is None:
        return None
    item = _row_to_dict(row)
    try:
        item["row"] = json.loads(item.get("payload") or "{}")
    except (TypeError, ValueError):
        item["row"] = {}
    return item


def _invoice_columns(db) -> set[str]:
    return {row[1] for row in db.execute("PRAGMA table_info(invoices)").fetchall()}


def restore(db, trash_id: int) -> dict:
    """Put a trashed invoice back and remove it from the trash.

    Returns ``{'restored': bool, 'invoice_no': str, 'id': int|None,
    'original_id': int|None, 'reason': str}``. The original id is reused when
    it is still free; if a newer invoice has taken it, the row is inserted with
    a new id and ``original_id`` says what it used to be, so the caller can tell
    the user instead of silently renumbering.
    """
    item = trash_item(db, trash_id)
    if item is None:
        return {"restored": False, "invoice_no": "", "id": None, "original_id": None, "reason": "missing"}
    stored = item.get("row") or {}
    if not stored:
        return {"restored": False, "invoice_no": item["invoice_no"], "id": None, "original_id": None, "reason": "unreadable"}
    columns = _invoice_columns(db)
    if not columns:
        return {"restored": False, "invoice_no": item["invoice_no"], "id": None, "original_id": None, "reason": "no-table"}
    values = {key: value for key, value in stored.items() if key in columns}
    original_id = values.get("id")
    if original_id is not None:
        taken = db.execute("SELECT 1 FROM invoices WHERE id=?", (original_id,)).fetchone()
        if taken is not None:
            values.pop("id", None)
    names = list(values)
    placeholders = ",".join("?" for _ in names)
    cursor = db.execute(
        f"INSERT INTO invoices({','.join(names)}) VALUES({placeholders})",
        [values[name] for name in names],
    )
    restored_id = cursor.lastrowid if values.get("id") is None else values["id"]
    db.execute(f"DELETE FROM {TRASH_TABLE} WHERE id=?", (trash_id,))
    return {
        "restored": True,
        "invoice_no": str(values.get("invoice_no") or item["invoice_no"]),
        "id": restored_id,
        "original_id": original_id,
        "renumbered": bool(values.get("id") is None and original_id is not None),
        "reason": "",
    }


def purge(db, trash_ids=None) -> int:
    """Delete trash rows for good; every row when no ids are given."""
    ensure_trash_schema(db)
    if trash_ids is None:
        cursor = db.execute(f"DELETE FROM {TRASH_TABLE}")
    else:
        ids = [int(value) for value in trash_ids]
        if not ids:
            return 0
        cursor = db.execute(
            f"DELETE FROM {TRASH_TABLE} WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        )
    return int(cursor.rowcount or 0)


def empty_trash(db) -> int:
    """Remove every trashed invoice for good and return how many were removed."""
    return purge(db, None)


def trash_summary(items) -> str:
    """One factual line about what the trash holds, in the current language."""
    count = len(list(items))
    if count == 0:
        return _("Papperskorgen är tom")
    if count == 1:
        return _("1 faktura i papperskorgen")
    return _("{count} fakturor i papperskorgen", count=count)
