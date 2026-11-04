"""Reusable customer email contacts for PayPamin Flow.

Copyright © 2026 Rickard Längkvist.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

EMAIL_PATTERN = re.compile(r"^[^\s@,]+@[^\s@,]+\.[^\s@,]+$")


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
        updated TEXT NOT NULL
        )"""
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(customer_contacts)").fetchall()}
    if "logo_file" not in columns:
        db.execute("ALTER TABLE customer_contacts ADD COLUMN logo_file TEXT NOT NULL DEFAULT ''")


def get_customer_contact(db: sqlite3.Connection, customer):
    key = normalize_customer_key(customer)
    if not key:
        return None
    return db.execute(
        "SELECT * FROM customer_contacts WHERE customer_key=?", (key,)
    ).fetchone()


def save_customer_contact(db: sqlite3.Connection, customer, emails, logo_file=None):
    """Save recipients and reuse the latest non-empty customer SVG choice."""
    name = " ".join(str(customer or "").split())
    key = normalize_customer_key(name)
    if not key:
        raise ValueError("Customer name is required")
    normalized = normalize_email_addresses(emails)
    existing = get_customer_contact(db, name)
    inherited_logo = ""
    if existing is not None and "logo_file" in existing.keys():
        inherited_logo = str(existing["logo_file"] or "")
    selected_logo = Path(str(logo_file)).name if logo_file else inherited_logo
    db.execute(
        """INSERT OR REPLACE INTO customer_contacts
        (customer_key,customer_name,emails,logo_file,updated) VALUES(?,?,?,?,?)""",
        (key, name, normalized, selected_logo, datetime.now().isoformat(timespec="seconds")),
    )
    return normalized
