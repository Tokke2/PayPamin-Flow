"""Currency validation and detection helpers for PayPamin Flow.

Invoices keep their original currency. No exchange-rate conversion is performed.
"""
from __future__ import annotations

import re

DEFAULT_CURRENCY = "SEK"
COMMON_CURRENCIES = (
    "SEK", "EUR", "USD", "GBP", "NOK", "DKK", "CHF", "PLN", "CZK",
    "HUF", "ISK", "JPY", "CNY", "CAD", "AUD", "NZD", "INR", "BRL",
    "ZAR", "AED",
)


def is_valid_currency(value: str) -> bool:
    """Accept a three-letter ISO 4217-style currency code."""
    return bool(re.fullmatch(r"[A-Za-z]{3}", str(value or "").strip()))


def normalize_currency(value: str, default: str = DEFAULT_CURRENCY) -> str:
    """Return an uppercase valid code, or the supplied fallback."""
    code = str(value or "").strip().upper()
    return code if is_valid_currency(code) else default


def find_currency_code(text: str) -> str:
    """Find a known currency code in text without guessing from other words."""
    if not text:
        return ""
    if re.fullmatch(r"\s*[A-Za-z]{3}\s*", text):
        return normalize_currency(text, default="")
    pattern = r"\b(?:" + "|".join(COMMON_CURRENCIES) + r")\b"
    match = re.search(pattern, text, re.I)
    return match.group(0).upper() if match else ""
