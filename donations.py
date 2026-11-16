"""Locked Swish donation details for PayPamin Flow.

The donation channel is part of the product, not a setting. Everything here is
a module constant: there is no setter, no database row, no environment variable
and no entry field, so neither a user, an imported backup nor a hand-edited
database can change where a donation goes or invent another amount.

The code is a plain **Swish standard** payment code - the same
``C<number>;<amount>;<message>;<edit mask>`` payload the Swish app itself reads -
and it is drawn by :mod:`qr_code` locally. Nothing is fetched from the network,
so the code works offline and never leaks that the app was opened.
"""
from __future__ import annotations

# The author's locked Swish number. Digits only when used in the payload.
SWISH_NUMBER = "0721817177"

# Edit mask 6: the receiver is locked, while amount and message stay editable
# inside the Swish app. That is the standard, least surprising behaviour.
SWISH_EDIT_MASK = 6

# Fixed amounts in kronor. The app has no free amount and no entry field.
AMOUNTS = (25, 50, 100, 200)
DEFAULT_AMOUNT = 50
CURRENCY = "SEK"


def swish_number() -> str:
    """Return the digits of the locked Swish number."""
    return "".join(character for character in str(SWISH_NUMBER) if character.isdigit())


def formatted_number() -> str:
    """Return the number grouped for reading: 0721-817 177."""
    digits = swish_number()
    if len(digits) == 10:
        return f"{digits[:4]}-{digits[4:7]} {digits[7:]}"
    return digits


def amounts() -> tuple[int, ...]:
    """Return the fixed donation amounts in kronor."""
    return AMOUNTS


def default_amount() -> int:
    """Return the amount selected when the panel opens."""
    return DEFAULT_AMOUNT


def normalize_amount(value) -> int:
    """Return a fixed amount, or raise instead of accepting a free number.

    Decimals, text and any number outside :data:`AMOUNTS` are rejected. An
    amount is never rounded into place, because that would quietly put a number
    nobody chose into a payment code.
    """
    if isinstance(value, bool):
        raise ValueError("Donation amounts are fixed")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Donation amounts are fixed") from None
    if number != int(number) or int(number) not in AMOUNTS:
        raise ValueError(f"Donation amounts are fixed: {AMOUNTS}")
    return int(number)


def is_fixed_amount(value) -> bool:
    """Return whether a value is one of the locked amounts."""
    try:
        normalize_amount(value)
    except ValueError:
        return False
    return True


def swish_payload(amount=None) -> str:
    """Return the standard Swish C payload for a fixed amount.

    ``C<number>;<amount>;<message>;<edit mask>`` - the exact format the Swish
    app reads from its own QR codes.
    """
    chosen = DEFAULT_AMOUNT if amount is None else normalize_amount(amount)
    number = swish_number()
    if not number:
        raise ValueError("No Swish number is configured")
    return f"C{number};{chosen};;{SWISH_EDIT_MASK}"


def summary(amount=None) -> str:
    """Return a short locked description, used by the panel and by tests."""
    chosen = DEFAULT_AMOUNT if amount is None else normalize_amount(amount)
    return f"{chosen} {CURRENCY} · Swish {formatted_number()}"
