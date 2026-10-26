"""PDF extraction and invoice parsing for PayPamin Flow.

This module deliberately has no Tkinter dependency so parsing can be tested and
reused on headless Windows, macOS and Linux systems.

Copyright © 2026 Rickard Länkvist.
"""
from __future__ import annotations

import re
from datetime import date

from currency import find_currency_code, normalize_currency
from i18n import _

PAYABLE_LABEL_PATTERN = r"(?:summa\s+att\s+betala|totalt\s+att\s+betala|att\s+betala|total\s+amount\s+due|amount\s+due|balance\s+due|total\s+payable|total\s+due|amount\s+to\s+pay)"
TOTAL_LABEL_PATTERN = r"(?:total\s+inkl\.?\s+moms|total\s+inklusive\s+moms|total\s+incl\.?\s+vat|total\s+including\s+vat|totalbelopp|fakturans\s+total|grand\s+total|invoice\s+total)"
AMOUNT_NUMBER_PATTERN = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+|\d+)(?:[.,]\d{1,2})?(?![\d.,])"
)
AMOUNT_STOP_PATTERN = re.compile(r"\b(?:moms|vat|exkl\.?\s+moms|excl\.?\s+vat|subtotal|net\s+total|öresavrundning|rounding)\b", re.I)
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
    return 0.0


def extract_pdf(path):
    """Best-effort text extraction; no silent auto-import of guessed invoice rows."""
    try:
        import fitz
        with fitz.open(path) as doc:
            text='\n'.join(page.get_text('text') for page in doc)
        if not text.strip():
            # Optional OCR fallback for scanned PDFs (requires pytesseract + Tesseract + pdf2image).
            try:
                from pdf2image import convert_from_path
                import pytesseract
                pages=convert_from_path(path, dpi=220)
                text='\n'.join(pytesseract.image_to_string(page, lang='swe+eng') for page in pages)
            except Exception as exc:
                raise ValueError(_('PDF verkar vara skannad. OCR kräver Tesseract, svenska språkdata, pdf2image och Poppler. Se README för installation.')) from exc
        if not text.strip(): raise ValueError(_('Ingen läsbar text hittades i PDF:en.'))
        return text
    except ImportError:
        raise ValueError(_('PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf'))


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
    amount=_payable_amount(cleaned,payable_labels)
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
        m=re.search(r'(?im)^\s*(?:faktureras\s*till|bill\s*to)\s*[:]?\s*([^\n]+)',cleaned)
        if m:customer=m.group(1).strip()
    # Pull the invoice line-item/description into the reminder's "Avser" field where possible.
    description=''
    for i,line in enumerate(lines):
        if re.search(r'\b(?:benämning|beskrivning|artikelbeskrivning|vara/tjänst|description)\b',line,re.I):
            candidates=[]
            for candidate in lines[i+1:i+5]:
                if not candidate: continue
                if re.search(r'\b(?:summa|exkl\.?\s*moms|moms|att\s*betala|total\s*due|amount\s*due|grand\s*total|vat|subtotal|öresavrundning|betalningsvillkor)\b',candidate,re.I): break
                if re.fullmatch(r'[\d.,\s]+(?:kr|sek)?',candidate,re.I): continue
                # Ignore likely numeric table headings, keep the actual item/service description.
                if re.search(r'^(?:artikel|antal|enhet|à[- ]?pris|pris|summa)\b',candidate,re.I): continue
                candidates.append(candidate)
                if len(' '.join(candidates))>240: break
            description=' '.join(candidates).strip()
            if description: break
    if not description:
        description=find_value(r'(?:avser|beskrivning|specifikation|description|service)')
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
