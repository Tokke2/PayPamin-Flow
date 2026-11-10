"""Local, reviewable self-learning for PayPamin Flow.

The app learns only from values that the user has already saved or explicitly
confirmed. Everything stays in the local SQLite database; nothing is uploaded.

Nothing is ever applied on the app's own initiative. Learned values are only
suggestions that the user must confirm each time, no matter how much evidence
has accumulated. Every learned value can be reviewed or forgotten in Settings.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

KIND_CUSTOMER = "customer"
KIND_SUPPLIER = "supplier"

# Evidence needed before a value is even offered as a question.
SUGGEST_MIN_OBSERVATIONS = 2
SUGGEST_MIN_SHARE = 0.60
MAX_VALUE_LENGTH = 500

# Learned supplier layout comparison. Similarity is a binary-token cosine.
# A match is only ever a prefill in the review dialog, never a saved decision.
SUPPLIER_SUGGEST_SIMILARITY = 0.82
SUPPLIER_MIN_MARGIN = 0.06
SIGNATURE_MIN_TOKENS = 40
SIGNATURE_MAX_TOKENS = 600
SIGNATURE_DUPLICATE_SIMILARITY = 0.97
SIGNATURE_MAX_PER_VENDOR = 40

_TOKEN_PATTERN = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
# Words every invoice shares carry no supplier identity.
_STOPWORDS = {
    "adress", "amount", "att", "betalas", "betalning", "betalningsvillkor",
    "belopp", "calc", "customer", "datum", "deadline", "delivery", "due",
    "faktura", "fakturan", "fakturadatum", "fakturanummer",
    "förfallodatum", "förfaller", "google", "invoice", "kund",
    "kundnummer", "moms", "number", "nummer", "ocr", "organisation",
    "organisationsnummer", "page", "referens", "reference", "sida", "sidan",
    "summa", "terms", "totalt", "total", "vat", "villkor", "betalningsfrist",
    "förseningsavgift", "påminnelse", "ränta", "skickas",
}


@dataclass(frozen=True)
class LearnedValue:
    """One candidate value with the evidence behind it."""

    kind: str
    scope: str
    scope_label: str
    field: str
    value: str
    observations: int
    total: int

    @property
    def share(self) -> float:
        return (self.observations / self.total) if self.total else 0.0

    @property
    def evidence(self) -> str:
        return f"{self.observations}/{self.total}"


@dataclass(frozen=True)
class LearningEntry(LearnedValue):
    """A stored value as shown in the review panel."""


@dataclass(frozen=True)
class SupplierSignatureMatch:
    vendor: str
    similarity: float
    margin: float


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_scope(value) -> str:
    """Match customer and supplier names regardless of case and spacing."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def normalize_value(value) -> str:
    """Trim a learned value without changing meaningful line breaks."""
    text = unicodedata.normalize("NFKC", str(value or "")).replace("\x00", "").strip()
    return text[:MAX_VALUE_LENGTH]


