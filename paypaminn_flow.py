#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lokal, desktopbaserad svensk fakturapåminnelseapp. Kräver Python 3.10+.
PDF-textavläsning: pip install pymupdf. OCR för skannade PDF: se README.
"""
from __future__ import annotations
import os, re, sqlite3, sys, webbrowser, subprocess, threading, queue, importlib.util, logging, statistics, base64
from logging.handlers import RotatingFileHandler
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP_DIR = Path.home() / ".paminnelseapp"
APP_DIR.mkdir(exist_ok=True)
DB_PATH = APP_DIR / "paminnelseapp.sqlite3"
APP_FOLDER = Path(__file__).resolve().parent
EXPORT_DIR = APP_FOLDER / "export"
EXPORT_DIR.mkdir(exist_ok=True)
SVG_DIR = APP_FOLDER / "svg"
SVG_DIR.mkdir(exist_ok=True)
IMPORT_DIR = APP_FOLDER / "import"
IMPORT_DIR.mkdir(exist_ok=True)
LOG_PATH = APP_DIR / "app.log"
logger = logging.getLogger('paminnelseapp')
logger.setLevel(logging.INFO)
if not logger.handlers:
    log_handler=RotatingFileHandler(LOG_PATH,maxBytes=2_000_000,backupCount=3,encoding='utf-8')
    log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(log_handler)



def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
            due_date TEXT NOT NULL, invoice_date TEXT DEFAULT '', template_vendor TEXT DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 1,
            amount REAL NOT NULL DEFAULT 0, paid REAL NOT NULL DEFAULT 0,
            email TEXT DEFAULT '', source TEXT DEFAULT '', ignored INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '', p1_date TEXT DEFAULT '', p2_date TEXT DEFAULT '', sent_count INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL)""")
        existing={row['name'] for row in db.execute('PRAGMA table_info(invoices)').fetchall()}
        if 'invoice_date' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN invoice_date TEXT DEFAULT ''")
        if 'template_vendor' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN template_vendor TEXT DEFAULT ''")
        if 'reviewed' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 1")
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS pdf_zones (
            vendor TEXT NOT NULL, field TEXT NOT NULL, page_index INTEGER NOT NULL,
            x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL, y1 REAL NOT NULL,
            samples INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(vendor,field))""")
        zone_cols={row['name'] for row in db.execute('PRAGMA table_info(pdf_zones)').fetchall()}
        if 'samples' not in zone_cols:db.execute('ALTER TABLE pdf_zones ADD COLUMN samples INTEGER NOT NULL DEFAULT 1')
        db.execute("""CREATE TABLE IF NOT EXISTS pdf_zone_samples (
            id INTEGER PRIMARY KEY, vendor TEXT NOT NULL, field TEXT NOT NULL, page_index INTEGER NOT NULL,
            x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL, y1 REAL NOT NULL, created TEXT NOT NULL)""")
        db.execute("CREATE TABLE IF NOT EXISTS vendor_logos (vendor TEXT PRIMARY KEY, logo_file TEXT NOT NULL DEFAULT '')")
        defaults={'p1_days':'5','p2_days':'5','p3_days':'5','fee':'150','fee_locked':'0','interest':'23','objection_days':'5','payment_deadline_days':'5','logo_path':'','logo_file':''}
        for k,v in defaults.items():
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))


def setting(key):
    with connect() as db:
        row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row['value'] if row else ''


def set_setting(key,value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,str(value)))


def money(x):
    return f"{x:,.2f}".replace(',',' ').replace('.',',') + ' kr'


def dparse(s):
    try: return date.fromisoformat(s)
    except Exception: return None


def next_stage(row):
    if row['ignored']:return 'Ignorerad'
    if not row['reviewed']:return 'Granska uppgifter'
    if float(row['amount'] or 0)-float(row['paid'] or 0) <= 0.005: return 'Avslutad'
    today=date.today(); due=dparse(row['due_date'])
    if not due: return 'Kontrollera datum'
    if not row['p1_date']:
        return 'P1 att skapa' if (today-due).days >= int(setting('p1_days') or 5) else 'Väntar P1'
    if not row['p2_date']:
        return 'P2 att skapa' if (today-dparse(row['p1_date'])).days >= int(setting('p2_days') or 5) else 'Väntar P2'
    if (today-dparse(row['p2_date'])).days >= int(setting('p3_days') or 5): return 'Kronofogden – granska'
    return 'Väntar – efter P2'


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
                raise ValueError('PDF verkar vara skannad. OCR kräver Tesseract, svenska språkdata, pdf2image och Poppler. Se README för installation.') from exc
        if not text.strip(): raise ValueError('Ingen läsbar text hittades i PDF:en.')
        return text
    except ImportError:
        raise ValueError('PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf')


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
    return {'invoice_no':number,'invoice_date':invoice_date,'due_date':due,'amount':amount,'customer':customer,'note':description}

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


class ReminderApp(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('PayPåminn Flow'); self.geometry('1180x700'); self.minsize(940,560)
        self.configure(bg='#f3f5f8'); self._style(); self.current_filter=tk.StringVar(value='Aktuella')
        self.build(); self.refresh()
        self.after(250,self.check_python_addons)

    def check_python_addons(self):
        """Install required PDF packages in the background only when missing; no terminal window."""
        missing=[]
        if importlib.util.find_spec('fitz') is None: missing.append('PyMuPDF')
        if importlib.util.find_spec('reportlab') is None: missing.append('reportlab')
        if importlib.util.find_spec('pytesseract') is None: missing.append('pytesseract')
        if importlib.util.find_spec('pdf2image') is None: missing.append('pdf2image')
        if importlib.util.find_spec('svglib') is None: missing.append('svglib')
        if not missing:return
        win=tk.Toplevel(self);win.title('Förbereder appen');win.transient(self);win.resizable(False,False)
        win.protocol('WM_DELETE_WINDOW',lambda:None)
        box=ttk.Frame(win,padding=22);box.pack()
        ttk.Label(box,text='Installerar saknade Python-tillägg',font=('Segoe UI',11,'bold')).pack(anchor='w')
        ttk.Label(box,text='Detta behövs för att läsa och skapa PDF. Installationen sker i bakgrunden.').pack(anchor='w',pady=(7,10))
        bar=ttk.Progressbar(box,mode='indeterminate',length=330);bar.pack(fill='x');bar.start(12)
        status=ttk.Label(box,text='Ansluter till Python-pakettjänsten…',style='Sub.TLabel');status.pack(anchor='w',pady=(8,0))
        win.update_idletasks()
        result_queue=queue.Queue()
        def install():
            packages=[]
            if 'PyMuPDF' in missing:packages.append('PyMuPDF>=1.23')
            if 'reportlab' in missing:packages.append('reportlab>=4.0')
            if 'pytesseract' in missing:packages.append('pytesseract')
            if 'pdf2image' in missing:packages.append('pdf2image')
            if 'svglib' in missing:packages.append('svglib>=1.5')
            args=[sys.executable,'-m','pip','install']+packages
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            try:
                proc=subprocess.run(args,capture_output=True,text=True,timeout=300,creationflags=flags)
                if proc.returncode!=0:
                    # Retry for Python installs where user-site installation is required.
                    proc=subprocess.run([sys.executable,'-m','pip','install','--user']+packages,capture_output=True,text=True,timeout=300,creationflags=flags)
                result_queue.put((proc.returncode==0,(proc.stderr or proc.stdout or '').strip()))
            except Exception as exc:result_queue.put((False,str(exc)))
        threading.Thread(target=install,daemon=True).start()
        def poll():
            try:ok,details=result_queue.get_nowait()
            except queue.Empty:
                self.after(250,poll);return
            bar.stop();win.destroy()
            if ok:
                messagebox.showinfo('Tillägg klara','Nödvändiga PDF-tillägg installerades. Appen är redo.',parent=self)
            else:
                messagebox.showerror('Kunde inte installera tillägg','PDF-tilläggen kunde inte installeras automatiskt. Kontrollera internetanslutning och pip.\n\n'+details[-1200:],parent=self)
        self.after(350,poll)

    def _style(self):
        s=ttk.Style(self); s.theme_use('clam')
        s.configure('TFrame',background='#f3f5f8'); s.configure('TLabel',background='#f3f5f8',foreground='#1f2a3d',font=('Segoe UI',10))
        s.configure('Title.TLabel',font=('Segoe UI',19,'bold'),foreground='#263a62')
        s.configure('Sub.TLabel',font=('Segoe UI',9),foreground='#667085')
        s.configure('TButton',font=('Segoe UI',9),padding=(10,7))
        s.configure('Accent.TButton',background='#304b79',foreground='white',font=('Segoe UI',9,'bold'))
        s.map('Accent.TButton',background=[('active','#263d64')])
        s.configure('Treeview',font=('Segoe UI',9),rowheight=30,background='white',fieldbackground='white')
        s.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),background='#e8edf4',foreground='#344054')

    def build(self):
        header=ttk.Frame(self,padding=(22,17,22,10)); header.pack(fill='x')
        ttk.Label(header,text='PayPåminn Flow',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text='Lokal app · dina filer stannar på datorn',style='Sub.TLabel').pack(side='left',padx=16,pady=(8,0))
        ttk.Button(header,text='Inställningar',command=self.settings).pack(side='right')
        bar=ttk.Frame(self,padding=(22,5,22,12)); bar.pack(fill='x')
        for text,cmd,style in [('Skanna importmapp',self.scan_import_folder,'Accent.TButton'),('Öppna importmapp',self.open_import_folder,'TButton'),('Lägg till faktura-PDF',self.import_invoice,'TButton'),('Lägg till manuellt',self.add_invoice,'TButton'),('Skapa påminnelse',self.make_reminder,'TButton'),('Ignorera / återaktivera',self.toggle_ignore,'TButton'),('Redigera vald',self.edit_invoice,'TButton'),('Visa fellogg',self.open_log,'TButton')]: 
            ttk.Button(bar,text=text,command=cmd,style=style).pack(side='left',padx=(0,7))
        controls=ttk.Frame(self,padding=(22,0,22,10));controls.pack(fill='x')
        ttk.Label(controls,text='Visa:').pack(side='left')
        cb=ttk.Combobox(controls,textvariable=self.current_filter,state='readonly',values=['Aktuella','Alla','Ignorerade','Kronofogden – granska'],width=23);cb.pack(side='left',padx=8);cb.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Label(controls,text='Välj en rad för att förhandsgranska / hantera.').pack(side='right')
        logo_bar=ttk.Frame(self,padding=(22,0,22,8));logo_bar.pack(fill='x')
        ttk.Label(logo_bar,text='Logotyp vid export:').pack(side='left')
        self.logo_var=tk.StringVar(value='(Ingen logotyp)')
        self.logo_combo=ttk.Combobox(logo_bar,textvariable=self.logo_var,state='readonly',width=34)
        self.logo_combo.pack(side='left',padx=8)
        self.logo_combo.bind('<<ComboboxSelected>>',self.on_logo_select)
        ttk.Button(logo_bar,text='Uppdatera lista',command=self.refresh_logo_choices).pack(side='left',padx=(0,6))
        ttk.Button(logo_bar,text='Öppna SVG-mapp',command=self.open_svg_folder).pack(side='left')
        self.refresh_logo_choices()
        wrap=ttk.Frame(self,padding=(22,0,22,12));wrap.pack(fill='both',expand=True)
        cols=('invoice_no','customer','due_date','amount','remaining','p1_date','p2_send_date','stage','fee')
        self.tree=ttk.Treeview(wrap,columns=cols,show='headings',selectmode='browse')
        labels={'invoice_no':'Fakturanr','customer':'Kund','due_date':'Förfallodatum','amount':'Fakturabelopp','remaining':'Kvar att betala','p1_date':'P1 skapades','p2_send_date':'P2 ska skickas','stage':'Status / nästa steg','fee':'Påminnelseavgift'}
        widths={'invoice_no':110,'customer':170,'due_date':105,'amount':115,'remaining':120,'p1_date':105,'p2_send_date':120,'stage':190,'fee':120}
        for c in cols:self.tree.heading(c,text=labels[c]);self.tree.column(c,width=widths[c],anchor='w')
        self.tree.pack(side='top',fill='both',expand=True); sb=ttk.Scrollbar(wrap,orient='vertical',command=self.tree.yview);sb.pack(side='right',fill='y');xsb=ttk.Scrollbar(wrap,orient='horizontal',command=self.tree.xview);xsb.pack(side='bottom',fill='x');self.tree.configure(yscrollcommand=sb.set,xscrollcommand=xsb.set)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.show_detail())
        self.tree.bind('<Delete>',lambda e:self.delete_invoice())
        self.tree.bind('<Button-3>',self.show_row_context_menu)
        self.tree.bind('<Button-2>',self.show_row_context_menu)
        self.row_menu=tk.Menu(self,tearoff=0)
        self.row_menu.add_command(label='Redigera faktura',command=self.edit_invoice)
        self.row_menu.add_command(label='Ignorera / återaktivera',command=self.toggle_ignore)
        self.row_menu.add_separator()
        self.row_menu.add_command(label='Ta bort fakturarad',command=self.delete_invoice)
        self.detail=ttk.Label(self,text='Importera PDF eller lägg till en faktura manuellt.',padding=(24,4,24,16),style='Sub.TLabel');self.detail.pack(fill='x')
        foot=ttk.Frame(self,padding=(22,0,22,12));foot.pack(fill='x')
        ttk.Label(foot,text='Startvärden: P1 +5 dagar · P2 +5 dagar · Kronofogden-granskning +5 dagar · avgift 150 kr · ränta 23%',style='Sub.TLabel').pack(side='left')
        ttk.Button(foot,text='Ta bort vald',command=self.delete_invoice).pack(side='right')

    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        with connect() as db: rows=db.execute('SELECT * FROM invoices ORDER BY due_date').fetchall()
        flt=self.current_filter.get()
        for r in rows:
            stage=next_stage(r)
            if flt=='Aktuella' and (r['ignored'] or stage in ('Avslutad','Kronofogden – granska')):continue
            if flt=='Ignorerade' and not r['ignored']:continue
            if flt=='Kronofogden – granska' and stage!='Kronofogden – granska':continue
            remain=max(0,float(r['amount'] or 0)-float(r['paid'] or 0))
            fee=f"{setting('fee')} kr" if r['p1_date'] else '—'
            p1_display=r['p1_date'] or '—'
            if r['ignored'] or remain<=0.005:p2_display='—'
            elif r['p2_date']:p2_display='Skickad '+r['p2_date']
            elif r['p1_date']:
                sent=dparse(r['p1_date'])
                p2_display=(sent+timedelta(days=int(setting('p2_days') or 5))).isoformat() if sent else '—'
            else:p2_display='—'
            self.tree.insert('', 'end',iid=str(r['id']),values=(r['invoice_no'],r['customer'],r['due_date'],money(float(r['amount'] or 0)),money(remain),p1_display,p2_display,('IGNORERAD · ' if r['ignored'] else '')+stage,fee))
        self.show_detail()

    def selected(self):
        sel=self.tree.selection()
        if not sel:messagebox.showinfo('Välj faktura','Markera en faktura i listan först.');return None
        with connect() as db:return db.execute('SELECT * FROM invoices WHERE id=?',(int(sel[0]),)).fetchone()

    def show_detail(self):
        sel=self.tree.selection()
        if not sel:self.detail.configure(text='Importera PDF eller lägg till en faktura manuellt.');return
        with connect() as db:r=db.execute('SELECT * FROM invoices WHERE id=?',(int(sel[0]),)).fetchone()
        if r:
            vendor=r['template_vendor'] or 'Ingen leverantörsmall'
            with connect() as db:logo=db.execute('SELECT logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(vendor,)).fetchone()
            logo_name=logo['logo_file'] if logo and logo['logo_file'] else 'ingen matchad logotyp'
            review='Granskad' if r['reviewed'] else 'KRÄVER GRANSKNING'
            self.detail.configure(text=f"{r['customer']} · {r['invoice_no']} · {next_stage(r)} · {review} · Mall: {vendor} · Logotyp: {logo_name} · {r['note'] or 'Ingen fakturatext'}")

    def show_row_context_menu(self,event):
        item=self.tree.identify_row(event.y)
        if not item:return
        self.tree.selection_set(item);self.tree.focus(item);self.show_detail()
        try:self.row_menu.tk_popup(event.x_root,event.y_root)
        finally:self.row_menu.grab_release()

    def refresh_logo_choices(self):
        SVG_DIR.mkdir(exist_ok=True)
        files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        choices=['(Ingen logotyp)']+files
        if not files:choices.append('(Lägg SVG i mappen svg)')
        self.logo_combo.configure(values=choices)
        preferred=setting('logo_file') or Path(setting('logo_path')).name
        self.logo_var.set(preferred if preferred in files else choices[0])

    def on_logo_select(self,event=None):
        selected=self.logo_var.get()
        if selected in [p.name for p in SVG_DIR.glob('*.svg')]:
            set_setting('logo_file',selected)
            set_setting('logo_path',str(SVG_DIR/selected))
        else:
            set_setting('logo_file','');set_setting('logo_path','')

    def selected_logo_path(self):
        selected=self.logo_var.get()
        path=SVG_DIR/selected
        return str(path) if selected not in ('(Ingen logotyp)','(Lägg SVG i mappen svg)') and path.is_file() else ''

    def open_svg_folder(self):
        SVG_DIR.mkdir(exist_ok=True)
        try:
            if sys.platform.startswith('win'):os.startfile(str(SVG_DIR))
            else:webbrowser.open(SVG_DIR.as_uri())
        except Exception:logger.exception('Could not open SVG folder')

    def open_log(self):
        logger.info('User opened diagnostic log')
        if sys.platform.startswith('win'):
            try: os.startfile(str(LOG_PATH))
            except Exception: webbrowser.open(LOG_PATH.as_uri())
        else: webbrowser.open(LOG_PATH.as_uri())

    def guess_supplier(self,text):
        for line in [re.sub(r'\s+',' ',x).strip() for x in text.splitlines()[:18]]:
            if re.search(r'(?i)\b(?:AB|ASA|AS|HB)\s*$',line) and len(line)<60 and not re.search(r'faktura|datum|kundnr',line,re.I):
                return line
        return ''

    def parse_zone_value(self,field,text):
        raw='\n'.join(x.strip() for x in text.splitlines() if x.strip()).strip()
        if not raw:return ''
        if field=='amount':
            m=re.search(r'(\d{1,3}(?:[\s.\u00a0\u202f]\d{3})*(?:,\d{2}|\.\d{2})|\d+(?:,\d{2}|\.\d{2}))',raw)
            return normalize_amount(m.group(1)) if m else ''
        if field in ('due_date','invoice_date'):
            m=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',raw)
            return normalize_date(m.group(1)) if m else ''
        if field=='invoice_no':
            m=re.search(r'([A-Z]*\d[A-Z0-9./-]*)',raw,re.I)
            return m.group(1) if m else raw.splitlines()[0]
        if field=='customer':return raw.splitlines()[0][:100]
        return raw[:300]

    def apply_saved_zones(self,path,vendor,guess):
        if not vendor:return guess
        try:
            import fitz
            vendor_key=vendor.strip().casefold()
            with connect() as db:
                zones=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?)',(vendor_key,)).fetchall()
                logo=db.execute('SELECT logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(vendor_key,)).fetchone()
            if logo:
                logo_file=logo['logo_file']
                if logo_file and (SVG_DIR/logo_file).is_file():
                    self.logo_var.set(logo_file);set_setting('logo_file',logo_file);set_setting('logo_path',str(SVG_DIR/logo_file))
                    logger.info('Matched reminder logo to invoice supplier template')
                elif not logo_file:
                    self.logo_var.set('(Ingen logotyp)');set_setting('logo_file','');set_setting('logo_path','')
                else:logger.warning('Matched SVG logo is missing from svg folder')
            if not zones:return guess
            doc=fitz.open(path);applied=[]
            for z in zones:
                if z['page_index']>=len(doc):continue
                page=doc[z['page_index']];r=fitz.Rect(z['x0']*page.rect.width,z['y0']*page.rect.height,z['x1']*page.rect.width,z['y1']*page.rect.height)
                val=self.parse_zone_value(z['field'],page.get_text('text',clip=r))
                if val!='':guess[z['field']]=val;applied.append(z['field'])
            doc.close()
            if applied:logger.info('Applied saved PDF field zones: vendor=%s fields=%s',vendor,','.join(applied))
        except Exception:logger.exception('Saved PDF zones could not be applied')
        return guess

    def preview_invoice(self,path,guess,vendor=''):
        try:
            import fitz
            doc=fitz.open(path)
        except Exception:
            logger.exception('Could not open PDF preview')
            return guess
        win=tk.Toplevel(self);win.title('Förhandsgranska faktura – markera fält att läsa');win.geometry('950x760');win.transient(self);win.grab_set()
        top=ttk.Frame(win,padding=(12,8));top.pack(fill='x')
        ttk.Label(top,text='Leverantör / mallnamn:').pack(side='left')
        vendor_var=tk.StringVar(value=vendor or Path(path).stem)
        ttk.Entry(top,textvariable=vendor_var,width=34).pack(side='left',padx=7)
        ttk.Label(top,text='Dra en ruta över värdet. Sparade rutor kan återanvändas för samma mall.').pack(side='left',padx=8)
        body=ttk.Frame(win,padding=(10,0,10,6));body.pack(fill='both',expand=True)
        left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True)
        nav=ttk.Frame(left);nav.pack(fill='x')
        page_var=tk.StringVar(value='Sida 1')
        ttk.Button(nav,text='◀',command=lambda:change_page(-1)).pack(side='left')
        ttk.Label(nav,textvariable=page_var).pack(side='left',padx=10)
        ttk.Button(nav,text='▶',command=lambda:change_page(1)).pack(side='left')
        ttk.Label(nav,text='Markera fält:').pack(side='left',padx=(25,5))
        fields={'Fakturanummer':'invoice_no','Belopp (ATT BETALA)':'amount','Fakturadatum':'invoice_date','Förfallodatum':'due_date','Kundnamn':'customer','Fakturatext / Avser':'note'}
        field_var=tk.StringVar(value='Belopp (ATT BETALA)')
        ttk.Combobox(nav,textvariable=field_var,state='readonly',values=list(fields),width=24).pack(side='left')
        canvas=tk.Canvas(left,width=620,height=650,bg='#dfe3ea',highlightthickness=0);canvas.pack(fill='both',expand=True,pady=5)
        right=ttk.Frame(body,width=235,padding=(10,4));right.pack(side='right',fill='y');right.pack_propagate(False)
        ttk.Label(right,text='Avlästa värden',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,8))
        logo_files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        with connect() as db:logo_row=db.execute('SELECT logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(vendor_var.get().strip(),)).fetchone()
        mapped_logo=logo_row['logo_file'] if logo_row else ''
        active_logo=self.logo_var.get()
        logo_choices=['(Välj logotyp för mallen)','(Ingen logotyp)']+logo_files
        initial_logo=mapped_logo if mapped_logo in logo_files else active_logo if active_logo in logo_files else logo_choices[0]
        preview_logo_var=tk.StringVar(value=initial_logo)
        ttk.Label(right,text='Logotyp som matchar fakturan',font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(3,0))
        logo_combo=ttk.Combobox(right,textvariable=preview_logo_var,state='readonly',values=logo_choices,width=27)
        logo_combo.pack(fill='x',pady=(2,6))
        result_labels={}
        status=tk.StringVar(value='Klicka Markera vid ett fält och dra sedan en ruta runt värdet.')
        def activate_field(label):
            field_var.set(label);status.set(f'Markera värdet för: {label}')
        for label,key in fields.items():
            row=ttk.Frame(right);row.pack(fill='x',pady=(4,0))
            ttk.Label(row,text=label,font=('Segoe UI',9,'bold')).pack(side='left',anchor='w')
            ttk.Button(row,text='Markera',command=lambda name=label:activate_field(name)).pack(side='right')
            lab=ttk.Label(right,text=str(guess.get(key,'') or '—'),wraplength=210,foreground='#344054');lab.pack(anchor='w')
            result_labels[key]=lab
        ttk.Label(right,textvariable=status,wraplength=210,foreground='#475467').pack(anchor='w',pady=8)
        pending={};state={'page':0,'scale':1.0,'photo':None,'start':None,'rect':None,'image_w':1,'image_h':1}
        def draw_saved():
            canvas.delete('zone')
            current_vendor=vendor_var.get().strip()
            with connect() as db:zs=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?) AND page_index=?',(current_vendor,state['page'])).fetchall()
            for z in zs:
                p=doc[state['page']];x0=z['x0']*p.rect.width*state['scale'];y0=z['y0']*p.rect.height*state['scale'];x1=z['x1']*p.rect.width*state['scale'];y1=z['y1']*p.rect.height*state['scale']
                canvas.create_rectangle(x0,y0,x1,y1,outline='#e13f43',width=2,tags='zone')
                canvas.create_text(x0+3,y0+3,text=f"{z['field']} · {z['samples']} matchningar",anchor='nw',fill='#9b2024',tags='zone')
        def render_page():
            page=doc[state['page']]
            state['scale']=min(610/page.rect.width,620/page.rect.height)
            pix=page.get_pixmap(matrix=fitz.Matrix(state['scale'],state['scale']),alpha=False)
            state['image_w'],state['image_h']=pix.width,pix.height
            state['photo']=tk.PhotoImage(data=base64.b64encode(pix.tobytes('png')).decode('ascii'))
            canvas.delete('all');canvas.config(scrollregion=(0,0,pix.width,pix.height),width=pix.width,height=pix.height)
            canvas.create_image(0,0,image=state['photo'],anchor='nw',tags='page')
            page_var.set(f'Sida {state["page"]+1} av {len(doc)}');draw_saved()
        def change_page(delta):
            state['page']=max(0,min(len(doc)-1,state['page']+delta));render_page()
        def start_draw(event):
            state['start']=(canvas.canvasx(event.x),canvas.canvasy(event.y))
            if state['rect']:canvas.delete(state['rect'])
            x,y=state['start'];state['rect']=canvas.create_rectangle(x,y,x,y,outline='#ed6b24',width=3,tags='draft')
        def move_draw(event):
            if state['start'] and state['rect']:
                x,y=state['start'];canvas.coords(state['rect'],x,y,canvas.canvasx(event.x),canvas.canvasy(event.y))
        def parse_zone(event):
            if not state['start']:return
            x0,y0=state['start'];x1,y1=canvas.canvasx(event.x),canvas.canvasy(event.y);state['start']=None
            xa,xb=sorted((max(0,min(state['image_w'],x0)),max(0,min(state['image_w'],x1))))
            ya,yb=sorted((max(0,min(state['image_h'],y0)),max(0,min(state['image_h'],y1))))
            if xb-xa<4 or yb-ya<4:status.set('Rutan blev för liten. Dra en större ruta.');return
            page=doc[state['page']];scale=state['scale'];rect=fitz.Rect(xa/scale,ya/scale,xb/scale,yb/scale)
            raw=page.get_text('text',clip=rect)
            field=fields[field_var.get()]
            if not raw.strip():
                try:
                    import pytesseract
                    from PIL import Image
                    import io
                    pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=rect,alpha=False)
                    raw=pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png'))),lang='swe+eng')
                except Exception:logger.exception('OCR of selected PDF zone failed')
            value=self.parse_zone_value(field,raw)
            if value=='':status.set('Ingen text hittades i rutan. Försök igen eller kontrollera OCR.');return
            guess[field]=value;result_labels[field].configure(text=str(value))
            p=doc[state['page']]
            pending[field]={'page_index':state['page'],'x0':rect.x0/p.rect.width,'y0':rect.y0/p.rect.height,'x1':rect.x1/p.rect.width,'y1':rect.y1/p.rect.height}
            if state['rect']:canvas.delete(state['rect']);state['rect']=None
            color='#1d8c66';canvas.create_rectangle(xa,ya,xb,yb,outline=color,width=2,tags='zone');canvas.create_text(xa+3,ya+3,text=field,anchor='nw',fill=color,tags='zone')
            status.set(f'{field_var.get()} avläst: {value}')
        canvas.bind('<ButtonPress-1>',start_draw);canvas.bind('<B1-Motion>',move_draw);canvas.bind('<ButtonRelease-1>',parse_zone)
        def finish(save):
            guess['template_vendor']=vendor_var.get().strip()
            selected_logo=preview_logo_var.get()
            save_logo=selected_logo not in ('(Välj logotyp för mallen)','')
            if save and (pending or save_logo):
                mall=vendor_var.get().strip()
                if not mall:messagebox.showerror('Mallnamn saknas','Ange leverantör eller mallnamn.',parent=win);return
                vendor_key=mall.casefold()
                with connect() as db:
                    for field,zone in pending.items():
                        old=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?) AND field=?',(mall,field)).fetchone()
                        count=db.execute('SELECT COUNT(*) AS n FROM pdf_zone_samples WHERE lower(vendor)=lower(?) AND field=?',(mall,field)).fetchone()['n']
                        if old and count==0:
                            db.execute('INSERT INTO pdf_zone_samples(vendor,field,page_index,x0,y0,x1,y1,created) VALUES(?,?,?,?,?,?,?,?)',(vendor_key,field,old['page_index'],old['x0'],old['y0'],old['x1'],old['y1'],'legacy'))
                        db.execute('INSERT INTO pdf_zone_samples(vendor,field,page_index,x0,y0,x1,y1,created) VALUES(?,?,?,?,?,?,?,?)',(vendor_key,field,zone['page_index'],zone['x0'],zone['y0'],zone['x1'],zone['y1'],datetime.now().isoformat(timespec='seconds')))
                        samples=db.execute('SELECT * FROM pdf_zone_samples WHERE lower(vendor)=lower(?) AND field=?',(mall,field)).fetchall()
                        page_counts={}
                        for sample in samples:page_counts[sample['page_index']]=page_counts.get(sample['page_index'],0)+1
                        best_page=max(page_counts,key=page_counts.get)
                        page_samples=[sample for sample in samples if sample['page_index']==best_page]
                        coords=tuple(statistics.median(sample[key] for sample in page_samples) for key in ('x0','y0','x1','y1'))
                        count_for_page=len(page_samples)
                        if old:db.execute('UPDATE pdf_zones SET page_index=?,x0=?,y0=?,x1=?,y1=?,samples=? WHERE vendor=? AND field=?',(best_page,*coords,count_for_page,old['vendor'],field))
                        else:db.execute('INSERT INTO pdf_zones(vendor,field,page_index,x0,y0,x1,y1,samples) VALUES(?,?,?,?,?,?,?,?)',(vendor_key,field,best_page,*coords,count_for_page))
                    if save_logo:
                        logo_file=selected_logo if selected_logo in logo_files else ''
                        old_logo=db.execute('SELECT vendor FROM vendor_logos WHERE lower(vendor)=lower(?)',(mall,)).fetchone()
                        if old_logo:db.execute('UPDATE vendor_logos SET logo_file=? WHERE vendor=?',(logo_file,old_logo['vendor']))
                        else:db.execute('INSERT INTO vendor_logos(vendor,logo_file) VALUES(?,?)',(vendor_key,logo_file))
                if save_logo:
                    self.logo_var.set(selected_logo if selected_logo in logo_files else '(Ingen logotyp)')
                    self.on_logo_select()
                logger.info('Updated learned invoice template: vendor=%s fields=%s logo_set=%s',vendor_key,','.join(pending),save_logo)
            doc.close();win.destroy()
        buttons=ttk.Frame(right);buttons.pack(side='bottom',fill='x',pady=8)
        ttk.Button(buttons,text='Fortsätt utan att spara mall',command=lambda:finish(False)).pack(fill='x',pady=3)
        ttk.Button(buttons,text='Spara markerade fält som mall och fortsätt',command=lambda:finish(True),style='Accent.TButton').pack(fill='x',pady=3)
        win.protocol('WM_DELETE_WINDOW',lambda:finish(False))
        render_page();win.wait_window();return guess


    def scan_import_folder(self):
        IMPORT_DIR.mkdir(exist_ok=True)
        files=sorted(p for p in IMPORT_DIR.glob('*.pdf') if p.is_file())
        if not files:
            messagebox.showinfo('Importmapp tom',f'Lägg faktura-PDF:er i mappen:\n{IMPORT_DIR}',parent=self);return
        imported=skipped=failed=0
        for path in files:
            source=str(path.resolve())
            with connect() as db: existing_sources=[row['source'] for row in db.execute('SELECT source FROM invoices').fetchall()]
            if source in existing_sources or path.name in [Path(value).name for value in existing_sources if value]:skipped+=1;continue
            try:
                text=extract_pdf(str(path));guess=parse_invoice_text(text);vendor=self.guess_supplier(text)
                guess['template_vendor']=vendor
                guess=self.apply_saved_zones(str(path),vendor,guess)
                guess=self.preview_invoice(str(path),guess,vendor)
                self.add_invoice(source=source,guess=guess)
                with connect() as db:
                    saved=db.execute('SELECT 1 FROM invoices WHERE source=? LIMIT 1',(source,)).fetchone()
                if saved:imported+=1
                else:skipped+=1
            except Exception:
                logger.exception('Import folder scan failed for %s',path.name);failed+=1
        logger.info('Import folder scan complete: imported=%s skipped=%s failed=%s',imported,skipped,failed)
        self.refresh()
        messagebox.showinfo('Skanning klar',f'Importerade: {imported}\nRedan importerade/avbrutna: {skipped}\nFel: {failed}',parent=self)

    def open_import_folder(self):
        IMPORT_DIR.mkdir(exist_ok=True)
        try:
            if sys.platform.startswith('win'):os.startfile(str(IMPORT_DIR))
            else:webbrowser.open(IMPORT_DIR.as_uri())
        except Exception:logger.exception('Could not open import folder')

    def import_invoice(self):
        path=filedialog.askopenfilename(title='Välj faktura-PDF',filetypes=[('PDF','*.pdf')])
        if not path:return
        try:
            text=extract_pdf(path); guess=parse_invoice_text(text)
            vendor=self.guess_supplier(text)
            guess['template_vendor']=vendor
            guess=self.apply_saved_zones(path,vendor,guess)
            logger.info('Invoice PDF read: extracted_chars=%s suggested_fields=%s',len(text),','.join(k for k,v in guess.items() if v))
        except Exception as e:
            logger.exception('Invoice PDF read failed: %s',path)
            messagebox.showerror('Kunde inte läsa PDF',str(e));return
        guess=self.preview_invoice(path,guess,vendor)
        self.add_invoice(source=str(Path(path).resolve()),guess=guess)

    def add_invoice(self,source='',guess=None):
        self.invoice_dialog('Lägg till faktura',source=source,guess=guess)

    def edit_invoice(self):
        r=self.selected()
        if r:self.invoice_dialog('Redigera faktura',row=r)

    def invoice_dialog(self,title,row=None,source='',guess=None):
        w=tk.Toplevel(self);w.title(title);w.transient(self);w.grab_set();w.resizable(False,False);w.configure(bg='#f3f5f8')
        fields=[('Kundnamn','customer'),('Fakturanummer','invoice_no'),('Fakturadatum (ÅÅÅÅ-MM-DD)','invoice_date'),('Förfallodatum (ÅÅÅÅ-MM-DD)','due_date'),('Fakturabelopp (kr)','amount'),('Redan betalt (kr)','paid'),('E-post','email'),('Fakturatext / Avser','note')]
        vals={k:(row[k] if row else (guess or {}).get(k,'')) for _,k in fields}
        vals['source']=row['source'] if row else source
        vals['template_vendor']=row['template_vendor'] if row else (guess or {}).get('template_vendor','')
        reviewed_var=tk.BooleanVar(value=bool(row['reviewed']) if row else not bool(source))
        entries={};form=ttk.Frame(w,padding=18);form.pack()
        for i,(lab,k) in enumerate(fields):
            ttk.Label(form,text=lab).grid(row=i,column=0,sticky='w',pady=5,padx=(0,12));e=ttk.Entry(form,width=43);e.grid(row=i,column=1,pady=5);e.insert(0,str(vals.get(k,'') or ''));entries[k]=e
        ttk.Checkbutton(form,text='Jag har granskat och godkänt fakturauppgifterna',variable=reviewed_var).grid(row=len(fields),column=0,columnspan=2,sticky='w',pady=(8,4))
        def save():
            v={k:e.get().strip() for k,e in entries.items()}
            if not v['customer'] or not v['invoice_no'] or not dparse(v['due_date']):messagebox.showerror('Kontrollera uppgifter','Kund, fakturanummer och giltigt förfallodatum krävs.',parent=w);return
            try:amount=float(v['amount'].replace(' ','').replace(',','.')) if v['amount'] else 0;paid=float(v['paid'].replace(' ','').replace(',','.')) if v['paid'] else 0
            except ValueError:messagebox.showerror('Fel belopp','Ange belopp som siffror.',parent=w);return
            with connect() as db:
                if row:db.execute('UPDATE invoices SET customer=?,invoice_no=?,invoice_date=?,due_date=?,template_vendor=?,amount=?,paid=?,email=?,note=?,reviewed=? WHERE id=?',(v['customer'],v['invoice_no'],v['invoice_date'],v['due_date'],vals['template_vendor'],amount,paid,v['email'],v['note'],int(reviewed_var.get()),row['id']))
                else:db.execute('INSERT INTO invoices(customer,invoice_no,due_date,invoice_date,template_vendor,amount,paid,email,source,note,reviewed,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(v['customer'],v['invoice_no'],v['due_date'],v['invoice_date'],vals['template_vendor'],amount,paid,v['email'],vals['source'],v['note'],int(reviewed_var.get()),datetime.now().isoformat(timespec='seconds')))
            logger.info('Invoice saved/edited: source_type=%s fields=customer,invoice_no,due_date,amount,paid,email,note',Path(vals['source']).suffix.lower() if vals['source'] else 'manual')
            w.destroy();self.refresh()
        ttk.Button(form,text='Spara',command=save,style='Accent.TButton').grid(row=len(fields)+1,column=1,sticky='e',pady=(12,0))
        w.wait_window()

    def toggle_ignore(self):
        r=self.selected()
        if not r:return
        new=0 if r['ignored'] else 1
        with connect() as db:db.execute('UPDATE invoices SET ignored=? WHERE id=?',(new,r['id']))
        self.refresh()

    def delete_invoice(self):
        r=self.selected()
        if r and messagebox.askyesno('Ta bort faktura',f"Ta bort {r['invoice_no']} permanent från den lokala databasen?"):
            with connect() as db:db.execute('DELETE FROM invoices WHERE id=?',(r['id'],))
            self.refresh()

    def make_reminder(self):
        r=self.selected()
        if not r:return
        stage=next_stage(r)
        if stage not in ('P1 att skapa','P2 att skapa'):
            messagebox.showwarning('Inte redo',f"Fakturan är inte redo för påminnelse. Status: {stage}");return
        fee=float(setting('fee') or 0);locked=setting('fee_locked')=='1'
        level='P1' if stage.startswith('P1') else 'P2'
        template_name=r['template_vendor'] or 'Ingen matchad mall'
        logo_name=self.logo_var.get() or '(Ingen logotyp)'
        if not messagebox.askyesno('Bekräfta påminnelse',f"Skapa {level} för {r['invoice_no']}?\n\nPåminnelseavgift: {money(fee)}{' (låst)' if locked else ''}\nRänta: {setting('interest')}% per år\nMall: {template_name}\nSVG-logotyp: {logo_name}\n\nAppen skickar inte e-post automatiskt."): 
            return
        logo_path=self.selected_logo_path()
        day=date.today().isoformat()
        with connect() as db:
            if level=='P1':db.execute('UPDATE invoices SET p1_date=?,sent_count=sent_count+1 WHERE id=?',(day,r['id']))
            else:db.execute('UPDATE invoices SET p2_date=?,sent_count=sent_count+1 WHERE id=?',(day,r['id']))
        self.write_letter(r,level,fee,logo_path)
        self.refresh()

    def write_letter(self,r,level,fee,logo_path=''):
        today=date.today();remaining=max(0,float(r['amount'] or 0)-float(r['paid'] or 0))
        p1_fee=fee; p2_fee=fee if level=='P2' else 0; total=remaining+p1_fee+p2_fee
        deadline_date=today+timedelta(days=int(setting('payment_deadline_days') or 5))
        months=['januari','februari','mars','april','maj','juni','juli','augusti','september','oktober','november','december']
        deadline=f"{deadline_date.day} {months[deadline_date.month-1]} {deadline_date.year}"
        p2_warning=(f"Ansökan om betalningsföreläggande lämnas in till Kronofogden om betalning inte kommit oss tillhanda senast den {deadline}. Kostnader för att driva ärendet kan tillkomma till dess full betalning har skett.") if level=='P2' else ''
        logger.info('Reminder generated: level=%s',level)
        reminder_number='1' if level=='P1' else '2'
        safe_invoice_no=re.sub(r'[^A-Za-z0-9_-]','_',str(r['invoice_no']))
        safe_customer=re.sub(r'[^\w-]+','_',str(r['customer']),flags=re.UNICODE).strip('_')[:60] or 'kund'
        pdf_out=EXPORT_DIR/f"paminnelse({reminder_number})_{safe_invoice_no}_{safe_customer}_{today.isoformat()}.pdf"
        try:
            self.write_pdf(pdf_out,r,level,fee,today,remaining,total,p2_warning,logo_path)
            logger.info('Reminder PDF created: path=%s',pdf_out)
            try:
                if sys.platform.startswith('win'):os.startfile(str(pdf_out))
                elif sys.platform=='darwin':subprocess.Popen(['open',str(pdf_out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                else:webbrowser.open(pdf_out.as_uri())
                logger.info('Opened generated PDF in default viewer')
            except Exception as open_exc:
                logger.exception('Could not automatically open generated PDF')
                messagebox.showwarning('PDF skapad',f'PDF:en sparades men kunde inte öppnas automatiskt.\n{pdf_out}\n\n{open_exc}')
        except ImportError:
            logger.exception('PDF generation dependency missing')
            messagebox.showerror('PDF-tillägg saknas','Kunde inte skapa PDF eftersom ett PDF-tillägg saknas. Öppna felloggen eller starta om appen med internetanslutning.')
        except Exception as exc:
            logger.exception('Reminder PDF generation failed: invoice=%s',r['invoice_no'])
            messagebox.showerror('PDF kunde inte skapas',f'Ett fel loggades. Öppna felloggen för detaljer.\n\n{exc}')

    def write_pdf(self,path,r,level,fee,today,remaining,total,p2_warning,logo_path=''):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Flowable
        from xml.sax.saxutils import escape
        styles=getSampleStyleSheet()
        styles.add(ParagraphStyle(name='LetterTitle',parent=styles['Heading1'],fontName='Times-Bold',fontSize=17,leading=21,textColor=colors.HexColor('#202020'),spaceBefore=9,spaceAfter=8))
        styles.add(ParagraphStyle(name='SmallText',parent=styles['BodyText'],fontName='Helvetica',fontSize=8.5,leading=12,spaceAfter=5))
        styles.add(ParagraphStyle(name='RightSmall',parent=styles['SmallText'],alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='AlertText',parent=styles['SmallText'],fontName='Helvetica-Bold',fontSize=9.2,leading=13,borderColor=colors.HexColor('#777777'),borderWidth=.6,borderPadding=8,spaceBefore=8,spaceAfter=10))
        doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=22*mm,leftMargin=22*mm,topMargin=18*mm,bottomMargin=18*mm,title=f'Betalningspåminnelse {level} {r["invoice_no"]}',author='Tadega AB')
        story=[]
        brand=Paragraph('<font name="Times-BoldItalic" size="22">Tadega AB</font>',styles['BodyText'])
        logo_path=Path(logo_path) if logo_path else None
        if logo_path and logo_path.is_file():
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPDF
                drawing=svg2rlg(str(logo_path))
                if drawing and drawing.width and drawing.height:
                    class LogoFlowable(Flowable):
                        def __init__(self,drawing,maxw,maxh):
                            Flowable.__init__(self);self.drawing=drawing;self.width=maxw;self.height=maxh;self.scale=min(maxw/drawing.width,maxh/drawing.height)
                        def draw(self):
                            self.canv.saveState();self.canv.scale(self.scale,self.scale);renderPDF.draw(self.drawing,self.canv,0,0);self.canv.restoreState()
                    brand=LogoFlowable(drawing,70*mm,28*mm)
            except Exception:logger.exception('Could not embed SVG logo in PDF')
        meta=Paragraph(f'Tadega AB<br/>Påminnelsedatum: {today.isoformat()}<br/>Påminnelse nummer {1 if level=="P1" else 2}<br/>Fakturanummer: {escape(str(r["invoice_no"]))}<br/>Fakturadatum: {escape(str(r["invoice_date"] or ""))}<br/>Förfallodatum: {escape(str(r["due_date"]))}',styles['RightSmall'])
        hdr=Table([[brand,meta]],colWidths=[85*mm,81*mm]);hdr.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.7,colors.HexColor('#777777')),('BOTTOMPADDING',(0,0),(-1,-1),9)]));story += [hdr,Spacer(1,9*mm)]
        story.append(Paragraph(f'<b>{escape(str(r["customer"]))}</b>',styles['SmallText']))
        n=1 if level=='P1' else 2
        story.append(Paragraph(f'Betalningspåminnelse nummer {n}',styles['LetterTitle']))
        story.append(Paragraph('Vi saknar fortfarande betalning för nedanstående faktura. Om betalning redan har gjorts, vänligen bortse från denna påminnelse.',styles['SmallText']))
        deadline_date=today+timedelta(days=int(setting('payment_deadline_days') or 5))
        months=['januari','februari','mars','april','maj','juni','juli','augusti','september','oktober','november','december']
        deadline_text=f'{deadline_date.day} {months[deadline_date.month-1]} {deadline_date.year}'
        story.append(Paragraph(f'<b>Betalning ska vara oss tillhanda senast {deadline_text}.</b>',styles['SmallText']))
        if level=='P2': story.append(Paragraph(escape(p2_warning),styles['AlertText']))
        story.append(Paragraph('<b>Avser:</b> '+escape(str(r['note'] or 'Överenskommen kostnad enligt fakturan.')),styles['SmallText']))
        rows=[[Paragraph('<b>Specifikation</b>',styles['SmallText']),Paragraph('<b>Belopp</b>',styles['RightSmall'])],
              [Paragraph(f'Faktura {escape(str(r["invoice_no"]))} – obetalt belopp',styles['SmallText']),Paragraph(money(remaining),styles['RightSmall'])],
              [Paragraph('Påminnelseavgift (påminnelse 1)',styles['SmallText']),Paragraph(money(fee),styles['RightSmall'])]]
        if level=='P2':rows.append([Paragraph('Påminnelseavgift (påminnelse 2)',styles['SmallText']),Paragraph(money(fee),styles['RightSmall'])])
        rows.append([Paragraph('<b>ATT BETALA</b>',styles['SmallText']),Paragraph(f'<b>{money(total)}</b>',styles['RightSmall'])])
        tab=Table(rows,colWidths=[112*mm,54*mm]);tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#444444')),('LINEBELOW',(0,1),(-1,-2),.3,colors.HexColor('#cccccc')),('LINEABOVE',(0,-1),(-1,-1),.8,colors.HexColor('#444444')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [Spacer(1,4*mm),tab,Spacer(1,4*mm)]
        hist=[[Paragraph('<b>Påminnelse</b>',styles['SmallText']),Paragraph('<b>Datum</b>',styles['SmallText']),Paragraph('<b>Avgift</b>',styles['RightSmall'])],
              [Paragraph('Påminnelse 1',styles['SmallText']),Paragraph(escape(str(r['p1_date'] or today.isoformat())),styles['SmallText']),Paragraph(money(fee),styles['RightSmall'])]]
        if level=='P2':hist.append([Paragraph('Påminnelse 2 (denna)',styles['SmallText']),Paragraph(today.isoformat(),styles['SmallText']),Paragraph(money(fee),styles['RightSmall'])])
        ht=Table(hist,colWidths=[78*mm,54*mm,34*mm]);ht.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#aaaaaa')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f1f1f1')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),2)]));story += [ht,Spacer(1,3*mm)]
        story.append(Paragraph('Ovanstående påminnelser har skickats för fakturan och samtliga avgifter ingår i beloppet ovan.',styles['SmallText']))
        story.append(Paragraph('<b>Betalning</b><br/>Bankgiro: 5660-4200 · Swish: 123 188 42 87<br/>Betalningsmottagare: Tadega AB. Ange fakturanumret vid betalning.<br/>IBAN: SE26 6000 0000 0005 3862 3322 · BIC: HANDSESS',styles['SmallText']))
        terms=f'Varan förblir vår egendom tills full betalning erlagts. Eventuella anmärkningar på fakturan ska göras inom {escape(setting("objection_days"))} dagar. Avgift per påminnelse: {money(fee)}. Försenad betalning debiteras {escape(setting("interest"))} % ränta. Vid beställning av specialdelar lämnas ingen returrätt.'
        story += [Spacer(1,2*mm),HRFlowable(width='100%',thickness=.4,color=colors.HexColor('#999999')),Spacer(1,2*mm),Paragraph(terms,styles['SmallText'])]
        doc.build(story)
    def settings(self):
        w=tk.Toplevel(self);w.title('Inställningar');w.transient(self);w.grab_set();w.resizable(False,False);form=ttk.Frame(w,padding=20);form.pack()
        fields=[('Dagar efter förfallodatum till P1','p1_days'),('Dagar efter P1 till P2','p2_days'),('Dagar efter P2 till Kronofogden-granskning','p3_days'),('Påminnelseavgift per påminnelse (kr)','fee'),('Dröjsmålsränta per år (%)','interest'),('Anmärkningstid enligt fakturavillkor (dagar)','objection_days'),('Betalningsfrist på påminnelsen (dagar)','payment_deadline_days')]
        entries={}
        for i,(label,key) in enumerate(fields):
            ttk.Label(form,text=label).grid(row=i,column=0,sticky='w',padx=(0,14),pady=6);e=ttk.Entry(form,width=16);e.grid(row=i,column=1,pady=6);e.insert(0,setting(key));entries[key]=e
            if key=='fee' and setting('fee_locked')=='1':e.configure(state='disabled')
        locked=tk.BooleanVar(value=setting('fee_locked')=='1')
        def toggle_lock():
            entries['fee'].configure(state='disabled' if locked.get() else 'normal')
        ttk.Checkbutton(form,text='Lås påminnelseavgiften (förhindra oavsiktlig ändring)',variable=locked,command=toggle_lock).grid(row=len(fields)+1,column=0,columnspan=3,sticky='w',pady=(8,4))
        ttk.Label(form,text='Låset skyddar inställningen i appen; lås upp här för att ändra avgiften.',style='Sub.TLabel').grid(row=len(fields)+2,column=0,columnspan=3,sticky='w')
        ttk.Label(form,text='Obs: kontrollera att avgift, ränta och villkor gäller för era kunder.',style='Sub.TLabel').grid(row=len(fields)+3,column=0,columnspan=3,sticky='w',pady=(8,0))
        def save():
            try:
                for k,e in entries.items():
                    v=e.get().strip()
                    if k in ('p1_days','p2_days','p3_days','objection_days','payment_deadline_days') and int(v)<0:raise ValueError()
                    if k in ('fee','interest') and float(v.replace(',','.'))<0:raise ValueError()
                for k,e in entries.items():set_setting(k,e.get().strip().replace(',','.'))
                set_setting('fee_locked','1' if locked.get() else '0')
            except Exception as exc:messagebox.showerror('Ogiltigt värde',str(exc) or 'Ange positiva siffror i inställningarna.',parent=w);return
            logger.info('Settings saved; fee_locked=%s',bool(locked.get()))
            w.destroy();self.refresh()
        ttk.Button(form,text='Spara inställningar',command=save,style='Accent.TButton').grid(row=len(fields)+4,column=1,sticky='e',pady=(15,0))

def main():
    init_db()
    logger.info('Application started')
    try: ReminderApp().mainloop()
    except tk.TclError as e:
        messagebox.showerror('PayPåminn Flow',f'Appen kunde inte starta. Kontrollera att Python installerats med Tkinter.\n\n{e}')


if __name__=='__main__':
    main()
