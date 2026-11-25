"""Swedish public holidays and bank-free days for due dates and reminder deadlines.

Adjusts invoice and reminder payment deadlines forward to the next Swedish
banking day (skuldebrevslagen 5 § 2 st.) so deadlines never fall on a Saturday,
Sunday, Midsummer Eve, Christmas Eve, New Year's Eve, or Swedish public holiday.

Copyright © 2026 Rickard Längkvist.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

WEEKEND_NAMES = {
    "sv": {5: "Lördag", 6: "Söndag"},
    "en": {5: "Saturday", 6: "Sunday"},
}

HOLIDAY_TRANSLATIONS_EN = {
    "Nyårsdagen": "New Year's Day",
    "Trettondedag jul": "Epiphany",
    "Långfredagen": "Good Friday",
    "Påskdagen": "Easter Sunday",
    "Annandag påsk": "Easter Monday",
    "Första maj": "May Day",
    "Kristi himmelsfärdsdag": "Ascension Day",
    "Pingstdagen": "Whit Sunday",
    "Sveriges nationaldag": "National Day of Sweden",
    "Midsommarafton": "Midsummer Eve",
    "Midsommardagen": "Midsummer Day",
    "Alla helgons dag": "All Saints' Day",
    "Julafton": "Christmas Eve",
    "Juldagen": "Christmas Day",
    "Annandag jul": "Second Day of Christmas",
    "Nyårsafton": "New Year's Eve",
}


@lru_cache(maxsize=64)
def easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday for ``year`` (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _first_weekday_on_or_after(start: date, weekday: int) -> date:
    offset = (weekday - start.weekday()) % 7
    return start + timedelta(days=offset)


@lru_cache(maxsize=64)
def swedish_non_banking_days(year: int) -> dict[date, str]:
    """Return non-weekend Swedish public holidays and bank-free eves in ``year``."""
    easter = easter_sunday(year)
    midsummer_eve = _first_weekday_on_or_after(date(year, 6, 19), 4)  # Friday Jun 19–25
    midsummer_day = midsummer_eve + timedelta(days=1)                 # Saturday Jun 20–26
    all_saints = _first_weekday_on_or_after(date(year, 10, 31), 5)    # Saturday Oct 31–Nov 6
    holidays: dict[date, str] = {
        date(year, 1, 1): "Nyårsdagen",
        date(year, 1, 6): "Trettondedag jul",
        easter - timedelta(days=2): "Långfredagen",
        easter: "Påskdagen",
        easter + timedelta(days=1): "Annandag påsk",
        date(year, 5, 1): "Första maj",
        easter + timedelta(days=39): "Kristi himmelsfärdsdag",
        easter + timedelta(days=49): "Pingstdagen",
        date(year, 6, 6): "Sveriges nationaldag",
        midsummer_eve: "Midsommarafton",
        midsummer_day: "Midsommardagen",
        all_saints: "Alla helgons dag",
        date(year, 12, 24): "Julafton",
        date(year, 12, 25): "Juldagen",
        date(year, 12, 26): "Annandag jul",
        date(year, 12, 31): "Nyårsafton",
    }
    return holidays


def non_banking_reason(day: date, language: str = "sv") -> str:
    """Return why ``day`` is not a Swedish banking day, or ``''`` when it is."""
    lang = "en" if str(language or "").strip().lower() == "en" else "sv"
    holiday_sv = swedish_non_banking_days(day.year).get(day, "")
    if holiday_sv:
        return HOLIDAY_TRANSLATIONS_EN.get(holiday_sv, holiday_sv) if lang == "en" else holiday_sv
    weekday = day.weekday()
    if weekday in (5, 6):
        return WEEKEND_NAMES[lang][weekday]
    return ""


def is_swedish_banking_day(day: date) -> bool:
    """Return ``True`` when ``day`` is an open Swedish banking day."""
    return not non_banking_reason(day, "sv")


def next_swedish_banking_day(day: date) -> date:
    """Return ``day`` if it is a Swedish banking day, else the next banking day."""
    current = day
    while not is_swedish_banking_day(current):
        current += timedelta(days=1)
    return current


def adjusted_deadline_date(
    start_day: date,
    days: int,
    *,
    language: str = "sv",
) -> tuple[date, date, tuple[str, ...]]:
    """Return ``(banking_deadline, raw_deadline, skipped_day_reasons)``."""
    raw = start_day + timedelta(days=int(days))
    current = raw
    reasons: list[str] = []
    seen: set[str] = set()
    while True:
        reason = non_banking_reason(current, language=language)
        if not reason:
            break
        if reason not in seen:
            reasons.append(reason)
            seen.add(reason)
        current += timedelta(days=1)
    return current, raw, tuple(reasons)
