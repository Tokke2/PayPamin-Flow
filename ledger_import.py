"""Read complete customer ledger lists and reconcile their paid status safely."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from i18n import _

_PAGE_MARKER = re.compile(r"\b(\d{1,4})\s*/\s*(\d{1,4})\b")
_LIST_DATE = re.compile(r"\bPer\s*datum\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_COUNT = re.compile(r"^Antal\s*fakturor\s*(\d+)\s*$", re.IGNORECASE)
_TOTAL = re.compile(r"^Totalsumma\s*i\s*SEK\s*(-?\d[\d\s\u00a0]*,\d{2})\s*$", re.IGNORECASE)
_CUSTOMER = re.compile(r"^(\d[\d-]*)\s+(.+)$")
_INVOICE_LIKE = re.compile(r"^\S+\s+\d{4}-\d{2}-\S{2}\s+")
_INVOICE = re.compile(
    r"^(?P<invoice_no>\d+)\s+"
    r"(?P<invoice_date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<due_date>\d{4}-\d{2}-\d{2})"
    r"(?:\s+(?P<reference>.*?))?\s+"
    r"(?P<currency>[A-Za-z]{3})\s+"
    r"(?P<amount>-?\d[\d\s\u00a0]*,\d{2})\s+"
    r"(?P<balance>-?\d[\d\s\u00a0]*,\d{2})\s*$"
)


class LedgerImportError(RuntimeError):
    """Raised when a ledger cannot be validated without risking paid changes."""


@dataclass(frozen=True)
class LedgerEntry:
    customer_number: str
    customer: str
    invoice_no: str
    invoice_date: str
    due_date: str
    currency: str
    amount: float
    balance: float
    note: str = ""

    @property
    def paid(self) -> float:
        return round(self.amount - self.balance, 2)


@dataclass(frozen=True)
class LedgerReport:
    list_date: str
    entries: tuple[LedgerEntry, ...]
    expected_count: int
    expected_total: float
    actual_total: float
    page_count: int
    total_verified: bool


@dataclass(frozen=True)
class MissingLedgerInvoice:
    invoice_id: int
    invoice_no: str
    customer: str
    amount: float
    currency: str


@dataclass(frozen=True)
class LedgerPaymentUpdate:
    invoice_id: int
    invoice_no: str
    customer: str
    amount: float
    currency: str
    previous_paid: float
    new_paid: float

    @property
    def fully_paid(self) -> bool:
        return self.amount - self.new_paid <= 0.005


@dataclass(frozen=True)
class LedgerDiagnostics:
    """Explain unchanged rows without weakening any reconciliation safeguard."""
    missing_already_paid: int = 0
    missing_without_history: int = 0
    missing_future_dated: int = 0
    listed_already_paid: int = 0
    listed_unchanged: int = 0
    listed_protected: int = 0


@dataclass(frozen=True)
class LedgerPlan:
    new_count: int
    existing_count: int
    missing: tuple[MissingLedgerInvoice, ...]
    previous_list_date: str
    payment_updates: tuple[LedgerPaymentUpdate, ...] = ()
    diagnostics: LedgerDiagnostics = field(default_factory=LedgerDiagnostics)


@dataclass(frozen=True)
class LedgerResult:
    imported: int
    existing: int
    marked_paid: int
    payment_updates: int = 0
    plan: LedgerPlan | None = None


def _amount(value: str) -> Decimal:
    try:
        return Decimal(value.replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise LedgerImportError(_("Ogiltigt belopp i reskontralistan: {value}", value=value)) from exc


def _normalise_invoice_number(value) -> str:
    return "".join(str(value or "").split()).casefold()


def _ordered_pages(page_texts) -> list[str]:
    pages = [str(text or "") for text in page_texts]
    if not pages:
        raise LedgerImportError(_("Inga sidor hittades i reskontralistan."))
    markers = []
    for text in pages:
        matches = _PAGE_MARKER.findall(text)
        markers.append(tuple(map(int, matches[-1])) if matches else None)
    if len(pages) == 1 and markers[0] is None:
        markers[0] = (1, 1)
    if any(marker is None for marker in markers):
        raise LedgerImportError(_("Reskontralistan saknar sidnummer. Välj alla sidor i listan."))
    expected_pages = markers[0][1]
    numbers = sorted(marker[0] for marker in markers)
    if expected_pages != len(pages) or numbers != list(range(1, expected_pages + 1)):
        raise LedgerImportError(_("Reskontralistan är ofullständig. Välj alla sidor från 1 till {pages}.", pages=expected_pages))
    ordered = [text for _marker, text in sorted(zip(markers, pages), key=lambda item: item[0][0])]
    return ordered


def parse_ledger_pages(page_texts) -> LedgerReport:
    """Parse and validate every page before any database change is allowed."""
    pages = _ordered_pages(page_texts)
    entries = []
    unreadable_rows = []
    seen_invoice_numbers = set()
    list_dates = set()
    expected_count = None
    expected_total = None
    pending_count = None
    current_customer = None

    for text in pages:
        lines = [" ".join(line.replace("\u00a0", " ").split()) for line in text.splitlines()]
        for index, line in enumerate(lines):
            if not line:
                continue
            list_date = _LIST_DATE.search(line)
            if list_date:
                list_dates.add(list_date.group(1))
            count = _COUNT.match(line)
            if count:
                pending_count = int(count.group(1))
                continue
            total = _TOTAL.match(line)
            if total:
                expected_total = _amount(total.group(1))
                expected_count = pending_count
                continue
            invoice = _INVOICE.match(line)
            if invoice:
                if current_customer is None:
                    raise LedgerImportError(_("Kund saknas för faktura {invoice_no}.", invoice_no=invoice.group("invoice_no")))
                invoice_no = invoice.group("invoice_no")
                key = _normalise_invoice_number(invoice_no)
                if key in seen_invoice_numbers:
                    raise LedgerImportError(_("Fakturanummer {invoice_no} förekommer flera gånger i reskontralistan.", invoice_no=invoice_no))
                seen_invoice_numbers.add(key)
                entries.append(LedgerEntry(
                    customer_number=current_customer[0],
                    customer=current_customer[1],
                    invoice_no=invoice_no,
                    invoice_date=invoice.group("invoice_date"),
                    due_date=invoice.group("due_date"),
                    currency=invoice.group("currency").upper(),
                    amount=float(_amount(invoice.group("amount"))),
                    balance=float(_amount(invoice.group("balance"))),
                    note=(invoice.group("reference") or "").strip(),
                ))
                continue
            if _INVOICE_LIKE.match(line):
                unreadable_rows.append(line)
                continue
            customer = _CUSTOMER.match(line)
            if customer:
                next_line = next((candidate for candidate in lines[index + 1:] if candidate), "")
                if _INVOICE.match(next_line) or _INVOICE_LIKE.match(next_line):
                    current_customer = (customer.group(1), customer.group(2).strip())

    if unreadable_rows:
        raise LedgerImportError(_("Fakturaraden kunde inte läsas säkert: {line}", line=unreadable_rows[0]))
    if not entries:
        raise LedgerImportError(_("Inga fakturarader hittades i reskontralistan."))
    if len(list_dates) != 1:
        raise LedgerImportError(_("Reskontralistan måste ha ett entydigt Per datum-värde."))
    if expected_count is None or expected_total is None:
        raise LedgerImportError(_("Reskontralistan saknar totalt fakturaantal eller totalsumma."))
    if len(entries) != expected_count:
        raise LedgerImportError(_("Fakturaantalet stämmer inte: listan anger {expected}, men {actual} rader lästes.", expected=expected_count, actual=len(entries)))

    actual_total = sum((Decimal(str(entry.balance)) for entry in entries), Decimal("0"))
    total_verified = all(entry.currency == "SEK" for entry in entries)
    if total_verified and abs(actual_total - expected_total) > Decimal("0.005"):
        raise LedgerImportError(_("Totalsumman stämmer inte: listan anger {expected} SEK, men radernas saldo är {actual} SEK.", expected=f"{expected_total:.2f}", actual=f"{actual_total:.2f}"))

    return LedgerReport(
        list_date=next(iter(list_dates)),
        entries=tuple(entries),
        expected_count=expected_count,
        expected_total=float(expected_total),
        actual_total=float(actual_total),
        page_count=len(pages),
        total_verified=total_verified,
    )


def _read_pdf(path: Path) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise LedgerImportError(_("PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf")) from exc
    try:
        with fitz.open(path) as document:
            pages = [page.get_text("text", sort=True) for page in document]
    except Exception as exc:
        raise LedgerImportError(_("PDF-reskontralistan kunde inte läsas: {error}", error=exc)) from exc
    if not any(text.strip() for text in pages):
        raise LedgerImportError(_("Ingen läsbar text hittades i PDF:en."))
    return pages


def read_ledger_report(path) -> LedgerReport:
    """Read one text-based Fortnox PDF and validate every printed page."""
    if not path:
        raise LedgerImportError(_("Välj en reskontralista först."))
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".pdf":
        raise LedgerImportError(_("Filtypen stöds inte för reskontralistor: {suffix}", suffix=path.suffix))
    return parse_ledger_pages(_read_pdf(path))


def ensure_ledger_schema(db: sqlite3.Connection) -> None:
    """Add persistent first/last-seen markers without altering reminder data."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(invoices)").fetchall()}
    for column in ("ledger_first_seen", "ledger_last_seen"):
        if column not in columns:
            db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "paid_before_marking" not in columns:
        db.execute("ALTER TABLE invoices ADD COLUMN paid_before_marking REAL")
    for column in ("paid_marked_at", "paid_marked_source"):
        if column not in columns:
            db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def _previous_list_date(db) -> str:
    table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
    if table is None:
        return ""
    row = db.execute("SELECT value FROM settings WHERE key='ledger_last_list_date'").fetchone()
    return str(row[0] or "") if row else ""


