"""Export the customer ledger (reskontra) with reminder counts and dates.

Supports both Swedish Excel-ready CSV (UTF-8 with BOM, semicolon delimiter,
comma decimals, integer reminder counts) and print-ready landscape A4 PDF
reports via ReportLab.
"""
from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from i18n import _

COLUMNS = (
    ("invoice_no", "Fakturanr"),
    ("customer", "Kund"),
    ("invoice_date", "Fakturadatum"),
    ("due_date", "Förfallodatum"),
    ("amount", "Belopp"),
    ("paid", "Betalt"),
    ("balance", "Saldo"),
    ("currency", "Valuta"),
    ("fee", "Påminnelseavgift"),
    ("payment_status", "Betalstatus"),
    ("stage", "Status / nästa steg"),
    ("reminder_count", "Antal påminnelser"),
    ("p1_date", "P1-datum"),
    ("p1_sent_date", "P1 skickad"),
    ("p2_date", "P2-datum"),
    ("p2_sent_date", "P2 skickad"),
    ("latest_reminder_date", "Senaste påminnelsedatum"),
    ("paid_date", "Betaldatum"),
    ("ledger_last_seen", "Reskontradatum"),
    ("note", "Anteckning"),
)

NUMBER_COLUMNS = ("amount", "paid", "balance", "fee")
INTEGER_COLUMNS = ("reminder_count",)
FORMULA_STARTS = ("=", "+", "@", "\t", "\r")

SCOPE_SLUGS = {
    "all": "reskontra",
    "open": "reskontra-oppen",
    "reminded": "reskontra-paminnelser",
    "view": "reskontra-vy",
}


def _row_get(row: Mapping | object, key: str, default=""):
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        keys = row.keys()  # type: ignore[attr-defined]
        return row[key] if key in keys else default  # type: ignore[index]
    except AttributeError:
        return getattr(row, key, default)


