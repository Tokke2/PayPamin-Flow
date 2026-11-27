"""Reusable customer email contacts for PayPamin Flow.

Copyright © 2026 Rickard Längkvist.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from fee_rules import CUSTOMER_TYPES

EMAIL_PATTERN = re.compile(r"^[^\s@,]+@[^\s@,]+\.[^\s@,]+$")
CUSTOMER_LANGUAGES = ("", "sv", "en")


def normalize_customer_language(value) -> str:
    """Return ``'sv'`` or ``'en'`` for an explicit customer language, else ``''``."""
    candidate = str(value or "").strip().lower()
    return candidate if candidate in {"sv", "en"} else ""


class EmailAddressError(ValueError):
    """One comma-separated recipient is not a valid email address."""

    def __init__(self, address):
        self.address = str(address or "")
        super().__init__(self.address)


def normalize_customer_key(customer):
    """Match customer names regardless of letter case and repeated whitespace."""
    return " ".join(str(customer or "").split()).casefold()


def parse_email_addresses(value):
    """Return unique comma-separated recipients while preserving their order."""
    recipients = []
    seen = set()
    for part in str(value or "").split(","):
        address = part.strip()
        if not address:
            continue
        if len(address) > 254 or not EMAIL_PATTERN.fullmatch(address):
            raise EmailAddressError(address)
        key = address.casefold()
        if key not in seen:
            recipients.append(address)
            seen.add(key)
    return recipients


def normalize_email_addresses(value):
    return ", ".join(parse_email_addresses(value))


def ensure_customer_contact_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS customer_contacts (
        customer_key TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL,
        emails TEXT NOT NULL DEFAULT '',
        logo_file TEXT NOT NULL DEFAULT '',
        language TEXT NOT NULL DEFAULT '',
        customer_type TEXT NOT NULL DEFAULT '',
        updated TEXT NOT NULL
        )"""
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(customer_contacts)").fetchall()}
    if "logo_file" not in columns:
        db.execute("ALTER TABLE customer_contacts ADD COLUMN logo_file TEXT NOT NULL DEFAULT ''")
    if "customer_type" not in columns:
        db.execute("ALTER TABLE customer_contacts ADD COLUMN customer_type TEXT NOT NULL DEFAULT ''")
    if "language" not in columns:
        db.execute("ALTER TABLE customer_contacts ADD COLUMN language TEXT NOT NULL DEFAULT ''")


def get_customer_contact(db: sqlite3.Connection, customer):
    key = normalize_customer_key(customer)
    if not key:
        return None
    return db.execute(
        "SELECT * FROM customer_contacts WHERE customer_key=?", (key,)
    ).fetchone()


def get_customer_language(db: sqlite3.Connection, customer) -> str:
    """Return saved reminder language (``'sv'``, ``'en'``, or ``''`` for app default)."""
    contact = get_customer_contact(db, customer)
    if contact is None or "language" not in contact.keys():
        return ""
    return normalize_customer_language(contact["language"])


def get_customer_type(db: sqlite3.Connection, customer) -> str:
    """Return an explicit saved type, or empty when the customer is unclassified."""
    contact = get_customer_contact(db, customer)
    if contact is None or "customer_type" not in contact.keys():
        return ""
    value = str(contact["customer_type"] or "").strip().lower()
    return value if value in CUSTOMER_TYPES else ""


def save_customer_contact(db: sqlite3.Connection, customer, emails, logo_file=None, language=None, customer_type=None):
    """Save customer defaults; omitted type/language never erase existing choices."""
    name = " ".join(str(customer or "").split())
    key = normalize_customer_key(name)
    if not key:
        raise ValueError("Customer name is required")
    normalized = normalize_email_addresses(emails)
    existing = get_customer_contact(db, name)
    inherited_logo = ""
    inherited_language = ""
    if existing is not None:
        if "logo_file" in existing.keys():
            inherited_logo = str(existing["logo_file"] or "")
        if "language" in existing.keys():
            inherited_language = normalize_customer_language(existing["language"])
    selected_type = get_customer_type(db, name) if customer_type is None else str(customer_type).strip().lower()
    if selected_type and selected_type not in CUSTOMER_TYPES:
        raise ValueError("Invalid customer type")
    selected_logo = Path(str(logo_file)).name if logo_file else inherited_logo
    selected_language = inherited_language if language is None else normalize_customer_language(language)
    db.execute(
        """INSERT OR REPLACE INTO customer_contacts
        (customer_key,customer_name,emails,logo_file,language,customer_type,updated) VALUES(?,?,?,?,?,?,?)""",
        (key, name, normalized, selected_logo, selected_language, selected_type, datetime.now().isoformat(timespec="seconds")),
    )
    return normalized
