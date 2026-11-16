"""Locked donation details for PayPamin Flow.

The donation channels are part of the product, not a setting. Everything here is
a module constant: there is no setter, no database row, no environment variable
and no entry field, so neither a user, an imported backup nor a hand-edited
database can change where a donation goes or invent another amount.

**Swish** is the primary channel and is shown as a standard payment code - the
same ``C<number>;<amount>;;<edit mask>`` payload the Swish app itself reads -
drawn locally by :mod:`qr_code`. Nothing is fetched from the network, so the
code works offline and never leaks that the app was opened. **PayPal** and
**Ko-fi** are ordinary buttons that open the author's own pages.
"""
from __future__ import annotations

from dataclasses import dataclass

# The author's locked Swish number. Digits only when used in the payload.
SWISH_NUMBER = "0721817177"

# Edit mask 6: the receiver is locked, while amount and message stay editable
# inside the Swish app. That is the standard, least surprising behaviour.
SWISH_EDIT_MASK = 6

# The author's own pages. These are the only addresses the app can ever open;
# a link is always built here and never from user input.
PAYPAL_URL = "https://paypal.me/Rickard3dPrint"
KOFI_URL = "https://ko-fi.com/tokke2"

# Fixed amounts in kronor. The app has no free amount and no entry field.
AMOUNTS = (25, 50, 100, 200)
DEFAULT_AMOUNT = 50
CURRENCY = "SEK"


@dataclass(frozen=True)
class Channel:
    """One locked donation destination."""

    key: str
    label: str
    url: str


CHANNELS = (
    Channel("paypal", "PayPal", PAYPAL_URL),
    Channel("kofi", "Ko-fi", KOFI_URL),
)


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
    """Return the amount selected when the dialogue opens."""
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


def channel(key) -> Channel:
    """Return a locked channel by key."""
    wanted = str(key or "").strip().lower()
    for item in CHANNELS:
        if item.key == wanted:
            return item
    raise KeyError(f"Unknown donation channel: {key}")


def paypal_link(amount=None) -> str:
    """Return the PayPal link for a fixed amount, or the plain profile link."""
    if amount is None:
        return PAYPAL_URL
    return f"{PAYPAL_URL}/{normalize_amount(amount)}{CURRENCY}"


def kofi_link() -> str:
    """Return the Ko-fi link. Ko-fi itself offers a monthly option."""
    return KOFI_URL


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
    """Return a short locked description, used by the dialogue and by tests."""
    chosen = DEFAULT_AMOUNT if amount is None else normalize_amount(amount)
    return f"{chosen} {CURRENCY} · Swish {formatted_number()}"


def links() -> tuple[str, ...]:
    """Return every address the app may open for donations."""
    return (PAYPAL_URL, KOFI_URL)


def is_locked_address(url) -> bool:
    """True when a URL belongs to the locked donation destinations."""
    text = str(url or "")
    if not text:
        return False
    if text in links():
        return True
    # A PayPal amount link is still the author's page, never another profile.
    if text.startswith(f"{PAYPAL_URL}/"):
        rest = text[len(PAYPAL_URL) + 1:]
        return rest.endswith(CURRENCY) and rest[:-len(CURRENCY)].isdigit()
    return False
