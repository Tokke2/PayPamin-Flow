"""PDF extraction and invoice parsing for PayPamin Flow.

This module deliberately has no Tkinter dependency so parsing can be tested and
reused on headless Windows, macOS and Linux systems.

Copyright © 2026 Rickard Längkvist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

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


def extract_pdf_pages(path):
    """Extract text page by page, retaining OCR support for scanned PDFs."""

    try:
        import fitz
    except ImportError as exc:
        raise ValueError(_('PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf')) from exc
    with fitz.open(path) as doc:
        pages=[page.get_text('text') for page in doc]
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
    r'bankgiro|plusgiro|iban|förfallodatum|due\s*date|payment\s*terms)\b', re.I
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
    # Use a payable gross total, never VAT or an ex-VAT subtotal. Support
    # Fortnox's Swedish labels and common English invoice labels/layouts.
    payable_labels=list(re.finditer(PAYABLE_LABEL_PATTERN,cleaned,re.I))
    amount=_payable_amount(cleaned,payable_labels) or 0.0
    # Prefer the customer postal block: company name immediately above a street address
    # and Swedish postal-code/city line (Fortnox Tadega layout, e.g. Protector Försäkring ASA).
    customer=''
    for i,line in enumerate(lines):
        if re.search(r'\b\d{3}\s?\d{2}\s+[A-Za-zÅÄÖåäö]',line):
            street=''
            for j in range(max(0,i-2),i):
                candidate=lines[j]
                if re.search(r'\d',candidate) and re.search(r'[A-Za-zÅÄÖåäö]',candidate) and not re.search(r'\b(?:FE|BOX|POSTBOX|KUNDNR)\b',candidate,re.I):
                    street=candidate
            if street:
                street_i=lines.index(street)
                for k in range(street_i-1,max(-1,street_i-3),-1):
                    candidate=lines[k].strip()
                    if candidate and not re.search(r'^(?:leveransadress|faktura|fakturanr|fakturanummer|kundnr|er referens|org(?:anis)?ationsnr|telefon|e-?post)\b',candidate,re.I) and not re.search(r'\d{3}\s?\d{2}',candidate):
                        customer=candidate;break
            if customer: break
    # Fallbacks for common labels. Do not treat Kundnr as the customer-name label.
    if not customer:
        cm=re.search(r'(?im)^\s*(?:fakturamottagare|kundnamn|kund\b)\s*[:]?\s*([^\n]{2,80})',cleaned)
        if cm:
            candidate=cm.group(1).strip()
            if not re.fullmatch(r'(?:nr\.?\s*)?\d+',candidate,re.I): customer=candidate
            if not customer:
                after=cleaned[cm.end():].splitlines()
                for ln in after[:4]:
                    ln=ln.strip()
                    if ln and not re.search(r'^(?:kundnr|kundnummer|org(?:anis)?ationsnr|fakturanummer|datum|adress|er referens)\b',ln,re.I) and not re.fullmatch(r'\d+',ln):
                        customer=ln;break
    if not customer:
        m=re.search(r'(?im)^\s*(?:faktureras\s*till|bill\s*to)\s*[:]?\s*([^\n]*)',cleaned)
        if m:
            candidate=m.group(1).strip()
            if candidate:
                customer=candidate
            else:
                for ln in cleaned[m.end():].splitlines()[:4]:
                    ln=ln.strip()
                    if ln and not re.search(r'^(?:kundnr|kundnummer|org(?:anis)?ationsnr|fakturanummer|invoice|date|datum|adress)\b',ln,re.I):
                        customer=ln;break
    # Prefer explicit invoice text and support multiline/table-based descriptions.
    description = _description_from_lines(lines)
    return {'invoice_no':number,'invoice_date':invoice_date,'due_date':due,'amount':amount,'currency':detect_invoice_currency(cleaned,payable_labels),'customer':customer,'note':description}

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
