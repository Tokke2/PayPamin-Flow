"""PDF extraction and invoice parsing for PayPamin Flow.

This module deliberately has no Tkinter dependency so parsing can be tested and
reused on headless Windows, macOS and Linux systems.

Copyright © 2026 Rickard Längkvist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from currency import find_currency_code, normalize_currency
from i18n import _

PAYABLE_LABEL_PATTERN = r"(?:summa\s+att\s+betala|totalt\s+att\s+betala|att\s+betala|total\s+amount\s+due|amount\s+due|balance\s+due|total\s+payable|total\s+due|amount\s+to\s+pay)"
TOTAL_LABEL_PATTERN = r"(?:(?:total|totalt|summa)\s+inkl\.?\s+moms|(?:total|totalt|summa)\s+inklusive\s+moms|fakturabelopp\s+inkl\.?\s+moms|total\s+incl\.?\s+vat|total\s+including\s+vat|totalbelopp|fakturans\s+total(?:belopp)?|grand\s+total|invoice\s+total)"
AMOUNT_NUMBER_PATTERN = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+|\d+)(?:[.,]\d{1,2})?(?![\d.,])"
)
AMOUNT_STOP_PATTERN = re.compile(r"\b(?:moms|vat|exkl\.?\s+moms|excl\.?\s+vat|subtotal|netto|net|net\s+total|öresavrundning|rounding)\b", re.I)
AMOUNT_SKIP_PATTERN = re.compile(r"\b(?:fakturanummer|fakturanr|fakturadatum|förfallodatum|invoice\s*(?:no\.?|number)|invoice\s*date|due\s*date|kundnr|kundnummer|customer\s*(?:no\.?|number)|org\.?\s*nr|referens|reference)\b|\b(?:invoice|faktura)\s*#", re.I)


def _amounts_in_line(line):
    """Yield plausible money values, excluding dates, percentages and fragments."""
    for match in AMOUNT_NUMBER_PATTERN.finditer(line):
        before = line[:match.start()].rstrip()
        after = line[match.end():].lstrip()
        if before.endswith(("-", "/")) or after.startswith(("-", "/")):
            continue
        if after.startswith("%"):
            continue
        yield match


def _amount_from_fragment(fragment, *, last=False):
    """Read an amount near a total label without crossing into VAT/subtotals."""
    found = []
    for raw_line in fragment.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if AMOUNT_SKIP_PATTERN.search(line):
            continue
        stop = AMOUNT_STOP_PATTERN.search(line)
        if stop:
            # A total on the same line before the VAT label is still valid;
            # otherwise the payable section has ended and guessing must stop.
            line = line[:stop.start()].strip()
            if not line:
                break
        matches = list(_amounts_in_line(line))
        if matches:
            found.extend(matches)
            if not last:
                break
        if stop:
            break
    if not found:
        return None
    match = found[-1] if last else found[0]
    return normalize_amount(match.group(0))


def _amount_near_label(text, label):
    tail = text[label.end():label.end() + 700]
    amount = _amount_from_fragment(tail)
    if amount is not None:
        return amount
    line_start = text.rfind("\n", 0, label.start()) + 1
    prefix = text[line_start:label.start()]
    return _amount_from_fragment(prefix, last=True)


def _payable_amount(text, payable_labels):
    for label in reversed(payable_labels):
        amount = _amount_near_label(text, label)
        if amount is not None:
            return amount
    for label in reversed(list(re.finditer(TOTAL_LABEL_PATTERN, text, re.I))):
        amount = _amount_near_label(text, label)
        if amount is not None:
            return amount
    return None


def parse_amount_value(text):
    """Return a labelled payable amount or one unambiguous amount from a field zone.

    Multiple unlabelled numbers are rejected so a VAT/net column cannot silently
    replace a previously reviewed amount. A labelled zero remains a valid value.
    """
    cleaned='\n'.join(re.sub(r'\s+',' ',line).strip() for line in str(text or '').splitlines())
    payable_labels=list(re.finditer(PAYABLE_LABEL_PATTERN,cleaned,re.I))
    if payable_labels or re.search(TOTAL_LABEL_PATTERN,cleaned,re.I):
        return _payable_amount(cleaned,payable_labels)
    matches=[]
    for raw_line in cleaned.splitlines():
        line=raw_line.strip()
        if not line or AMOUNT_SKIP_PATTERN.search(line) or AMOUNT_STOP_PATTERN.search(line):
            continue
        matches.extend(_amounts_in_line(line))
    if len(matches)!=1:
        return None
    return normalize_amount(matches[0].group(0))


@dataclass(frozen=True)
class InvoiceSection:
    """One invoice and its zero-based page indexes in the source PDF."""

    page_indexes: tuple[int, ...]
    text: str


def _spatial_header_columns_from_fitz_page(page):
    """Return de-interleaved (right_column_text, left_column_text) from a PDF page."""
    if not hasattr(page, 'rect') or not hasattr(page, 'get_text'):
        return '', ''
    width = float(getattr(page.rect, 'width', 0.0) or 0.0)
    height = float(getattr(page.rect, 'height', 0.0) or 0.0)
    if width <= 0 or height <= 0:
        return '', ''
    data = page.get_text('dict')
    if not isinstance(data, dict):
        return '', ''
    right_lines = []
    left_lines = []
    split_x = width * 0.42
    max_y = height * 0.52
    for block in data.get('blocks', ()):
        if block.get('type', 0) != 0:
            continue
        for line in block.get('lines', ()):
            bbox = line.get('bbox') or (0.0, 0.0, 0.0, 0.0)
            x0, y0 = float(bbox[0]), float(bbox[1])
            if y0 > max_y:
                continue
            text = re.sub(
                r'\s+', ' ',
                ''.join(span.get('text', '') for span in line.get('spans', ())),
            ).strip()
            if not text:
                continue
            item = (round(y0 / 2.0) * 2.0, x0, text)
            if x0 >= split_x:
                right_lines.append(item)
            else:
                left_lines.append(item)
    right_lines.sort(key=lambda entry: (entry[0], entry[1]))
    left_lines.sort(key=lambda entry: (entry[0], entry[1]))
    return (
        '\n'.join(entry[2] for entry in right_lines),
        '\n'.join(entry[2] for entry in left_lines),
    )


def _extract_single_fitz_page(page):
    raw_text = page.get_text('text')
    if not raw_text.strip():
        return raw_text
    need_customer = not extract_customer_name(raw_text)
    need_terms = not extract_payment_terms(raw_text)
    if not need_customer and not need_terms:
        return raw_text
    right_col, left_col = _spatial_header_columns_from_fitz_page(page)
    extras = []
    if need_customer:
        for col_text in (right_col, left_col):
            if col_text:
                spatial_customer = extract_customer_name(col_text)
                if spatial_customer:
                    extras.append(f'Fakturaadress: {spatial_customer}')
                    break
    if need_terms:
        for col_text in (left_col, right_col):
            if col_text:
                spatial_terms = extract_payment_terms(col_text)
                if spatial_terms:
                    extras.append(f'Betalningsvillkor: {spatial_terms}')
                    break
    if extras:
        return raw_text.rstrip() + '\n' + '\n'.join(extras) + '\n'
    return raw_text


def extract_pdf_pages(path):
    """Extract text page by page, retaining OCR support for scanned PDFs."""

    try:
        import fitz
    except ImportError as exc:
        raise ValueError(_('PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf')) from exc
    with fitz.open(path) as doc:
        pages=[_extract_single_fitz_page(page) for page in doc]
    if not any(text.strip() for text in pages):
        # Optional OCR fallback for scanned PDFs (requires pytesseract + Tesseract + pdf2image).
        try:
            from pdf2image import convert_from_path
            import pytesseract
            images=convert_from_path(path, dpi=220)
            pages=[pytesseract.image_to_string(image, lang='swe+eng') for image in images]
        except Exception as exc:
            raise ValueError(_('PDF verkar vara skannad. OCR kräver Tesseract, svenska språkdata, pdf2image och Poppler. Se README för installation.')) from exc
    if not any(text.strip() for text in pages):
        raise ValueError(_('Ingen läsbar text hittades i PDF:en.'))
    return pages


def extract_pdf(path):
    """Best-effort text extraction retained for single-invoice callers."""

    return '\n'.join(extract_pdf_pages(path))


_EXPLICIT_PAGE_RE = re.compile(
    r'\b(?:sida|sid\.?|page)\s*[:.#-]?\s*(\d{1,3})\s*(?:av|of|/|\()\s*(\d{1,3})\)?',
    re.I,
)
_BARE_PAGE_LINE_RE = re.compile(r'^(\d{1,2})\s*(?:\(\s*(\d{1,2})\s*\)|/\s*(\d{1,2}))$')
_CONTINUATION_WORD_RE = re.compile(
    r'\b(?:fortsättning|forts\.|continuation|continued|överfört|transport)\b',
    re.I,
)
_NEXT_PAGE_HINT_RE = re.compile(
    r'\b(?:fortsätter\s+på\s+nästa\s+sida|continued\s+on\s+next\s+page)\b',
    re.I,
)


def _page_position(text):
    """Return ``(current_page, total_pages)`` when stated on the page, else None."""
    explicit = _EXPLICIT_PAGE_RE.search(text)
    if explicit:
        cur, tot = int(explicit.group(1)), int(explicit.group(2))
        if 1 <= cur <= tot <= 200:
            return (cur, tot)
    non_empty = [line.strip() for line in str(text or '').splitlines() if line.strip()]
    edge_lines = non_empty[:8] + non_empty[-8:]
    for line in edge_lines:
        bare = _BARE_PAGE_LINE_RE.fullmatch(line)
        if bare:
            cur = int(bare.group(1))
            tot = int(bare.group(2) or bare.group(3))
            if 1 <= cur <= tot <= 50:
                return (cur, tot)
    return None


def _continuation_page(text):
    pos = _page_position(text)
    if pos is not None and pos[0] > 1:
        return True
    return bool(_CONTINUATION_WORD_RE.search(text))


def _expects_next_page(text):
    pos = _page_position(text)
    if pos is not None and pos[0] < pos[1]:
        return True
    return bool(_NEXT_PAGE_HINT_RE.search(text))


def split_invoice_pages(page_texts):
    """Split a PDF into individual invoices: 1 invoice per page unless stated otherwise.

    Pages stay grouped as one multi-page invoice only when stated:
    - the same invoice number is repeated across pages,
    - a page states continuation (e.g. ``Sida 2 av 2``, ``2(2)``, ``2/2``,
      ``Page 2 of 2``, ``Fortsättning``, ``Continued``),
    - the previous page stated ``Sida 1 av 2`` / ``Fortsätter på nästa sida``, or
    - the previous page had an invoice number without any payable total yet and
      the next page is an unnumbered specification/total overflow page.
    Otherwise each non-blank page becomes its own invoice.
    """

    sections = []
    page_texts = list(page_texts)
    current = []
    current_number = ''
    current_complete = False
    prev_expects_more = False
    prev_explicitly_finished = False

    def finish():
        if current:
            sections.append(InvoiceSection(tuple(current), '\n'.join(str(page_texts[index]) for index in current)))

    for index, text in enumerate(page_texts):
        text = str(text)
        if not text.strip():
            if current:
                current.append(index)
            continue
        page_guess = parse_invoice_text(text)
        number = page_guess.get('invoice_no', '')
        normalized = ''.join(number.split()).casefold()
        current_normalized = ''.join(current_number.split()).casefold()
        pos = _page_position(text)
        has_total = bool(re.search(rf'(?:{PAYABLE_LABEL_PATTERN}|{TOTAL_LABEL_PATTERN})', text, re.I))

        if current:
            if normalized and current_normalized:
                if normalized != current_normalized:
                    is_continuation = False
                else:
                    is_continuation = not (pos is not None and pos[0] == 1 and prev_explicitly_finished)
            elif pos is not None and pos[0] == 1:
                is_continuation = False
            elif _continuation_page(text):
                is_continuation = True
            elif prev_expects_more and not normalized:
                is_continuation = True
            elif (
                bool(current_normalized)
                and not normalized
                and not current_complete
                and not prev_explicitly_finished
                and not page_guess.get('invoice_date')
                and not page_guess.get('due_date')
            ):
                is_continuation = True
            else:
                # Default rule: 1 invoice per page unless stated otherwise.
                is_continuation = False

            if not is_continuation:
                finish()
                current = []
                current_number = ''
                current_complete = False
                prev_expects_more = False
                prev_explicitly_finished = False

        current.append(index)
        if number:
            current_number = number
        if has_total:
            current_complete = True
        prev_expects_more = _expects_next_page(text)
        prev_explicitly_finished = bool(pos is not None and pos[0] >= pos[1])
    finish()
    return sections


def extract_invoice_sections(path):
    """Return every invoice in a PDF, including invoices spanning pages."""

    return split_invoice_pages(extract_pdf_pages(path))


def detect_invoice_currency(text,payable_labels=()):
    """Suggest a currency near the payable total, defaulting safely to SEK."""
    explicit=re.search(r'(?i)\b(?:valuta|currency)\s*[:#-]?\s*([A-Za-z]{3})\b',text)
    if explicit:
        code=normalize_currency(explicit.group(1),default='')
        if code:return code
    for label in reversed(payable_labels):
        context=text[max(0,label.start()-120):label.end()+700]
        code=find_currency_code(context)
        if code:return code
        if '€' in context:return 'EUR'
        if '£' in context:return 'GBP'
    for line in text.splitlines():
        if re.search(r'\d',line):
            code=find_currency_code(line)
            if code:return code
    return 'SEK'


NOTE_PRIMARY_LABEL_PATTERN = re.compile(r'^\s*(?:fakturatext|avser)\b\s*[:#-]?\s*(.*)$', re.I)
NOTE_GENERIC_LABEL_PATTERN = re.compile(r'^\s*(?:specifikation|description|service)\b\s*[:#-]?\s*(.*)$', re.I)
NOTE_TABLE_HEADER_PATTERN = re.compile(r'\b(?:benämning|beskrivning|artikelbeskrivning|vara/tjänst|description)\b', re.I)
NOTE_STOP_PATTERN = re.compile(
    r'\b(?:summa|exkl\.?\s*moms|moms|att\s*betala|total\s*due|amount\s*due|'
    r'grand\s*total|totalt|totalbelopp|vat|subtotal|netto|net|öresavrundning|betalningsvillkor|'
    r'bankgiro|plusgiro|iban|förfallodatum|due\s*date|payment\s*terms|fakturaadress)\b', re.I
)
NOTE_NUMBER_ONLY_PATTERN = re.compile(
    r'^[\d\s.,:;+%()/\\-]+(?:\s*(?:kr|sek|eur|usd|gbp|nok|dkk|jpy|chf|pln|czk|huf))?$', re.I
)


def _clean_note_line(line):
    line = re.sub(r'\s+', ' ', str(line or '')).strip()
    line = re.sub(
        r'^(?:fakturatext|avser|specifikation|description|service)\b\s*[:#-]?\s*',
        '', line, flags=re.I
    ).strip()
    if not line or NOTE_NUMBER_ONLY_PATTERN.fullmatch(line) or NOTE_TABLE_HEADER_PATTERN.fullmatch(line):
        return ''
    if re.match(r'^(?:artikel|antal|enhet|à[- ]?pris|pris|summa)\b', line, re.I):
        return ''

    # In a table row, retain the wording before the first decimal/currency amount.
    # A bare year such as 2026 is not treated as a price and is therefore preserved.
    for match in _amounts_in_line(line):
        token = match.group(0)
        after = line[match.end():].lstrip()
        decimal_amount = bool(re.search(r'[.,]\d{1,2}$', token))
        currency_after = bool(re.match(
            r'(?:kr|sek|eur|usd|gbp|nok|dkk|jpy|chf|pln|czk|huf)\b|[€£]',
            after, re.I
        ))
        prefix = line[:match.start()].strip(' \t;,-')
        if (decimal_amount or currency_after) and re.search(r'[A-Za-zÅÄÖåäö]', prefix):
            line = prefix
            break

    line = re.sub(r'^[A-Z]{1,5}\d[A-Z0-9./-]*\s+', '', line)
    line = re.sub(
        r'^\d+(?:[.,]\d+)?\s+(?:st|stk|stycke|stycken|timmar?|tim|dagar?|mån|månader|pcs?|hrs?|hours?)\s+',
        '', line, flags=re.I
    ).strip(' \t;,-')
    if not line or NOTE_NUMBER_ONLY_PATTERN.fullmatch(line):
        return ''
    return line


def clean_invoice_note(text, max_lines=8):
    """Clean an invoice-text zone without inventing or completing missing text."""
    parts = []
    for raw_line in str(text or '').splitlines():
        if NOTE_STOP_PATTERN.search(raw_line):
            break
        line = _clean_note_line(raw_line)
        if not line:
            continue
        parts.append(line)
        if len(parts) >= max_lines or len(' '.join(parts)) >= 300:
            break
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()[:300].strip()


def _description_from_lines(lines):
    """Prefer explicit Avser/fakturatext, then use conservative table extraction."""
    for index, line in enumerate(lines):
        match = NOTE_PRIMARY_LABEL_PATTERN.match(line)
        if match:
            note = clean_invoice_note('\n'.join([match.group(1)] + lines[index + 1:index + 7]))
            if note:
                return note

    for index, line in enumerate(lines):
        if NOTE_TABLE_HEADER_PATTERN.search(line):
            note = clean_invoice_note('\n'.join(lines[index + 1:index + 9]))
            if note:
                return note

    for index, line in enumerate(lines):
        match = NOTE_GENERIC_LABEL_PATTERN.match(line)
        if match:
            note = clean_invoice_note('\n'.join([match.group(1)] + lines[index + 1:index + 7]))
            if note:
                return note
    return ''


_INVOICE_TITLE_ONLY_RE = re.compile(
    r'^(?:faktura|kontantfaktura|kreditfaktura|debetfaktura|samlingsfaktura|delfaktura|'
    r'invoice|tax\s+invoice|credit\s+note)(?:\s+(?:nr\.?\s*|#\s*)?[A-Z0-9./-]+)?$',
    re.I,
)
_BILLING_HEADER_ONLY_RE = re.compile(
    r'^(?:fakturaadress|faktureringsadress|fakturamottagare|kundens\s+namn|kundnamn|'
    r'mottagare|k[oö]pare|betalare|faktureras\s*till|kund|bill\s*to|billed\s*to|'
    r'invoice\s*to|customer(?:\s+name)?)\s*[:#-]?\s*$',
    re.I,
)
_DELIVERY_HEADER_ONLY_RE = re.compile(
    r'^(?:leveransadress|godsadress|levereras\s*till|h[äa]mtningsadress|skadeplats|'
    r'delivery\s*address|ship(?:ping)?\s*to)\s*[:#-]?\s*$',
    re.I,
)
_INLINE_CUSTOMER_LABEL_RE = re.compile(
    r'^(?:fakturaadress|faktureringsadress|fakturamottagare|kundens\s+namn|kundnamn|'
    r'mottagare|k[oö]pare|betalare|faktureras\s*till|'
    r'kund\b(?!\s*(?:nr|nummer|kontakt|kod|kategori|typ|grupp|reskontra))|'
    r'bill\s*to|billed\s*to|invoice\s*to|'
    r'customer(?:\s+name)?\b(?!\s*(?:no|number|id|code|ledger)))\s*[:#-]?\s*(.*)$',
    re.I,
)
_POSTAL_CITY_LINE_RE = re.compile(
    r'^(?:(?:(?:SE|S|FI|DE|FR|PL)\s*-?\s*)?\d{3}\s?\d{2}|(?:NO|N|DK|CH|AT|BE|NL)\s*-\s*\d{4})'
    r'\s+[A-Za-zÅÄÖåäöÆØÅæøåÜüß][A-Za-zÅÄÖåäöÆØÅæøåÜüß\s./-]{1,}$'
)
_POSTAL_FAKE_UNIT_RE = re.compile(
    r'^\S+(?:\s+\S+)?\s+(?:kr|sek|eur|usd|gbp|nok|dkk|st|stk|styck|tim|timmar|moms|exkl|inkl)\b',
    re.I,
)
_BODY_OR_FOOTER_START_RE = re.compile(
    r'^(?:artikel(?:nr|nummer)?\b|art\.?\s*nr\b|ben[äa]mning\b|specifikation\b|'
    r'vara/tj[äa]nst\b|beskrivning\b|description\b|avser\b|fakturatext\b|'
    r'att\s+betala\b|summa\s+att\s+betala\b|totalt\s+att\s+betala\b|'
    r'total\s+due\b|amount\s+due\b|grand\s+total\b|'
    r'postadress\b|bes[öo]ksadress\b|utdelningsadress\b|'
    r'godk[äa]nd\s+f[öo]r\s+f-?skatt|innehar\s+f-?skatt|styrelsens\s+s[äa]te|'
    r'bankgiro\b|plusgiro\b|iban\b)',
    re.I,
)
_METADATA_STOP_RE = re.compile(
    r'^(?:faktura|kontantfaktura|kreditfaktura|debetfaktura|samlingsfaktura|delfaktura|'
    r'invoice|tax\s+invoice|credit\s+note|fakturanr|fakturanummer|invoice\s*(?:no|number|#)|'
    r'fakturadatum|fakturadato|invoice\s*date|f[oö]rfallodatum|f[oö]rfallodag|f[oö]rfaller|'
    r'due\s*date|kundnr|kundnummer|customer\s*(?:no|number|id)|'
    r'er\s+referens|v[åa]r\s+referens|ert\s+ordernr|v[åa]rt\s+ordernr|ordernr|ordernummer|'
    r'betalningsvillkor|payment\s*terms|dr[öo]jsm[åa]lsr[äa]nta|leveransvillkor|leveranss[äa]tt|'
    r'leveransdatum|org\.?\s*nr|organisationsnr|organisationsnummer|momsreg|vat\s*(?:no|reg)|'
    r'reg\.?\s*nr|skadenr|skadenummer|telefon|tel\.?\b|v[äa]xel|e-?post|email|hemsida|webb|'
    r'www\.|ocr\b|sida\s+\d|page\s+\d)\b',
    re.I,
)
_ADDRESS_SUBLINE_RE = re.compile(
    r'^(?:c/o\b|att\.?\s*[: ]|box\s+\d|postbox\s+\d|p\.?o\.?\s*box\b|fe\s+\d|skador\s+fe\s+\d)',
    re.I,
)
_TRAILING_COLUMN_METADATA_RE = re.compile(
    r'\s+(?:fakturanummer|fakturanr|fakturadatum|f[oö]rfallodatum|kundnr|kundnummer|'
    r'v[åa]r\s+referens|er\s+referens|org\.?\s*nr|betalningsvillkor|'
    r'invoice\s*(?:no\.?|number|date|#)|due\s*date|customer\s*(?:no\.?|number))\b.*$',
    re.I,
)
_DATE_OR_PAGE_ONLY_RE = re.compile(
    r'^(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d+\s*(?:/|\()\s*\d+\)?)$'
)


def _is_postal_city_line(line):
    return bool(_POSTAL_CITY_LINE_RE.match(line)) and not bool(_POSTAL_FAKE_UNIT_RE.match(line))


def _clean_customer_candidate(raw):
    candidate = re.sub(r'\s+', ' ', str(raw or '')).strip(' \t:;-')
    if not candidate:
        return ''
    candidate = _TRAILING_COLUMN_METADATA_RE.sub('', candidate).strip(' \t:;-')
    if not candidate or len(candidate) < 2:
        return ''
    if re.fullmatch(r'(?:nr\.?\s*|#\s*)?[\d\s./-]+', candidate, re.I):
        return ''
    if _DATE_OR_PAGE_ONLY_RE.match(candidate) or _is_postal_city_line(candidate):
        return ''
    if (
        _BILLING_HEADER_ONLY_RE.match(candidate)
        or _DELIVERY_HEADER_ONLY_RE.match(candidate)
        or _METADATA_STOP_RE.match(candidate)
        or _BODY_OR_FOOTER_START_RE.match(candidate)
        or _ADDRESS_SUBLINE_RE.match(candidate)
    ):
        return ''
    if not re.search(r'[A-Za-zÅÄÖåäöÆØÅæøå]', candidate):
        return ''
    return candidate[:100]


def _sender_header_key(non_empty_lines):
    """Detect a top-of-page supplier title immediately preceding 'Faktura' / 'Invoice'."""
    if len(non_empty_lines) < 2:
        return ''
    first = non_empty_lines[0]
    if _BILLING_HEADER_ONLY_RE.match(first) or _INLINE_CUSTOMER_LABEL_RE.match(first):
        return ''
    for probe in non_empty_lines[1:4]:
        if _INVOICE_TITLE_ONLY_RE.match(probe):
            return first.casefold()
    return ''


def extract_customer_name(text_or_lines):
    """Extract the billing customer name from Swedish/English invoice text."""
    if isinstance(text_or_lines, str):
        raw_lines = text_or_lines.splitlines()
    else:
        raw_lines = list(text_or_lines)
    lines = [re.sub(r'\s+', ' ', str(ln or '')).strip() for ln in raw_lines]
    non_empty = [ln for ln in lines if ln]
    sender_key = _sender_header_key(non_empty)

    header_lines = []
    for ln in non_empty:
        if _BODY_OR_FOOTER_START_RE.match(ln):
            break
        header_lines.append(ln)
        if len(header_lines) >= 45:
            break

    labelled_postal_customers = []
    unlabelled_postal_customers = []
    for idx, line in enumerate(header_lines):
        if not _is_postal_city_line(line):
            continue
        block = []
        is_billing = False
        is_delivery = False
        for up in range(idx - 1, max(-1, idx - 6), -1):
            prev = header_lines[up]
            if _BILLING_HEADER_ONLY_RE.match(prev):
                is_billing = True
                break
            if _DELIVERY_HEADER_ONLY_RE.match(prev):
                is_delivery = True
                break
            if (
                _is_postal_city_line(prev)
                or _METADATA_STOP_RE.match(prev)
                or _DATE_OR_PAGE_ONLY_RE.match(prev)
                or _INLINE_CUSTOMER_LABEL_RE.match(prev)
            ):
                if _INLINE_CUSTOMER_LABEL_RE.match(prev):
                    inline_match = _INLINE_CUSTOMER_LABEL_RE.match(prev)
                    inline_val = _clean_customer_candidate(inline_match.group(1))
                    if inline_val:
                        block.append(inline_val)
                        is_billing = True
                break
            if sender_key and prev.casefold() == sender_key and up == 0:
                break
            block.append(prev)
        block.reverse()
        if is_delivery or not block:
            continue
        # An unlabelled postal block needs at least [customer_name, street_or_box]
        # above the postal-code line so a single interleaved street line is never
        # mistaken for a customer name.
        if not is_billing and len(block) < 2:
            continue
        chosen = ''
        for entry in block:
            cleaned_entry = _clean_customer_candidate(entry)
            if not cleaned_entry:
                continue
            if not is_billing and sender_key and cleaned_entry.casefold() == sender_key:
                continue
            chosen = cleaned_entry
            break
        if chosen:
            if is_billing:
                labelled_postal_customers.append(chosen)
            else:
                unlabelled_postal_customers.append(chosen)

    if labelled_postal_customers:
        return labelled_postal_customers[0]

    # Explicit customer/billing labels (both header and full text for appended spatial hints).
    for scan_pool in (header_lines, non_empty):
        for idx, line in enumerate(scan_pool):
            match = _INLINE_CUSTOMER_LABEL_RE.match(line)
            if not match:
                continue
            inline_candidate = _clean_customer_candidate(match.group(1))
            if inline_candidate:
                return inline_candidate
            for follow in scan_pool[idx + 1:idx + 5]:
                if _DELIVERY_HEADER_ONLY_RE.match(follow) or _METADATA_STOP_RE.match(follow):
                    break
                if _ADDRESS_SUBLINE_RE.match(follow):
                    continue
                next_candidate = _clean_customer_candidate(follow)
                if next_candidate:
                    return next_candidate

    if unlabelled_postal_customers:
        return unlabelled_postal_customers[0]
    return ''


def clean_customer_zone_text(text):
    """Extract a clean customer name from a user-drawn PDF preview zone."""
    raw_lines = [re.sub(r'\s+', ' ', ln).strip() for ln in str(text or '').splitlines() if ln.strip()]
    if not raw_lines:
        return ''
    parsed = extract_customer_name(raw_lines)
    if parsed:
        return parsed
    for line in raw_lines:
        match = _INLINE_CUSTOMER_LABEL_RE.match(line)
        if match:
            cleaned = _clean_customer_candidate(match.group(1))
            if cleaned:
                return cleaned
            continue
        cleaned = _clean_customer_candidate(line)
        if cleaned:
            return cleaned
    return raw_lines[0][:100]


_PAYMENT_TERMS_LABEL_RE = re.compile(
    r'^(?:betalningsvillkor|bet\.?\s*villkor|betalvillkor|kredittid|'
    r'payment\s*terms|terms\s+of\s+payment)\s*[:#-]?\s*(.*)$',
    re.I,
)
_PAYMENT_TERMS_TRAILING_STOP_RE = re.compile(
    r'\s+(?:dr[öo]jsm[åa]lsr[äa]nta|r[äa]nta\s+efter|f[oö]rfallodatum|f[oö]rfallodag|'
    r'fakturadatum|fakturanummer|fakturanr|kundnr|kundnummer|v[åa]r\s+referens|'
    r'er\s+referens|leveransvillkor|leveranss[äa]tt|due\s*date|invoice\s*(?:no|number|date)|'
    r'late\s+interest|penalty\s+interest)\b.*$',
    re.I,
)
_PAYMENT_TERMS_VALUE_RE = re.compile(
    r'(?:\b\d{1,3}\s*(?:dagar(?:\s+netto)?|dag|dgr(?:\s+netto)?|d\b|days?(?:\s+net)?|'
    r'kal\.?\s*dagar|bankdagar)\b|'
    r'\bnet(?:to)?\s*\d{1,3}(?:\s*(?:dagar|days?))?\b|'
    r'\b(?:omg[åa]ende|kontant|vid\s+anfordran|f[oö]rskott|autogiro|'
    r'due\s+on\s+receipt|upon\s+receipt|immediate(?:ly)?|cash\s+on\s+delivery)\b)',
    re.I,
)


def _clean_payment_terms_candidate(raw):
    candidate = re.sub(r'\s+', ' ', str(raw or '')).strip(' \t:;,-')
    if not candidate:
        return ''
    candidate = _PAYMENT_TERMS_TRAILING_STOP_RE.sub('', candidate).strip(' \t:;,-')
    if not candidate or len(candidate) > 80:
        return ''
    if _DATE_OR_PAGE_ONLY_RE.match(candidate):
        return ''
    if not _PAYMENT_TERMS_VALUE_RE.search(candidate):
        return ''
    return candidate[:80]


def parse_payment_terms_days(terms):
    """Return integer credit days from payment terms (e.g. '30 dagar netto' -> 30)."""
    cleaned = re.sub(r'\s+', ' ', str(terms or '')).strip()
    if not cleaned:
        return None
    if re.search(
        r'\b(?:omg[åa]ende|kontant|vid\s+anfordran|due\s+on\s+receipt|upon\s+receipt|immediate(?:ly)?)\b',
        cleaned, re.I,
    ):
        return 0
    m = re.search(
        r'\b(\d{1,3})\s*(?:dagar|dag|dgr|d\b|days?|kal\.?\s*dagar)\b|\bnet(?:to)?\s*(\d{1,3})\b',
        cleaned, re.I,
    )
    if not m:
        return None
    days = int(m.group(1) or m.group(2))
    return days if 0 <= days <= 365 else None


def extract_payment_terms(text_or_lines):
    """Extract payment terms (e.g. '30 dagar netto', '10 dagar', 'Net 30') from invoice text."""
    if isinstance(text_or_lines, str):
        raw_lines = text_or_lines.splitlines()
    else:
        raw_lines = list(text_or_lines)
    lines = [re.sub(r'\s+', ' ', str(ln or '')).strip() for ln in raw_lines if str(ln or '').strip()]
    for idx, line in enumerate(lines):
        match = _PAYMENT_TERMS_LABEL_RE.match(line)
        if not match:
            # Also support mid-line label in multi-column text, e.g.
            # "Fakturadatum 2026-11-01 Betalningsvillkor: 30 dagar netto"
            inline = re.search(
                r'\b(?:betalningsvillkor|bet\.?\s*villkor|betalvillkor|kredittid|payment\s*terms)\s*[:#-]?\s*([^\n]{1,80})',
                line, re.I,
            )
            if inline:
                cand = _clean_payment_terms_candidate(inline.group(1))
                if cand:
                    return cand
            continue
        cand = _clean_payment_terms_candidate(match.group(1))
        if cand:
            return cand
        for follow in lines[idx + 1:idx + 4]:
            cand = _clean_payment_terms_candidate(follow)
            if cand:
                return cand
    return ''


def clean_payment_terms_zone(text):
    """Clean a user-selected payment-terms zone in the PDF preview."""
    raw_lines = [re.sub(r'\s+', ' ', ln).strip() for ln in str(text or '').splitlines() if ln.strip()]
    if not raw_lines:
        return ''
    parsed = extract_payment_terms(raw_lines)
    if parsed:
        return parsed
    for line in raw_lines:
        stripped = _PAYMENT_TERMS_LABEL_RE.sub(r'\1', line).strip(' \t:;,-')
        cand = _clean_payment_terms_candidate(stripped)
        if cand:
            return cand
        if stripped and not _PAYMENT_TERMS_LABEL_RE.match(line + ':'):
            return stripped[:80]
    return raw_lines[0][:80]


def parse_invoice_text(text):
    """Extract likely fields from Swedish and English invoice PDFs; review all suggestions."""
    lines=[re.sub(r'\s+',' ',ln).strip() for ln in text.splitlines()]
    cleaned='\n'.join(lines)
    def find_value(labels):
        pat=r'(?:'+labels+r')\s*[:#]?\s*(?:\n\s*)?([^\n]{1,100})'
        m=re.search(pat,cleaned,re.I)
        return m.group(1).strip() if m else ''
    # Invoice numbers are sometimes in a header as "Faktura 6258" or under a label.
    number=find_value(r'(?:fakturanummer|faktura\s*(?:nr\.?|nummer|no\.?|#)|invoice\s*(?:no\.?|number|#))')
    if not number:
        m=re.search(r'(?im)^\s*(?:faktura|invoice)\s+([A-Z0-9][A-Z0-9./-]{2,})\s*$',cleaned)
        if m:number=m.group(1)
    number_match=re.search(r'([A-Z0-9][A-Z0-9./-]{2,})',number,re.I)
    number=number_match.group(1) if number_match else ''
    due=find_value(r'(?:f[oö]rfallodatum|f[oö]rfallodag|f[oö]rfaller|due\s*date)')
    dm=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',due)
    due=normalize_date(dm.group(1)) if dm else ''
    issued=find_value(r'(?:fakturadatum|fakturadato|invoice\s*date)')
    im=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',issued)
    invoice_date=normalize_date(im.group(1)) if im else ''
    payment_terms=extract_payment_terms(lines)
    if not due and invoice_date and payment_terms:
        terms_days=parse_payment_terms_days(payment_terms)
        if terms_days is not None:
            due=(date.fromisoformat(invoice_date)+timedelta(days=terms_days)).isoformat()
    # Use a payable gross total, never VAT or an ex-VAT subtotal. Support
    # Fortnox's Swedish labels and common English invoice labels/layouts.
    payable_labels=list(re.finditer(PAYABLE_LABEL_PATTERN,cleaned,re.I))
    amount=_payable_amount(cleaned,payable_labels) or 0.0
    customer=extract_customer_name(lines)
    # Prefer explicit invoice text and support multiline/table-based descriptions.
    description = _description_from_lines(lines)
    return {
        'invoice_no':number,
        'invoice_date':invoice_date,
        'due_date':due,
        'payment_terms':payment_terms,
        'amount':amount,
        'currency':detect_invoice_currency(cleaned,payable_labels),
        'customer':customer,
        'note':description,
    }

def normalize_date(s):
    if not s:return ''
    s=s.replace('.','-').replace('/','-')
    bits=s.split('-')
    try:
        if len(bits[0])==4: return date(int(bits[0]),int(bits[1]),int(bits[2])).isoformat()
        y=int(bits[2]); y=y+2000 if y<100 else y
        return date(y,int(bits[1]),int(bits[0])).isoformat()
    except Exception:return ''


def normalize_amount(s):
    """Normalize Swedish, European and English money notation safely.

    Two trailing digits are treated as decimals. A single comma/dot followed by
    three digits is treated as a thousands separator when the leading group has
    at most three digits; when both separators exist, the last one is decimal.
    """
    if not s:return 0.0
    value=re.sub(r'[\s\u00a0\u202f]','',str(s))
    if not value:return 0.0
    comma=value.rfind(',');dot=value.rfind('.')
    if comma>=0 and dot>=0:
        if comma>dot:value=value.replace('.','').replace(',','.')
        else:value=value.replace(',','')
    elif comma>=0:
        groups=value.split(',')
        if len(groups)>2 and all(len(group)==3 for group in groups[1:]):value=''.join(groups)
        elif len(groups)==2 and len(groups[1])==3 and len(groups[0].lstrip('+-'))<=3:value=''.join(groups)
        else:value=value.replace(',','.')
    elif dot>=0:
        groups=value.split('.')
        if len(groups)>2 and all(len(group)==3 for group in groups[1:]):value=''.join(groups)
        elif len(groups)==2 and len(groups[1])==3 and len(groups[0].lstrip('+-'))<=3:value=''.join(groups)
    try:return float(value)
    except (TypeError,ValueError):return 0.0