def _present_payment_update(row, entry: LedgerEntry):
    """Return a safe paid-amount increase for an invoice present in the list."""
    amount = float(row["amount"] or 0)
    previous_paid = float(row["paid"] or 0)
    if amount - previous_paid <= 0.005:
        return None
    currency = str(row["currency"] or "SEK").strip().upper()
    if currency != entry.currency:
        return None
    if entry.balance <= 0.005:
        # A zero balance is authoritative even if the app's historic amount was corrected.
        new_paid = amount
    else:
        # Do not guess a partial payment across differing historic invoice amounts.
        if abs(amount - entry.amount) > 0.005:
            return None
        new_paid = round(entry.paid, 2)
    if new_paid - previous_paid <= 0.005:
        return None
    return LedgerPaymentUpdate(
        invoice_id=int(row["id"]), invoice_no=str(row["invoice_no"]),
        customer=str(row["customer"]), amount=amount, currency=currency,
        previous_paid=previous_paid, new_paid=new_paid,
    )


def _plan(db, report: LedgerReport) -> LedgerPlan:
    ensure_ledger_schema(db)
    previous = _previous_list_date(db)
    if previous and report.list_date < previous:
        raise LedgerImportError(_("En äldre reskontralista kan inte ersätta den senaste betalavstämningen."))
    rows = db.execute("SELECT * FROM invoices").fetchall()
    by_number = {}
    for row in rows:
        by_number.setdefault(_normalise_invoice_number(row["invoice_no"]), row)
    current = {_normalise_invoice_number(entry.invoice_no) for entry in report.entries}
    existing_count = sum(1 for entry in report.entries if _normalise_invoice_number(entry.invoice_no) in by_number)
    missing = []
    payment_updates = []
    diagnostics = LedgerDiagnostics()
    if report.total_verified:
        listed_already_paid = listed_unchanged = listed_protected = 0
        for entry in report.entries:
            row = by_number.get(_normalise_invoice_number(entry.invoice_no))
            if row is None:
                continue
            update = _present_payment_update(row, entry)
            if update is not None:
                payment_updates.append(update)
                continue
            amount = float(row["amount"] or 0)
            previous_paid = float(row["paid"] or 0)
            currency = str(row["currency"] or "SEK").strip().upper()
            if amount - previous_paid <= 0.005:
                listed_already_paid += 1
            elif currency != entry.currency:
                listed_protected += 1
            elif entry.balance > 0.005 and abs(amount - entry.amount) > 0.005:
                listed_protected += 1
            else:
                listed_unchanged += 1
        missing_already_paid = missing_without_history = missing_future_dated = 0
        for row in rows:
            key = _normalise_invoice_number(row["invoice_no"])
            if key in current:
                continue
            if not row["ledger_first_seen"] or not row["ledger_last_seen"]:
                missing_without_history += 1
                continue
            # Several complete exports can be replaced during the same day.
            # Only a row seen in a future-dated list is incompatible here;
            # older report dates are already rejected against ``previous``.
            if row["ledger_last_seen"] > report.list_date:
                missing_future_dated += 1
                continue
            if float(row["amount"] or 0) - float(row["paid"] or 0) <= 0.005:
                missing_already_paid += 1
                continue
            missing.append(MissingLedgerInvoice(
                invoice_id=int(row["id"]), invoice_no=str(row["invoice_no"]),
                customer=str(row["customer"]), amount=float(row["amount"] or 0),
                currency=str(row["currency"] or "SEK"),
            ))
        diagnostics = LedgerDiagnostics(
            missing_already_paid=missing_already_paid,
            missing_without_history=missing_without_history,
            missing_future_dated=missing_future_dated,
            listed_already_paid=listed_already_paid,
            listed_unchanged=listed_unchanged,
            listed_protected=listed_protected,
        )
    return LedgerPlan(
        len(report.entries) - existing_count, existing_count, tuple(missing), previous,
        tuple(payment_updates), diagnostics,
    )