def ensure_learning_schema(db) -> None:
    """Create the per-user learning store; safe to call on every start."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS learning_values (
        kind TEXT NOT NULL,
        scope TEXT NOT NULL,
        scope_label TEXT NOT NULL DEFAULT '',
        field TEXT NOT NULL,
        value TEXT NOT NULL,
        observations INTEGER NOT NULL DEFAULT 1,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        PRIMARY KEY(kind, scope, field, value)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS learning_dismissals (
        kind TEXT NOT NULL,
        scope TEXT NOT NULL,
        field TEXT NOT NULL,
        value TEXT NOT NULL,
        observations INTEGER NOT NULL DEFAULT 0,
        dismissed TEXT NOT NULL,
        PRIMARY KEY(kind, scope, field, value)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS learning_signatures (
        id INTEGER PRIMARY KEY,
        vendor TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        tokens TEXT NOT NULL,
        created TEXT NOT NULL,
        UNIQUE(vendor, fingerprint)
        )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS learning_values_scope_idx "
        "ON learning_values(kind, scope, field)"
    )


def record(db, kind, scope, field, value, *, scope_label=None) -> bool:
    """Add one observation from an already saved user action.

    Empty values are ignored, so a blank field never erases what was learned.
    """
    scope_key = normalize_scope(scope)
    field_key = str(field or "").strip()
    stored_value = normalize_value(value)
    if not scope_key or not field_key or not stored_value:
        return False
    label = " ".join(str(scope_label or scope).split())[:MAX_VALUE_LENGTH]
    now = _now()
    db.execute(
        """INSERT INTO learning_values
        (kind, scope, scope_label, field, value, observations, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(kind, scope, field, value) DO UPDATE SET
            observations = observations + 1,
            last_seen = excluded.last_seen,
            scope_label = CASE WHEN excluded.scope_label != '' THEN excluded.scope_label ELSE scope_label END""",
        (str(kind), scope_key, label, field_key, stored_value, now, now),
    )
    return True


def _dismissed_observations(db, kind, scope, field, value) -> int | None:
    row = db.execute(
        """SELECT observations FROM learning_dismissals
        WHERE kind=? AND scope=? AND field=? AND value=?""",
        (kind, scope, field, value),
    ).fetchone()
    if row is None:
        return None
    return int(row[0] if not hasattr(row, "keys") else row["observations"])


def recommend(db, kind, scope, field) -> LearnedValue | None:
    """Return a learned suggestion, or None when evidence is insufficient.

    The result always requires an explicit confirmation. A tie between equally
    common values is never suggested, and a declined suggestion is only offered
    again after at least two further observations.
    """
    scope_key = normalize_scope(scope)
    if not scope_key:
        return None
    rows = db.execute(
        """SELECT value, observations, scope_label FROM learning_values
        WHERE kind=? AND scope=? AND field=?
        ORDER BY observations DESC, last_seen DESC""",
        (str(kind), scope_key, str(field)),
    ).fetchall()
    if not rows:
        return None
    top_value, top_count, label = rows[0][0], int(rows[0][1]), rows[0][2]
    if len(rows) > 1 and int(rows[1][1]) == top_count:
        return None  # Ambiguous evidence must not even be suggested.
    total = sum(int(row[1]) for row in rows)
    share = top_count / total if total else 0.0
    if top_count < SUGGEST_MIN_OBSERVATIONS or share < SUGGEST_MIN_SHARE:
        return None
    dismissed = _dismissed_observations(db, str(kind), scope_key, str(field), top_value)
    if dismissed is not None and top_count <= dismissed + 1:
        return None
    return LearnedValue(
        kind=str(kind),
        scope=scope_key,
        scope_label=str(label or scope_key),
        field=str(field),
        value=top_value,
        observations=top_count,
        total=total,
    )


def decline(db, learned: LearnedValue) -> None:
    """Remember that the user said no to a suggestion.

    The suggestion becomes available again once more evidence has accumulated.
    """
    db.execute(
        """INSERT INTO learning_dismissals(kind, scope, field, value, observations, dismissed)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(kind, scope, field, value) DO UPDATE SET
            observations = excluded.observations,
            dismissed = excluded.dismissed""",
        (learned.kind, learned.scope, learned.field, learned.value, learned.observations, _now()),
    )


def entries(db, kind=None) -> list[LearningEntry]:
    """Return every learned value with its evidence for the review panel."""
    if kind is None:
        rows = db.execute(
            """SELECT kind, scope, scope_label, field, value, observations
            FROM learning_values ORDER BY kind, scope_label, field, observations DESC, value"""
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT kind, scope, scope_label, field, value, observations
            FROM learning_values WHERE kind=?
            ORDER BY scope_label, field, observations DESC, value""",
            (str(kind),),
        ).fetchall()
    totals: dict[tuple, int] = {}
    for row in rows:
        key = (row[0], row[1], row[3])
        totals[key] = totals.get(key, 0) + int(row[5])
    result = []
    for row in rows:
        kind_value, scope, label, field, value, observations = (
            row[0], row[1], row[2], row[3], row[4], int(row[5]),
        )
        total = totals.get((kind_value, scope, field), observations)
        result.append(
            LearningEntry(
                kind=kind_value,
                scope=scope,
                scope_label=str(label or scope),
                field=field,
                value=value,
                observations=observations,
                total=total,
            )
        )
    return result


