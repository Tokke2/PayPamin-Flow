"""CSV export of the invoice register.

The file is written the way a Swedish spreadsheet expects it, so a double
click opens it with the columns already in place: semicolon between the
columns, comma as the decimal mark and a UTF-8 byte-order mark in front so
Excel reads Å, Ä and Ö correctly. Numbers are written as numbers, never with a
currency suffix, so they can be summed straight away.

Everything here is plain text handling; the app decides which invoices are in
the list and this module only turns them into a file.
"""
import csv
from datetime import date
from pathlib import Path

# The columns follow the order of the invoice list, plus the facts an export
# needs but the list only shows indirectly (invoice date, paid amount, note).
COLUMNS = (
    ("invoice_no", "Fakturanr"),
    ("customer", "Kund"),
    ("invoice_date", "Fakturadatum"),
    ("due_date", "Förfallodatum"),
    ("amount", "Belopp"),
    ("currency", "Valuta"),
    ("paid", "Betalt"),
    ("balance", "Saldo"),
    ("stage", "Status / nästa steg"),
    ("p1_date", "P1-datum"),
    ("p2_date", "P2-datum"),
    ("fee", "Påminnelseavgift"),
    ("email_status", "E-post (senaste)"),
    ("note", "Anteckning"),
)

# Amounts travel as plain figures with a comma, the way Excel expects them.
NUMBER_COLUMNS = ("amount", "paid", "balance", "fee")

# A cell that starts with one of these would be treated as a formula when the
# file is opened. A customer name is data, never a formula, so it is prefixed
# with an apostrophe, which spreadsheets hide.
FORMULA_STARTS = ("=", "+", "@", "\t", "\r")


def suggested_name(day=None):
    """Return a file name that says what the file holds and when it was made."""
    day = day or date.today()
    return f"fakturor-{day.isoformat()}.csv"


def number(value):
    """Format an amount with a comma and two decimals, or blank when unknown."""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def safe_text(value):
    """Keep a value from being read as a formula, without changing what it says."""
    text = "" if value is None else str(value)
    if text[:1] in FORMULA_STARTS:
        return "'" + text
    if text[:1] == "-" and not text[1:2].isdigit():
        return "'" + text
    return text


def cell(key, value):
    """Turn one record value into the text that belongs in the file."""
    if key in NUMBER_COLUMNS:
        return safe_text(number(value))
    return safe_text(value)


def rows_for(records, columns=COLUMNS):
    """Yield the header and one list per record, ready for csv.writer."""
    yield [label for _, label in columns]
    for record in records:
        yield [cell(key, record.get(key, "")) for key, _ in columns]


def write(path, records, columns=COLUMNS):
    """Write records to path and return how many rows were written.

    The file is always UTF-8 with a BOM, semicolons and CRLF, so the same file
    opens correctly in Excel on Windows and in LibreOffice on macOS and Linux.
    """
    records = list(records)
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(
            handle, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL
        )
        for line in rows_for(records, columns):
            writer.writerow(line)
    return len(records)


def totals(records):
    """Sum amount, paid and balance per currency for the confirmation."""
    sums = {}
    for record in records:
        currency = str(record.get("currency") or "").strip() or "SEK"
        bucket = sums.setdefault(currency, {"amount": 0.0, "paid": 0.0, "balance": 0.0})
        for key in bucket:
            try:
                bucket[key] += float(record.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return sums