def plan_ledger_import(database_path, report: LedgerReport) -> LedgerPlan:
    """Preview present-row payment updates and previously seen missing invoices."""
    with closing(sqlite3.connect(str(database_path))) as db:
        db.row_factory = sqlite3.Row
        return _plan(db, report)


def apply_ledger_import(database_path, report: LedgerReport) -> LedgerResult:
    """Atomically insert rows, update listed payments and settle missing invoices."""
    with closing(sqlite3.connect(str(database_path))) as db:
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            plan = _plan(db, report)
            rows = db.execute("SELECT * FROM invoices").fetchall()
            by_number = {_normalise_invoice_number(row["invoice_no"]): row for row in rows}
            created = datetime.now().isoformat(timespec="seconds")
            for entry in report.entries:
                key = _normalise_invoice_number(entry.invoice_no)
                existing = by_number.get(key)
                if existing is not None:
                    first_seen = existing["ledger_first_seen"] or report.list_date
                    db.execute(
                        "UPDATE invoices SET ledger_first_seen=?,ledger_last_seen=? WHERE id=?",
                        (first_seen, report.list_date, existing["id"]),
                    )
                    continue
                db.execute(
                    """INSERT INTO invoices(
                    customer,invoice_no,invoice_date,due_date,template_vendor,amount,currency,paid,
                    email,source,source_hash,note,reviewed,ledger_first_seen,ledger_last_seen,created
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entry.customer, entry.invoice_no, entry.invoice_date, entry.due_date, "",
                        entry.amount, entry.currency, entry.paid, "", "", "", entry.note, 1,
                        report.list_date, report.list_date, created,
                    ),
                )
            for update in plan.payment_updates:
                if update.fully_paid:
                    db.execute(
                        """UPDATE invoices SET paid_before_marking=paid,paid_marked_at=?,
                        paid_marked_source='ledger',paid=? WHERE id=?""",
                        (created, update.new_paid, update.invoice_id),
                    )
                else:
                    db.execute("UPDATE invoices SET paid=? WHERE id=?", (update.new_paid, update.invoice_id))
            for missing in plan.missing:
                db.execute(
                    """UPDATE invoices SET paid_before_marking=paid,paid_marked_at=?,
                    paid_marked_source='ledger',paid=amount WHERE id=?""",
                    (created, missing.invoice_id),
                )
            db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('ledger_last_list_date',?)",
                (report.list_date,),
            )
            db.commit()
            marked_paid = len(plan.missing) + sum(update.fully_paid for update in plan.payment_updates)
            return LedgerResult(
                plan.new_count, plan.existing_count, marked_paid, len(plan.payment_updates), plan,
            )
        except Exception:
            db.rollback()
            raise