def forget(db, *, kind=None, scope=None, field=None, value=None) -> int:
    """Delete learned values and their dismissals; invoices are untouched."""
    clauses = []
    params: list[str] = []
    for column, item in (("kind", kind), ("scope", scope), ("field", field), ("value", value)):
        if item is None:
            continue
        clauses.append(f"{column}=?")
        params.append(str(item) if column != "scope" else normalize_scope(item))
    if not clauses:
        where = ""
    else:
        where = " WHERE " + " AND ".join(clauses)
    removed = db.execute("SELECT COUNT(*) FROM learning_values" + where, params).fetchone()[0]
    db.execute("DELETE FROM learning_values" + where, params)
    db.execute("DELETE FROM learning_dismissals" + where, params)
    return int(removed)


def counts(db) -> dict:
    """Return small counters for the Settings summary."""
    learned = db.execute("SELECT COUNT(*) FROM learning_values").fetchone()[0]
    signatures = db.execute("SELECT COUNT(*) FROM learning_signatures").fetchone()[0]
    return {"values": int(learned), "signatures": int(signatures)}


def _signature_tokens(text) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(text or ""))[:8000].casefold()
    tokens: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_PATTERN.findall(normalized):
        if token in seen or token in _STOPWORDS:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= SIGNATURE_MAX_TOKENS:
            break
    return tokens


def _cosine(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / math.sqrt(len(first) * len(second))


def record_supplier_signature(db, vendor, text) -> bool:
    """Store the wording layout of a confirmed supplier PDF.

    Near-identical layouts are not stored twice, and each supplier keeps a
    bounded history so comparison stays fast on a long-lived installation.
    """
    name = " ".join(str(vendor or "").split())
    tokens = _signature_tokens(text)
    if not name or len(tokens) < SIGNATURE_MIN_TOKENS:
        return False
    rows = db.execute(
        "SELECT tokens FROM learning_signatures WHERE lower(vendor)=lower(?)", (name,)
    ).fetchall()
    current = set(tokens)
    for row in rows:
        try:
            stored = set(json.loads(row[0]))
        except (TypeError, ValueError):
            continue
        if _cosine(current, stored) >= SIGNATURE_DUPLICATE_SIMILARITY:
            return False
    if len(rows) >= SIGNATURE_MAX_PER_VENDOR:
        return False
    fingerprint = hashlib.sha256(
        "\n".join(tokens).encode("utf-8")
    ).hexdigest()
    before = db.total_changes
    db.execute(
        "INSERT OR IGNORE INTO learning_signatures(vendor,fingerprint,tokens,created) VALUES(?,?,?,?)",
        (name, fingerprint, json.dumps(tokens, ensure_ascii=False), _now()),
    )
    return db.total_changes > before


def match_supplier_signature(db, text) -> SupplierSignatureMatch | None:
    """Find the supplier whose confirmed PDFs read most like this one."""
    tokens = _signature_tokens(text)
    if len(tokens) < SIGNATURE_MIN_TOKENS:
        return None
    current = set(tokens)
    best: dict[str, float] = {}
    rows = db.execute("SELECT vendor, tokens FROM learning_signatures").fetchall()
    for row in rows:
        try:
            stored = set(json.loads(row[1]))
        except (TypeError, ValueError):
            continue
        score = _cosine(current, stored)
        vendor = str(row[0])
        if score > best.get(vendor, 0.0):
            best[vendor] = score
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    vendor, similarity = ranked[0]
    margin = similarity - (ranked[1][1] if len(ranked) > 1 else 0.0)
    if similarity < SUPPLIER_SUGGEST_SIMILARITY:
        return None
    return SupplierSignatureMatch(vendor, round(similarity, 4), round(margin, 4))