def _iso_day(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        candidate = text[:10]
        try:
            date.fromisoformat(candidate)
            return candidate
        except ValueError:
            return text
    return text


def reminder_count_for(row: Mapping | object) -> int:
    """Return total created reminders for one invoice row as a non-negative int."""
    p1 = bool(str(_row_get(row, "p1_date", "") or "").strip())
    p2 = bool(str(_row_get(row, "p2_date", "") or "").strip())
    dated_levels = int(p1) + int(p2)
    try:
        sent_count = max(0, int(_row_get(row, "sent_count", 0) or 0))
    except (TypeError, ValueError):
        sent_count = 0
    return max(sent_count, dated_levels)


def latest_reminder_date_for(row: Mapping | object) -> str:
    """Return the latest reminder date (ISO YYYY-MM-DD) recorded on ``row``."""
    dates: list[str] = []
    for field in ("p2_sent_date", "p2_date", "p1_sent_date", "p1_date"):
        day = _iso_day(_row_get(row, field, ""))
        if len(day) == 10:
            try:
                date.fromisoformat(day)
                dates.append(day)
            except ValueError:
                continue
    if dates:
        return max(dates)
    for field in ("p2_date", "p1_date"):
        raw = str(_row_get(row, field, "") or "").strip()
        if raw:
            return raw
    return ""


def paid_date_for(row: Mapping | object) -> str:
    """Return the ISO date when an invoice was marked paid, if settled."""
    try:
        amount = float(_row_get(row, "amount", 0) or 0)
        paid = float(_row_get(row, "paid", 0) or 0)
    except (TypeError, ValueError):
        return ""
    if amount - paid > 0.005:
        return ""
    return _iso_day(_row_get(row, "paid_marked_at", ""))


def payment_status_label(row: Mapping | object) -> str:
    """Return localized payment status key for one invoice."""
    try:
        amount = float(_row_get(row, "amount", 0) or 0)
        paid = float(_row_get(row, "paid", 0) or 0)
    except (TypeError, ValueError):
        return _("Obetald")
    if amount - paid <= 0.005:
        return _("Betald")
    if paid > 0.005:
        return _("Delbetald")
    return _("Obetald")


def suggested_name(day: date | None = None, scope: str = "all", suffix: str = ".csv") -> str:
    """Return a dated filename describing the ledger export."""
    day = day or date.today()
    ext = suffix if str(suffix).startswith(".") else f".{suffix}"
    prefix = SCOPE_SLUGS.get(scope, "reskontra")
    return f"{prefix}-{day.isoformat()}{ext.lower()}"


def number(value) -> str:
    """Format an amount with a comma and two decimals, or blank when empty."""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def integer_text(value) -> str:
    """Format an integer counter cleanly for spreadsheets."""
    if value is None or value == "":
        return "0"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def safe_text(value) -> str:
    """Prevent spreadsheet formula injection while keeping numbers numeric."""
    text = "" if value is None else str(value)
    if text[:1] in FORMULA_STARTS:
        return "'" + text
    if text[:1] == "-" and not text[1:2].isdigit():
        return "'" + text
    return text


def cell(key: str, value) -> str:
    if key in NUMBER_COLUMNS:
        return safe_text(number(value))
    if key in INTEGER_COLUMNS:
        return integer_text(value)
    return safe_text(value)


def rows_for(records: Iterable[Mapping], columns=COLUMNS):
    yield [label for _, label in columns]
    for record in records:
        yield [cell(key, record.get(key, "")) for key, _ in columns]


def write_csv(path: str | Path, records: Iterable[Mapping], columns=COLUMNS) -> int:
    """Write semicolon UTF-8-BOM CSV ready for Excel and LibreOffice."""
    items = list(records)
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(
            handle, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL,
        )
        for line in rows_for(items, columns):
            writer.writerow(line)
    return len(items)


def summary_stats(records: Iterable[Mapping]) -> dict:
    """Compute invoice count, reminder totals and per-currency amount sums."""
    items = list(records)
    reminded_invoices = 0
    total_reminders = 0
    currencies: dict[str, dict[str, float]] = {}
    for record in items:
        try:
            rcount = int(record.get("reminder_count") or 0)
        except (TypeError, ValueError):
            rcount = 0
        if rcount > 0:
            reminded_invoices += 1
            total_reminders += rcount
        currency = str(record.get("currency") or "").strip() or "SEK"
        bucket = currencies.setdefault(currency, {"amount": 0.0, "paid": 0.0, "balance": 0.0})
        for key in bucket:
            try:
                bucket[key] += float(record.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
    return {
        "invoice_count": len(items),
        "reminded_invoices": reminded_invoices,
        "total_reminders": total_reminders,
        "currencies": currencies,
    }


def write_pdf(
    path: str | Path,
    records: Iterable[Mapping],
    *,
    title: str | None = None,
    export_date: date | None = None,
) -> int:
    """Write a landscape A4 customer ledger PDF with reminder counts and dates."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    items = list(records)
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    day = export_date or date.today()
    stats = summary_stats(items)
    heading_text = title or _("Kundreskontra — PayPamin Flow")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LedgerTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=14, leading=18, textColor=colors.HexColor("#0F172A"), spaceAfter=2 * mm,
    )
    meta_style = ParagraphStyle(
        "LedgerMeta", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"), spaceAfter=4 * mm,
    )
    cell_style = ParagraphStyle(
        "LedgerCell", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.2, leading=9.2, textColor=colors.HexColor("#0F172A"),
    )
    right_style = ParagraphStyle(
        "LedgerCellRight", parent=cell_style, alignment=2,
    )
    center_style = ParagraphStyle(
        "LedgerCellCenter", parent=cell_style, alignment=1,
    )
    header_style = ParagraphStyle(
        "LedgerHeader", parent=cell_style, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0F172A"),
    )

    doc = SimpleDocTemplate(
        str(target), pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
        title=heading_text,
    )

    currency_parts = [
        f"{cur}: {_('Belopp')} {vals['amount']:,.2f}".replace(",", " ").replace(".", ",")
        + f" · {_('Betalt')} {vals['paid']:,.2f}".replace(",", " ").replace(".", ",")
        + f" · {_('Saldo')} {vals['balance']:,.2f}".replace(",", " ").replace(".", ",")
        for cur, vals in sorted(stats["currencies"].items())
    ]
    meta_lines = [
        xml_escape(
            _(
                "Per datum {date} · Antal fakturor: {count} · Påminda fakturor: {reminded} · Totalt antal påminnelser: {reminders}",
                date=day.isoformat(),
                count=stats["invoice_count"],
                reminded=stats["reminded_invoices"],
                reminders=stats["total_reminders"],
            )
        )
    ]
    if currency_parts:
        meta_lines.append(xml_escape("  |  ".join(currency_parts)))

    pdf_headers = [
        _("Fakturanr"),
        _("Kund"),
        _("Fakturadatum"),
        _("Förfallodatum"),
        _("Belopp"),
        _("Betalt"),
        _("Saldo"),
        _("Valuta"),
        _("Påm."),
        _("P1-datum"),
        _("P2-datum"),
        _("Senaste påm."),
        _("Betaldatum"),
        _("Betalstatus"),
    ]
    table_rows = [[Paragraph(xml_escape(label), header_style) for label in pdf_headers]]
    for record in items:
        table_rows.append([
            Paragraph(xml_escape(str(record.get("invoice_no") or "")), cell_style),
            Paragraph(xml_escape(str(record.get("customer") or "")), cell_style),
            Paragraph(xml_escape(_iso_day(record.get("invoice_date"))), cell_style),
            Paragraph(xml_escape(_iso_day(record.get("due_date"))), cell_style),
            Paragraph(xml_escape(number(record.get("amount"))), right_style),
            Paragraph(xml_escape(number(record.get("paid"))), right_style),
            Paragraph(xml_escape(number(record.get("balance"))), right_style),
            Paragraph(xml_escape(str(record.get("currency") or "SEK")), center_style),
            Paragraph(xml_escape(integer_text(record.get("reminder_count"))), center_style),
            Paragraph(xml_escape(_iso_day(record.get("p1_date"))), cell_style),
            Paragraph(xml_escape(_iso_day(record.get("p2_date"))), cell_style),
            Paragraph(xml_escape(_iso_day(record.get("latest_reminder_date"))), cell_style),
            Paragraph(xml_escape(_iso_day(record.get("paid_date"))), cell_style),
            Paragraph(xml_escape(str(record.get("payment_status") or "")), cell_style),
        ])

    col_widths = [
        18 * mm, 44 * mm, 19 * mm, 19 * mm, 20 * mm, 20 * mm, 20 * mm,
        12 * mm, 11 * mm, 19 * mm, 19 * mm, 20 * mm, 19 * mm, 17 * mm,
    ]
    table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))

    story = [
        Paragraph(xml_escape(heading_text), title_style),
        Paragraph("<br/>".join(meta_lines), meta_style),
        Spacer(1, 1 * mm),
        table,
    ]
    doc.build(story)
    return len(items)


def write(
    path: str | Path,
    records: Iterable[Mapping],
    columns=COLUMNS,
    *,
    title: str | None = None,
    export_date: date | None = None,
) -> int:
    """Write records to ``path`` as CSV or PDF depending on the file extension."""
    target = Path(path)
    if target.suffix.lower() == ".pdf":
        return write_pdf(target, records, title=title, export_date=export_date)
    return write_csv(target, records, columns=columns)
