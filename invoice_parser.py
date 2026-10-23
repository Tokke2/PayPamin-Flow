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


def extract_pdf(path):
    """Best-effort text extraction; no silent auto-import of guessed invoice rows."""
    try:
        import fitz
        doc=fitz.open(path)
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
        context=text[label.start():label.start()+700]
        code=find_currency_code(context)
        if code:return code
    for line in text.splitlines():
        if re.search(r'\d',line):
            code=find_currency_code(line)
            if code:return code
    return 'SEK'


def parse_invoice_text(text):
    """Extract likely invoice fields from Swedish invoice PDFs; all suggestions must be reviewed."""
    lines=[re.sub(r'\s+',' ',ln).strip() for ln in text.splitlines()]
    cleaned='\n'.join(lines)
    def find_value(labels):
        pat=r'(?:'+labels+r')\s*[:#]?\s*(?:\n\s*)?([^\n]{1,100})'
        m=re.search(pat,cleaned,re.I)
        return m.group(1).strip() if m else ''
    # Invoice numbers are sometimes in a header as "Faktura 6258" or under a label.
    number=find_value(r'(?:fakturanummer|faktura\s*(?:nr\.?|nummer|no\.?)|invoice\s*(?:no\.?|number))')
    if not number:
        m=re.search(r'(?im)^\s*faktura\s+([A-Z0-9][A-Z0-9./-]{2,})\s*$',cleaned)
        if m:number=m.group(1)
    number_match=re.search(r'([A-Z0-9][A-Z0-9./-]{2,})',number,re.I)
    number=number_match.group(1) if number_match else ''
    due=find_value(r'(?:f[oö]rfallodatum|f[oö]rfallodag|f[oö]rfaller|due\s*date)')
    dm=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',due)
    due=normalize_date(dm.group(1)) if dm else ''
    issued=find_value(r'(?:fakturadatum|fakturadato|invoice\s*date)')
    im=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',issued)
    invoice_date=normalize_date(im.group(1)) if im else ''
    # The reminder must use the payable gross total, not the ex-VAT subtotal.
    # Explicit "Att betala" always wins over line-item sum, net, VAT, or subtotal labels.
    # In Fortnox PDFs the amount and the "ATT BETALA" label can be far apart
    # on the same extracted line because they are laid out in separate columns.
    amount_match=None
    payable_labels=list(re.finditer(r'\batt\s*betala\b',cleaned,re.I))
    amount_pattern=r'(?<!\d)(\d{1,3}(?:[\s.\u00a0\u202f]\d{3})*(?:,\d{2}|\.\d{2})|\d+(?:,\d{2}|\.\d{2}))(?!\d)'
    # Use the final payable label (usually in the totals footer), then the first
    # monetary amount following it, even if PDF text order has large gaps/newlines.
    for label_match in reversed(payable_labels):
        tail=cleaned[label_match.end():label_match.end()+700]
        amount_match=re.search(amount_pattern,tail,re.I)
        if amount_match:break
    if not amount_match:
        amount_patterns=[
            r'(?im)^\s*(?:total\s*(?:inkl\.?\s*moms|inklusive\s*moms)|totalbelopp|fakturans\s*total)\b[^\d\n]{0,50}(?:\n\s*)?(?:SEK|kr)?\s*([\d][\d .]*(?:,\d{2}|\.\d{2}))',
            r'(?im)^\s*(?:summa\s*att\s*betala|totalt\s*att\s*betala)\b[^\d\n]{0,50}(?:\n\s*)?(?:SEK|kr)?\s*([\d][\d .]*(?:,\d{2}|\.\d{2}))',
        ]
        for pattern in amount_patterns:
            amount_match=re.search(pattern,cleaned,re.I)
            if amount_match:break
    amount=normalize_amount(amount_match.group(1)) if amount_match else 0.0
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
        if re.search(r'\b(?:benämning|beskrivning|artikelbeskrivning|vara/tjänst)\b',line,re.I):
            candidates=[]
            for candidate in lines[i+1:i+5]:
                if not candidate: continue
                if re.search(r'\b(?:summa|exkl\.?\s*moms|moms|att\s*betala|öresavrundning|betalningsvillkor)\b',candidate,re.I): break
                if re.fullmatch(r'[\d.,\s]+(?:kr|sek)?',candidate,re.I): continue
                # Ignore likely numeric table headings, keep the actual item/service description.
                if re.search(r'^(?:artikel|antal|enhet|à[- ]?pris|pris|summa)\b',candidate,re.I): continue
                candidates.append(candidate)
                if len(' '.join(candidates))>240: break
            description=' '.join(candidates).strip()
            if description: break
    if not description:
        description=find_value(r'(?:avser|beskrivning|specifikation)')
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
    if not s:return 0.0
    s=re.sub(r'[\s\u00a0\u202f]','',s).replace('.','').replace(',','.')
    try:return float(s)
    except Exception:return 0.0
