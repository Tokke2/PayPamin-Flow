#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PayPamin Flow – lokal fakturapåminnelseapp för Windows, macOS och Linux.
Kräver Python 3.10+. PDF-textavläsning: pip install pymupdf.
OCR för skannade PDF: se README.

Copyright © 2026 Rickard Längkvist. Skapare: Rickard Längkvist.
"""
from __future__ import annotations
import os, re, sqlite3, sys, webbrowser, subprocess, threading, queue, importlib.util, logging, statistics, base64, hashlib, tempfile, json
from logging.handlers import RotatingFileHandler
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog

from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_ID, APP_NAME, APP_SLUG, APP_VERSION, MINIMIZED_START_ARG, SUPPORTED_PLATFORMS
from activity_log import instrument_tk_command, log_activity
from build_info import APP_RELEASE_COMMIT
from app_backup import (
    BackupError,
    BackupPaths,
    create_backup as create_local_backup,
    restore_backup as restore_local_backup,
    suggested_backup_filename,
)
from autostart import AutostartError, autostart_location, set_autostart
from cache_cleaner import clean_cache
from tray import TrayController, TrayUnavailable
from currency import find_currency_code, is_valid_currency, normalize_currency
from console_free import configure_console_free_subprocesses
from error_log import ERROR_LOG_NAME, refresh_error_log, resolve_errors
from log_archive import DailySizeRotatingFileHandler, archive_old_logs
from customer_contacts import (
    EmailAddressError, ensure_customer_contact_schema, get_customer_contact,
    normalize_email_addresses, parse_email_addresses, save_customer_contact,
)
from i18n import SUPPORTED_LANGUAGES, _, format_long_date, format_money, get_language, language_code, set_language
from invoice_parser import (
    clean_invoice_note, extract_invoice_sections, normalize_date,
    parse_amount_value, parse_invoice_text,
)
from import_watcher import ImportFolderMonitor
from ledger_import import (
    LedgerImportError, apply_ledger_import, ensure_ledger_schema,
    plan_ledger_import, read_ledger_report,
)
from mail_compose import default_thunderbird_executable, open_thunderbird_draft, windows_uses_thunderbird
from logo_matching import match_pdf_logo
from reminder_archive import ARCHIVE_FOLDER_NAME, archive_old_reminders, customer_archive_path
from supplier_matching import (
    SupplierMatch,
    extract_bankgiro_numbers,
    extract_org_numbers,
    format_bankgiro_number,
    format_org_number,
    match_supplier,
    normalize_bankgiro_number,
    normalize_org_number,
    parse_supplier_identifier,
    svg_logo_aliases,
    validate_supplier_logo_link,
)
from reminder_journal import (
    JOURNAL_FILENAME,
    JournalError,
    create_weekly_backup as create_weekly_journal_backup,
    ensure_journal_schema,
    export_journal as export_reminder_journal,
    import_journal as import_reminder_journal_file,
    record_reminder as record_reminder_journal,
)
from update_checker import (
    UPDATE_CHECK_INTERVAL_MS,
    UpdateCheckError,
    fetch_latest_release,
    is_update_available,
    missing_release_assets,
    update_change_kind,
)
from update_installer import (
    UpdateInstallError,
    cleanup_update,
    install_update,
    mark_update_ready,
    restart_updated_app,
    rollback_update,
    stage_update,
    wait_for_update_restart,
)
from python_maintenance import (
    MAINTENANCE_POLL_INTERVAL_MS,
    addon_package_specs,
    install_python_addons,
    maintenance_due,
    maintenance_week,
    missing_addon_package_specs,
    read_maintenance_week,
    write_maintenance_week,
)
from accessibility import (
    AccessibleStyle,
    FONT_SCALE_CHOICES,
    FONT_SCALE_SETTING,
    SYSTEM_CONTRAST_POLL_INTERVAL_MS,
    ScrollableForm,
    apply_widget_contrast,
    contrast_palette,
    fit_window_to_screen,
    focus_first,
    font_scale_label,
    font_scale_storage,
    normalize_font_scale,
    prepare_focus_tree,
    scaled_number,
    stepped_font_scale,
    system_high_contrast,
)

IMPORT_WATCH_INTERVAL_MS = 5000
LEDGER_REMINDER_INTERVAL_MS = 15 * 60 * 1000
ERROR_LOG_REFRESH_INTERVAL_MS = 60 * 1000
CACHE_CLEANUP_INTERVAL_MS = 60 * 60 * 1000
JOURNAL_BACKUP_INTERVAL_MS = 60 * 60 * 1000
REMINDER_ARCHIVE_INTERVAL_MS = 60 * 60 * 1000

APP_DIR = Path.home() / ".paminnelseapp"
APP_DIR.mkdir(parents=True,exist_ok=True)
DB_PATH = APP_DIR / "paminnelseapp.sqlite3"
JOURNAL_PATH = APP_DIR / JOURNAL_FILENAME
JOURNAL_BACKUP_DIR = APP_DIR / "backups" / "journal"
APP_FOLDER = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys,'_MEIPASS',APP_FOLDER))
# A frozen app must not write invoices to its temporary bundle or Program Files.
DATA_FOLDER = APP_DIR if getattr(sys,'frozen',False) else APP_FOLDER
EXPORT_DIR = DATA_FOLDER / "export"
EXPORT_DIR.mkdir(parents=True,exist_ok=True)
SVG_DIR = DATA_FOLDER / "svg"
SVG_DIR.mkdir(parents=True,exist_ok=True)
IMPORT_DIR = DATA_FOLDER / "import"
IMPORT_DIR.mkdir(parents=True,exist_ok=True)
ICON_DIR = RESOURCE_DIR / "assets"
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True,exist_ok=True)
PYTHON_ADDONS_MAINTENANCE_MARKER = APP_DIR / "python-addons-week.txt"


def _relocate_legacy_logs():
    """Move only known app logs into their own folder without overwriting."""
    moved=[];errors=[]
    try:candidates=sorted(APP_DIR.iterdir())
    except OSError:return moved,['.']
    for source in candidates:
        name=source.name
        known=name in {'app.log','errors.log','startup.log','update.log'} or re.fullmatch(r'(?:app|update)\.log\.\d+',name)
        if not known or source.is_symlink() or not source.is_file():continue
        destination=LOG_DIR/name
        if destination.exists() or destination.is_symlink():
            destination=LOG_DIR/f'legacy-{name}'
            index=2
            while destination.exists() or destination.is_symlink():
                destination=LOG_DIR/f'legacy-{index}-{name}';index+=1
        try:
            source.rename(destination);moved.append((name,destination.name))
        except OSError:errors.append(name)
    return moved,errors


_legacy_log_moves,_legacy_log_errors=_relocate_legacy_logs()
LOG_PATH = LOG_DIR / "app.log"
ERROR_LOG_PATH = LOG_DIR / ERROR_LOG_NAME
logger = logging.getLogger(APP_SLUG)
logger.setLevel(logging.INFO)
if not logger.handlers:
    log_handler=DailySizeRotatingFileHandler(LOG_PATH,maxBytes=5_000_000,backupCount=5,encoding='utf-8')
    log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(log_handler)
for _source_name,_destination_name in _legacy_log_moves:
    logger.info('Legacy log moved into logs folder: %s -> %s',_source_name,_destination_name)
for _source_name in _legacy_log_errors:
    logger.warning('Legacy log could not be moved into logs folder: %s',_source_name)


def _archive_previous_day_logs():
    """Roll an idle log at midnight, then archive files from earlier days."""
    for handler in logger.handlers:
        if isinstance(handler,DailySizeRotatingFileHandler):
            handler.rollover_for_new_day()
    return archive_old_logs(LOG_DIR)


def _refresh_and_archive_logs():
    """Capture unresolved errors before their technical sources are archived."""
    report=refresh_error_log(LOG_DIR)
    archive=_archive_previous_day_logs()
    if archive.archived or archive.collisions or archive.errors:
        log=logger.warning if archive.errors else logger.info
        log('Daily log archive: archived=%d collisions=%d errors=%d',archive.archived,archive.collisions,archive.errors)
    return report


def _ledger_log_json(payload):
    """Serialize diagnostic values without allowing newlines to forge log rows."""
    return json.dumps(payload,ensure_ascii=False,sort_keys=True)


def _log_ledger_report(source,report):
    """Record every parsed value before any database change."""
    source_name=Path(source).name
    logger.info('Customer ledger PDF read: %s',_ledger_log_json({
        'source':source_name,'list_date':report.list_date,'pages':report.page_count,
        'expected_count':report.expected_count,'read_count':len(report.entries),
        'expected_total':f'{report.expected_total:.2f}',
        'actual_total':f'{report.actual_total:.2f}','total_verified':report.total_verified,
    }))
    for row_number,entry in enumerate(report.entries,1):
        logger.info('Customer ledger row: %s',_ledger_log_json({
            'source':source_name,'row':row_number,'rows':len(report.entries),
            'customer_number':entry.customer_number,'customer':entry.customer,
            'invoice_no':entry.invoice_no,'invoice_date':entry.invoice_date,
            'due_date':entry.due_date,'currency':entry.currency,
            'amount':f'{entry.amount:.2f}','balance':f'{entry.balance:.2f}',
            'paid':f'{entry.paid:.2f}',
        }))


def _log_ledger_plan(source,plan):
    """Record all listed-payment updates and missing-invoice paid candidates."""
    source_name=Path(source).name
    logger.info('Customer ledger import plan: %s',_ledger_log_json({
        'source':source_name,'previous_list_date':plan.previous_list_date,
        'new':plan.new_count,'existing':plan.existing_count,
        'paid_candidates':len(plan.missing)+sum(update.fully_paid for update in plan.payment_updates),
        'payment_updates':len(plan.payment_updates),
        'diagnostics':plan.diagnostics.__dict__,
    }))
    for candidate in plan.missing:
        logger.info('Customer ledger paid candidate: %s',_ledger_log_json({
            'source':source_name,'invoice_id':candidate.invoice_id,
            'invoice_no':candidate.invoice_no,'customer':candidate.customer,
            'amount':f'{candidate.amount:.2f}','currency':candidate.currency,
        }))
    for update in plan.payment_updates:
        logger.info('Customer ledger listed payment update: %s',_ledger_log_json({
            'source':source_name,'invoice_id':update.invoice_id,
            'invoice_no':update.invoice_no,'customer':update.customer,
            'amount':f'{update.amount:.2f}','currency':update.currency,
            'previous_paid':f'{update.previous_paid:.2f}',
            'new_paid':f'{update.new_paid:.2f}','fully_paid':update.fully_paid,
        }))


def ledger_receipt_text(report,plan):
    """Describe the actual applied plan, including an evidence-based zero result."""
    lines=[]
    fully_paid_updates=[update for update in plan.payment_updates if update.fully_paid]
    partial_updates=[update for update in plan.payment_updates if not update.fully_paid]
    if plan.missing or fully_paid_updates:
        lines.append(_('Betalmarkerade fakturor'))
        for candidate in plan.missing:
            lines.append(_('{invoice} – {customer} – {amount} – Saknas i den nya kompletta listan',invoice=candidate.invoice_no,customer=candidate.customer,amount=money(candidate.amount,candidate.currency)))
        for update in fully_paid_updates:
            lines.append(_('{invoice} – {customer} – {previous} → {new} – Saldo 0 i listan',invoice=update.invoice_no,customer=update.customer,previous=money(update.previous_paid,update.currency),new=money(update.new_paid,update.currency)))
    else:
        lines.append(_('Inga fakturor betalmarkerades.'))
        if not report.total_verified:
            lines.append(_('Listans SEK-total är inte verifierad, därför ändrades ingen befintlig betalstatus automatiskt.'))
        elif not plan.previous_list_date:
            lines.append(_('Detta är den första reskontralistan. Den bygger listhistorik och använder inte frånvaro som bevis för betalning.'))
        else:
            lines.append(_('Ingen obetald faktura uppfyllde reglerna för automatisk betalmarkering.'))
        diagnostics=plan.diagnostics
        explanations=(
            ('missing_already_paid','Saknade fakturor som redan var betalda: {count}'),
            ('missing_without_history','Saknade fakturor utan tidigare listhistorik (oförändrade): {count}'),
            ('missing_future_dated','Saknade fakturor med senare listdatum (skyddade): {count}'),
            ('listed_already_paid','Fakturor i listan som redan var betalda: {count}'),
            ('listed_unchanged','Fakturor i listan med oförändrat betalbelopp: {count}'),
            ('listed_protected','Fakturor där belopp eller valuta skyddades mot osäker tolkning: {count}'),
        )
        added=False
        for name,template in explanations:
            count=getattr(diagnostics,name)
            if count:lines.append(_(template,count=count));added=True
        if report.total_verified and plan.previous_list_date and not added:
            lines.append(_('Alla obetalda fakturor med tidigare listhistorik finns kvar i den valda listan.'))
    if partial_updates:
        lines.extend(('',_('Uppdaterade delbetalningar')))
        for update in partial_updates:
            lines.append(_('{invoice} – {customer} – {previous} → {new} – Belopp/Saldo i listan',invoice=update.invoice_no,customer=update.customer,previous=money(update.previous_paid,update.currency),new=money(update.new_paid,update.currency)))
    return '\n'.join(lines)


def configure_windows_app_identity():
    """Give pythonw.exe its own taskbar identity on Windows."""

    if not sys.platform.startswith('win'):
        return
    try:
        import ctypes

        set_app_id=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes=[ctypes.c_wchar_p]
        set_app_id.restype=ctypes.c_long
        result=set_app_id(APP_ID)
        if result!=0:
            raise OSError(result,'SetCurrentProcessExplicitAppUserModelID failed')
        logger.info('Windows application identity configured: %s',APP_ID)
    except Exception as exc:
        # Icon setup must never prevent the main window from opening.
        logger.warning('Windows application identity could not be configured: %s',exc)


_WINDOWS_NATIVE_ICONS = {}


def configure_windows_window_icon(window):
    """Set native small/big HWND icons for the taskbar and Task Manager app view.

    The process-lifetime cache shares each loaded HICON between all app windows.
    Windows reclaims them at exit. The Details tab can still use pythonw.exe's
    embedded icon; changing that would require a native executable.
    """
    if not sys.platform.startswith('win'):return False
    try:
        import ctypes

        icon_path=ICON_DIR/'paypamin_flow.ico'
        if not icon_path.is_file():return False
        user32=ctypes.windll.user32
        get_metrics=user32.GetSystemMetrics
        get_metrics.argtypes=[ctypes.c_int];get_metrics.restype=ctypes.c_int
        load_image=user32.LoadImageW
        load_image.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
        load_image.restype=ctypes.c_void_p
        send_message=user32.SendMessageW
        send_message.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
        send_message.restype=ctypes.c_ssize_t
        get_ancestor=user32.GetAncestor
        get_ancestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        get_ancestor.restype=ctypes.c_void_p

        def icon_handle(width,height):
            key=(str(icon_path.resolve()),width,height)
            if key not in _WINDOWS_NATIVE_ICONS:
                handle=load_image(None,key[0],1,width,height,0x0010)
                if not handle:raise OSError(f'LoadImageW failed for {width}x{height}')
                _WINDOWS_NATIVE_ICONS[key]=handle
            return _WINDOWS_NATIVE_ICONS[key]

        small=icon_handle(get_metrics(49),get_metrics(50))
        large=icon_handle(get_metrics(11),get_metrics(12))
        source_hwnd=int(window.winfo_id())
        # Tk's winfo_id() can be an inner child HWND. The taskbar, Alt-Tab
        # and Task Manager app view read WM_SETICON from the top-level HWND.
        hwnd=int(get_ancestor(source_hwnd,2) or source_hwnd)  # GA_ROOT
        send_message(hwnd,0x0080,0,small)
        send_message(hwnd,0x0080,1,large)
        logger.info('Windows product icon applied: source_hwnd=%s root_hwnd=%s',source_hwnd,hwnd)
        return True
    except Exception as exc:
        logger.warning('Native Windows window icon could not be configured: %s',exc)
        return False


def open_path(path):
    """Open a file or folder with the default application on every desktop OS."""
    target=Path(path).resolve()
    if sys.platform.startswith('win'):
        os.startfile(str(target))
        return
    command=['open',str(target)] if sys.platform=='darwin' else ['xdg-open',str(target)]
    try:
        subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except FileNotFoundError:
        # Fallback for minimal Unix environments without xdg-open.
        if not webbrowser.open(target.as_uri()):
            raise


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then close the SQLite handle on every with exit."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    db = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
            due_date TEXT NOT NULL, invoice_date TEXT DEFAULT '', template_vendor TEXT DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 1,
            logo_file TEXT,
            amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'SEK', paid REAL NOT NULL DEFAULT 0,
            paid_before_marking REAL, paid_marked_at TEXT NOT NULL DEFAULT '', paid_marked_source TEXT NOT NULL DEFAULT '',
            email TEXT DEFAULT '', source TEXT DEFAULT '', source_hash TEXT NOT NULL DEFAULT '', ignored INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '', p1_date TEXT DEFAULT '', p2_date TEXT DEFAULT '', sent_count INTEGER NOT NULL DEFAULT 0,
            p1_snapshot TEXT DEFAULT '', p2_snapshot TEXT DEFAULT '',
            p1_draft_date TEXT DEFAULT '', p2_draft_date TEXT DEFAULT '',
            p1_sent_date TEXT DEFAULT '', p2_sent_date TEXT DEFAULT '', created TEXT NOT NULL)""")
        existing={row['name'] for row in db.execute('PRAGMA table_info(invoices)').fetchall()}
        if 'invoice_date' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN invoice_date TEXT DEFAULT ''")
        if 'template_vendor' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN template_vendor TEXT DEFAULT ''")
        if 'reviewed' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 1")
        if 'logo_file' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN logo_file TEXT")
        if 'currency' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN currency TEXT NOT NULL DEFAULT 'SEK'")
        if 'paid_before_marking' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN paid_before_marking REAL")
        for column in ('paid_marked_at','paid_marked_source'):
            if column not in existing:db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        if 'source_hash' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''")
        if 'p1_snapshot' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN p1_snapshot TEXT DEFAULT ''")
        if 'p2_snapshot' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN p2_snapshot TEXT DEFAULT ''")
        for column in ('p1_draft_date','p2_draft_date','p1_sent_date','p2_sent_date'):
            if column not in existing:db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT DEFAULT ''")
        ensure_ledger_schema(db)
        ensure_journal_schema(db)
        ensure_customer_contact_schema(db)
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
        db.execute("""CREATE TABLE IF NOT EXISTS vendor_logos (
            vendor TEXT PRIMARY KEY,logo_file TEXT NOT NULL DEFAULT '',
            org_number TEXT NOT NULL DEFAULT '',bankgiro_number TEXT NOT NULL DEFAULT '')""")
        vendor_logo_columns={row['name'] for row in db.execute('PRAGMA table_info(vendor_logos)').fetchall()}
        for column in ('org_number','bankgiro_number'):
            if column not in vendor_logo_columns:
                db.execute("ALTER TABLE vendor_logos ADD COLUMN "+column+" TEXT NOT NULL DEFAULT ''")
        defaults={'p1_days':'5','p2_days':'5','p3_days':'5','fee':'150','fee_locked':'0','interest':'23','objection_days':'5','payment_deadline_days':'5','logo_path':'','logo_file':'','autostart':'1','update_auto':'1','auto_import':'1','cache_auto':'1','cache_last_cleanup':'','ledger_friday_reminder':'1','ledger_last_friday_prompt':'','ledger_last_list_date':'','language':'sv',FONT_SCALE_SETTING:'1.0'}
        for k,v in defaults.items():
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))


def setting(key):
    with connect() as db:
        row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row['value'] if row else ''


def set_setting(key,value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,str(value)))


def saved_supplier_profiles():
    """Load logo and legacy zone-only templates for matching and review."""
    with connect() as db:
        rows=db.execute('SELECT vendor,logo_file,org_number,bankgiro_number FROM vendor_logos').fetchall()
        zone_vendors=db.execute('SELECT DISTINCT vendor FROM pdf_zones').fetchall()
    profiles=[];known=set()
    for row in rows:
        profile=dict(row);key=str(profile.get('vendor') or '').strip().casefold()
        if not key or key in known:continue
        logo_file=Path(str(profile.get('logo_file') or '')).name
        profile['aliases']=svg_logo_aliases(SVG_DIR/logo_file) if logo_file else []
        profiles.append(profile);known.add(key)
    for row in zone_vendors:
        key=str(row['vendor'] or '').strip().casefold()
        if not key or key in known:continue
        profiles.append({'vendor':row['vendor'],'logo_file':'','org_number':'','bankgiro_number':'','aliases':[]})
        known.add(key)
    return profiles


def match_saved_identifier_zones(path,page_indexes,profiles):
    """Match supplier identifiers from their saved, supplier-specific PDF zones."""

    profile_by_key={
        str(profile.get('vendor') or '').strip().casefold():profile
        for profile in profiles if str(profile.get('vendor') or '').strip()
    }
    try:
        with connect() as db:
            zones=db.execute(
                "SELECT vendor,field,page_index,x0,y0,x1,y1 FROM pdf_zones WHERE field IN ('org_number','bankgiro_number') ORDER BY vendor,field"
            ).fetchall()
        if not zones:return None
        import fitz
        candidates={}
        with fitz.open(path) as doc:
            available_pages=list(page_indexes) if page_indexes is not None else list(range(len(doc)))
            for zone in zones:
                key=str(zone['vendor'] or '').strip().casefold()
                profile=profile_by_key.get(key)
                if not profile:continue
                field=zone['field']
                normalizer=normalize_org_number if field=='org_number' else normalize_bankgiro_number
                try:expected=normalizer(profile.get(field))
                except ValueError:continue
                if not expected:continue
                relative_page=zone['page_index']
                if relative_page<0 or relative_page>=len(available_pages):continue
                source_page=available_pages[relative_page]
                if source_page<0 or source_page>=len(doc):continue
                page=doc[source_page]
                rect=fitz.Rect(
                    zone['x0']*page.rect.width,zone['y0']*page.rect.height,
                    zone['x1']*page.rect.width,zone['y1']*page.rect.height,
                )
                actual=parse_supplier_identifier(field,page.get_text('text',clip=rect))
                if not actual or normalizer(actual)!=expected:continue
                entry=candidates.setdefault(key,{'vendor':profile['vendor'],'org':False,'bg':False})
                entry['org' if field=='org_number' else 'bg']=True
    except Exception:
        logger.exception('Saved supplier identifier zones could not be read: file=%s',path)
        return None
    if not candidates:return None
    if len(candidates)!=1:return SupplierMatch('', 'ambiguous_identifier_zone',0)
    entry=next(iter(candidates.values()))
    methods=[]
    if entry['org']:methods.append('org_number_zone')
    if entry['bg']:methods.append('bankgiro_number_zone')
    score=(1000 if entry['org'] else 0)+(800 if entry['bg'] else 0)
    return SupplierMatch(entry['vendor'],'+'.join(methods),score)


def apply_saved_customer_contact(values):
    """Apply saved recipients and an unset invoice logo for the same customer."""
    customer=str(values.get('customer') or '').strip()
    if not customer:return values
    with connect() as db:contact=get_customer_contact(db,customer)
    if contact is not None:
        values['email']=contact['emails']
        saved_logo=str(contact['logo_file'] or '') if 'logo_file' in contact.keys() else ''
        if saved_logo and values.get('logo_file') is None:
            values['logo_file']=saved_logo
            logger.info('Reused logo from previous customer invoice: customer=%s logo=%s',customer,saved_logo)
    return values


def reminder_email_addresses(row):
    """Prefer the customer contact, falling back to legacy invoice email data."""
    with connect() as db:contact=get_customer_contact(db,row['customer'])
    email_text=contact['emails'] if contact is not None else row['email']
    return parse_email_addresses(email_text)


def normalize_invoice_number(value):
    """Treat letter case and whitespace as formatting, not as a new invoice."""
    return ''.join(str(value or '').split()).casefold()


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def invoice_section_hash(source_hash,page_indexes,section_count):
    """Keep single-PDF hashes compatible and distinguish bundled invoices."""

    if section_count<=1:
        return source_hash
    pages=','.join(str(index+1) for index in page_indexes)
    return hashlib.sha256(f'{source_hash}:invoice-pages:{pages}'.encode('ascii')).hexdigest()


def read_invoice_candidates(path):
    """Parse every invoice section and assign a stable per-invoice identity."""

    source_hash=file_sha256(path)
    sections=extract_invoice_sections(str(path))
    return [
        (section,parse_invoice_text(section.text),invoice_section_hash(source_hash,section.page_indexes,len(sections)))
        for section in sections
    ]


INVOICE_PDF_COMPARE_FIELDS = (
    ('invoice_no', 'Fakturanummer'),
    ('customer', 'Kundnamn'),
    ('invoice_date', 'Fakturadatum'),
    ('due_date', 'Förfallodatum'),
    ('amount', 'Fakturabelopp'),
    ('currency', 'Valuta'),
    ('note', 'Fakturatext / Avser'),
)


def find_invoice_pdf_candidate(row, candidates):
    """Find the same invoice section, including in a multi-invoice PDF."""
    values = dict(row)
    source_hash = str(values.get('source_hash') or '').strip()
    if source_hash:
        for candidate in candidates:
            if len(candidate) > 2 and candidate[2] == source_hash:
                return candidate
    invoice_key = normalize_invoice_number(values.get('invoice_no'))
    if not invoice_key:
        return None
    matches = []
    for candidate in candidates:
        if len(candidate) > 1 and normalize_invoice_number((candidate[1] or {}).get('invoice_no')) == invoice_key:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def has_ledger_import_basis(row):
    """Return whether this row has authoritative customer-ledger import markers."""

    values = dict(row)
    return bool(values.get('ledger_first_seen') or values.get('ledger_last_seen'))


ORIGINAL_INVOICE_PROTECTED_FIELDS = ('invoice_no', 'amount', 'currency', 'paid')
ORIGINAL_INVOICE_ENRICHABLE_FIELDS = (
    'customer', 'invoice_date', 'due_date', 'email', 'note', 'template_vendor',
)


def merge_original_invoice_values(row, pdf_values):
    """Add reviewed original-PDF details without replacing ledger financial data."""

    merged = dict(row)
    pdf_values = pdf_values or {}
    for field in ORIGINAL_INVOICE_ENRICHABLE_FIELDS:
        if field not in pdf_values:
            continue
        value = pdf_values.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == '':
            continue
        merged[field] = value
    if 'logo_file' in pdf_values:
        merged['logo_file'] = pdf_values.get('logo_file')
    for field in ORIGINAL_INVOICE_PROTECTED_FIELDS:
        merged[field] = row[field]
    return merged


def compare_invoice_pdf_values(row, pdf_values):
    """Return saved/PDF differences without changing the reviewed invoice."""
    saved = dict(row)
    pdf_values = pdf_values or {}
    differences = []
    for field, _label in INVOICE_PDF_COMPARE_FIELDS:
        if field not in pdf_values:
            continue
        actual = pdf_values.get(field)
        if actual is None or (isinstance(actual, str) and not actual.strip()):
            # A parser that could not read a field must not invent a mismatch.
            continue
        expected = saved.get(field)
        if field == 'invoice_no':
            different = normalize_invoice_number(expected) != normalize_invoice_number(actual)
        elif field in ('invoice_date', 'due_date'):
            different = normalize_date(str(expected or '')) != normalize_date(str(actual or ''))
        elif field == 'amount':
            try:
                different = abs(float(expected or 0) - float(actual or 0)) > 0.005
            except (TypeError, ValueError):
                different = str(expected or '').strip() != str(actual or '').strip()
        elif field == 'currency':
            different = normalize_currency(expected, default='') != normalize_currency(actual, default='')
        else:
            normalize_text = lambda value: re.sub(r'\s+', ' ', str(value or '')).strip().casefold()
            different = normalize_text(expected) != normalize_text(actual)
        if different:
            differences.append({'field': field, 'saved': expected, 'pdf': actual})
    return differences


def verify_invoice_source(row, zone_applier=None):
    """Check an existing source PDF before P1; manual/missing sources are unchanged."""
    values = dict(row)
    source = str(values.get('source') or '').strip()
    if not source:
        return []
    path = Path(source).expanduser()
    if path.suffix.lower() != '.pdf' or not path.is_file():
        return []
    candidates = read_invoice_candidates(path)
    if zone_applier is not None:
        candidates = [
            (section, zone_applier(path, section, dict(pdf_values)), candidate_hash)
            for section, pdf_values, candidate_hash in candidates
        ]
    candidate = find_invoice_pdf_candidate(values, candidates)
    if candidate is None:
        return [{'field': 'source', 'saved': values.get('invoice_no', ''), 'pdf': ''}]
    _section, pdf_values, _candidate_hash = candidate
    return compare_invoice_pdf_values(values, pdf_values)


def find_duplicate_invoice(invoice_no='',source_hash='',exclude_id=None,db=None):
    """Return an existing invoice matched by number or identical PDF content."""
    own_connection=db is None
    connection=db or connect()
    invoice_key=normalize_invoice_number(invoice_no)
    try:
        rows=connection.execute('SELECT * FROM invoices').fetchall()
        for existing in rows:
            if exclude_id is not None and int(existing['id'])==int(exclude_id):
                continue
            if invoice_key and normalize_invoice_number(existing['invoice_no'])==invoice_key:
                return existing
            if source_hash and existing['source_hash'] and existing['source_hash']==source_hash:
                return existing
        return None
    finally:
        if own_connection:
            connection.close()


def save_invoice_record(values,row_id=None):
    """Save an invoice and its reusable customer contact in one transaction."""
    values=dict(values)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if row_id is None:
            contact=get_customer_contact(db,values.get('customer',''))
            if contact is not None:
                reused=[]
                if not str(values.get('email') or '').strip() and contact['emails']:
                    values['email']=contact['emails'];reused.append('email')
                saved_logo=str(contact['logo_file'] or '') if 'logo_file' in contact.keys() else ''
                if saved_logo and values.get('logo_file') is None:
                    values['logo_file']=saved_logo;reused.append('logo')
                if reused:logger.info('Reused customer details while saving new invoice: customer=%s fields=%s',values.get('customer',''),','.join(reused))
        values['email']=normalize_email_addresses(values.get('email',''))
        duplicate=find_duplicate_invoice(values['invoice_no'],values.get('source_hash',''),row_id,db)
        if duplicate is None:
            params=(
                values['customer'],values['invoice_no'],values['invoice_date'],values['due_date'],
                values['template_vendor'],values['amount'],values['currency'],values['paid'],
                values['email'],values['source'],values.get('source_hash',''),values['note'],values['reviewed'],
                values.get('logo_file'),
            )
            if row_id is None:
                db.execute('''INSERT INTO invoices(
                    customer,invoice_no,invoice_date,due_date,template_vendor,amount,currency,paid,email,
                    source,source_hash,note,reviewed,logo_file,created
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',params+(datetime.now().isoformat(timespec='seconds'),))
            else:
                db.execute('''UPDATE invoices SET customer=?,invoice_no=?,invoice_date=?,due_date=?,
                    template_vendor=?,amount=?,currency=?,paid=?,email=?,source=?,source_hash=?,note=?,reviewed=?,logo_file=?
                    WHERE id=?''',params+(row_id,))
            save_customer_contact(db,values['customer'],values['email'],values.get('logo_file'))
    return duplicate


def refresh_json_journal(parent=None):
    """Immediately mirror committed changes to the portable JSON journal."""
    try:
        export_reminder_journal(DB_PATH,JOURNAL_PATH)
        return True
    except Exception as exc:
        logger.exception('JSON journal refresh after saved change failed')
        messagebox.showwarning(
            _('JSON-journalen kunde inte uppdateras'),
            _('JSON-journalen kunde inte skrivas: {error}',error=exc),
            parent=parent,
        )
        return False


def show_duplicate_invoice(duplicate,parent=None):
    messagebox.showwarning(
        _('Dubblettfaktura'),
        _('Faktura {invoice_no} för {customer} finns redan. Den har inte importerats eller sparats igen.',
          invoice_no=duplicate['invoice_no'],customer=duplicate['customer']),
        parent=parent,
    )


def reminder_file_path(row,level,day,prefix=None):
    """Build the reminder filename, optionally matching its original language."""
    reminder_number='1' if level=='P1' else '2'
    safe_invoice_no=re.sub(r'[^A-Za-z0-9_-]','_',str(row['invoice_no']))
    safe_customer=re.sub(r'[^\w-]+','_',str(row['customer']),flags=re.UNICODE).strip('_')[:60] or 'kund'
    prefix=prefix or ('reminder' if get_language()=='en' else 'paminnelse')
    return EXPORT_DIR/f"{prefix}({reminder_number})_{safe_invoice_no}_{safe_customer}_{day.isoformat()}.pdf"


def current_reminder_terms(fee):
    """Capture the terms that affect a reminder PDF, not just its date."""
    return {
        'fee':float(fee or 0),
        'interest':str(setting('interest') or ''),
        'objection_days':str(setting('objection_days') or ''),
        'payment_deadline_days':str(setting('payment_deadline_days') or ''),
    }


def capture_reminder_snapshot(row,fee,day,level):
    """Keep original P1/P2 content so a later logo edit changes only the logo."""
    if level not in ('P1','P2'):raise ValueError('Unknown reminder level')
    snapshot_row=dict(row)
    snapshot_row.pop('p1_snapshot',None)
    snapshot_row.pop('p2_snapshot',None)
    snapshot_row[level.lower()+'_date']=day
    return json.dumps({
        'version':1,
        'row':snapshot_row,
        'terms':current_reminder_terms(fee),
        'language':get_language(),
    },ensure_ascii=False,sort_keys=True)


def capture_p1_snapshot(row,fee,day):
    return capture_reminder_snapshot(row,fee,day,'P1')


def read_reminder_snapshot(value):
    try:
        payload=json.loads(value or '')
    except (TypeError,ValueError):
        return None
    if not isinstance(payload,dict) or not isinstance(payload.get('row'),dict) or not isinstance(payload.get('terms'),dict):
        return None
    return payload


def read_p1_snapshot(value):
    return read_reminder_snapshot(value)


class LogoEmbedError(RuntimeError):
    """Raised when a selected SVG cannot be embedded instead of falling back silently."""


def load_svg_drawing(logo_path):
    path=Path(logo_path)
    if not path.is_file():
        raise LogoEmbedError(_('SVG-logotypen hittades inte: {path}',path=path))
    try:
        from svglib.svglib import svg2rlg
        drawing=svg2rlg(str(path))
    except Exception as exc:
        raise LogoEmbedError(_('SVG-logotypen kunde inte läsas: {path}\n{error}',path=path,error=exc)) from exc
    try:
        from math import isfinite
        width=float(drawing.width);height=float(drawing.height)
    except (AttributeError,TypeError,ValueError):
        raise LogoEmbedError(_('SVG-logotypen har ingen giltig storlek: {path}',path=path))
    if not isfinite(width) or not isfinite(height) or width<=0 or height<=0:
        raise LogoEmbedError(_('SVG-logotypen har ingen giltig storlek: {path}',path=path))
    drawing.width=width;drawing.height=height
    return drawing


def money(x,currency='SEK'):
    return format_money(x,currency)


REMINDER_BCC = 'rl@tadega.com'


def reminder_email_company(row):
    """Return the supplier linked to the reminder, never the customer or a guess."""
    vendor=str(row.get('template_vendor') or '').strip()
    if vendor:return vendor
    logo_file=str(row.get('logo_file') or '').strip()
    if not logo_file:return ''
    try:
        with connect() as db:
            rows=db.execute('SELECT vendor FROM vendor_logos WHERE logo_file=?',(Path(logo_file).name,)).fetchall()
    except sqlite3.Error:
        logger.exception('Could not resolve supplier name for reminder email subject: logo=%s',logo_file)
        return ''
    companies={str(item['vendor'] or '').strip() for item in rows if str(item['vendor'] or '').strip()}
    if len(companies)==1:return next(iter(companies))
    if companies:logger.warning('Reminder email supplier logo is ambiguous: logo=%s matches=%d',logo_file,len(companies))
    return ''


def build_reminder_email_content(row,level,recipients):
    """Build editable preview content with a fixed BCC; never send automatically."""
    addresses=parse_email_addresses(','.join(recipients))
    if not addresses:raise ValueError('At least one recipient is required')
    email_row=dict(row)
    try:followup=level=='P2' or int(email_row.get('sent_count') or 0)>0
    except (TypeError,ValueError):followup=level=='P2'
    terms=current_reminder_terms(float(setting('fee') or 0))
    snapshot_column=level.lower()+'_snapshot'
    snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
    if snapshot:
        email_row.update(snapshot['row'])
        terms=snapshot['terms']
    try:fee=float(terms.get('fee') if terms.get('fee') is not None else setting('fee') or 0)
    except (TypeError,ValueError):fee=float(setting('fee') or 0)
    remaining=max(0,float(email_row['amount'] or 0)-float(email_row['paid'] or 0))
    reminder_day=dparse(email_row.get(level.lower()+'_date')) or date.today()
    try:
        saved_deadline=terms.get('payment_deadline_days')
        deadline_days=int(saved_deadline) if saved_deadline not in (None,'') else 5
    except (TypeError,ValueError):deadline_days=5
    deadline=format_long_date(reminder_day+timedelta(days=deadline_days))
    currency=email_row['currency']
    invoice_no=email_row['invoice_no']
    values={
        'invoice_no':invoice_no,'due_date':email_row['due_date'],
        'remaining':money(remaining,currency),'fee':money(fee,currency),
        'fees':money(fee*(2 if level=='P2' else 1),currency),
        'total':money(remaining+fee*(2 if level=='P2' else 1),currency),
        'deadline':deadline,
    }
    subject=_('Faktura {invoice_no} – betalningspåminnelse',invoice_no=invoice_no)
    company=reminder_email_company(email_row)
    if company:subject+=f' - {company}'
    if followup:subject=('Re: ' if get_language()=='en' else 'SV: ')+subject
    if level=='P2':
        body=_(
            'Hej!\n\nTrots tidigare påminnelse är faktura {invoice_no}, som förföll {due_date}, fortfarande obetald. Detta är andra påminnelsen.\n\nKvarstående fakturabelopp: {remaining}\nPåminnelseavgifter för P1 och P2: {fees}\nAtt betala: {total}\nSista betalningsdag: {deadline}\n\nBetalningen av hela beloppet ska vara oss tillhanda senast {deadline}. Ange fakturanumret som referens. Om betalningen inte har kommit in efter sista betalningsdag kan ärendet lämnas vidare utan ytterligare påminnelse. Påminnelsen skickas som PDF. Om betalningen redan är gjord, kontakta oss med betalningsuppgifter så att vi kan stämma av.\n\nVänliga hälsningar\nTadega AB',
            invoice_no=invoice_no,due_date=email_row['due_date'],remaining=values['remaining'],
            fees=values['fees'],total=values['total'],deadline=deadline,
        )
    else:
        body=_(
            'Hej!\n\nFaktura {invoice_no} förföll {due_date} och är fortfarande obetald. Detta är första påminnelsen.\n\nKvarstående fakturabelopp: {remaining}\nPåminnelseavgift: {fee}\nAtt betala: {total}\nSista betalningsdag: {deadline}\n\nBetalningen av hela beloppet ska vara oss tillhanda senast {deadline}. Ange fakturanumret som referens. Påminnelsen skickas som PDF. Om betalningen redan är gjord, kontakta oss med betalningsuppgifter så att vi kan stämma av.\n\nVänliga hälsningar\nTadega AB',
            invoice_no=invoice_no,due_date=email_row['due_date'],remaining=values['remaining'],
            fee=values['fee'],total=values['total'],deadline=deadline,
        )
    return {'recipients':addresses,'bcc':REMINDER_BCC,'subject':subject,'body':body}


def build_reminder_mailto(row,level,recipients,content=None):
    """Encode previewed content without allowing recipients or BCC to be changed."""
    content=content or build_reminder_email_content(row,level,recipients)
    addresses=content['recipients']
    query=urlencode({'bcc':REMINDER_BCC,'subject':content['subject'],'body':content['body']},quote_via=quote)
    return 'mailto:'+quote(','.join(addresses),safe='@,+._-')+'?'+query


def dparse(s):
    try: return date.fromisoformat(s)
    except Exception: return None


def is_fully_paid(row):
    """Use the same settled threshold for display and import suppression."""

    return float(row['amount'] or 0)-float(row['paid'] or 0)<=0.005


def p2_due_date(row):
    """Respect both the configured P2 interval and the printed P1 deadline."""
    p1_date=dparse(row['p1_date'])
    if not p1_date:return None
    interval_days=int(setting('p2_days') or 5)
    deadline_days=int(setting('payment_deadline_days') or 5)
    snapshot=read_p1_snapshot(row['p1_snapshot'] if 'p1_snapshot' in row.keys() else '')
    if snapshot:
        try:
            saved_deadline=snapshot['terms'].get('payment_deadline_days')
            if saved_deadline not in (None,''):deadline_days=int(saved_deadline)
        except (TypeError,ValueError):
            pass
    return p1_date+timedelta(days=max(interval_days,deadline_days))


def next_stage(row):
    if row['ignored']:return 'Ignorerad'
    if is_fully_paid(row): return 'Avslutad'
    if not row['reviewed']:return 'Granska uppgifter'
    today=date.today(); due=dparse(row['due_date'])
    if not due: return 'Kontrollera datum'
    if not row['p1_date']:
        return 'P1 att skapa' if (today-due).days >= int(setting('p1_days') or 5) else 'Väntar P1'
    if not row['p2_date']:
        p2_due=p2_due_date(row)
        return 'P2 att skapa' if p2_due and today>=p2_due else 'Väntar P2'
    if (today-dparse(row['p2_date'])).days >= int(setting('p3_days') or 5): return 'Kronofogden – granska'
    return 'Väntar – efter P2'


INVOICE_ROW_COLORS = {
    'status-not-due':'#e2f4e8',
    'status-p1':'#fff1c2',
    'status-p2':'#fbdede',
}


def configure_invoice_row_colors(tree,high_contrast=False):
    """Keep status text readable in both normal and system high-contrast mode."""
    palette=contrast_palette(high_contrast)
    for tag,background in INVOICE_ROW_COLORS.items():
        tree.tag_configure(
            tag,
            background=palette['field_background'] if high_contrast else background,
            foreground=palette['text'],
        )


def invoice_row_color_tag(row,stage=None,today=None):
    """Map the existing reminder state to a color without changing the workflow."""
    if row['ignored'] or is_fully_paid(row) or not row['reviewed']:return ''
    due=dparse(row['due_date'])
    if not due:return ''
    stage=stage or next_stage(row)
    if row['p2_date'] or stage=='P2 att skapa':return 'status-p2'
    if row['p1_date'] or stage=='P1 att skapa':return 'status-p1'
    if due>=(today or date.today()):return 'status-not-due'
    return ''


def due_reminder_invoices():
    """Return unpaid, reviewed invoices whose normal workflow is ready for P1/P2."""
    with connect() as db:
        rows=db.execute('SELECT * FROM invoices ORDER BY due_date,invoice_no').fetchall()
    return [row for row in rows if next_stage(row) in ('P1 att skapa','P2 att skapa')]


def show_due_reminder_dialog(parent=None):
    """Tell the user which invoices are ready after an import-folder scan."""
    rows=due_reminder_invoices()
    if not rows:return False
    lines=[]
    for row in rows[:12]:
        level='P1' if next_stage(row)=='P1 att skapa' else 'P2'
        lines.append(f"{level}: {row['invoice_no']} – {row['customer']}")
    if len(rows)>12:lines.append(_('… och {count} till',count=len(rows)-12))
    messagebox.showinfo(
        _('Dags att skapa P1/P2'),
        _('Följande fakturor är redo för P1 eller P2:\n\n{reminders}\n\nVälj en faktura i listan och klicka på Skapa påminnelse.',reminders='\n'.join(lines)),
        parent=parent,
    )
    return True


def reminder_file_candidates(row,level):
    """Return possible original P1/P2 paths in snapshot/language order."""
    if level not in ('P1','P2'):return []
    date_column=level.lower()+'_date';snapshot_column=level.lower()+'_snapshot'
    original_date=dparse(row[date_column])
    if not original_date:return []
    snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
    base=dict(row);language=get_language()
    if snapshot:
        base.update(snapshot['row'])
        snapshot_language=str(snapshot.get('language') or '')
        if snapshot_language in SUPPORTED_LANGUAGES:language=snapshot_language
    prefixes=('reminder','paminnelse') if language=='en' else ('paminnelse','reminder')
    paths=[]
    for prefix in prefixes:
        path=reminder_file_path(base,level,original_date,prefix)
        paths.extend((
            path,
            customer_archive_path(EXPORT_DIR,base['customer'],path.name),
            path.parent/ARCHIVE_FOLDER_NAME/path.name,
        ))
    return list(dict.fromkeys(paths))


def p1_file_candidates(row):
    return reminder_file_candidates(row,'P1')


def p2_file_candidates(row):
    return reminder_file_candidates(row,'P2')


def find_reminder_pdf(row,level):
    """Locate an existing P1/P2 PDF, including archived and legacy event paths."""
    if level not in ('P1','P2'):return None
    paths=list(reminder_file_candidates(row,level))
    if 'id' in row.keys():
        with connect() as db:
            events=db.execute(
                'SELECT payload FROM reminder_events WHERE invoice_id=? AND level=? AND reminder_date=? ORDER BY created_utc DESC',
                (row['id'],level,row[level.lower()+'_date']),
            ).fetchall()
        recorded=[]
        for event in events:
            try:payload=json.loads(event['payload'])
            except (TypeError,ValueError):continue
            if not isinstance(payload,dict):continue
            pdf_name=Path(str(payload.get('pdf_name') or '')).name
            if pdf_name:
                event_invoice=payload.get('invoice') if isinstance(payload.get('invoice'),dict) else {}
                customer=event_invoice.get('customer') or row['customer']
                recorded.extend((
                    EXPORT_DIR/pdf_name,
                    customer_archive_path(EXPORT_DIR,customer,pdf_name),
                    EXPORT_DIR/ARCHIVE_FOLDER_NAME/pdf_name,
                ))
        paths=recorded+paths
    return next((path for path in dict.fromkeys(paths) if path.is_file()),None)


def latest_reminder_level(row):
    """Return the latest existing level; P2 always takes precedence over P1."""
    return 'P2' if row['p2_date'] else ('P1' if row['p1_date'] else '')


def reminder_email_status(row,level=None):
    """Describe one level, defaulting to the latest, apart from PDF dates."""
    level=level or latest_reminder_level(row)
    if not level:return '—'
    prefix=level.lower();keys=row.keys()
    sent=row[prefix+'_sent_date'] if prefix+'_sent_date' in keys else ''
    draft=row[prefix+'_draft_date'] if prefix+'_draft_date' in keys else ''
    if sent:return _('{level} · skickad {date}',level=level,date=sent)
    if draft:return _('{level} · utkast öppnat {date}',level=level,date=draft)
    return _('{level} · utkast ej öppnat',level=level)


def record_reminder_draft_opened(row,level):
    """Remember the first successful draft opening without changing reminder history."""
    if level not in ('P1','P2'):return
    column=level.lower()+'_draft_date';today=date.today().isoformat()
    with connect() as db:
        db.execute(
            f"UPDATE invoices SET {column}=CASE WHEN {column} IS NULL OR {column}='' THEN ? ELSE {column} END WHERE id=?",
            (today,row['id']),
        )


def p1_file_missing(row):
    """A recorded P1 whose PDF no longer exists can be recreated safely."""
    return bool(row['p1_date']) and not any(path.is_file() for path in p1_file_candidates(row))


def reminder_archive_customer_map():
    """Map exact reminder basenames to their saved customer without guessing."""
    customers={};ambiguous=set()
    with connect() as db:rows=db.execute('SELECT * FROM invoices').fetchall()
    for row in rows:
        for level in ('P1','P2'):
            if not row[level.lower()+'_date']:continue
            snapshot_column=level.lower()+'_snapshot'
            snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
            customer=str(snapshot['row'].get('customer') or row['customer']).strip() if snapshot else str(row['customer'] or '').strip()
            if not customer:continue
            for path in reminder_file_candidates(row,level):
                name=path.name
                if name in ambiguous:continue
                existing=customers.get(name)
                if existing is not None and existing.casefold()!=customer.casefold():
                    ambiguous.add(name);customers.pop(name,None)
                else:customers[name]=customer
    if ambiguous:
        logger.warning('Reminder archive skipped ambiguous customer mappings: files=%s',','.join(sorted(ambiguous)))
    return customers


class ReminderApp(tk.Tk):
    def __init__(self):
        set_language(setting('language') or 'sv')
        super().__init__(); self.title(APP_NAME); self.geometry('1180x700'); self.minsize(940,560)
        self.configure(bg='#f3f5f8'); self._style(); self._configure_icons(); self.current_filter_key='current'
        self.invoice_sort_column='due_date';self.invoice_sort_reverse=False
        self._update_check_running=False;self._update_install_running=False;self._update_install_stage=None;self._available_update=None;self._update_helper_process=None;self.update_button=None
        self.tray=None;self._quitting=False;self._contrast_check_running=False
        self._import_monitor=ImportFolderMonitor(IMPORT_DIR);self._import_scan_running=False;self._python_addons_ready=False
        self._python_addon_install_running=False;self._python_addon_updates_running=False;self._python_addon_maintenance_attempted_week=''
        self.build(); self.refresh()
        self.after(SYSTEM_CONTRAST_POLL_INTERVAL_MS,self._poll_system_contrast)
        self.protocol('WM_DELETE_WINDOW',self.hide_to_tray)
        self.bind('<Unmap>',self._on_main_window_unmap,add='+')
        self.start_tray()
        self.after(100,self.sync_autostart)
        # Startup only recovers missing dependencies. Weekly upgrades are separate.
        self.after(250,self.check_python_addons)
        if not sys.platform.startswith('win'):
            self.after(1000,self._run_scheduled_python_addon_maintenance)
        self.after(2000,self._run_scheduled_update_check)
        self.after(1500,self._run_scheduled_import_scan)
        self.after(2500,self._run_scheduled_error_log_refresh)
        self.after(3000,self._run_scheduled_cache_cleanup)
        self.after(4000,self._run_scheduled_journal_backup)
        self.after(4500,self._run_scheduled_reminder_archive)
        self.after(6000,self._run_scheduled_ledger_reminder)

    def report_callback_exception(self,exc_type,exc_value,exc_traceback):
        """Retain unexpected Tk callback failures in a console-free installation."""
        log_activity(
            'ui','unhandled_callback_exception','error',level=logging.ERROR,
            exc_info=(exc_type,exc_value,exc_traceback),
            error_type=getattr(exc_type,'__name__',str(exc_type)),error=str(exc_value),
        )

    def start_tray(self):
        """Start the tray icon lazily so unsupported desktops can still run the app."""
        if self.tray is not None and self.tray.running:return
        self.tray=TrayController(
            name=APP_NAME,identifier=APP_SLUG,icon_path=ICON_DIR/'paypamin_flow_256.png',
            scheduler=lambda callback:self.after(0,callback),on_open=self.show_from_tray,
            on_update=self.update_from_tray,on_exit=self.quit_app,
            open_label=lambda:_('Öppna {app_name}',app_name=APP_NAME),
            update_label=self._update_tray_label,exit_label=lambda:_('Avsluta helt'),on_error=self.handle_tray_error)
        try:
            self.tray.start();self._configure_macos_dock_icon();logger.info('System tray icon started')
        except TrayUnavailable as exc:
            logger.warning('System tray is unavailable: %s',exc)

    def handle_tray_error(self,error):
        if self._quitting:return
        logger.error('System tray stopped unexpectedly: %s',error)
        if self.tray is not None:self.tray.stop()
        self.deiconify()
        messagebox.showwarning(_('Systemfältet är inte tillgängligt'),_('Systemfältet slutade fungera. Fönstret visas igen.'),parent=self)

    def show_from_tray(self):
        log_activity('tray','open_window','started')
        self.deiconify();self.lift()
        try:self.focus_force()
        except tk.TclError:pass
        if sys.platform.startswith('win'):
            self.after_idle(lambda:configure_windows_window_icon(self))
        self.after_idle(self._maybe_show_ledger_reminder)
        log_activity('tray','open_window','completed')

    def update_from_tray(self):
        """Open a visible manual update check from the system-tray menu."""
        log_activity('tray','update_requested','started')
        self.show_from_tray()
        result=self.check_for_updates(manual=True)
        log_activity('tray','update_requested','completed')
        return result

    def _on_main_window_unmap(self,event):
        """Handle a window-manager minimize after Tk has updated its state."""
        if event.widget is not self or self._quitting:return
        self.after_idle(self._hide_minimized_window)

    def _hide_minimized_window(self):
        """Minimize hides to the tray; our own withdraw must not retrigger it."""
        if self._quitting:return
        try:minimized=self.state()=='iconic'
        except tk.TclError:return
        if minimized:self.hide_to_tray()

    def hide_to_tray(self):
        """Close and minimize hide the window until the user chooses full exit."""
        if self._quitting:return
        if self.tray is None or not self.tray.running:self.start_tray()
        if self.tray is None or not self.tray.running:
            try:
                if self.state()=='iconic':self.deiconify()
            except tk.TclError:pass
            if messagebox.askyesno(_('Systemfältet är inte tillgängligt'),_('Fönstret kan inte döljas i systemfältet på den här datorn. Vill du avsluta appen helt?'),parent=self):self.quit_app()
            return
        self.withdraw();logger.info('Main window hidden to system tray')
        log_activity('tray','window_hidden','completed')

    def quit_app(self):
        """Exit the whole application rather than only hiding its window."""
        if self._quitting:return
        if getattr(self,'_update_install_running',False):
            messagebox.showinfo(_('Uppdatering pågår'),_('Vänta tills uppdateringen är klar. Appen startas sedan om automatiskt.'),parent=self)
            return
        self._quitting=True
        self._run_exit_cache_cleanup()
        if self.tray is not None:self.tray.stop()
        logger.info('Application exited by user')
        log_activity('application','exit_requested','completed')
        self.destroy()

    def backup_paths(self):
        return BackupPaths(database=DB_PATH,export_dir=EXPORT_DIR,svg_dir=SVG_DIR,safety_dir=APP_DIR/'backups')

    def create_backup(self):
        selected=filedialog.asksaveasfilename(parent=self,title=_('Säkerhetskopiera inställningar och påminnelser'),initialfile=suggested_backup_filename(),defaultextension='.zip',filetypes=[(_('ZIP-säkerhetskopia'),'*.zip')])
        if not selected:return
        try:
            destination=create_local_backup(selected,self.backup_paths())
            logger.info('Local backup created: %s',destination)
            messagebox.showinfo(_('Säkerhetskopiering klar'),_('Inställningar, fakturor, påminnelser och logotyper har kopierats till:\n{path}',path=destination),parent=self)
        except BackupError as exc:
            logger.error('Local backup failed: %s',exc)
            messagebox.showerror(_('Säkerhetskopieringen misslyckades'),str(exc),parent=self)

    def restore_backup(self):
        selected=filedialog.askopenfilename(parent=self,title=_('Återställ säkerhetskopia'),filetypes=[(_('ZIP-säkerhetskopia'),'*.zip')])
        if not selected:return
        if not messagebox.askyesno(_('Återställ säkerhetskopia'),_('Nuvarande inställningar, fakturor, påminnelser och logotyper ersätts. En ny säkerhetskopia av nuvarande data skapas först. Vill du fortsätta?'),parent=self):return
        try:
            safety=restore_local_backup(selected,self.backup_paths())
            init_db();set_language(setting('language') or 'sv');self.sync_autostart();self.rebuild_ui()
            logger.info('Local backup restored; safety copy: %s',safety)
            messagebox.showinfo(_('Återställningen är klar'),_('Säkerhetskopian har återställts. En kopia av tidigare data finns här:\n{path}',path=safety),parent=self)
        except BackupError as exc:
            logger.error('Local restore failed: %s',exc)
            messagebox.showerror(_('Återställningen misslyckades'),str(exc),parent=self)

    def import_journal(self):
        """Import a portable JSON journal after reinstalling or on another copy."""
        initial_dir=JOURNAL_BACKUP_DIR if JOURNAL_BACKUP_DIR.is_dir() else APP_DIR
        selected=filedialog.askopenfilename(
            parent=self,title=_('Importera JSON-journal'),initialdir=str(initial_dir),
            filetypes=[(_('JSON-journal'),'*.json')],
        )
        if not selected:return
        if not messagebox.askyesno(
            _('Importera JSON-journal'),
            _('JSON-journalen slås samman med befintliga fakturor och påminnelser. Dubbletter skapas inte. Importerade inställningar och mallar återställs. Vill du fortsätta?'),
            parent=self,
        ):return
        try:
            result=import_reminder_journal_file(DB_PATH,JOURNAL_PATH,selected)
            init_db();set_language(setting('language') or 'sv');self.sync_autostart();self.rebuild_ui()
            logger.info('JSON journal imported: invoices_added=%s invoices_merged=%s reminders_added=%s reminders_skipped=%s',result.invoices_added,result.invoices_merged,result.reminders_added,result.reminders_skipped)
            messagebox.showinfo(
                _('JSON-journal importerad'),
                _('Fakturor tillagda: {added}\nBefintliga fakturor sammanfogade: {merged}\nPåminnelser tillagda: {reminders}\nDubbletter som hoppades över: {skipped}',added=result.invoices_added,merged=result.invoices_merged,reminders=result.reminders_added,skipped=result.reminders_skipped),
                parent=self,
            )
        except JournalError as exc:
            logger.error('JSON journal import failed: %s',exc)
            messagebox.showerror(_('JSON-journalen kunde inte importeras'),str(exc),parent=self)

    def _configure_icons(self):
        """Use the product identity for windows, OS icons and the header logo."""
        self._window_icons=[];self._header_icon=None;self._brand_logo=None;self._action_icons={}
        self._configure_macos_dock_icon()
        try:
            for size in (16,32,48,256):
                path=ICON_DIR/f'paypamin_flow_{size}.png'
                if path.is_file():self._window_icons.append(tk.PhotoImage(master=self,file=str(path)))
            if self._window_icons:self.iconphoto(True,*self._window_icons)
            header_path=ICON_DIR/'paypamin_flow_48.png'
            if header_path.is_file():self._header_icon=tk.PhotoImage(master=self,file=str(header_path))
            logo_path=ICON_DIR/'paypamin_logo.png'
            if logo_path.is_file():self._brand_logo=tk.PhotoImage(master=self,file=str(logo_path))
            # Keep the native Windows icon last so it is not replaced by the
            # generic pythonw.exe taskbar icon on older Tk/Windows versions.
            if sys.platform.startswith('win') and (ICON_DIR/'paypamin_flow.ico').is_file():
                self.iconbitmap(default=str(ICON_DIR/'paypamin_flow.ico'))
                configure_windows_window_icon(self)
                # Reapply after the native top-level window has been mapped.
                self.after_idle(lambda:configure_windows_window_icon(self))
        except tk.TclError:
            logger.exception('Application icon could not be loaded')

    def _ui_icon(self,name,inverse=False):
        """Load and retain one shared transparent action icon."""
        if not name:return None
        key=(name,bool(inverse))
        if key in self._action_icons:return self._action_icons[key]
        suffix='_light' if inverse else ''
        path=ICON_DIR/'icons'/f'{name}{suffix}.png'
        if not path.is_file():return None
        try:
            image=tk.PhotoImage(master=self,file=str(path))
        except tk.TclError:
            logger.warning('UI icon could not be loaded: %s',path)
            return None
        self._action_icons[key]=image
        return image

    def _instrument_menu_actions(self,menu):
        """Trace every menu command while retaining its registered Tk callback."""
        try:
            last=menu.index('end')
            if last is None:return
            completed=getattr(menu,'_activity_logged_entries',set())
            for index in range(last+1):
                if index in completed or menu.type(index)!='command':continue
                command=menu.entrycget(index,'command')
                if not command:continue
                label=menu.entrycget(index,'label')
                menu.entryconfigure(index,command=instrument_tk_command(menu,command,label,'menu'))
                completed.add(index)
            menu._activity_logged_entries=completed
        except (tk.TclError,AttributeError,TypeError):
            logger.debug('Menu activity tracing could not be applied',exc_info=True)

    def _instrument_action_tree(self,root):
        """Recursively trace buttons and checkboxes after a window has been built."""
        try:
            if root.winfo_class() in ('TButton','Button','TCheckbutton','Checkbutton','TRadiobutton','Radiobutton'):
                if not getattr(root,'_activity_command_instrumented',False):
                    command=root.cget('command')
                    if command:
                        label=root.cget('text') or root.winfo_class()
                        root.configure(command=instrument_tk_command(root,command,label,'ui'))
                    root._activity_command_instrumented=True
            children=root.winfo_children()
        except (tk.TclError,AttributeError,TypeError):
            return
        for child in children:self._instrument_action_tree(child)

    def _finalize_window_actions(self,window,main_window=False):
        self._apply_action_icons(window)
        self._instrument_action_tree(window)
        try:focus_window=window.winfo_toplevel()
        except (AttributeError,tk.TclError):focus_window=window
        self._install_accessibility_shortcuts(focus_window,main_window=main_window)
        high_contrast=getattr(self,'_high_contrast',False)
        apply_widget_contrast(focus_window,high_contrast)
        prepare_focus_tree(focus_window,high_contrast)
        for menu in (getattr(self,'main_menu',None),getattr(self,'file_menu',None),getattr(self,'help_menu',None),getattr(self,'row_menu',None)):
            if menu is not None:apply_widget_contrast(menu,high_contrast)
        try:focus_window.after_idle(lambda:focus_first(focus_window))
        except (AttributeError,tk.TclError):focus_first(focus_window)

    def _apply_menu_icons(self,menu):
        """Keep menu commands and cascades text-only without changing actions."""
        try:
            last=menu.index('end')
            if last is None:return
            for index in range(last+1):
                if menu.type(index) not in ('command','cascade'):continue
                menu.entryconfigure(index,image='',compound='none')
        except (tk.TclError,AttributeError):
            logger.debug('Text-only menu entries could not be applied',exc_info=True)

    def _apply_action_icons(self,root):
        """Recursively keep buttons text-only without changing their commands."""
        try:
            if root.winfo_class() in ('TButton','Button'):
                root.configure(image='',compound='none')
            children=root.winfo_children()
        except (tk.TclError,AttributeError):
            return
        for child in children:self._apply_action_icons(child)

    def _set_window_icon(self,window):
        """Explicitly brand every secondary window on every desktop platform."""
        try:
            if self._window_icons:window.iconphoto(False,*self._window_icons)
            if sys.platform.startswith('win') and (ICON_DIR/'paypamin_flow.ico').is_file():
                window.iconbitmap(str(ICON_DIR/'paypamin_flow.ico'))
                configure_windows_window_icon(window)
        except tk.TclError:
            logger.exception('Secondary window icon could not be loaded')

    def _finalize_toplevel(self,window):
        # Repeat native branding after mapping so Windows cannot retain the
        # generic pythonw.exe icon in the taskbar or window switcher.
        self._set_window_icon(window)
        self._finalize_window_actions(window)
        fit_window_to_screen(window)

    def _new_toplevel(self,title):
        window=tk.Toplevel(self)
        window.title(title);window.transient(self);window.resizable(True,True)
        self._set_window_icon(window)
        window.after_idle(lambda: self._finalize_toplevel(window))
        return window

    def _dialog_form(self,window,padding=20):
        """Return a scrollable form so large text never hides dialog actions."""
        return ScrollableForm(window,tk,ttk,padding=padding).form

    def _configure_macos_dock_icon(self):
        if sys.platform!='darwin':return
        try:
            from AppKit import NSApplication,NSImage
            image=NSImage.alloc().initWithContentsOfFile_(str(ICON_DIR/'paypamin_flow_256.png'))
            if image:NSApplication.sharedApplication().setApplicationIconImage_(image)
        except Exception as exc:
            # Python Launcher may not have installed PyObjC yet; pystray pulls
            # it in and the next icon setup retries without affecting the UI.
            logger.info('macOS dock icon is not available yet: %s',exc)

    def sync_autostart(self):
        try:
            set_autostart(setting('autostart')=='1')
            logger.info('Login autostart synchronized: enabled=%s',setting('autostart')=='1')
        except AutostartError as exc:
            logger.error('Login autostart could not be synchronized: %s',exc)
            messagebox.showwarning(_('Autostart kunde inte uppdateras'),_('Inställningen för autostart kunde inte sparas.\n\nPlats: {location}\n\n{error}',location=autostart_location(),error=_(str(exc))),parent=self)

    def show_about(self):
        w=self._new_toplevel(_('Om {app_name}',app_name=APP_NAME));w.resizable(True,True);w.configure(bg='#f3f5f8')
        form=self._dialog_form(w,padding=24)
        if self._brand_logo:ttk.Label(form,image=self._brand_logo).pack(pady=(0,10))
        else:
            if self._header_icon:ttk.Label(form,image=self._header_icon).pack(pady=(0,10))
            ttk.Label(form,text=APP_NAME,style='Title.TLabel').pack()
        ttk.Label(form,text=_('Version {version}',version=APP_VERSION),style='Sub.TLabel').pack(pady=(3,12))
        if APP_RELEASE_COMMIT:ttk.Label(form,text=_('Byggcommit: {commit}',commit=APP_RELEASE_COMMIT[:12]),style='Sub.TLabel').pack(pady=(0,8))
        ttk.Label(form,text=_('Lokal app för fakturor och betalningspåminnelser')).pack()
        ttk.Label(form,text=SUPPORTED_PLATFORMS,style='Sub.TLabel').pack(pady=(5,16))
        ttk.Label(form,text=APP_COPYRIGHT).pack()
        ttk.Label(form,text=_('Skapare: {author}',author=APP_AUTHOR)).pack(pady=(4,0))
        ttk.Button(form,text=_('Stäng'),command=w.destroy,style='Accent.TButton').pack(pady=(20,0))

    def _run_scheduled_update_check(self):
        if setting('update_auto')=='1':self.check_for_updates(manual=False)
        self.after(UPDATE_CHECK_INTERVAL_MS,self._run_scheduled_update_check)

    def _update_button_idle_text(self):
        return _('Uppdatering tillgänglig') if getattr(self,'_available_update',None) is not None else _('Uppdatera appen')

    def _update_tray_label(self):
        if getattr(self,'_update_install_running',False):return _('Uppdaterar…')
        if getattr(self,'_update_check_running',False):return _('Söker…')
        return self._update_button_idle_text()

    def _refresh_tray_menu(self):
        tray=getattr(self,'tray',None)
        if tray is not None:
            try:tray.refresh()
            except Exception:logger.debug('Tray update label could not be refreshed',exc_info=True)

    def _set_update_available(self,release):
        self._available_update=release
        self._refresh_tray_menu()
        if getattr(self,'_update_check_running',False) or getattr(self,'_update_install_running',False):return
        button=getattr(self,'update_button',None)
        if not button:return
        try:button.configure(text=self._update_button_idle_text(),state='normal')
        except tk.TclError:pass

    def _set_update_check_busy(self,busy):
        self._refresh_tray_menu()
        button=getattr(self,'update_button',None)
        if not button:return
        try:button.configure(text=_('Söker…') if busy else self._update_button_idle_text(),state='disabled' if busy else 'normal')
        except tk.TclError:pass

    def _set_update_install_busy(self,busy,stage=None):
        if busy and stage:self._update_install_stage=stage
        elif not busy:self._update_install_stage=None
        self._refresh_tray_menu()
        button=getattr(self,'update_button',None)
        if not button:return
        labels={'download':_('Hämtar och verifierar…'),'install':_('Installerar filer…'),'restart':_('Startar om…')}
        text=labels.get(getattr(self,'_update_install_stage',None),_('Uppdaterar…')) if busy else self._update_button_idle_text()
        try:button.configure(text=text,state='disabled' if busy else 'normal')
        except tk.TclError:pass

    def check_for_updates(self,manual=False,force=False):
        """Open a known update or check GitHub in a background worker."""
        log_activity('update','check_requested','started',manual=manual,force=force)
        if self._update_check_running or self._update_install_running:
            log_activity('update','check_requested','skipped',manual=manual,reason='already_running')
            if manual:messagebox.showinfo(_('Uppdateringskontroll'),_('En uppdateringskontroll eller installation pågår redan.'),parent=self)
            return
        available=getattr(self,'_available_update',None)
        if manual and available is not None and not force:
            log_activity('update','check_requested','completed',manual=manual,cached=True)
            self.show_update_available(available);return
        if force:self._set_update_available(None)
        self._update_check_running=True;self._set_update_check_busy(True)
        result_queue=queue.Queue()
        def check():
            try:result_queue.put(('ok',manual,fetch_latest_release()))
            except Exception as exc:result_queue.put(('error',manual,exc))
        threading.Thread(target=check,daemon=True).start()
        log_activity('update','check_requested','completed',manual=manual,force=force,cached=False)
        self.after(200,lambda:self._poll_update_check(result_queue))

    def _poll_update_check(self,result_queue):
        try:status,manual,payload=result_queue.get_nowait()
        except queue.Empty:
            self.after(200,lambda:self._poll_update_check(result_queue));return
        self._update_check_running=False;self._set_update_check_busy(False)
        if status=='error':
            log_activity('update','check_finished','error',level=logging.WARNING,manual=manual,error=str(payload))
            logger.warning('GitHub update check failed: %s',payload)
            if manual:
                details=str(payload) if isinstance(payload,UpdateCheckError) else _('Ett oväntat fel uppstod vid uppdateringskontrollen.')
                messagebox.showwarning(_('Kunde inte söka efter uppdateringar'),details,parent=self)
            return
        release=payload
        if is_update_available(release,APP_VERSION):
            self._set_update_available(release)
            missing=missing_release_assets(release)
            log_activity('update','check_finished','update_available',manual=manual,version=release.version,release_id=release.release_id,commit=release.release_commit,missing_assets=missing)
            logger.info('New PayPamin Flow release available: current=%s latest=%s release_id=%s commit=%s files=%s missing_assets=%s',APP_VERSION,release.version,release.release_id,release.release_commit,release.package_fingerprint[:12],missing)
            if missing:
                logger.warning('Release package is not ready; automatic installation waits')
                if manual:self.show_update_available(release)
                return
            if manual:self.show_update_available(release)
            elif setting('update_auto')=='1':self.start_update_installation(release,manual=False)
            return
        self._set_update_available(None)
        log_activity('update','check_finished','current',manual=manual,version=release.version,release_id=release.release_id,commit=release.release_commit)
        logger.info('No newer PayPamin Flow release: current=%s latest=%s',APP_VERSION,release.version)
        if manual:
            commit=release.release_commit[:12] or APP_RELEASE_COMMIT[:12] or _('okänd')
            messagebox.showinfo(_('Ingen uppdatering tillgänglig'),_('Ingen ny version eller ändrade releasefiler finns.\n\nInstallerad version: {current}\nSenaste release: {latest}\nRelease-commit: {commit}',current=APP_VERSION,latest=release.version,commit=commit),parent=self)

    def start_update_installation(self,release,manual=False):
        log_activity('update','install_requested','started',manual=manual,version=release.version,release_id=release.release_id)
        if self._update_install_running:
            log_activity('update','install_requested','skipped',manual=manual,reason='already_running')
            return
        missing=missing_release_assets(release)
        if missing:
            log_activity('update','install_requested','blocked',level=logging.WARNING,manual=manual,missing_assets=missing)
            logger.warning('Update installation blocked until release files are ready: %s',missing)
            if manual:messagebox.showwarning(_('Uppdateringsfiler saknas'),_('Releasefilerna är inte klara ännu. Försök igen senare.\n\nSaknas: {files}',files=', '.join(missing)),parent=self)
            return
        self._update_install_running=True;self._set_update_install_busy(True)
        result_queue=queue.Queue()
        def install():
            try:
                result_queue.put(('progress',manual,release,'download'))
                plan=stage_update(release,log_path=LOG_DIR/'update.log')
                result_queue.put(('progress',manual,release,'install'))
                installed=install_update(plan)
                result_queue.put(('progress',manual,release,'restart'))
                result_queue.put(('restart',manual,release,installed))
            except Exception as exc:result_queue.put(('error',manual,release,exc))
        threading.Thread(target=install,daemon=True).start()
        log_activity('update','install_requested','completed',manual=manual,version=release.version,release_id=release.release_id)
        self.after(200,lambda:self._poll_update_installation(result_queue))

    def _update_restart_failed(self,release,installed,error,manual):
        try:rollback_update(installed)
        except UpdateInstallError:logger.exception('Update rollback failed')
        cleanup_update(installed)
        self._update_helper_process=None
        self._update_install_running=False;self._set_update_install_busy(False)
        logger.error('Updated app could not be restarted: %s',error)
        if manual:self._show_update_install_error(release,error)

    def _poll_update_installation(self,result_queue):
        try:status,manual,release,payload=result_queue.get_nowait()
        except queue.Empty:
            self.after(200,lambda:self._poll_update_installation(result_queue));return
        if status=='progress':
            log_activity('update','install_stage','started',manual=manual,stage=payload,version=release.version)
            self._set_update_install_busy(True,payload)
            self.after(200,lambda:self._poll_update_installation(result_queue));return
        if status=='restart':
            installed=payload
            try:
                process=restart_updated_app(installed)
                self._update_helper_process=process
            except Exception as error:
                self._update_restart_failed(release,installed,error,manual)
                return
            def wait_for_ready():
                try:
                    wait_for_update_restart(installed,process)
                    result_queue.put(('restart_ready',manual,release,installed))
                except Exception as error:
                    result_queue.put(('restart_failed',manual,release,(installed,error)))
            threading.Thread(target=wait_for_ready,daemon=True).start()
            # Keep the old window and its rollback copy alive until the child
            # confirms that its UI event loop is actually running.
            self.after(200,lambda:self._poll_update_installation(result_queue));return
        if status=='restart_ready':
            installed=payload
            cleanup_update(installed)
            logger.info('Python update installed and UI confirmed; closing old app for restart to %s',release.version)
            self._quitting=True
            if self.tray is not None:self.tray.stop()
            self.destroy();return
        if status=='restart_failed':
            installed,error=payload
            self._update_restart_failed(release,installed,error,manual);return
        self._update_install_running=False;self._set_update_install_busy(False)
        logger.error('Automatic update installation failed: %s',payload)
        if manual:self._show_update_install_error(release,payload)

    def _show_update_install_error(self,release,error):
        details=str(error) if isinstance(error,UpdateInstallError) else _('Ett oväntat fel uppstod vid installationen.')
        messagebox.showerror(_('Uppdateringen kunde inte installeras'),_('{error}\n\nDu kan ladda ner uppdateringen manuellt:\n{url}',error=details,url=release.url),parent=self)

    def show_update_available(self,release):
        w=self._new_toplevel(_('Uppdatering tillgänglig'));w.resizable(True,True);w.configure(bg='#f3f5f8')
        form=ttk.Frame(w,padding=24);form.pack()
        heading=_('Uppdaterat bygge av version {version} är tillgänglig',version=release.version) if release.version==APP_VERSION else _('Version {version} är tillgänglig',version=release.version)
        ttk.Label(form,text=heading,style='Title.TLabel').pack(anchor='w')
        change_labels={'version':_('Ny programversion'),'commit':_('Ny commit'),'files':_('Ändrade appfiler'),'commit_and_files':_('Ny commit och ändrade appfiler'),'release':_('Nytt release-bygge')}
        change=change_labels[update_change_kind(release)]
        current_commit=APP_RELEASE_COMMIT[:12] or _('okänd');release_commit=release.release_commit[:12] or _('okänd')
        ttk.Label(form,text=_('Installerad version: {current}\nSenaste release: {latest}',current=APP_VERSION,latest=release.version),justify='left').pack(anchor='w',pady=(8,4))
        ttk.Label(form,text=_('Typ av uppdatering: {change}',change=change),justify='left').pack(anchor='w',pady=(0,4))
        ttk.Label(form,text=_('Installerad commit: {current}\nRelease-commit: {latest}',current=current_commit,latest=release_commit),style='Sub.TLabel',justify='left').pack(anchor='w',pady=(0,8))
        ttk.Label(form,text=_('Lokala fakturor, inställningar och mallar påverkas inte.'),justify='left').pack(anchor='w',pady=(0,8))
        missing=missing_release_assets(release)
        if missing:ttk.Label(form,text=_('Releasefilerna är inte klara ännu. Försök igen senare.\nSaknas: {files}',files=', '.join(missing)),style='Sub.TLabel',wraplength=520,justify='left').pack(anchor='w',pady=(0,8))
        def open_download():
            try:
                if not webbrowser.open(release.url,new=2):raise RuntimeError('No web browser available')
            except Exception:
                logger.exception('Could not open GitHub release download page')
                messagebox.showerror(_('Kunde inte öppna webbläsaren'),_('Öppna nedladdningssidan manuellt:\n{url}',url=release.url),parent=w);return
            w.destroy()
        def install_now():
            w.destroy();self.start_update_installation(release,manual=True)
        def check_again():
            w.destroy();self.check_for_updates(manual=True,force=True)
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(8,0))
        install_button=ttk.Button(buttons,text=_('Installera och starta om'),command=install_now,style='Accent.TButton')
        install_button.pack(side='left')
        if missing:install_button.state(['disabled'])
        ttk.Button(buttons,text=_('Sök igen'),command=check_again).pack(side='left',padx=(8,0))
        ttk.Button(buttons,text=_('Stäng'),command=w.destroy).pack(side='right')
        ttk.Button(buttons,text=_('Öppna nedladdningssida'),command=open_download).pack(side='right',padx=(0,8))

    def rebuild_ui(self):
        """Rebuild the main window without interrupting background child windows."""
        for child in self.winfo_children():
            if child.winfo_class()!='Toplevel':child.destroy()
        self.build();self.refresh()
        if self.tray is not None:self.tray.refresh()

    def select_invoice_filter(self,key):
        """Select a main-list tab without changing any invoice data."""
        if key not in getattr(self,'filter_options',{}):key='current'
        self.current_filter_key=key
        tabs=getattr(self,'view_tabs',None)
        tab=getattr(self,'filter_tabs',{}).get(key)
        if tabs is not None and tab is not None:tabs.select(tab)

    def on_filter_select(self,event=None):
        selected=str(self.view_tabs.select())
        key=self.filter_tab_ids.get(selected)
        if not key or key==self.current_filter_key:return
        self.current_filter_key=key
        log_activity('ui','invoice_filter_changed','completed',filter=key)
        self.refresh()

    def on_invoice_search(self,*_args):
        query=self.invoice_search_var.get().strip()
        log_activity('ui','invoice_search_changed','completed',query=query)
        self.refresh()

    def sort_invoice_column(self,column):
        previous=getattr(self,'invoice_sort_column','due_date')
        if previous==column:
            self.invoice_sort_reverse=not getattr(self,'invoice_sort_reverse',False)
        else:
            self.invoice_sort_column=column;self.invoice_sort_reverse=False
        log_activity('ui','invoice_sort_changed','completed',column=self.invoice_sort_column,reverse=self.invoice_sort_reverse)
        self.refresh()

    def check_python_addons(self):
        """Recover missing dependencies at startup without upgrading existing ones."""
        if getattr(self,'_python_addon_install_running',False):return
        missing=list(missing_addon_package_specs())
        if not missing:
            self._python_addons_ready=True
            return
        self._python_addon_install_running=True
        win=self._new_toplevel(_('Förbereder appen'));win.resizable(True,True)
        win.protocol('WM_DELETE_WINDOW',lambda:None)
        box=self._dialog_form(win,padding=22)
        ttk.Label(box,text=_('Installerar saknade Python-tillägg'),style='Heading.TLabel').pack(anchor='w')
        ttk.Label(box,text=_('Detta behövs för PDF och systemfält. Installationen sker i bakgrunden.')).pack(anchor='w',pady=(7,10))
        bar=ttk.Progressbar(box,mode='indeterminate',length=330);bar.pack(fill='x');bar.start(12)
        status=ttk.Label(box,text=_('Ansluter till Python-pakettjänsten…'),style='Sub.TLabel');status.pack(anchor='w',pady=(8,0))
        win.update_idletasks()
        result_queue=queue.Queue()
        def install():
            try:
                result_queue.put(install_python_addons(sys.executable,missing,upgrade=False))
            except Exception as exc:
                result_queue.put((False,str(exc)))
        threading.Thread(target=install,daemon=True).start()
        def poll():
            try:ok,details=result_queue.get_nowait()
            except queue.Empty:
                self.after(250,poll);return
            self._python_addon_install_running=False
            bar.stop();win.destroy()
            if ok:
                self._python_addons_ready=True
                importlib.invalidate_caches()
                self.start_tray()
                messagebox.showinfo(_('Tillägg klara'),_('Nödvändiga Python-tillägg installerades. Appen är redo.'),parent=self)
            else:
                messagebox.showerror(_('Kunde inte installera tillägg'),_('Python-tilläggen kunde inte installeras automatiskt. Kontrollera internetanslutning och pip.\n\n')+details[-1200:],parent=self)
        self.after(350,poll)

    def _run_scheduled_python_addon_maintenance(self):
        """Run non-Windows add-on upgrades once after Monday 08:00 local time."""
        try:
            if self._quitting or sys.platform.startswith('win'):return
            now=datetime.now();week=maintenance_week(now)
            if self._python_addon_maintenance_attempted_week==week:return
            if getattr(self,'_python_addon_install_running',False):return
            if maintenance_due(now,read_maintenance_week(PYTHON_ADDONS_MAINTENANCE_MARKER)):
                # Claim the week before starting a thread, including failures,
                # so an offline Monday cannot cause a retry on every startup.
                self._python_addon_maintenance_attempted_week=week
                self.update_python_addons()
        except Exception:
            logger.exception('Weekly Python add-on maintenance failed')
        finally:
            if not self._quitting:self.after(MAINTENANCE_POLL_INTERVAL_MS,self._run_scheduled_python_addon_maintenance)

    def update_python_addons(self):
        """Upgrade non-Windows requirements in the current environment weekly."""
        if sys.platform.startswith('win') or getattr(self,'_python_addon_install_running',False):return False
        now=datetime.now();week=maintenance_week(now)
        self._python_addon_maintenance_attempted_week=week
        try:
            write_maintenance_week(PYTHON_ADDONS_MAINTENANCE_MARKER,week)
        except Exception as exc:
            logger.exception('Could not save the weekly Python add-on marker')
            messagebox.showerror(_('Kunde inte uppdatera Python-tillägg'),_('Veckomarkören för Python-tillägg kunde inte sparas.\n\n{error}',error=exc),parent=self)
            return False
        self._python_addon_install_running=True
        self._python_addon_updates_running=True
        result_queue=queue.Queue()
        def update():
            try:
                result_queue.put(install_python_addons(sys.executable,addon_package_specs(),upgrade=True))
            except Exception as exc:
                result_queue.put((False,str(exc)))
        threading.Thread(target=update,daemon=True).start()
        def poll():
            try:ok,details=result_queue.get_nowait()
            except queue.Empty:
                self.after(250,poll);return
            self._python_addon_install_running=False
            self._python_addon_updates_running=False
            if ok:
                self._python_addons_ready=True
                importlib.invalidate_caches()
                self.start_tray()
                logger.info('Weekly Python add-on update completed in the existing environment')
            else:
                logger.error('Weekly Python add-on update failed: %s',details[-1200:])
                messagebox.showerror(_('Kunde inte uppdatera Python-tillägg'),_('Python-tilläggen kunde inte uppdateras automatiskt. Kontrollera internetanslutning och pip.\n\n')+details[-1200:],parent=self)
        self.after(350,poll)
        return True

    def _style(self):
        s=ttk.Style(self); s.theme_use('clam')
        self.font_family=tkfont.nametofont('TkDefaultFont').cget('family')
        self.ui_font_scale=normalize_font_scale(setting(FONT_SCALE_SETTING))
        self._high_contrast=system_high_contrast()
        self._accessibility_style=AccessibleStyle(s,tkfont,self.font_family)
        self._accessibility_style.apply(self.ui_font_scale,high_contrast=self._high_contrast)

    def _apply_accessibility_palette(self):
        """Re-style open windows after a desktop high-contrast change."""
        style=getattr(self,'_accessibility_style',None)
        high_contrast=getattr(self,'_high_contrast',False)
        if style is not None:style.apply(getattr(self,'ui_font_scale',1.0),high_contrast=high_contrast)
        tree=getattr(self,'tree',None)
        if tree is not None:configure_invoice_row_colors(tree,high_contrast)
        windows=[self]+[child for child in self.winfo_children() if child.winfo_class()=='Toplevel']
        for window in windows:
            apply_widget_contrast(window,high_contrast)
            prepare_focus_tree(window,high_contrast)
        for menu in (getattr(self,'main_menu',None),getattr(self,'file_menu',None),getattr(self,'help_menu',None),getattr(self,'row_menu',None)):
            if menu is not None:apply_widget_contrast(menu,high_contrast)

    def _poll_system_contrast(self):
        if getattr(self,'_quitting',False) or getattr(self,'_contrast_check_running',False):return
        self._contrast_check_running=True
        result_queue=queue.Queue()
        def check():
            try:result_queue.put(system_high_contrast())
            except Exception:result_queue.put(getattr(self,'_high_contrast',False))
        threading.Thread(target=check,daemon=True).start()
        def poll():
            if getattr(self,'_quitting',False):return
            try:enabled=result_queue.get_nowait()
            except queue.Empty:
                try:self.after(100,poll)
                except tk.TclError:pass
                return
            self._contrast_check_running=False
            if enabled!=getattr(self,'_high_contrast',False):
                self._high_contrast=enabled
                self._apply_accessibility_palette()
                logger.info('System high-contrast mode changed: enabled=%s',enabled)
            try:self.after(SYSTEM_CONTRAST_POLL_INTERVAL_MS,self._poll_system_contrast)
            except tk.TclError:pass
        poll()

    def set_font_scale(self,value,persist=True):
        """Apply a bounded text zoom immediately without rebuilding open dialogs."""
        self.ui_font_scale=normalize_font_scale(value)
        if persist:
            set_setting(FONT_SCALE_SETTING,font_scale_storage(self.ui_font_scale))
            refresh_json_journal(parent=self)
        style=getattr(self,'_accessibility_style',None)
        if style is not None:style.apply(self.ui_font_scale,high_contrast=getattr(self,'_high_contrast',False))
        tree=getattr(self,'tree',None)
        if tree is not None:
            for column,width in getattr(self,'_invoice_column_widths',{}).items():
                try:tree.column(column,width=scaled_number(width,self.ui_font_scale))
                except tk.TclError:pass
        scale_var=getattr(self,'_font_scale_var',None)
        if scale_var is not None:
            try:scale_var.set(font_scale_label(self.ui_font_scale))
            except tk.TclError:pass
        help_label=getattr(self,'_keyboard_help_scale_label',None)
        if help_label is not None:
            try:help_label.configure(text=_('Textstorlek: {scale}. Alla kontroller nås med Tab och har synlig fokusmarkering.',scale=font_scale_label(self.ui_font_scale)))
            except tk.TclError:pass
        high_contrast=getattr(self,'_high_contrast',False)
        for window in [self]+[child for child in self.winfo_children() if child.winfo_class()=='Toplevel']:
            apply_widget_contrast(window,high_contrast)
            prepare_focus_tree(window,high_contrast)
            if window is not self:fit_window_to_screen(window)
        logger.info('UI text scale changed: scale=%s',font_scale_storage(self.ui_font_scale))
        return self.ui_font_scale

    def change_font_scale(self,direction):
        self.set_font_scale(stepped_font_scale(getattr(self,'ui_font_scale',1.0),direction))
        return 'break'

    def reset_font_scale(self):
        self.set_font_scale(1.0)
        return 'break'

    def _shortcut_modifier(self):
        return 'Command' if sys.platform=='darwin' else 'Control'

    @staticmethod
    def _shortcut_callback(callback):
        def run(_event=None):
            callback()
            return 'break'
        return run

    def _install_accessibility_shortcuts(self,window,main_window=False):
        """Install idempotent keyboard access on the root and every dialog."""
        if getattr(window,'_accessibility_shortcuts_bound',False):return
        bind=lambda sequence,callback:window.bind(sequence,self._shortcut_callback(callback),add='+')
        modifier=self._shortcut_modifier()
        for sequence in ('<F1>',):bind(sequence,self.show_keyboard_help)
        for suffix in ('plus','equal','KP_Add'):
            bind(f'<{modifier}-{suffix}>',lambda:self.change_font_scale(1))
        for suffix in ('minus','KP_Subtract'):
            bind(f'<{modifier}-{suffix}>',lambda:self.change_font_scale(-1))
        bind(f'<{modifier}-0>',self.reset_font_scale)
        if main_window:
            bind(f'<{modifier}-f>',self.focus_invoice_search)
            bind(f'<{modifier}-n>',self.add_invoice)
            bind(f'<{modifier}-o>',self.import_invoice)
            bind(f'<{modifier}-e>',self.edit_invoice)
            bind(f'<{modifier}-comma>',self.settings)
            bind('<F2>',self.edit_invoice)
            bind('<F5>',self.scan_import_folder)
            bind('<F10>',self.show_file_menu)
            bind('<Alt-a>',self.show_file_menu)
            bind('<Alt-h>',self.show_help_menu)
            bind('<Control-Tab>',lambda:self.cycle_invoice_filter(1))
            bind('<Control-Shift-Tab>',lambda:self.cycle_invoice_filter(-1))
            bind(f'<{modifier}-Return>',self.open_selected_invoice_pdf)
        window._accessibility_shortcuts_bound=True

    def _open_keyboard_menu(self,menu):
        try:menu.unpost()
        except tk.TclError:pass
        menu.tk_popup(self.winfo_rootx()+12,self.winfo_rooty()+30)
        try:menu.grab_release()
        except tk.TclError:pass
        return 'break'

    def show_file_menu(self):
        return self._open_keyboard_menu(self.file_menu)

    def show_help_menu(self):
        return self._open_keyboard_menu(self.help_menu)

    def focus_invoice_search(self):
        search=getattr(self,'invoice_search',None)
        if search is not None:
            search.focus_set()
            try:search.selection_range(0,'end')
            except tk.TclError:pass
        return 'break'

    def cycle_invoice_filter(self,direction):
        tabs=self.view_tabs.tabs()
        if not tabs:return 'break'
        try:index=tabs.index(self.view_tabs.select())
        except ValueError:index=0
        self.view_tabs.select(tabs[(index+direction)%len(tabs)])
        return 'break'

    def show_keyboard_help(self):
        """Explain all keyboard access and offer visible text-size controls."""
        existing=getattr(self,'_keyboard_help_window',None)
        if existing is not None:
            try:
                if existing.winfo_exists():existing.deiconify();existing.lift();existing.focus_force();return existing
            except tk.TclError:pass
        previous_grab=self.grab_current() or None
        w=self._new_toplevel(_('Kortkommandon och tillgänglighet'));w.resizable(True,True);w.configure(bg='#f3f5f8')
        self._keyboard_help_window=w
        def close_help():
            w.destroy()
            if previous_grab is not None:
                try:
                    if previous_grab.winfo_exists():previous_grab.grab_set()
                except (tk.TclError,AttributeError):pass
        w.protocol('WM_DELETE_WINDOW',close_help)
        form=self._dialog_form(w,padding=22)
        ttk.Label(form,text=_('Kortkommandon och tillgänglighet'),style='Title.TLabel').pack(anchor='w',pady=(0,10))
        modifier='Cmd' if sys.platform=='darwin' else 'Ctrl'
        rows=[
            (_('Flytta fokus framåt / bakåt'),'Tab / Shift+Tab'),
            (_('Sök kund eller faktura'),f'{modifier}+F'),
            (_('Lägg till faktura manuellt'),f'{modifier}+N'),
            (_('Lägg till faktura-PDF'),f'{modifier}+O'),
            (_('Redigera vald faktura'),f'{modifier}+E / F2'),
            (_('Skanna importmappen'),'F5'),
            (_('Öppna original-PDF för vald faktura'),f'{modifier}+Enter'),
            (_('Växla fakturaflik'),'Ctrl+Tab / Ctrl+Shift+Tab'),
            (_('Öppna fakturans högerklicksmeny'),'Shift+F10'),
            (_('Öppna inställningar'),f'{modifier}+,'),
            (_('Öppna Arkiv-menyn'),'F10 / Alt+A'),
            (_('Öppna Hjälp-menyn'),'Alt+H'),
            (_('Visa den här hjälpen'),'F1'),
            (_('Öka eller minska textstorlek'),f'{modifier} + / {modifier} −'),
            (_('Återställ textstorlek'),f'{modifier}+0'),
        ]
        for label,key in rows:
            row=ttk.Frame(form);row.pack(fill='x',pady=2)
            ttk.Label(row,text=label).pack(side='left',anchor='w')
            ttk.Label(row,text=key,style='BodyBold.TLabel').pack(side='right',anchor='e',padx=(20,0))
        self._keyboard_help_scale_label=ttk.Label(form,text=_('Textstorlek: {scale}. Alla kontroller nås med Tab och har synlig fokusmarkering.',scale=font_scale_label(self.ui_font_scale)),style='Sub.TLabel',wraplength=560)
        self._keyboard_help_scale_label.pack(anchor='w',pady=(14,8))
        zoom=ttk.Frame(form);zoom.pack(fill='x',pady=(0,10))
        ttk.Button(zoom,text=_('Minska text'),command=lambda:self.change_font_scale(-1)).pack(side='left')
        ttk.Button(zoom,text=_('Normal textstorlek'),command=self.reset_font_scale).pack(side='left',padx=7)
        ttk.Button(zoom,text=_('Öka text'),command=lambda:self.change_font_scale(1)).pack(side='left')
        ttk.Button(form,text=_('Stäng'),command=close_help,style='Accent.TButton').pack(anchor='e',pady=(8,0))
        if previous_grab is not None:w.grab_set()
        return w

    def _build_menu(self):
        menu=tk.Menu(self)
        self.main_menu=menu
        file_menu=tk.Menu(menu,tearoff=0)
        self.file_menu=file_menu
        file_menu.add_command(label=_('Säkerhetskopiera inställningar och påminnelser'),command=self.create_backup)
        file_menu.add_command(label=_('Återställ säkerhetskopia'),command=self.restore_backup)
        file_menu.add_command(label=_('Importera JSON-journal'),command=self.import_journal)
        file_menu.add_command(label=_('Importera reskontralista'),command=self.import_ledger_list)
        file_menu.add_command(label=_('Öppna exportmapp'),command=self.open_export_folder)
        file_menu.add_command(label=_('Rensa cache nu'),command=self.clear_cache_now)
        file_menu.add_separator()
        file_menu.add_command(label=_('Dölj till systemfältet'),command=self.hide_to_tray)
        file_menu.add_command(label=_('Avsluta helt'),command=self.quit_app)
        menu.add_cascade(label=_('Arkiv'),menu=file_menu)
        help_menu=tk.Menu(menu,tearoff=0)
        self.help_menu=help_menu
        help_menu.add_command(label=_('Visa samlad fellogg'),command=self.open_log)
        help_menu.add_command(label=_('Markera fellogg som åtgärdad'),command=self.resolve_error_log)
        help_menu.add_command(label=_('Visa teknisk logg'),command=self.open_technical_log)
        help_menu.add_command(label=_('Uppdatera appen'),command=lambda:self.check_for_updates(manual=True))
        help_menu.add_command(label=_('Kortkommandon och tillgänglighet'),command=self.show_keyboard_help,accelerator='F1')
        help_menu.add_command(label=_('Om {app_name}',app_name=APP_NAME),command=self.show_about)
        menu.add_cascade(label=_('Hjälp'),menu=help_menu)
        self._apply_menu_icons(file_menu);self._apply_menu_icons(help_menu);self._apply_menu_icons(menu)
        self._instrument_menu_actions(file_menu);self._instrument_menu_actions(help_menu);self._instrument_menu_actions(menu)
        self.configure(menu=menu)

    def build(self):
        self._build_menu()
        header=ttk.Frame(self,padding=(22,17,22,10)); header.pack(fill='x')
        if self._brand_logo:tk.Label(header,image=self._brand_logo,bg='#f3f5f8',borderwidth=0).pack(side='left',padx=(0,8))
        else:
            if self._header_icon:tk.Label(header,image=self._header_icon,bg='#f3f5f8',borderwidth=0).pack(side='left',padx=(0,11))
            ttk.Label(header,text=APP_NAME,style='Title.TLabel').pack(side='left')
        ttk.Label(header,text=_('Lokal app · dina filer stannar på datorn'),style='Sub.TLabel').pack(side='left',padx=16,pady=(8,0))
        ttk.Button(header,text=_('Inställningar'),command=self.settings).pack(side='right')
        ttk.Button(header,text=_('Om {app_name}',app_name=APP_NAME),command=self.show_about).pack(side='right',padx=(0,7))
        self.update_button=ttk.Button(header,text=self._update_button_idle_text(),command=lambda:self.check_for_updates(manual=True),style='Accent.TButton')
        self.update_button.pack(side='right',padx=(0,7))
        if self._update_install_running:self._set_update_install_busy(True)
        elif self._update_check_running:self._set_update_check_busy(True)
        primary_actions=[('Skanna importmapp',self.scan_import_folder,'Accent.TButton'),('Öppna importmapp',self.open_import_folder,'TButton'),('Öppna exportmapp',self.open_export_folder,'TButton'),('Lägg till faktura-PDF',self.import_invoice,'TButton'),('Lägg till manuellt',self.add_invoice,'TButton'),('Skapa påminnelse',self.make_reminder,'TButton')]
        secondary_actions=[('Redigera P1',self.edit_p1,'TButton'),('Redigera P2',self.edit_p2,'TButton'),('Markera som betald',self.mark_invoice_paid,'TButton'),('Ångra betalmarkering',self.undo_invoice_paid,'TButton'),('Ignorera / återaktivera',self.toggle_ignore,'TButton'),('Redigera vald',self.edit_invoice,'TButton'),('Visa samlad fellogg',self.open_log,'TButton')]
        for actions,padding in ((primary_actions,(22,5,22,4)),(secondary_actions,(22,0,22,12))):
            bar=ttk.Frame(self,padding=padding);bar.pack(fill='x')
            for key,cmd,style in actions:
                ttk.Button(bar,text=_(key),command=cmd,style=style).pack(side='left',padx=(0,7))
        controls=ttk.Frame(self,padding=(22,0,22,10));controls.pack(fill='x')
        self.filter_options={'current':_('Aktuella'),'history':_('Historik / arkiverade / betalda'),'all':_('Alla'),'ignored':_('Ignorerade'),'debt_review':_('Kronofogden – granska')}
        self.view_tabs=ttk.Notebook(controls)
        self.filter_tabs={};self.filter_tab_ids={}
        for key,label in self.filter_options.items():
            tab=ttk.Frame(self.view_tabs)
            self.view_tabs.add(tab,text=label)
            self.filter_tabs[key]=tab;self.filter_tab_ids[str(tab)]=key
        self.view_tabs.pack(side='left')
        self.view_tabs.select(self.filter_tabs.get(self.current_filter_key,self.filter_tabs['current']))
        self.view_tabs.bind('<<NotebookTabChanged>>',self.on_filter_select)
        self.invoice_search_var=tk.StringVar()
        search=ttk.Entry(controls,textvariable=self.invoice_search_var,width=24)
        self.invoice_search=search
        search.pack(side='right')
        ttk.Label(controls,text=_('Sök kund/faktura:')).pack(side='right',padx=(8,6))
        self.invoice_search_var.trace_add('write',self.on_invoice_search)
        logo_bar=ttk.Frame(self,padding=(22,0,22,8));logo_bar.pack(fill='x')
        ttk.Label(logo_bar,text=_('Logotyp vid export:')).pack(side='left')
        self.logo_var=tk.StringVar(value=_('(Ingen logotyp)'))
        self.logo_combo=ttk.Combobox(logo_bar,textvariable=self.logo_var,state='readonly',width=34)
        self.logo_combo.pack(side='left',padx=8)
        self.logo_combo.bind('<<ComboboxSelected>>',self.on_logo_select)
        ttk.Button(logo_bar,text=_('Uppdatera lista'),command=self.refresh_logo_choices).pack(side='left',padx=(0,6))
        ttk.Button(logo_bar,text=_('Öppna SVG-mapp'),command=self.open_svg_folder).pack(side='left')
        self.refresh_logo_choices()
        wrap=ttk.Frame(self,padding=(22,0,22,12));wrap.pack(fill='both',expand=True)
        cols=('invoice_no','customer','due_date','amount','remaining','p1_date','p2_send_date','email_status','stage','fee')
        self.tree=ttk.Treeview(wrap,columns=cols,show='headings',selectmode='browse')
        configure_invoice_row_colors(self.tree,getattr(self,'_high_contrast',False))
        labels={'invoice_no':_('Fakturanr'),'customer':_('Kund'),'due_date':_('Förfallodatum'),'amount':_('Fakturabelopp'),'remaining':_('Kvar att betala'),'p1_date':_('P1 skapades'),'p2_send_date':_('P2-datum'),'email_status':_('E-post (senaste)'),'stage':_('Status / nästa steg'),'fee':_('Påminnelseavgift')}
        widths={'invoice_no':110,'customer':170,'due_date':105,'amount':115,'remaining':120,'p1_date':105,'p2_send_date':125,'email_status':190,'stage':180,'fee':120}
        self._invoice_column_widths=widths.copy()
        for c in cols:
            self.tree.heading(c,text=labels[c],command=lambda column=c:self.sort_invoice_column(column))
            self.tree.column(c,width=scaled_number(widths[c],self.ui_font_scale),anchor='w')
        self.tree.pack(side='top',fill='both',expand=True); sb=ttk.Scrollbar(wrap,orient='vertical',command=self.tree.yview);sb.pack(side='right',fill='y');xsb=ttk.Scrollbar(wrap,orient='horizontal',command=self.tree.xview);xsb.pack(side='bottom',fill='x');self.tree.configure(yscrollcommand=sb.set,xscrollcommand=xsb.set)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.show_detail())
        self.tree.bind('<Delete>',lambda e:self.delete_invoice())
        self.tree.bind('<Shift-F10>',self.show_selected_row_context_menu)
        self.tree.bind('<App>',self.show_selected_row_context_menu)
        self.tree.bind('<Button-3>',self.show_row_context_menu)
        self.tree.bind('<Button-2>',self.show_row_context_menu)
        self.row_menu=tk.Menu(self,tearoff=0)
        self.row_menu.add_command(label=_('Öppna original-PDF'),command=self.open_selected_invoice_pdf)
        self.row_menu.add_command(label=_('Importera originalfaktura till vald'),command=self.import_original_invoice)
        self.row_menu.add_command(label=_('Öppna senaste påminnelse-PDF'),command=self.open_selected_reminder_pdf)
        self.row_menu.add_separator()
        self.row_menu.add_command(label=_('Redigera faktura'),command=self.edit_invoice)
        self.row_menu.add_command(label=_('Redigera kund'),command=self.edit_customer)
        self.row_menu.add_command(label=_('Redigera P1'),command=self.edit_p1)
        self.row_menu.add_command(label=_('Redigera P2'),command=self.edit_p2)
        self.row_menu.add_command(label=_('Skapa e-postutkast'),command=self.create_reminder_email)
        self.row_menu.add_command(label=_('Markera e-post som skickad'),command=self.mark_reminder_email_sent)
        self.row_menu.add_command(label=_('Markera som betald'),command=self.mark_invoice_paid)
        self.row_menu.add_command(label=_('Ångra betalmarkering'),command=self.undo_invoice_paid)
        self.row_menu.add_command(label=_('Ignorera / återaktivera'),command=self.toggle_ignore)
        self.row_menu.add_separator()
        self.row_menu.add_command(label=_('Ta bort fakturarad'),command=self.delete_invoice)
        self._apply_menu_icons(self.row_menu)
        self._instrument_menu_actions(self.row_menu)
        self.detail=ttk.Label(self,text=_('Importera PDF eller lägg till en faktura manuellt.'),padding=(24,4,24,16),style='Sub.TLabel');self.detail.pack(fill='x')
        foot=ttk.Frame(self,padding=(22,0,22,12));foot.pack(fill='x')
        ttk.Label(foot,text=_('Startvärden: P1 +5 dagar · P2 +5 dagar · Kronofogden-granskning +5 dagar · avgift 150 i fakturans valuta · ränta 23%'),style='Sub.TLabel').pack(side='left')
        ttk.Button(foot,text=_('Ta bort vald'),command=self.delete_invoice).pack(side='right')
        ttk.Label(self,text=_('{copyright} · Skapare: {author}',copyright=APP_COPYRIGHT,author=APP_AUTHOR),padding=(24,0,24,9),style='Sub.TLabel').pack(fill='x')
        self._finalize_window_actions(self,main_window=True)

    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        with connect() as db: rows=db.execute('SELECT * FROM invoices ORDER BY due_date').fetchall()
        flt=self.current_filter_key
        search_var=getattr(self,'invoice_search_var',None)
        query=' '.join(search_var.get().strip().casefold().split()) if search_var is not None else ''
        fee_value=float(setting('fee') or 0)
        visible=[]
        for r in rows:
            stage=next_stage(r)
            remain=max(0,float(r['amount'] or 0)-float(r['paid'] or 0))
            if flt=='current' and (r['ignored'] or stage in ('Avslutad','Kronofogden – granska')):continue
            if flt=='history' and not (r['ignored'] or remain<=0.005):continue
            if flt=='ignored' and not r['ignored']:continue
            if flt=='debt_review' and stage!='Kronofogden – granska':continue
            if query:
                searchable=' '.join(f"{r['invoice_no']} {r['customer']}".casefold().split())
                if query not in searchable:continue
            visible.append((r,stage,remain))
        sort_column=getattr(self,'invoice_sort_column','due_date')
        def sort_key(item):
            r,stage,remain=item
            if sort_column=='remaining':return remain
            if sort_column=='amount':return float(r['amount'] or 0)
            if sort_column=='fee':return fee_value if r['p1_date'] else -1.0
            if sort_column=='invoice_no':
                value=str(r['invoice_no'] or '')
                return (0,int(value)) if value.isdigit() else (1,value.casefold())
            if sort_column=='stage':return _(stage).casefold()
            if sort_column=='email_status':return reminder_email_status(r).casefold()
            if sort_column=='p2_send_date':return str(r['p2_date'] or '')
            if sort_column in r.keys():return str(r[sort_column] or '').casefold()
            return ''
        visible.sort(key=sort_key,reverse=getattr(self,'invoice_sort_reverse',False))
        for r,stage,remain in visible:
            fee=money(fee_value,r['currency']) if r['p1_date'] else '—'
            p1_display=r['p1_date'] or '—'
            if r['ignored'] or remain<=0.005:p2_display='—'
            elif r['p2_date']:p2_display=_('Skapad {date}',date=r['p2_date'])
            elif r['p1_date']:
                p2_due=p2_due_date(r)
                p2_display=p2_due.isoformat() if p2_due else '—'
            else:p2_display='—'
            stage_display=(_('IGNORERAD')+' · ' if r['ignored'] else '')+_(stage)
            color_tag=invoice_row_color_tag(r,stage)
            self.tree.insert('', 'end',iid=str(r['id']),values=(r['invoice_no'],r['customer'],r['due_date'],money(float(r['amount'] or 0),r['currency']),money(remain,r['currency']),p1_display,p2_display,reminder_email_status(r),stage_display,fee),tags=(color_tag,) if color_tag else ())
        self.show_detail()

    def selected(self):
        sel=self.tree.selection()
        if not sel:messagebox.showinfo(_('Välj faktura'),_('Markera en faktura i listan först.'));return None
        with connect() as db:return db.execute('SELECT * FROM invoices WHERE id=?',(int(sel[0]),)).fetchone()

    def open_selected_invoice_pdf(self):
        row=self.selected()
        if row is None:return None
        path=Path(str(row['source'] or '')).expanduser()
        if not str(row['source'] or '').strip() or not path.is_file():
            messagebox.showinfo(_('Original-PDF saknas'),_('Det finns ingen sparad original-PDF för faktura {invoice}.',invoice=row['invoice_no']),parent=self)
            return None
        try:
            open_path(path)
            log_activity('invoice','original_pdf_opened','completed',invoice_id=row['id'],invoice_no=row['invoice_no'])
            return path
        except Exception as exc:
            logger.exception('Could not open original invoice PDF: invoice=%s',row['id'])
            messagebox.showerror(_('PDF kunde inte öppnas'),str(exc),parent=self)
            return None

    def open_selected_reminder_pdf(self):
        row=self.selected()
        if row is None:return None
        level=latest_reminder_level(row)
        path=find_reminder_pdf(row,level) if level else None
        if path is None:
            messagebox.showinfo(_('Påminnelse-PDF saknas'),_('Det finns ingen befintlig P1/P2-PDF för faktura {invoice}.',invoice=row['invoice_no']),parent=self)
            return None
        try:
            open_path(path)
            log_activity('invoice','reminder_pdf_opened','completed',invoice_id=row['id'],invoice_no=row['invoice_no'],level=level)
            return path
        except Exception as exc:
            logger.exception('Could not open reminder PDF: invoice=%s level=%s',row['id'],level)
            messagebox.showerror(_('PDF kunde inte öppnas'),str(exc),parent=self)
            return None

    def show_detail(self):
        sel=self.tree.selection()
        if not sel:
            if getattr(self,'_last_activity_invoice_id',None) is not None:
                log_activity('invoice','selection_cleared','completed')
            self._last_activity_invoice_id=None
            self.detail.configure(text=_('Importera PDF eller lägg till en faktura manuellt.'));return
        with connect() as db:r=db.execute('SELECT * FROM invoices WHERE id=?',(int(sel[0]),)).fetchone()
        if r:
            if getattr(self,'_last_activity_invoice_id',None)!=r['id']:
                log_activity('invoice','selection_changed','completed',invoice_id=r['id'],invoice_no=r['invoice_no'])
            self._last_activity_invoice_id=r['id']
            vendor=r['template_vendor'] or _('Ingen leverantörsmall')
            _logo_path,logo_name=self.invoice_logo(r)
            review=_('Granskad') if r['reviewed'] else _('KRÄVER GRANSKNING')
            note=r['note'] or _('Ingen fakturatext')
            detail_text=_('{customer} · {invoice_no} · Belopp: {amount} · {stage} · {review} · Mall: {vendor} · Logotyp: {logo} · {note}',customer=r['customer'],invoice_no=r['invoice_no'],amount=money(float(r['amount'] or 0),r['currency']),stage=_(next_stage(r)),review=review,vendor=vendor,logo=logo_name,note=note)
            email_status=' · '.join(
                reminder_email_status(r,level) for level in ('P1','P2') if r[level.lower()+'_date']
            )
            if email_status:detail_text+='\n'+_('E-post: {status}',status=email_status)
            self.detail.configure(text=detail_text)

    def show_row_context_menu(self,event):
        item=self.tree.identify_row(event.y)
        if not item:return
        self.tree.selection_set(item);self.tree.focus(item);self.show_detail()
        log_activity('ui','invoice_context_menu_opened','completed',invoice_id=int(item))
        try:self.row_menu.tk_popup(event.x_root,event.y_root)
        finally:self.row_menu.grab_release()

    def show_selected_row_context_menu(self,event=None):
        """Keyboard equivalent of right-click for the selected invoice row."""
        item=self.tree.focus() or (self.tree.selection()[0] if self.tree.selection() else '')
        if not item or not self.tree.exists(item):return 'break'
        self.tree.selection_set(item);self.tree.focus(item);self.show_detail()
        try:
            bounds=self.tree.bbox(item)
            if bounds:
                x,y,width,height=bounds
                x_root=self.tree.winfo_rootx()+x;y_root=self.tree.winfo_rooty()+y+height
            else:
                self.tree.see(item)
                x_root=self.tree.winfo_rootx()+20;y_root=self.tree.winfo_rooty()+30
            self.row_menu.tk_popup(x_root,y_root)
        finally:self.row_menu.grab_release()
        log_activity('ui','invoice_context_menu_opened','completed',invoice_id=int(item))
        return 'break'

    def dismiss_row_context_menu(self):
        """Do not leave a second active menu grab above a modal preview."""
        menu=getattr(self,'row_menu',None)
        if menu is None:return
        try:menu.unpost()
        except tk.TclError:pass
        try:menu.grab_release()
        except tk.TclError:pass

    def close_invoice_preview(self,win,doc):
        """Release the modal grab and close both PDF and window on every exit."""
        try:win.grab_release()
        except tk.TclError:pass
        try:doc.close()
        finally:
            try:
                if win.winfo_exists():win.destroy()
            except tk.TclError:pass

    def refresh_logo_choices(self):
        SVG_DIR.mkdir(exist_ok=True)
        files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        choices=[_('(Ingen logotyp)')]+files
        if not files:choices.append(_('(Lägg SVG i mappen svg)'))
        self.logo_combo.configure(values=choices)
        preferred=setting('logo_file') or Path(setting('logo_path')).name
        self.logo_var.set(preferred if preferred in files else choices[0])

    def on_logo_select(self,event=None,sync_json=True):
        selected=self.logo_var.get()
        if selected in [p.name for p in SVG_DIR.glob('*.svg')]:
            set_setting('logo_file',selected)
            set_setting('logo_path',str(SVG_DIR/selected))
        else:
            set_setting('logo_file','');set_setting('logo_path','')
        log_activity('settings','export_logo_changed','completed',logo=self.logo_var.get(),sync_json=sync_json)
        if sync_json:refresh_json_journal(parent=self)

    def selected_logo_path(self):
        selected=self.logo_var.get()
        path=SVG_DIR/selected
        return str(path.resolve()) if selected and path.is_file() else ''

    def logo_file_path(self,filename):
        """Resolve one safe supplier-logo filename inside the user's SVG folder."""
        if not filename:return '',_('(Ingen logotyp)')
        root=SVG_DIR.resolve();path=(SVG_DIR/filename).resolve()
        if path.parent!=root:
            logger.warning('Invoice logo is outside the SVG folder: %s',filename)
            return '',filename
        if not path.is_file():
            # Keep the safe path so PDF generation reports a missing selected
            # logo instead of silently replacing it with the text brand.
            logger.warning('Invoice logo is missing: %s',filename)
        return str(path),filename

    def invoice_logo(self,row):
        """Return the invoice's persistent logo, then template/global fallbacks."""
        selected=row['logo_file'] if 'logo_file' in row.keys() else None
        if selected is not None:return self.logo_file_path(selected)
        vendor=(row['template_vendor'] or '').strip()
        if vendor:
            with connect() as db:
                mapped=db.execute('SELECT logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(vendor,)).fetchone()
            if mapped is not None:return self.logo_file_path(mapped['logo_file'])
        customer=str(row['customer'] or '').strip() if 'customer' in row.keys() else ''
        if customer:
            with connect() as db:contact=get_customer_contact(db,customer)
            saved_logo=str(contact['logo_file'] or '') if contact is not None and 'logo_file' in contact.keys() else ''
            if saved_logo:return self.logo_file_path(saved_logo)
        return self.selected_logo_path(),self.logo_var.get() or _('(Ingen logotyp)')

    def open_svg_folder(self):
        SVG_DIR.mkdir(exist_ok=True)
        try:open_path(SVG_DIR)
        except Exception:logger.exception('Could not open SVG folder')

    def open_log(self):
        logger.info('User opened consolidated error log')
        try:
            report=_refresh_and_archive_logs()
            open_path(report.path)
        except Exception:
            logger.exception('Could not open consolidated error log')
            try:open_path(LOG_PATH)
            except Exception:logger.exception('Could not open diagnostic log')

    def resolve_error_log(self):
        """Resolve the reviewed error view without altering technical sources."""
        logger.info('User requested consolidated error log resolution')
        try:
            report=_refresh_and_archive_logs()
            if not report.error_count:
                messagebox.showinfo(APP_NAME,_('Det finns inga olösta fel i felloggen.'),parent=self)
                return
            if not messagebox.askyesno(APP_NAME,_('Markera alla fel i felloggen som åtgärdade?\n\nEn kopia sparas i loggarkivet. De tekniska källoggarna ändras inte.'),parent=self):
                logger.info('Consolidated error log resolution cancelled')
                return
            resolved=resolve_errors(LOG_DIR)
            logger.info('Consolidated errors marked resolved: count=%d archive=%s',resolved.resolved_count,resolved.archive_path)
            messagebox.showinfo(APP_NAME,_('Felloggen markerades som åtgärdad. {count} fel sparades i loggarkivet.',count=resolved.resolved_count),parent=self)
        except Exception:
            logger.exception('Could not resolve consolidated error log')
            messagebox.showerror(APP_NAME,_('Felloggen kunde inte markeras som åtgärdad. Se den tekniska loggen.'),parent=self)

    def open_technical_log(self):
        """Open the complete local log, including successful PDF diagnostics."""
        logger.info('User opened technical diagnostic log')
        try:open_path(LOG_PATH)
        except Exception:logger.exception('Could not open technical diagnostic log')

    def _run_scheduled_error_log_refresh(self):
        """Keep the consolidated local view current without touching source logs."""
        if self._quitting:return
        try:_refresh_and_archive_logs()
        except Exception:logger.exception('Consolidated error log refresh or daily archive failed')
        if not self._quitting:self.after(ERROR_LOG_REFRESH_INTERVAL_MS,self._run_scheduled_error_log_refresh)

    def clear_cache_now(self):
        """Run the same conservative age/type filter as the daily cleanup."""

        try:
            report=clean_cache(APP_FOLDER)
            set_setting('cache_last_cleanup',date.today().isoformat())
            logger.info('Manual smart cache cleanup: files=%d directories=%d bytes=%d errors=%d',report.removed_files,report.removed_directories,report.freed_bytes,report.errors)
            size=f'{report.freed_bytes:,}'.replace(',',' ')
            messagebox.showinfo(_('Cache rensad'),_('Tillfälliga filer rensade: {files}\nFrigjort utrymme: {bytes} byte\nFel: {errors}\n\nFakturor, importmapp, inställningar och säkerhetskopior har inte rörts.',files=report.removed_files,bytes=size,errors=report.errors),parent=self)
        except Exception as exc:
            logger.exception('Manual smart cache cleanup failed')
            messagebox.showerror(_('Kunde inte rensa cache'),str(exc),parent=self)

    def _run_exit_cache_cleanup(self):
        """Clean stale app caches on full exit without ever blocking the exit."""

        try:
            if setting('cache_auto')!='1':
                logger.info('Smart cache cleanup on exit skipped: disabled')
                return
            report=clean_cache(APP_FOLDER,max_age_hours=0)
            set_setting('cache_last_cleanup',date.today().isoformat())
            logger.info('Exit smart cache cleanup: files=%d directories=%d bytes=%d errors=%d',report.removed_files,report.removed_directories,report.freed_bytes,report.errors)
        except Exception:
            logger.exception('Exit smart cache cleanup failed')

    def _run_scheduled_cache_cleanup(self):
        """Clean at most once per calendar day while the app is running."""

        if self._quitting:return
        try:
            today=date.today().isoformat()
            if setting('cache_auto')=='1' and setting('cache_last_cleanup')!=today:
                report=clean_cache(APP_FOLDER)
                set_setting('cache_last_cleanup',today)
                logger.info('Automatic smart cache cleanup: files=%d directories=%d bytes=%d errors=%d',report.removed_files,report.removed_directories,report.freed_bytes,report.errors)
        except Exception:
            logger.exception('Automatic smart cache cleanup failed')
        if not self._quitting:self.after(CACHE_CLEANUP_INTERVAL_MS,self._run_scheduled_cache_cleanup)

    def _run_scheduled_journal_backup(self):
        """Refresh the JSON journal and keep one automatic copy per ISO week."""
        if self._quitting:return
        try:
            backup=create_weekly_journal_backup(
                DB_PATH,JOURNAL_PATH,JOURNAL_BACKUP_DIR,
                import_dir=IMPORT_DIR,export_dir=EXPORT_DIR,
            )
            if backup:logger.info('Weekly JSON and import/export backup created: %s',backup)
        except Exception:
            logger.exception('Weekly JSON journal backup failed')
        if not self._quitting:self.after(JOURNAL_BACKUP_INTERVAL_MS,self._run_scheduled_journal_backup)

    def _run_scheduled_reminder_archive(self):
        """Archive old reminder PDFs without changing invoice or journal history."""
        if self._quitting:return
        try:
            report=archive_old_reminders(EXPORT_DIR,reminder_archive_customer_map())
            if report.archived or report.conflicts or report.errors or report.unmatched:
                logger.info('Reminder archive: archived=%d conflicts=%d errors=%d unmatched=%d',report.archived,report.conflicts,report.errors,report.unmatched)
        except Exception:
            logger.exception('Automatic reminder archive failed')
        if not self._quitting:self.after(REMINDER_ARCHIVE_INTERVAL_MS,self._run_scheduled_reminder_archive)

    def guess_supplier(self,text,path=None,page_indexes=None):
        profiles=saved_supplier_profiles()
        source=Path(path).name if path else ''
        pages=','.join(str(index+1) for index in page_indexes) if page_indexes is not None else ('1' if path else '')
        matched=match_supplier(text,profiles)
        if matched:
            if not matched.vendor:
                logger.warning('Supplier template match left unresolved: file=%s pages=%s method=%s',source,pages,matched.method)
                return ''
            exact_text=any(method in ('org_number','bankgiro_number') for method in matched.method.split('+'))
            if not path or exact_text:
                logger.info('Supplier template matched: file=%s pages=%s vendor=%s method=%s score=%d',source,pages,matched.vendor,matched.method,matched.score)
                return matched.vendor
        if path:
            zone_match=match_saved_identifier_zones(path,page_indexes,profiles)
            if zone_match:
                if not zone_match.vendor:
                    logger.warning('Supplier identifier-zone match left unresolved: file=%s pages=%s method=%s',source,pages,zone_match.method)
                    return ''
                logger.info('Supplier template matched by saved identifier zone: file=%s pages=%s vendor=%s method=%s score=%d',source,pages,zone_match.vendor,zone_match.method,zone_match.score)
                return zone_match.vendor
            if matched:
                logger.info('Supplier template matched: file=%s pages=%s vendor=%s method=%s score=%d',source,pages,matched.vendor,matched.method,matched.score)
                return matched.vendor
            logger.info('No supplier text or identifier-zone match; trying visual logo: file=%s pages=%s profiles=%d',source,pages,len(profiles))
            matched=match_pdf_logo(path,page_indexes,profiles,SVG_DIR)
            if matched:
                if not matched.vendor:
                    logger.warning('Visual supplier logo match left unresolved: file=%s pages=%s method=%s',source,pages,matched.method)
                    return ''
                logger.info('Supplier template matched visually: file=%s pages=%s vendor=%s method=%s score=%d',source,pages,matched.vendor,matched.method,matched.score)
                return matched.vendor
            logger.warning('Supplier visual logo matching failed; trying legacy name fallback: file=%s pages=%s',source,pages)
        elif page_indexes is not None:
            logger.info('Visual supplier logo matching skipped for bundled invoice: pages=%s',pages)
        for line in [re.sub(r'\s+',' ',x).strip() for x in text.splitlines()[:18]]:
            if re.search(r'(?i)\b(?:AB|ASA|AS|HB)\s*$',line) and len(line)<60 and not re.search(r'faktura|datum|kundnr',line,re.I):
                logger.info('Supplier template matched by legacy company-name fallback: file=%s pages=%s vendor=%s',source,pages,line)
                return line
        logger.warning('Supplier template matching failed; manual review required: file=%s pages=%s profiles=%d',source,pages,len(profiles))
        return ''

    def parse_zone_value(self,field,text):
        raw='\n'.join(x.strip() for x in text.splitlines() if x.strip()).strip()
        if not raw:return ''
        if field in ('org_number','bankgiro_number'):return parse_supplier_identifier(field,raw)
        if field=='amount':
            value=parse_amount_value(raw)
            return value if value is not None else ''
        if field=='currency':return find_currency_code(raw)
        if field in ('due_date','invoice_date'):
            m=re.search(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',raw)
            return normalize_date(m.group(1)) if m else ''
        if field=='invoice_no':
            m=re.search(r'([A-Z]*\d[A-Z0-9./-]*)',raw,re.I)
            return m.group(1) if m else raw.splitlines()[0]
        if field=='customer':return raw.splitlines()[0][:100]
        if field=='note':return clean_invoice_note(raw)
        return raw[:300]

    def apply_saved_zones(self,path,vendor,guess,page_indexes=None,update_logo=True):
        if not vendor:return guess
        try:
            import fitz
            vendor_key=vendor.strip().casefold()
            with connect() as db:
                zones=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?)',(vendor_key,)).fetchall()
                logo=db.execute('SELECT logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(vendor_key,)).fetchone()
            if logo and update_logo:
                logo_file=logo['logo_file']
                if logo_file and (SVG_DIR/logo_file).is_file():
                    self.logo_var.set(logo_file);set_setting('logo_file',logo_file);set_setting('logo_path',str(SVG_DIR/logo_file))
                    logger.info('Matched reminder logo to invoice supplier template')
                elif not logo_file:
                    self.logo_var.set(_('(Ingen logotyp)'));set_setting('logo_file','');set_setting('logo_path','')
                else:logger.warning('Matched SVG logo is missing from svg folder')
            if not zones:return guess
            applied=[]
            with fitz.open(path) as doc:
                available_pages=list(page_indexes) if page_indexes is not None else list(range(len(doc)))
                for z in zones:
                    relative_page=z['page_index']
                    if relative_page<0 or relative_page>=len(available_pages):continue
                    source_page=available_pages[relative_page]
                    if source_page<0 or source_page>=len(doc):continue
                    page=doc[source_page];r=fitz.Rect(z['x0']*page.rect.width,z['y0']*page.rect.height,z['x1']*page.rect.width,z['y1']*page.rect.height)
                    val=self.parse_zone_value(z['field'],page.get_text('text',clip=r))
                    if val!='':guess[z['field']]=val;applied.append(z['field'])
            if applied:logger.info('Applied saved PDF field zones: vendor=%s fields=%s',vendor,','.join(applied))
        except Exception:logger.exception('Saved PDF zones could not be applied')
        return guess

    def preview_invoice(self,path,guess,vendor='',page_indexes=None):
        self.dismiss_row_context_menu()
        try:
            import fitz
            doc=fitz.open(path)
        except Exception:
            logger.exception('Could not open PDF preview')
            return guess
        available_pages=[index for index in (page_indexes if page_indexes is not None else range(len(doc))) if 0<=index<len(doc)]
        if not available_pages:
            doc.close()
            return guess
        # Never turn the PDF filename into a supplier when no match was found.
        original_vendor=vendor or ''
        supplier_profiles=saved_supplier_profiles()
        def supplier_profile(name):
            key=str(name or '').strip().casefold()
            return next((profile for profile in supplier_profiles if str(profile.get('vendor') or '').strip().casefold()==key),None)
        initial_profile=supplier_profile(original_vendor)
        try:initial_org=format_org_number(initial_profile.get('org_number')) if initial_profile else ''
        except ValueError:initial_org=''
        try:initial_bg=format_bankgiro_number(initial_profile.get('bankgiro_number')) if initial_profile else ''
        except ValueError:initial_bg=''
        preview_text='\n'.join(doc[index].get_text('text') or '' for index in available_pages)
        suggested_orgs=extract_org_numbers(preview_text)
        suggested_bgs=extract_bankgiro_numbers(preview_text)
        if not initial_org and len(suggested_orgs)==1:initial_org=format_org_number(next(iter(suggested_orgs)))
        if not initial_bg and len(suggested_bgs)==1:initial_bg=format_bankgiro_number(next(iter(suggested_bgs)))
        win=self._new_toplevel(_('Förhandsgranska faktura – markera fält att läsa'));win.geometry('950x790')
        top=ttk.Frame(win,padding=(12,8));top.pack(fill='x')
        ttk.Label(top,text=_('Leverantör / mallnamn:')).pack(side='left')
        vendor_var=tk.StringVar(value=original_vendor)
        vendor_combo=ttk.Combobox(top,textvariable=vendor_var,width=32,values=sorted((profile['vendor'] for profile in supplier_profiles),key=str.casefold))
        vendor_combo.pack(side='left',padx=7)
        ttk.Label(top,text=_('Dra en ruta över värdet. Sparade rutor kan återanvändas för samma mall.')).pack(side='left',padx=8)
        identifiers=ttk.Frame(win,padding=(12,0,12,4));identifiers.pack(fill='x')
        ttk.Label(identifiers,text=_('Leverantörens org.nr:')).pack(side='left')
        org_var=tk.StringVar(value=initial_org)
        ttk.Entry(identifiers,textvariable=org_var,width=17).pack(side='left',padx=(5,16))
        ttk.Label(identifiers,text=_('Bankgiro:')).pack(side='left')
        bg_var=tk.StringVar(value=initial_bg)
        ttk.Entry(identifiers,textvariable=bg_var,width=15).pack(side='left',padx=5)
        ttk.Label(identifiers,text=_('Kontrollera förslagen före sparning.')).pack(side='left',padx=12)
        body=ttk.Frame(win,padding=(10,0,10,6));body.pack(fill='both',expand=True)
        left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True)
        nav=ttk.Frame(left);nav.pack(fill='x')
        page_var=tk.StringVar(value=_('Sida 1'))
        ttk.Button(nav,text='◀',command=lambda:change_page(-1)).pack(side='left')
        ttk.Label(nav,textvariable=page_var).pack(side='left',padx=10)
        ttk.Button(nav,text='▶',command=lambda:change_page(1)).pack(side='left')
        ttk.Label(nav,text=_('Markera fält:')).pack(side='left',padx=(25,5))
        fields={_('Fakturanummer'):'invoice_no',_('Belopp (ATT BETALA)'):'amount',_('Valuta'):'currency',_('Fakturadatum'):'invoice_date',_('Förfallodatum'):'due_date',_('Kundnamn'):'customer',_('Fakturatext / Avser'):'note',_('Org.nr (leverantör)'):'org_number',_('Bankgiro (leverantör)'):'bankgiro_number'}
        field_labels={key:label for label,key in fields.items()}
        field_var=tk.StringVar(value=_('Belopp (ATT BETALA)'))
        ttk.Combobox(nav,textvariable=field_var,state='readonly',values=list(fields),width=24).pack(side='left')
        canvas=tk.Canvas(left,width=620,height=650,bg='#dfe3ea',highlightthickness=2,highlightcolor='#005a9c',takefocus=1);canvas.pack(fill='both',expand=True,pady=5)
        right=ttk.Frame(body,width=235,padding=(10,4));right.pack(side='right',fill='y');right.pack_propagate(False)
        ttk.Label(right,text=_('Avlästa värden'),style='Heading.TLabel').pack(anchor='w',pady=(0,8))
        logo_files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        mapped_logo=initial_profile.get('logo_file') if initial_profile else ''
        logo_choices=[_('(Välj logotyp för mallen)'),_('(Ingen logotyp)')]+logo_files
        initial_logo=mapped_logo if mapped_logo in logo_files else logo_choices[0]
        preview_logo_var=tk.StringVar(value=initial_logo)
        ttk.Label(right,text=_('Logotyp som matchar fakturan'),style='BodyBold.TLabel').pack(anchor='w',pady=(3,0))
        logo_combo=ttk.Combobox(right,textvariable=preview_logo_var,state='readonly',values=logo_choices,width=27)
        logo_combo.pack(fill='x',pady=(2,2))
        ttk.Label(right,text=_('Logotypen kopplas till vald leverantör/mall ovan.'),wraplength=210,style='Sub.TLabel').pack(anchor='w',pady=(0,2))
        ttk.Button(right,text=_('Matcha bildlogotyp i PDF'),command=lambda:match_visual_supplier()).pack(fill='x',pady=(0,6))
        def load_selected_profile(event=None):
            profile=supplier_profile(vendor_var.get())
            if not profile:return
            try:org_var.set(format_org_number(profile.get('org_number')))
            except ValueError:org_var.set('')
            try:bg_var.set(format_bankgiro_number(profile.get('bankgiro_number')))
            except ValueError:bg_var.set('')
            profile_logo=profile.get('logo_file') or ''
            if profile_logo in logo_files:preview_logo_var.set(profile_logo)
            elif profile_logo:preview_logo_var.set(_('(Välj logotyp för mallen)'))
            else:preview_logo_var.set(_('(Ingen logotyp)'))
            draw_saved()
        vendor_combo.bind('<<ComboboxSelected>>',load_selected_profile)
        result_labels={}
        status=tk.StringVar(value=_('Klicka Markera vid ett fält och dra sedan en ruta runt värdet.'))
        def match_visual_supplier():
            matched=match_pdf_logo(path,available_pages,supplier_profiles,SVG_DIR)
            if matched and matched.vendor:
                vendor_var.set(matched.vendor);load_selected_profile()
                status.set(_('Bildlogotypen i PDF:en matchar {vendor}.',vendor=matched.vendor))
                logger.info('Dialog visual supplier logo matched: file=%s page=%d vendor=%s',path,available_pages[0]+1,matched.vendor)
                return
            if matched:
                status.set(_('Bildlogotypen är tvetydig. Välj leverantör manuellt.'))
                logger.warning('Dialog visual supplier logo match was ambiguous: file=%s page=%d method=%s',path,available_pages[0]+1,matched.method)
                messagebox.showwarning(_('Bildlogotypen är tvetydig'),_('Flera leverantörers logotyper liknar bilden i PDF:en. Välj leverantör manuellt.'),parent=win)
                return
            status.set(_('Ingen entydig bildlogotypmatchning hittades i PDF:en.'))
            logger.warning('Dialog visual supplier logo match failed: file=%s page=%d',path,available_pages[0]+1)
            messagebox.showinfo(_('Ingen bildlogotypmatchning'),_('Logotypen i PDF:en kunde inte matchas entydigt. Kontrollera den tekniska loggen eller välj leverantör manuellt.'),parent=win)
        def activate_field(label):
            field_var.set(label);status.set(_('Markera värdet för: {label}',label=label))
        for label,key in fields.items():
            row=ttk.Frame(right);row.pack(fill='x',pady=(4,0))
            ttk.Label(row,text=label,style='BodyBold.TLabel').pack(side='left',anchor='w')
            ttk.Button(row,text=_('Markera'),command=lambda name=label:activate_field(name)).pack(side='right')
            # Identifier values already have editable fields at the top; avoid a duplicate row here.
            if key in ('org_number','bankgiro_number'):continue
            lab=ttk.Label(right,text=str(guess.get(key,'') or '—'),wraplength=210,style='Sub.TLabel');lab.pack(anchor='w')
            result_labels[key]=lab
        ttk.Label(right,textvariable=status,wraplength=210,style='Sub.TLabel').pack(anchor='w',pady=8)
        pending={};state={'page':available_pages[0],'scale':1.0,'photo':None,'start':None,'rect':None,'image_w':1,'image_h':1,'closed':False}
        def close_preview():
            if state['closed']:return
            state['closed']=True
            self.close_invoice_preview(win,doc)
        def draw_saved():
            canvas.delete('zone')
            current_vendor=vendor_var.get().strip()
            relative_page=available_pages.index(state['page'])
            with connect() as db:zs=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?) AND page_index=?',(current_vendor,relative_page)).fetchall()
            for z in zs:
                p=doc[state['page']];x0=z['x0']*p.rect.width*state['scale'];y0=z['y0']*p.rect.height*state['scale'];x1=z['x1']*p.rect.width*state['scale'];y1=z['y1']*p.rect.height*state['scale']
                canvas.create_rectangle(x0,y0,x1,y1,outline='#e13f43',width=2,tags='zone')
                canvas.create_text(x0+3,y0+3,text=_('{field} · {count} matchningar',field=field_labels.get(z['field'],z['field']),count=z['samples']),anchor='nw',fill='#9b2024',tags='zone')
        def render_page():
            page=doc[state['page']]
            state['scale']=min(610/page.rect.width,620/page.rect.height)
            pix=page.get_pixmap(matrix=fitz.Matrix(state['scale'],state['scale']),alpha=False)
            state['image_w'],state['image_h']=pix.width,pix.height
            state['photo']=tk.PhotoImage(data=base64.b64encode(pix.tobytes('png')).decode('ascii'))
            canvas.delete('all');canvas.config(scrollregion=(0,0,pix.width,pix.height),width=pix.width,height=pix.height)
            canvas.create_image(0,0,image=state['photo'],anchor='nw',tags='page')
            page_var.set(_('Sida {page} av {pages}',page=state['page']+1,pages=len(doc)));draw_saved()
        def change_page(delta):
            position=available_pages.index(state['page'])
            position=max(0,min(len(available_pages)-1,position+delta))
            state['page']=available_pages[position];render_page()
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
            if xb-xa<4 or yb-ya<4:status.set(_('Rutan blev för liten. Dra en större ruta.'));return
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
            if value=='':
                if field in ('org_number','bankgiro_number'):
                    status.set(_('Inget giltigt org.nr eller bankgironummer hittades. Markera endast leverantörens nummer.'))
                else:status.set(_('Ingen text hittades i rutan. Försök igen eller kontrollera OCR.'))
                return
            guess[field]=value
            if field in result_labels:result_labels[field].configure(text=str(value))
            if field=='org_number':org_var.set(value)
            elif field=='bankgiro_number':bg_var.set(value)
            p=doc[state['page']]
            pending[field]={'page_index':available_pages.index(state['page']),'x0':rect.x0/p.rect.width,'y0':rect.y0/p.rect.height,'x1':rect.x1/p.rect.width,'y1':rect.y1/p.rect.height}
            if state['rect']:canvas.delete(state['rect']);state['rect']=None
            color='#1d8c66';canvas.create_rectangle(xa,ya,xb,yb,outline=color,width=2,tags='zone');canvas.create_text(xa+3,ya+3,text=field_labels[field],anchor='nw',fill=color,tags='zone')
            status.set(_('{label} avläst: {value}',label=field_var.get(),value=value))
        canvas.bind('<ButtonPress-1>',start_draw);canvas.bind('<B1-Motion>',move_draw);canvas.bind('<ButtonRelease-1>',parse_zone)
        def save_and_finish(save):
            selected_logo=preview_logo_var.get()
            save_logo=selected_logo not in (_('(Välj logotyp för mallen)'),'')
            try:mall=validate_supplier_logo_link(vendor_var.get(),selected_logo,logo_files)
            except ValueError:
                logger.warning('Supplier logo link blocked because no supplier was selected: logo=%s',selected_logo)
                messagebox.showerror(_('Leverantör saknas'),_('Välj vilken leverantör logotypen tillhör innan den kopplas.'),parent=win)
                return
            guess['template_vendor']=mall
            if save_logo:
                # Keep the choice on this invoice even without saving field zones.
                guess['logo_file']=selected_logo if selected_logo in logo_files else ''
            raw_org=org_var.get().strip();raw_bg=bg_var.get().strip()
            if save and (pending or save_logo or raw_org or raw_bg or initial_org or initial_bg or mall!=original_vendor):
                if not mall:messagebox.showerror(_('Mallnamn saknas'),_('Ange leverantör eller mallnamn.'),parent=win);return
                try:org_number=normalize_org_number(raw_org)
                except ValueError:
                    messagebox.showerror(_('Ogiltigt organisationsnummer'),_('Ange organisationsnumret med 10 siffror, till exempel 556123-4567.'),parent=win);return
                try:bankgiro_number=normalize_bankgiro_number(raw_bg)
                except ValueError:
                    messagebox.showerror(_('Ogiltigt bankgironummer'),_('Ange bankgironumret med 7 eller 8 siffror, till exempel 1234-5678.'),parent=win);return
                vendor_key=mall.casefold()
                with connect() as db:
                    for other in db.execute('SELECT vendor,org_number,bankgiro_number FROM vendor_logos WHERE lower(vendor)<>lower(?)',(mall,)).fetchall():
                        try:other_org=normalize_org_number(other['org_number'])
                        except ValueError:other_org=''
                        try:other_bg=normalize_bankgiro_number(other['bankgiro_number'])
                        except ValueError:other_bg=''
                        if (org_number and other_org==org_number) or (bankgiro_number and other_bg==bankgiro_number):
                            messagebox.showerror(_('Leverantörsuppgifterna används redan'),_('Organisationsnumret eller bankgironumret används redan av leverantörsmallen {vendor}. Samma nummer kan inte sparas på flera mallar.',vendor=other['vendor']),parent=win);return
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
                    old_profile=db.execute('SELECT vendor,logo_file FROM vendor_logos WHERE lower(vendor)=lower(?)',(mall,)).fetchone()
                    if save_logo:logo_file=selected_logo if selected_logo in logo_files else ''
                    else:logo_file=old_profile['logo_file'] if old_profile else ''
                    if old_profile:
                        db.execute('UPDATE vendor_logos SET logo_file=?,org_number=?,bankgiro_number=? WHERE vendor=?',(logo_file,org_number,bankgiro_number,old_profile['vendor']))
                    else:
                        db.execute('INSERT INTO vendor_logos(vendor,logo_file,org_number,bankgiro_number) VALUES(?,?,?,?)',(vendor_key,logo_file,org_number,bankgiro_number))
                if save_logo:
                    self.logo_var.set(selected_logo if selected_logo in logo_files else _('(Ingen logotyp)'))
                    self.on_logo_select(sync_json=False)
                refresh_json_journal(parent=win)
                logger.info('Updated learned invoice template: vendor=%s fields=%s logo_set=%s identity_set=%s',vendor_key,','.join(pending),save_logo,bool(org_number or bankgiro_number))
            close_preview()
        def finish(save):
            if state['closed']:return
            try:save_and_finish(save)
            except Exception as exc:
                logger.exception('Invoice template could not be saved from PDF preview')
                messagebox.showerror(_('Mallen kunde inte sparas'),_('PDF-granskningen är fortfarande öppen. Försök igen eller fortsätt utan att spara mall.\n\n{error}',error=exc),parent=win)
        buttons=ttk.Frame(right);buttons.pack(side='bottom',fill='x',pady=8)
        ttk.Button(buttons,text=_('Fortsätt utan att spara mall'),command=lambda:finish(False)).pack(fill='x',pady=3)
        ttk.Button(buttons,text=_('Spara leverantörsmall och fortsätt'),command=lambda:finish(True),style='Accent.TButton').pack(fill='x',pady=3)
        win.protocol('WM_DELETE_WINDOW',lambda:finish(False))
        try:
            render_page()
            # Grab only after the complete preview has rendered successfully.
            win.grab_set()
            win.wait_window()
        finally:
            close_preview()
        return guess


    def _run_scheduled_import_scan(self):
        """Poll for stable PDFs, then reuse the reviewed manual import flow."""
        if self._quitting:return
        try:
            if setting('auto_import')=='1' and self._python_addons_ready and not self._import_scan_running:
                files=self._import_monitor.poll()
                if files:
                    logger.info('Automatic import detected %d stable PDF file(s)',len(files))
                    if self.state()=='withdrawn':self.deiconify()
                    self.scan_import_folder(automatic=True,paths=files)
        except Exception:
            logger.exception('Automatic import folder watch failed')
        if not self._quitting:self.after(IMPORT_WATCH_INTERVAL_MS,self._run_scheduled_import_scan)

    def scan_import_folder(self,automatic=False,paths=None):
        if getattr(self,'_import_scan_running',False):return
        self._import_scan_running=True
        try:
            IMPORT_DIR.mkdir(exist_ok=True)
            files=sorted(Path(p) for p in paths) if paths is not None else sorted(
                p for p in IMPORT_DIR.iterdir() if p.is_file() and p.suffix.lower()=='.pdf')
            if not files:
                if not automatic:messagebox.showinfo(_('Importmapp tom'),_('Lägg faktura-PDF:er i mappen:\n{folder}',folder=IMPORT_DIR),parent=self)
                return
            imported=skipped=failed=duplicates=paid_skipped=0
            for path in files:
                try:
                    candidates=read_invoice_candidates(path)
                    logger.info('PDF import found %d invoice section(s): file=%s',len(candidates),path.name)
                    for section,guess,candidate_hash in candidates:
                        try:
                            source=str(path.resolve())
                            duplicate=find_duplicate_invoice(guess.get('invoice_no',''),candidate_hash)
                            if duplicate and is_fully_paid(duplicate):
                                paid_skipped+=1
                                logger.info('Paid invoice import skipped: existing_id=%s file=%s pages=%s',duplicate['id'],path.name,','.join(str(index+1) for index in section.page_indexes))
                                continue
                            if duplicate:
                                duplicates+=1
                                logger.info('Duplicate import blocked: existing_id=%s file=%s pages=%s',duplicate['id'],path.name,','.join(str(index+1) for index in section.page_indexes))
                                continue
                            vendor=self.guess_supplier(section.text,path=str(path) if len(candidates)==1 else None,page_indexes=section.page_indexes)
                            guess['template_vendor']=vendor
                            guess=self.apply_saved_zones(str(path),vendor,guess,page_indexes=section.page_indexes)
                            guess=self.preview_invoice(str(path),guess,vendor,page_indexes=section.page_indexes)
                            self.add_invoice(source=source,guess=guess,source_hash=candidate_hash)
                            with connect() as db:
                                saved=db.execute('SELECT 1 FROM invoices WHERE source_hash=? LIMIT 1',(candidate_hash,)).fetchone()
                            if saved:imported+=1
                            else:skipped+=1
                        except Exception:
                            logger.exception('Invoice section import failed for %s pages=%s',path.name,section.page_indexes);failed+=1
                except Exception:
                    logger.exception('Import folder scan failed for %s',path.name);failed+=1
            logger.info('Import folder scan complete: automatic=%s imported=%d duplicates=%d paid_skipped=%d skipped=%d failed=%d',automatic,imported,duplicates,paid_skipped,skipped,failed)
            self.refresh()
            # Automatic duplicate-only and user-cancelled batches must not add
            # another popup after the review dialog. Manual scans always report.
            if not automatic or imported or failed:
                title=_('Automatisk import klar') if automatic else _('Skanning klar')
                messagebox.showinfo(title,_('Importerade: {imported}\nDubbletter som inte importerades: {duplicates}\nBetalda som hoppades över: {paid}\nAvbrutna: {skipped}\nFel: {failed}',imported=imported,duplicates=duplicates,paid=paid_skipped,skipped=skipped,failed=failed),parent=self)
            if not automatic or imported:
                show_due_reminder_dialog(parent=self)
        finally:
            self._import_scan_running=False

    def open_import_folder(self):
        IMPORT_DIR.mkdir(exist_ok=True)
        try:open_path(IMPORT_DIR)
        except Exception:logger.exception('Could not open import folder')

    def open_export_folder(self):
        EXPORT_DIR.mkdir(exist_ok=True)
        try:open_path(EXPORT_DIR)
        except Exception:logger.exception('Could not open export folder')

    def show_ledger_history(self,window):
        search=getattr(self,'invoice_search_var',None)
        if search is not None:search.set('')
        self.select_invoice_filter('history')
        self.refresh()
        window.destroy()
        log_activity('ledger','receipt_history_opened','completed')

    def show_ledger_receipt(self,source_name,report,result,plan):
        """Show every applied paid change and explain an unchanged import."""
        actual_plan=result.plan or plan
        win=self._new_toplevel(_('Reskontrakvitto'))
        win.geometry('900x560');win.minsize(650,400)
        form=ttk.Frame(win,padding=18);form.pack(fill='both',expand=True)
        commit=APP_RELEASE_COMMIT[:12] or _('källkörning')
        summary=_('Lista per {date} · {source}\nNya fakturor: {new} · Befintliga: {existing} · Betalmarkerade: {paid} · Uppdaterade betalbelopp: {updated}\nBuild: {commit}',date=report.list_date,source=source_name,new=result.imported,existing=result.existing,paid=result.marked_paid,updated=result.payment_updates,commit=commit)
        ttk.Label(form,text=summary,style='Sub.TLabel',justify='left',wraplength=840).pack(anchor='w',pady=(0,12))
        body=ttk.Frame(form);body.pack(fill='both',expand=True)
        text=tk.Text(body,wrap='word',font='TkTextFont',background='white',foreground='#1f2a3d',relief='solid',borderwidth=1,padx=12,pady=12,highlightthickness=2)
        scroll=ttk.Scrollbar(body,orient='vertical',command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        text.insert('1.0',ledger_receipt_text(report,actual_plan));text.configure(state='disabled')
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text=_('Visa historik / arkiverade / betalda'),command=lambda:self.show_ledger_history(win),style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Stäng'),command=win.destroy).pack(side='right')
        self._finalize_window_actions(form)
        win.grab_set()
        log_activity('ledger','receipt_shown','completed',source=source_name,paid=result.marked_paid,payment_updates=result.payment_updates,commit=commit)
        return win

    def import_ledger_list(self):
        """Import a complete ledger and reconcile paid invoices automatically after validation."""
        path=filedialog.askopenfilename(
            title=_('Välj reskontralista'),filetypes=[('PDF','*.pdf')],
        )
        if not path:return None
        source_name=Path(path).name
        logger.info('Customer ledger import selected: %s',_ledger_log_json({'source':source_name}))
        try:
            report=read_ledger_report(path)
            _log_ledger_report(path,report)
            plan=plan_ledger_import(DB_PATH,report)
            _log_ledger_plan(path,plan)
        except LedgerImportError as exc:
            logger.warning('Customer ledger validation failed: %s',_ledger_log_json({'source':source_name,'error':str(exc)}))
            messagebox.showerror(_('Reskontralistan kunde inte läsas'),_('Reskontralistan kunde inte läsas.\n\n{error}',error=exc),parent=self)
            return None
        except Exception as exc:
            logger.exception('Customer ledger import planning failed: file=%s',source_name)
            messagebox.showerror(_('Reskontralistan kunde inte läsas'),_('Reskontralistan kunde inte läsas.\n\n{error}',error=exc),parent=self)
            return None

        try:
            result=apply_ledger_import(DB_PATH,report)
        except Exception as exc:
            logger.exception('Customer ledger import failed: file=%s',source_name)
            messagebox.showerror(_('Reskontralistan kunde inte importeras'),_('Reskontralistan kunde inte importeras.\n\n{error}',error=exc),parent=self)
            return None
        refresh_json_journal(parent=self)
        logger.info('Customer ledger imported: %s',_ledger_log_json({
            'source':source_name,'list_date':report.list_date,'new':result.imported,
            'existing':result.existing,'marked_paid':result.marked_paid,
            'payment_updates':result.payment_updates,
        }))
        previous_filter=getattr(self,'current_filter_key','current')
        self.select_invoice_filter('current')
        log_activity('ledger','active_invoice_list_restored','completed',previous_filter=previous_filter,marked_paid=result.marked_paid)
        self.refresh()
        self.show_ledger_receipt(source_name,report,result,plan)
        return result

    def _maybe_show_ledger_reminder(self):
        """Offer the Friday ledger import once per date while the window is visible."""
        try:
            today=date.today()
            if self._quitting or today.weekday()!=4:return False
            if setting('ledger_friday_reminder')!='1' or setting('ledger_last_friday_prompt')==today.isoformat():return False
            try:visible=bool(self.winfo_viewable())
            except (AttributeError,tk.TclError):visible=True
            if not visible:return False
            set_setting('ledger_last_friday_prompt',today.isoformat())
            if messagebox.askyesno(
                _('Veckans reskontralista'),
                _('Det är fredag. Hämta en aktuell kundreskontralista från Fortnox och importera den för att uppdatera fakturor och betalstatus.\n\nVill du välja listan nu?'),
                parent=self,
            ):self.import_ledger_list()
            return True
        except Exception:
            logger.exception('Weekly customer ledger reminder failed')
            return False

    def _run_scheduled_ledger_reminder(self):
        if self._quitting:return
        self._maybe_show_ledger_reminder()
        if not self._quitting:self.after(LEDGER_REMINDER_INTERVAL_MS,self._run_scheduled_ledger_reminder)

    def import_invoice(self):
        path=filedialog.askopenfilename(title=_('Välj faktura-PDF'),filetypes=[('PDF','*.pdf')])
        if not path:return
        try:
            candidates=read_invoice_candidates(path)
        except Exception as e:
            logger.exception('Invoice PDF read failed: %s',path)
            messagebox.showerror(_('Kunde inte läsa PDF'),_(str(e)));return
        multiple=len(candidates)>1
        imported=skipped=failed=duplicates=paid_skipped=0
        for section,guess,candidate_hash in candidates:
            try:
                duplicate=find_duplicate_invoice(guess.get('invoice_no',''),candidate_hash)
                if duplicate and is_fully_paid(duplicate):
                    paid_skipped+=1
                    logger.info('Paid invoice import skipped: existing_id=%s pages=%s',duplicate['id'],section.page_indexes)
                    if not multiple:
                        messagebox.showinfo(_('Betald faktura'),_('Faktura {invoice_no} är redan betald och importeras inte igen.',invoice_no=duplicate['invoice_no']),parent=self)
                        return
                    continue
                if duplicate:
                    duplicates+=1
                    logger.info('Duplicate import blocked: existing_id=%s pages=%s',duplicate['id'],section.page_indexes)
                    if not multiple:
                        show_duplicate_invoice(duplicate,parent=self)
                        return
                    continue
                vendor=self.guess_supplier(section.text,path=path if len(candidates)==1 else None,page_indexes=section.page_indexes)
                guess['template_vendor']=vendor
                guess=self.apply_saved_zones(path,vendor,guess,page_indexes=section.page_indexes)
                logger.info('Invoice PDF section read: pages=%s extracted_chars=%s suggested_fields=%s',section.page_indexes,len(section.text),','.join(k for k,v in guess.items() if v))
                guess=self.preview_invoice(path,guess,vendor,page_indexes=section.page_indexes)
                self.add_invoice(source=str(Path(path).resolve()),guess=guess,source_hash=candidate_hash)
                with connect() as db:
                    saved=db.execute('SELECT 1 FROM invoices WHERE source_hash=? LIMIT 1',(candidate_hash,)).fetchone()
                if saved:imported+=1
                else:skipped+=1
            except Exception as e:
                failed+=1
                logger.exception('Invoice PDF section import failed: %s pages=%s',path,section.page_indexes)
                if not multiple:
                    messagebox.showerror(_('Kunde inte läsa PDF'),_(str(e)),parent=self);return
        if multiple:
            self.refresh()
            messagebox.showinfo(_('Skanning klar'),_('Importerade: {imported}\nDubbletter som inte importerades: {duplicates}\nBetalda som hoppades över: {paid}\nAvbrutna: {skipped}\nFel: {failed}',imported=imported,duplicates=duplicates,paid=paid_skipped,skipped=skipped,failed=failed),parent=self)

    def import_original_invoice(self):
        """Enrich one ledger-imported row from its reviewed original invoice PDF."""

        row=self.selected()
        if row is None:return None
        if not has_ledger_import_basis(row):
            logger.warning('Original invoice enrichment requires a ledger-imported row: invoice=%s',row['id'])
            messagebox.showinfo(_('Inte en reskontrafaktura'),_('Välj en faktura som har importerats från kundreskontran.'),parent=self)
            return None
        path=filedialog.askopenfilename(title=_('Välj originalfaktura-PDF'),filetypes=[('PDF','*.pdf')])
        if not path:return None
        try:
            candidates=read_invoice_candidates(path)
            candidate=find_invoice_pdf_candidate(row,candidates)
            if candidate is None and len(candidates)==1 and not str((candidates[0][1] or {}).get('invoice_no') or '').strip():
                # A single invoice with an unreadable number may be corrected in
                # the normal preview, but is verified again before anything saves.
                candidate=candidates[0]
            if candidate is None:
                logger.warning('Original invoice PDF has no unique matching section: invoice=%s invoice_no=%s file=%s candidates=%d',row['id'],row['invoice_no'],path,len(candidates))
                messagebox.showerror(_('Originalfakturan matchar inte'),_('PDF:en innehåller ingen entydig fakturasektion med fakturanummer {invoice_no}. Välj originalfakturan för den markerade reskontrafakturan.',invoice_no=row['invoice_no']),parent=self)
                return None
            section,guess,candidate_hash=candidate
            duplicate=find_duplicate_invoice('',candidate_hash,exclude_id=row['id'])
            if duplicate:
                logger.warning('Original invoice PDF is already linked to another row: invoice=%s duplicate=%s file=%s',row['id'],duplicate['id'],path)
                show_duplicate_invoice(duplicate,parent=self)
                return None
            vendor=str(row['template_vendor'] or '').strip()
            if not vendor:
                vendor=self.guess_supplier(section.text,path=path if len(candidates)==1 else None,page_indexes=section.page_indexes)
            guess=dict(guess);guess['template_vendor']=vendor
            guess=self.apply_saved_zones(path,vendor,guess,page_indexes=section.page_indexes)
            guess=self.preview_invoice(path,guess,vendor,page_indexes=section.page_indexes)
            if normalize_invoice_number(guess.get('invoice_no'))!=normalize_invoice_number(row['invoice_no']):
                logger.warning('Original invoice enrichment blocked by invoice-number mismatch: invoice=%s expected=%s actual=%s file=%s',row['id'],row['invoice_no'],guess.get('invoice_no'),path)
                messagebox.showerror(_('Originalfakturan matchar inte'),_('Fakturanumret i originalfakturan måste vara {invoice_no} innan informationen kan sparas.',invoice_no=row['invoice_no']),parent=self)
                return None
            saved=self.invoice_dialog(
                'Komplettera faktura från original-PDF',row=row,source=str(Path(path).resolve()),
                guess=guess,source_hash=candidate_hash,enrich_original=True,
            )
            if not saved:
                logger.info('Original invoice enrichment cancelled: invoice=%s file=%s',row['id'],path)
                return None
            with connect() as db:updated=db.execute('SELECT * FROM invoices WHERE id=?',(row['id'],)).fetchone()
            logger.info('Original invoice linked and ledger row enriched: invoice=%s invoice_no=%s file=%s pages=%s',row['id'],row['invoice_no'],path,section.page_indexes)
            log_activity('invoice','original_invoice_imported','completed',invoice_id=row['id'],invoice_no=row['invoice_no'],source=Path(path).name,pages=list(section.page_indexes))
            messagebox.showinfo(_('Originalfaktura importerad'),_('Faktura {invoice_no} har kompletterats med originalfakturans uppgifter. Reskontrans belopp, valuta och betalda belopp samt P1/P2-historik har inte ändrats.',invoice_no=row['invoice_no']),parent=self)
            return updated
        except Exception as exc:
            logger.exception('Original invoice enrichment failed: invoice=%s file=%s',row['id'],path)
            messagebox.showerror(_('Originalfakturan kunde inte importeras'),str(exc),parent=self)
            return None

    def add_invoice(self,source='',guess=None,source_hash=''):
        self.invoice_dialog('Lägg till faktura',source=source,guess=guess,source_hash=source_hash)

    def edit_invoice(self):
        r=self.selected()
        if r:self.invoice_dialog('Redigera faktura',row=r)

    def edit_customer(self):
        """Edit the selected invoice's customer and reusable recipient list."""
        r=self.selected()
        if not r:return
        values=apply_saved_customer_contact(dict(r))
        w=self._new_toplevel(_('Redigera kund'));w.grab_set();w.resizable(True,True)
        form=self._dialog_form(w,padding=20)
        ttk.Label(form,text=_('Kundnamn')).grid(row=0,column=0,sticky='w',padx=(0,12),pady=5)
        customer_entry=ttk.Entry(form,width=52);customer_entry.grid(row=0,column=1,pady=5);customer_entry.insert(0,r['customer'])
        ttk.Label(form,text=_('E-postadresser')).grid(row=1,column=0,sticky='w',padx=(0,12),pady=5)
        email_entry=ttk.Entry(form,width=52);email_entry.grid(row=1,column=1,pady=5);email_entry.insert(0,values.get('email',''))
        ttk.Label(
            form,text=_('Flera adresser: separera med kommatecken (,). Kundens adresser återanvänds på nästa faktura till samma kund.'),
            wraplength=470,
        ).grid(row=2,column=0,columnspan=2,sticky='w',pady=(5,12))
        def save():
            customer=customer_entry.get().strip()
            if not customer:
                messagebox.showerror(_('Kontrollera uppgifter'),_('Ange ett kundnamn.'),parent=w);return
            try:emails=normalize_email_addresses(email_entry.get())
            except EmailAddressError as exc:
                messagebox.showerror(_('Ogiltig e-postadress'),_('Kontrollera adressen: {email}',email=exc.address),parent=w);return
            record=dict(r);record['customer']=customer;record['email']=emails
            duplicate=save_invoice_record(record,r['id'])
            if duplicate:
                show_duplicate_invoice(duplicate,parent=w);return
            refresh_json_journal(parent=w)
            logger.info('Customer contact updated: invoice=%s recipients=%d',r['id'],len(parse_email_addresses(emails)))
            w.destroy();self.refresh()
        buttons=ttk.Frame(form);buttons.grid(row=3,column=0,columnspan=2,sticky='e')
        ttk.Button(buttons,text=_('Spara'),command=save,style='Accent.TButton').pack(side='left',padx=(0,7))
        ttk.Button(buttons,text=_('Stäng'),command=w.destroy).pack(side='left')
        w.wait_window()

    def invoice_dialog(self,title,row=None,source='',guess=None,source_hash='',enrich_original=False):
        w=self._new_toplevel(_(title));w.grab_set();w.resizable(True,True);w.configure(bg='#f3f5f8')
        fields=[('Kundnamn','customer'),('Fakturanummer','invoice_no'),('Fakturadatum (ÅÅÅÅ-MM-DD)','invoice_date'),('Förfallodatum (ÅÅÅÅ-MM-DD)','due_date'),('Fakturabelopp','amount'),('Valuta (ISO-kod, t.ex. SEK/EUR)','currency'),('Redan betalt','paid'),('E-post','email'),('Fakturatext / Avser','note')]
        enriched=merge_original_invoice_values(row,guess) if enrich_original and row is not None else None
        vals={k:(enriched[k] if enriched is not None else (row[k] if row else (guess or {}).get(k,''))) for _label,k in fields}
        vals['currency']=normalize_currency(vals.get('currency'))
        vals['source']=source if enrich_original else (row['source'] if row else source)
        vals['source_hash']=source_hash if enrich_original else (row['source_hash'] if row else source_hash)
        vals['template_vendor']=enriched['template_vendor'] if enriched is not None else (row['template_vendor'] if row else (guess or {}).get('template_vendor',''))
        vals['logo_file']=enriched['logo_file'] if enriched is not None else (row['logo_file'] if row else (guess or {}).get('logo_file'))
        apply_saved_customer_contact(vals)
        reviewed_var=tk.BooleanVar(value=bool(row['reviewed']) if row else not bool(source))
        entries={};form=self._dialog_form(w,padding=18)
        for i,(lab,k) in enumerate(fields):
            ttk.Label(form,text=_(lab)).grid(row=i,column=0,sticky='w',pady=5,padx=(0,12));e=ttk.Entry(form,width=43);e.grid(row=i,column=1,pady=5);e.insert(0,str(vals.get(k,'') or ''));entries[k]=e
            if enrich_original and k in ORIGINAL_INVOICE_PROTECTED_FIELDS:e.configure(state='readonly')
        review_row=len(fields)
        if enrich_original:
            ttk.Label(form,text=_('Reskontrans fakturanummer, belopp, valuta och betalda belopp är låsta. P1/P2-historiken behålls.'),wraplength=520).grid(row=review_row,column=0,columnspan=2,sticky='w',pady=(9,2))
            review_row+=1
        ttk.Checkbutton(form,text=_('Jag har granskat och godkänt fakturauppgifterna'),variable=reviewed_var).grid(row=review_row,column=0,columnspan=2,sticky='w',pady=(8,4))
        saved=False
        def save():
            nonlocal saved
            v={k:e.get().strip() for k,e in entries.items()}
            if enrich_original and normalize_invoice_number(v['invoice_no'])!=normalize_invoice_number(row['invoice_no']):
                messagebox.showerror(_('Originalfakturan matchar inte'),_('Fakturanumret kan inte ändras när en reskontrafaktura kompletteras.'),parent=w);return
            if not v['customer'] or not v['invoice_no'] or not dparse(v['due_date']):messagebox.showerror(_('Kontrollera uppgifter'),_('Kund, fakturanummer och giltigt förfallodatum krävs.'),parent=w);return
            if not is_valid_currency(v['currency']):messagebox.showerror(_('Ogiltig valuta'),_('Ange en valuta med tre bokstäver, till exempel SEK, EUR eller USD.'),parent=w);return
            try:v['email']=normalize_email_addresses(v['email'])
            except EmailAddressError as exc:
                messagebox.showerror(_('Ogiltig e-postadress'),_('Kontrollera adressen: {email}',email=exc.address),parent=w);return
            currency=normalize_currency(v['currency'])
            try:amount=float(v['amount'].replace(' ','').replace(',','.')) if v['amount'] else 0;paid=float(v['paid'].replace(' ','').replace(',','.')) if v['paid'] else 0
            except ValueError:messagebox.showerror(_('Fel belopp'),_('Ange belopp som siffror.'),parent=w);return
            record=dict(v)
            record.update(
                template_vendor=vals['template_vendor'],amount=amount,currency=currency,paid=paid,
                source=vals['source'],source_hash=vals['source_hash'],reviewed=int(reviewed_var.get()),
                logo_file=vals['logo_file'],
            )
            duplicate=save_invoice_record(record,row['id'] if row else None)
            if duplicate:
                logger.info('Duplicate invoice save blocked: existing_id=%s',duplicate['id'])
                show_duplicate_invoice(duplicate,parent=w)
                return
            refresh_json_journal(parent=w)
            logger.info('Invoice saved/edited: source_type=%s fields=customer,invoice_no,due_date,amount,currency,paid,email,note',Path(vals['source']).suffix.lower() if vals['source'] else 'manual')
            saved=True
            w.destroy();self.refresh()
        ttk.Button(form,text=_('Spara'),command=save,style='Accent.TButton').grid(row=review_row+1,column=1,sticky='e',pady=(12,0))
        w.wait_window()
        return saved

    def mark_invoice_paid(self):
        """Settle the selected invoice while retaining one safe paid undo value."""

        r=self.selected()
        if not r:return False
        if is_fully_paid(r):
            messagebox.showinfo(_('Redan betald'),_('Faktura {invoice_no} är redan markerad som betald.',invoice_no=r['invoice_no']),parent=self)
            return False
        marked_at=datetime.now().isoformat(timespec='seconds')
        with connect() as db:
            db.execute(
                "UPDATE invoices SET paid_before_marking=paid,paid_marked_at=?,paid_marked_source='manual',paid=amount WHERE id=?",
                (marked_at,r['id']),
            )
        refresh_json_journal(parent=self)
        logger.info('Invoice marked as fully paid: id=%s previous_paid=%s',r['id'],r['paid'])
        log_activity('invoice','marked_paid','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],previous_paid=float(r['paid'] or 0),source='manual')
        self.refresh()
        return True

    def undo_invoice_paid(self):
        """Restore a paid row to the active list without changing its history."""

        r=self.selected()
        if not r:return False
        if not is_fully_paid(r):
            messagebox.showinfo(_('Inte betalmarkerad'),_('Faktura {invoice_no} är inte helt betalmarkerad.',invoice_no=r['invoice_no']),parent=self)
            return False
        amount=float(r['amount'] or 0)
        keys=r.keys();raw_previous=r['paid_before_marking'] if 'paid_before_marking' in keys else None
        has_previous=raw_previous is not None and str(raw_previous)!=''
        try:previous=float(raw_previous) if has_previous else 0.0
        except (TypeError,ValueError):
            messagebox.showerror(_('Betalbeloppet kan inte återställas'),_('Det sparade tidigare betalbeloppet är ogiltigt. Korrigera fakturan via Redigera faktura.'),parent=self)
            return False
        remaining=amount-previous
        if previous<0 or remaining<=0.005:
            messagebox.showerror(_('Betalbeloppet kan inte återställas'),_('Det tidigare betalbeloppet ger inget kvarstående belopp. Korrigera fakturan via Redigera faktura.'),parent=self)
            return False
        if has_previous:
            restore_text=_('Redan betalt återställs till {paid} och kvar att betala blir {remaining}.',paid=money(previous,r['currency']),remaining=money(remaining,r['currency']))
        else:
            restore_text=_('Inget tidigare betalbelopp finns sparat för denna äldre betalmarkering. Redan betalt sätts till {paid} och kvar att betala blir {remaining}.',paid=money(0,r['currency']),remaining=money(remaining,r['currency']))
        confirmed=messagebox.askyesno(
            _('Ångra betalmarkering'),
            _('Återför faktura {invoice_no} som obetald?\n\n{restore}\n\nP1/P2-, e-post- och reskontrahistorik ändras inte.',invoice_no=r['invoice_no'],restore=restore_text),
            parent=self,
        )
        source=str(r['paid_marked_source'] or '') if 'paid_marked_source' in keys else ''
        if not confirmed:
            log_activity('invoice','paid_marking_undo_declined','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],source=source)
            return False
        with connect() as db:
            db.execute(
                "UPDATE invoices SET paid=?,paid_before_marking=NULL,paid_marked_at='',paid_marked_source='' WHERE id=?",
                (previous,r['id']),
            )
        refresh_json_journal(parent=self)
        logger.info('Invoice paid marking undone: id=%s restored_paid=%s source=%s',r['id'],previous,source or 'legacy')
        log_activity('invoice','paid_marking_undone','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],restored_paid=previous,source=source or 'legacy')
        selector=getattr(self,'select_invoice_filter',None)
        if selector:selector('current')
        else:self.current_filter_key='current'
        self.refresh()
        return True

    def toggle_ignore(self):
        r=self.selected()
        if not r:return
        new=0 if r['ignored'] else 1
        with connect() as db:db.execute('UPDATE invoices SET ignored=? WHERE id=?',(new,r['id']))
        log_activity('invoice','ignore_toggled','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],ignored=bool(new))
        refresh_json_journal(parent=self)
        self.refresh()

    def delete_invoice(self):
        r=self.selected()
        if r and messagebox.askyesno(_('Ta bort faktura'),_('Ta bort {invoice_no} permanent från den lokala databasen?',invoice_no=r['invoice_no'])):
            with connect() as db:db.execute('DELETE FROM invoices WHERE id=?',(r['id'],))
            log_activity('invoice','deleted','completed',invoice_id=r['id'],invoice_no=r['invoice_no'])
            refresh_json_journal(parent=self)
            self.refresh()

    def mark_reminder_email_sent(self):
        """Let the user explicitly confirm a manual send for the latest level."""
        r=self.selected()
        if not r:return False
        level=latest_reminder_level(r)
        if not level:
            messagebox.showinfo(_('Påminnelse saknas'),_('Skapa P1 eller P2 först.'),parent=self);return False
        column=level.lower()+'_sent_date'
        existing=r[column] if column in r.keys() else ''
        if existing:
            messagebox.showinfo(
                _('Redan markerad som skickad'),
                _('E-posten för {level} är redan markerad som skickad {date}.',level=level,date=existing),parent=self,
            );return False
        today=date.today().isoformat()
        if not messagebox.askyesno(
            _('Bekräfta skickad e-post'),
            _('Appen kan inte kontrollera e-postprogrammet. Bekräfta endast om du själv har skickat {level} för faktura {invoice_no}.\n\nSkickaddatum blir {date}.',level=level,invoice_no=r['invoice_no'],date=today),
            parent=self,
        ):return False
        with connect() as db:db.execute(f'UPDATE invoices SET {column}=? WHERE id=?',(today,r['id']))
        refresh_json_journal(parent=self)
        logger.info('Email manually marked as sent: invoice=%s level=%s date=%s',r['id'],level,today)
        self.refresh()
        return True

    def preview_reminder_email(self,content,pdf_path):
        """Review and optionally edit one draft before handing it to the OS mail app."""
        result=None
        w=self._new_toplevel(_('Förhandsgranska e-post'));w.grab_set();w.resizable(True,True)
        form=ttk.Frame(w,padding=20);form.pack(fill='both',expand=True)
        thunderbird=content.get('attachment_handler')=='thunderbird'
        thunderbird_unavailable=content.get('attachment_handler')=='thunderbird_unavailable'
        if thunderbird:
            pdf_label=_('PDF som bifogas automatiskt i Thunderbird: {path}',path=pdf_path)
            instructions=_('Ändringarna gäller bara detta utkast. PDF:en bifogas automatiskt i Thunderbird. Granska och skicka mejlet manuellt.')
        elif thunderbird_unavailable:
            pdf_label=_('Thunderbird är standardapp men programfilen hittades inte. PDF att bifoga manuellt: {path}',path=pdf_path)
            instructions=_('Thunderbird hittades inte för automatisk bilaga. Utkastet öppnas via mailto; bifoga PDF:en och skicka mejlet manuellt.')
        else:
            pdf_label=_('PDF att bifoga manuellt: {path}',path=pdf_path)
            instructions=_('Ändringarna gäller bara detta utkast. Bifoga PDF:en och skicka mejlet manuellt i e-postappen.')
        ttk.Label(
            form,text=_('Mottagare: {recipients}',recipients=', '.join(content['recipients'])),wraplength=680,
        ).pack(anchor='w',pady=(0,6))
        ttk.Label(form,text=_('Dold kopia (BCC): {email}',email=REMINDER_BCC)).pack(anchor='w',pady=(0,6))
        ttk.Label(form,text=pdf_label,wraplength=680).pack(anchor='w',pady=(0,12))
        ttk.Label(form,text=_('Ämne')).pack(anchor='w')
        subject_var=tk.StringVar(value=content['subject'])
        ttk.Entry(form,textvariable=subject_var,width=90).pack(fill='x',pady=(3,10))
        ttk.Label(form,text=_('Meddelande')).pack(anchor='w')
        body=ttk.Frame(form);body.pack(fill='both',expand=True,pady=(3,10))
        body_text=tk.Text(body,width=90,height=20,wrap='word',undo=True)
        body_scroll=ttk.Scrollbar(body,orient='vertical',command=body_text.yview)
        body_text.configure(yscrollcommand=body_scroll.set)
        body_text.insert('1.0',content['body'])
        body_text.pack(side='left',fill='both',expand=True);body_scroll.pack(side='right',fill='y')
        ttk.Label(form,text=instructions,wraplength=680).pack(anchor='w',pady=(0,12))
        def accept():
            nonlocal result
            subject=subject_var.get().strip();body=body_text.get('1.0','end-1c').strip()
            if not subject or not body:
                messagebox.showerror(_('Kontrollera e-post'),_('Ämne och meddelande krävs.'),parent=w);return
            result=dict(content);result['subject']=subject;result['body']=body
            w.destroy()
        def cancel():
            w.destroy()
        buttons=ttk.Frame(form);buttons.pack(fill='x')
        ttk.Button(buttons,text=_('Öppna i e-postappen'),command=accept,style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Avbryt'),command=cancel).pack(side='right')
        w.protocol('WM_DELETE_WINDOW',cancel)
        w.wait_window()
        return result

    def create_reminder_email(self):
        """Open a draft for the latest existing reminder using current contacts."""
        r=self.selected()
        if not r:return False
        level=latest_reminder_level(r)
        if not level:
            messagebox.showinfo(
                _('Påminnelse saknas'),
                _('Skapa P1 eller P2 innan ett e-postutkast kan öppnas.'),parent=self,
            );return False
        try:recipients=reminder_email_addresses(r)
        except EmailAddressError as exc:
            messagebox.showwarning(
                _('Ogiltig e-postadress'),_('Kontrollera adressen: {email}',email=exc.address),parent=self,
            );return False
        if not recipients:
            messagebox.showinfo(
                _('E-postadresser saknas'),
                _('Lägg till kundens e-postadresser via Redigera kund innan utkastet skapas.'),parent=self,
            );return False
        pdf_path=find_reminder_pdf(r,level)
        if pdf_path is None:
            messagebox.showwarning(
                _('Påminnelse-PDF saknas'),
                _('PDF:en för {level} hittades inte. Återskapa den via Redigera {level} innan e-postutkastet skapas.',level=level),parent=self,
            );return False
        return self.open_reminder_email(r,level,pdf_path)

    def open_reminder_email(self,r,level,pdf_path):
        """Preview, then open, but never automatically send, a customer draft."""
        try:
            recipients=reminder_email_addresses(r)
            if not recipients:return False
            content=build_reminder_email_content(r,level,recipients)
            thunderbird_unavailable=False
            try:
                thunderbird=default_thunderbird_executable()
                thunderbird_unavailable=not thunderbird and windows_uses_thunderbird()
            except Exception:
                logger.exception('Thunderbird detection failed; using standard mailto')
                thunderbird=None
            content['attachment_handler']='thunderbird' if thunderbird else ('thunderbird_unavailable' if thunderbird_unavailable else 'manual')
            preview=getattr(self,'preview_reminder_email',None)
            if preview:
                content=preview(content,pdf_path)
                if content is None:return False
            if thunderbird:
                if not open_thunderbird_draft(thunderbird,content,pdf_path):raise RuntimeError('Thunderbird compose failed')
            else:
                url=build_reminder_mailto(r,level,recipients,content=content)
                if not webbrowser.open(url):raise RuntimeError('mailto handler returned False')
        except Exception as exc:
            logger.exception('Reminder email draft could not be opened')
            messagebox.showwarning(
                _('E-postutkastet kunde inte öppnas'),
                _('Påminnelsen är skapad men e-postappen kunde inte öppnas.\n\nPDF: {path}\n\n{error}',path=pdf_path,error=exc),
                parent=self,
            )
            return False
        if thunderbird:logger.info('Thunderbird compose requested with PDF: invoice=%s level=%s path=%s',r['id'],level,pdf_path)
        logger.info('Opened reminder email draft: invoice=%s level=%s recipients=%d handler=%s',r['id'],level,len(recipients),'thunderbird' if thunderbird else 'mailto')
        try:
            record_reminder_draft_opened(r,level)
            refresh_json_journal(parent=self)
        except Exception as exc:
            logger.exception('Email draft opened but its status could not be saved')
            messagebox.showwarning(
                _('E-poststatusen kunde inte sparas'),
                _('Utkastet öppnades, men e-poststatusen kunde inte sparas.\n\n{error}',error=exc),parent=self,
            )
        refresher=getattr(self,'refresh',None)
        if refresher:
            try:refresher()
            except Exception:logger.exception('UI refresh after email draft failed')
        return True

    def confirm_ledger_p1_fallback(self,row,reason):
        """Ask before using ledger data when original-PDF verification failed."""

        confirmed=messagebox.askyesno(
            _('Använd reskontraunderlag för P1?'),
            _('Original-PDF:en kunde inte bekräfta fakturan.\n\n{reason}\n\nVill du skapa P1 med reskontraimportens uppgifter i stället? Valet loggas. Original-PDF:en och reskontradata ändras inte.',reason=reason),
            parent=self,
        )
        action='p1_ledger_basis_accepted' if confirmed else 'p1_ledger_basis_declined'
        log_activity('reminder',action,'completed',invoice_id=row['id'],invoice_no=row['invoice_no'],reason=reason)
        if confirmed:logger.warning('P1 will use customer-ledger data after original-PDF verification failed: invoice=%s',row['id'])
        else:logger.info('P1 customer-ledger fallback declined: invoice=%s',row['id'])
        return confirmed

    def make_reminder(self):
        r=self.selected()
        if not r:return
        latest=None
        recreated=False
        stage=next_stage(r)
        if r['p1_date'] and stage not in ('Avslutad', 'Ignorerad') and p1_file_missing(r):
            result=self.recreate_p1(r)
            if not result:return None
            recreated=True
            with connect() as db:r=db.execute('SELECT * FROM invoices WHERE id=?',(r['id'],)).fetchone()
            latest=(r,'P1',result)
            stage=next_stage(r)
        if stage not in ('P1 att skapa','P2 att skapa'):
            if recreated:return latest[2]
            messagebox.showwarning(_('Inte redo'),_('Fakturan är inte redo för påminnelse. Status: {stage}',stage=_(stage)));return

        ledger_fallback_used=False
        while stage in ('P1 att skapa','P2 att skapa'):
            level='P1' if stage.startswith('P1') else 'P2'
            if level == 'P1':
                source_differences=[]
                try:
                    apply_zones = getattr(self, 'apply_saved_zones', None)
                    zone_applier = None
                    if r['template_vendor'] and apply_zones:
                        def zone_applier(path, section, pdf_values):
                            # Reuse learned fields without changing the selected logo.
                            return apply_zones(
                                path, r['template_vendor'], pdf_values,
                                page_indexes=section.page_indexes, update_logo=False,
                            )
                    source_differences = verify_invoice_source(r, zone_applier=zone_applier)
                except Exception as exc:
                    logger.exception('Original invoice verification failed before P1: invoice=%s',r['id'])
                    if has_ledger_import_basis(r):
                        if not self.confirm_ledger_p1_fallback(r,str(exc)):
                            return latest[2] if latest else None
                        ledger_fallback_used=True
                    else:
                        messagebox.showerror(
                            _('Originalfakturan kunde inte kontrolleras'),
                            _('P1 skapades inte eftersom original-PDF:en kunde inte läsas.\n\n{error}',error=exc),
                            parent=self,
                        )
                        return latest[2] if latest else None
                if source_differences:
                    labels = dict(INVOICE_PDF_COMPARE_FIELDS)
                    details = []
                    for difference in source_differences:
                        field = difference['field']
                        label = _('Original-PDF / fakturadel') if field == 'source' else _(labels.get(field, field))
                        saved = difference.get('saved')
                        actual = difference.get('pdf')
                        if field == 'source':
                            actual = _('hittades inte')
                        saved = '—' if saved in (None, '') else str(saved)
                        actual = '—' if actual in (None, '') else str(actual)
                        details.append(_('{label}: sparat {saved} · PDF {actual}',label=label,saved=saved,actual=actual))
                    logger.warning('P1 blocked because saved invoice differs from source PDF: invoice=%s fields=%s',r['id'],','.join(item['field'] for item in source_differences))
                    if has_ledger_import_basis(r):
                        if not self.confirm_ledger_p1_fallback(r,'\n'.join(details)):
                            return latest[2] if latest else None
                        ledger_fallback_used=True
                    else:
                        messagebox.showwarning(
                            _('Fakturan stämmer inte med original-PDF:en'),
                            _('P1 skapades inte. Kontrollera och redigera fakturan innan du försöker igen.\n\n{details}',details='\n'.join(details)),
                            parent=self,
                        )
                        return latest[2] if latest else None
            fee=float(setting('fee') or 0);locked=setting('fee_locked')=='1'
            template_name=r['template_vendor'] or _('Ingen matchad mall')
            logo_path,logo_name=self.invoice_logo(r)
            confirmation=_('Skapa {level} för {invoice_no}?\n\nPåminnelseavgift: {fee}{locked}\nRänta: {interest}% per år\nMall: {template}\nSVG-logotyp: {logo}\n\nEn e-postförhandsgranskning visas om kunden har adresser. E-postappen öppnas först efter ditt godkännande. När Thunderbird är standardapp i Windows bifogas PDF:en automatiskt; annars bifogas den manuellt. Inget mejl skickas automatiskt.',level=level,invoice_no=r['invoice_no'],fee=money(fee,r['currency']),locked=_(' (låst)') if locked else '',interest=setting('interest'),template=template_name,logo=logo_name)
            if ledger_fallback_used and level=='P1':
                confirmation+='\n\n'+_('Underlag: reskontraimporten. Original-PDF-kontrollen har kringgåtts efter ditt godkännande.')
            if not messagebox.askyesno(_('Bekräfta påminnelse'),confirmation):
                break
            day=date.today().isoformat()
            snapshot=capture_reminder_snapshot(r,fee,day,level)
            with connect() as db:
                if level=='P1':db.execute('UPDATE invoices SET p1_date=?,p1_snapshot=?,sent_count=sent_count+1 WHERE id=?',(day,snapshot,r['id']))
                else:db.execute('UPDATE invoices SET p2_date=?,p2_snapshot=?,sent_count=sent_count+1 WHERE id=?',(day,snapshot,r['id']))
            result=self.write_letter(r,level,fee,logo_path)
            if result:
                latest=(r,level,result)
                try:
                    record_reminder_journal(
                        DB_PATH,JOURNAL_PATH,r['id'],level,day,fee,current_reminder_terms(fee),
                        get_language(),Path(logo_path).name if logo_path else (r['logo_file'] or ''),Path(str(result)).name,
                    )
                    logger.info('Reminder journal updated: invoice=%s level=%s date=%s',r['id'],level,day)
                except Exception as exc:
                    # The PDF and SQLite reminder are already valid; do not undo
                    # them because the supplementary journal could not be written.
                    logger.exception('Reminder was created but JSON journal update failed')
                    messagebox.showwarning(_('JSON-journalen kunde inte uppdateras'),str(exc),parent=self)
            else:
                break
            if level=='P2':break
            with connect() as db:r=db.execute('SELECT * FROM invoices WHERE id=?',(r['id'],)).fetchone()
            stage=next_stage(r)

        self.refresh()
        if latest:
            latest_row,latest_level,latest_result=latest
            opener=getattr(self,'open_reminder_email',None)
            if opener:opener(latest_row,latest_level,latest_result)
            return latest_result
        return None

    def recreate_p1(self,row=None):
        """Recreate a missing P1 PDF without creating a new reminder event."""
        r=row or self.selected()
        if not r:return None
        if not dparse(r['p1_date']):
            messagebox.showinfo(_('P1 saknas'),_('Skapa P1 innan den kan återskapas.'),parent=self)
            return None
        confirmation=_('P1-PDF:en saknas. Skapa en ny kopia med ursprungligt P1-datum och oförändrad påminnelsehistorik?')
        if not messagebox.askyesno(_('Återskapa P1'),confirmation,parent=self):
            return None
        logo_file=r['logo_file'] if 'logo_file' in r.keys() else None
        result=self.update_p1_logo(r,logo_file,parent=self)
        if result:
            self.refresh()
            messagebox.showinfo(_('P1 återskapad'),_('P1-PDF:en har återskapats med ursprungligt P1-datum. Påminnelsehistoriken är oförändrad.'),parent=self)
        return result

    def edit_p1(self):
        self.edit_reminder('P1')

    def edit_p2(self):
        self.edit_reminder('P2')

    def edit_reminder(self,level):
        """Choose a replacement logo and regenerate an existing P1 or P2 safely."""
        if level not in ('P1','P2'):return
        r=self.selected()
        if not r:return
        if not r[level.lower()+'_date']:
            messagebox.showinfo(
                _('{level} saknas',level=level),
                _('Skapa {level} innan den kan redigeras.',level=level),parent=self,
            );return
        logo_files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        _current_logo_path,current_logo=self.invoice_logo(r)
        choices=[_('(Ingen logotyp)')]+logo_files
        w=self._new_toplevel(_('Redigera {level}',level=level));w.grab_set();w.resizable(True,True)
        form=self._dialog_form(w,padding=20)
        ttk.Label(form,text=_('Välj ny logotyp för {level}. PDF:en skrivs om med ursprungligt påminnelsedatum.',level=level),wraplength=390).pack(anchor='w',pady=(0,10))
        logo_var=tk.StringVar(value=current_logo if current_logo in logo_files else choices[0])
        combo=ttk.Combobox(form,textvariable=logo_var,state='readonly',values=choices,width=42)
        combo.pack(fill='x',pady=(0,12))
        def save():
            selected=logo_var.get()
            result=self.update_reminder_logo(r,level,selected if selected in logo_files else '',parent=w)
            if not result:return
            w.destroy();self.refresh()
            messagebox.showinfo(
                _('{level} uppdaterad',level=level),
                _('{level} har skrivits om med vald logotyp. Påminnelsedatum och historik är oförändrade.',level=level),parent=self,
            )
        buttons=ttk.Frame(form);buttons.pack(fill='x')
        ttk.Button(buttons,text=_('Spara och skriv om {level}',level=level),command=save,style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Stäng'),command=w.destroy).pack(side='right')
        w.wait_window()

    def update_p1_logo(self,row,logo_file,parent=None):
        return self.update_reminder_logo(row,'P1',logo_file,parent=parent)

    def update_p2_logo(self,row,logo_file,parent=None):
        return self.update_reminder_logo(row,'P2',logo_file,parent=parent)

    def update_reminder_logo(self,row,level,logo_file,parent=None):
        """Regenerate P1/P2 without changing original content, date or history."""
        if level not in ('P1','P2'):return None
        date_column=level.lower()+'_date';snapshot_column=level.lower()+'_snapshot'
        original_date=dparse(row[date_column])
        if not original_date:return None
        snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
        updated=dict(row)
        reminder_terms=current_reminder_terms(float(setting('fee') or 0))
        snapshot_language=''
        if snapshot:
            updated.update(snapshot['row'])
            reminder_terms=snapshot['terms']
            snapshot_language=str(snapshot.get('language') or '')
        updated['id']=row['id'];updated['logo_file']=logo_file
        fee_value=reminder_terms.get('fee')
        fee=float(setting('fee') or 0) if fee_value is None else float(fee_value or 0)
        logo_path,_logo_name=self.invoice_logo(updated)
        output_path=next((path for path in reminder_file_candidates(row,level) if path.is_file()),None)
        previous_language=get_language()
        if snapshot_language in SUPPORTED_LANGUAGES and snapshot_language!=previous_language:
            set_language(snapshot_language)
        try:
            result=self.write_letter(
                updated,level,fee,logo_path,
                reminder_date=original_date,output_path=output_path,parent=parent,
                reminder_terms=reminder_terms,
            )
        finally:
            if get_language()!=previous_language:set_language(previous_language)
        if not result:return None
        with connect() as db:
            if snapshot:
                db.execute('UPDATE invoices SET logo_file=? WHERE id=?',(logo_file,row['id']))
            else:
                # Older reminders have no snapshot. Freeze the values used for
                # this successful regeneration before any later edit.
                snapshot_text=capture_reminder_snapshot(updated,fee,original_date.isoformat(),level)
                db.execute(f'UPDATE invoices SET logo_file=?,{snapshot_column}=? WHERE id=?',(logo_file,snapshot_text,row['id']))
        try:
            export_reminder_journal(DB_PATH,JOURNAL_PATH)
        except Exception as exc:
            logger.exception('%s logo was updated but JSON journal refresh failed',level)
            dialog_options={'parent':parent} if parent is not None else {}
            messagebox.showwarning(_('JSON-journalen kunde inte uppdateras'),str(exc),**dialog_options)
        logger.info('%s regenerated with a replacement logo: id=%s path=%s',level,row['id'],result)
        return result

    def write_letter(self,r,level,fee,logo_path='',reminder_date=None,output_path=None,parent=None,reminder_terms=None):
        today=reminder_date or date.today();remaining=max(0,float(r['amount'] or 0)-float(r['paid'] or 0))
        effective_terms=reminder_terms or current_reminder_terms(fee)
        p1_fee=fee; p2_fee=fee if level=='P2' else 0; total=remaining+p1_fee+p2_fee
        deadline_date=today+timedelta(days=int(effective_terms.get('payment_deadline_days') or 5))
        deadline=format_long_date(deadline_date)
        p2_warning=_('Ansökan om betalningsföreläggande lämnas in till Kronofogden om betalning inte kommit oss tillhanda senast den {deadline}. Kostnader för att driva ärendet kan tillkomma till dess full betalning har skett.',deadline=deadline) if level=='P2' else ''
        logger.info('Reminder generated: level=%s',level)
        pdf_out=Path(output_path) if output_path else reminder_file_path(r,level,today)
        temporary_pdf=None;dialog_options={'parent':parent} if parent is not None else {}
        try:
            descriptor,temporary_name=tempfile.mkstemp(prefix='.paypamin-reminder-',suffix='.pdf',dir=EXPORT_DIR)
            os.close(descriptor);temporary_pdf=Path(temporary_name)
            if reminder_terms is None:self.write_pdf(temporary_pdf,r,level,fee,today,remaining,total,p2_warning,logo_path)
            else:self.write_pdf(temporary_pdf,r,level,fee,today,remaining,total,p2_warning,logo_path,effective_terms)
            os.replace(temporary_pdf,pdf_out)
            logger.info('Reminder PDF created: path=%s',pdf_out)
            try:
                open_path(pdf_out)
                logger.info('Opened generated PDF in default viewer')
            except Exception as open_exc:
                logger.exception('Could not automatically open generated PDF')
                messagebox.showwarning(_('PDF skapad'),_('PDF:en sparades men kunde inte öppnas automatiskt.\n{path}\n\n{error}',path=pdf_out,error=open_exc),**dialog_options)
            return pdf_out
        except LogoEmbedError as exc:
            logger.exception('Reminder logo could not be embedded: invoice=%s',r['invoice_no'])
            messagebox.showerror(_('Logotypen kunde inte användas'),str(exc),**dialog_options)
            return None
        except ImportError:
            logger.exception('PDF generation dependency missing')
            messagebox.showerror(_('PDF-tillägg saknas'),_('Kunde inte skapa PDF eftersom ett PDF-tillägg saknas. Öppna felloggen eller starta om appen med internetanslutning.'),**dialog_options)
            return None
        except Exception as exc:
            logger.exception('Reminder PDF generation failed: invoice=%s',r['invoice_no'])
            messagebox.showerror(_('PDF kunde inte skapas'),_('Ett fel loggades. Öppna felloggen för detaljer.\n\n{error}',error=exc),**dialog_options)
            return None
        finally:
            if temporary_pdf is not None:
                try:temporary_pdf.unlink()
                except FileNotFoundError:pass
                except OSError:logger.warning('Temporary reminder PDF could not be removed: %s',temporary_pdf)

    def write_pdf(self,path,r,level,fee,today,remaining,total,p2_warning,logo_path='',reminder_terms=None):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Flowable
        from xml.sax.saxutils import escape
        effective_terms=reminder_terms or current_reminder_terms(fee)
        currency=normalize_currency(r['currency'])
        styles=getSampleStyleSheet()
        styles.add(ParagraphStyle(name='LetterTitle',parent=styles['Heading1'],fontName='Times-Bold',fontSize=17,leading=21,textColor=colors.HexColor('#202020'),spaceBefore=9,spaceAfter=8))
        styles.add(ParagraphStyle(name='SmallText',parent=styles['BodyText'],fontName='Helvetica',fontSize=8.5,leading=12,spaceAfter=5))
        styles.add(ParagraphStyle(name='RightSmall',parent=styles['SmallText'],alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='AlertText',parent=styles['SmallText'],fontName='Helvetica-Bold',fontSize=9.2,leading=13,borderColor=colors.HexColor('#777777'),borderWidth=.6,borderPadding=8,spaceBefore=8,spaceAfter=10))
        doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=22*mm,leftMargin=22*mm,topMargin=18*mm,bottomMargin=18*mm,title=_('Betalningspåminnelse {level} {invoice_no}',level=level,invoice_no=r['invoice_no']),author='Tadega AB',creator=f'{APP_NAME} – {APP_AUTHOR}')
        story=[]
        brand=Paragraph('<font name="Times-BoldItalic" size="22">Tadega AB</font>',styles['BodyText'])
        logo_path=Path(logo_path) if logo_path else None
        if logo_path:
            drawing=load_svg_drawing(logo_path)
            from reportlab.graphics import renderPDF
            class LogoFlowable(Flowable):
                def __init__(self,drawing,maxw,maxh):
                    Flowable.__init__(self);self.drawing=drawing;self.width=maxw;self.height=maxh;self.scale=min(maxw/drawing.width,maxh/drawing.height)
                def draw(self):
                    try:
                        self.canv.saveState();self.canv.scale(self.scale,self.scale);renderPDF.draw(self.drawing,self.canv,0,0)
                    except Exception as exc:
                        try:self.canv.restoreState()
                        except Exception:pass
                        raise LogoEmbedError(_('SVG-logotypen kunde inte bäddas in: {path}\n{error}',path=logo_path,error=exc)) from exc
                    self.canv.restoreState()
            brand=LogoFlowable(drawing,70*mm,28*mm)
        n=1 if level=='P1' else 2
        meta_lines=['Tadega AB',f"{_('Påminnelsedatum')}: {today.isoformat()}",_('Påminnelse nummer {number}',number=n),f"{_('Fakturanummer')}: {escape(str(r['invoice_no']))}",f"{_('Fakturadatum')}: {escape(str(r['invoice_date'] or ''))}",f"{_('Förfallodatum')}: {escape(str(r['due_date']))}",f"{_('Valuta')}: {currency}"]
        meta=Paragraph('<br/>'.join(meta_lines),styles['RightSmall'])
        hdr=Table([[brand,meta]],colWidths=[85*mm,81*mm]);hdr.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.7,colors.HexColor('#777777')),('BOTTOMPADDING',(0,0),(-1,-1),9)]));story += [hdr,Spacer(1,9*mm)]
        story.append(Paragraph(f'<b>{escape(str(r["customer"]))}</b>',styles['SmallText']))
        story.append(Paragraph(_('Betalningspåminnelse nummer {number}',number=n),styles['LetterTitle']))
        story.append(Paragraph(_('Vi saknar fortfarande betalning för nedanstående faktura. Om betalning redan har gjorts, vänligen bortse från denna påminnelse.'),styles['SmallText']))
        deadline_date=today+timedelta(days=int(effective_terms.get('payment_deadline_days') or 5))
        deadline_text=format_long_date(deadline_date)
        story.append(Paragraph(f"<b>{escape(_('Betalning ska vara oss tillhanda senast {date}.',date=deadline_text))}</b>",styles['SmallText']))
        if level=='P2': story.append(Paragraph(escape(p2_warning),styles['AlertText']))
        note=str(r['note'] or '').strip()
        if note:
            story.append(Paragraph(f"<b>{_('Avser:')}</b> "+escape(note),styles['SmallText']))
        rows=[[Paragraph(f"<b>{_('Specifikation')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Belopp')}</b>",styles['RightSmall'])],
              [Paragraph(_('Faktura {invoice_no} – obetalt belopp',invoice_no=escape(str(r['invoice_no']))),styles['SmallText']),Paragraph(money(remaining,currency),styles['RightSmall'])],
              [Paragraph(_('Påminnelseavgift (påminnelse 1)'),styles['SmallText']),Paragraph(money(fee,currency),styles['RightSmall'])]]
        if level=='P2':rows.append([Paragraph(_('Påminnelseavgift (påminnelse 2)'),styles['SmallText']),Paragraph(money(fee,currency),styles['RightSmall'])])
        rows.append([Paragraph(f"<b>{_('ATT BETALA')}</b>",styles['SmallText']),Paragraph(f'<b>{money(total,currency)}</b>',styles['RightSmall'])])
        tab=Table(rows,colWidths=[112*mm,54*mm]);tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#444444')),('LINEBELOW',(0,1),(-1,-2),.3,colors.HexColor('#cccccc')),('LINEABOVE',(0,-1),(-1,-1),.8,colors.HexColor('#444444')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [Spacer(1,4*mm),tab,Spacer(1,4*mm)]
        hist=[[Paragraph(f"<b>{_('Påminnelse')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Datum')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Avgift')}</b>",styles['RightSmall'])],
              [Paragraph(_('Påminnelse 1'),styles['SmallText']),Paragraph(escape(str(r['p1_date'] or today.isoformat())),styles['SmallText']),Paragraph(money(fee,currency),styles['RightSmall'])]]
        if level=='P2':hist.append([Paragraph(_('Påminnelse 2 (denna)'),styles['SmallText']),Paragraph(today.isoformat(),styles['SmallText']),Paragraph(money(fee,currency),styles['RightSmall'])])
        ht=Table(hist,colWidths=[78*mm,54*mm,34*mm]);ht.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#aaaaaa')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f1f1f1')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),2)]));story += [ht,Spacer(1,3*mm)]
        story.append(Paragraph(_('Ovanstående påminnelser har skickats för fakturan och samtliga avgifter ingår i beloppet ovan.'),styles['SmallText']))
        payment_text=f"<b>{_('Betalning')}</b><br/>Bankgiro: 5660-4200 · Swish: 123 188 42 87<br/>{_('Betalningsmottagare')}: Tadega AB. {_('Ange fakturanumret vid betalning.')}<br/>IBAN: SE26 6000 0000 0005 3862 3322 · BIC: HANDSESS"
        story.append(Paragraph(payment_text,styles['SmallText']))
        terms=_('Varan förblir vår egendom tills full betalning erlagts. Eventuella anmärkningar på fakturan ska göras inom {days} dagar. Avgift per påminnelse: {fee}. Försenad betalning debiteras {interest} % ränta. Vid beställning av specialdelar lämnas ingen returrätt.',days=escape(str(effective_terms.get('objection_days') or '')),fee=money(fee,currency),interest=escape(str(effective_terms.get('interest') or '')))
        story += [Spacer(1,2*mm),HRFlowable(width='100%',thickness=.4,color=colors.HexColor('#999999')),Spacer(1,2*mm),Paragraph(terms,styles['SmallText'])]
        doc.build(story)
    def settings(self):
        w=self._new_toplevel(_('Inställningar'));w.grab_set();w.resizable(True,True);form=self._dialog_form(w,padding=20)
        language_var=tk.StringVar(value=SUPPORTED_LANGUAGES[get_language()])
        ttk.Label(form,text=_('Språk')).grid(row=0,column=0,sticky='w',padx=(0,14),pady=6)
        ttk.Combobox(form,textvariable=language_var,state='readonly',values=list(SUPPORTED_LANGUAGES.values()),width=15).grid(row=0,column=1,sticky='w',pady=6)
        fields=[('Dagar efter förfallodatum till P1','p1_days'),('Dagar efter P1 till P2','p2_days'),('Dagar efter P2 till Kronofogden-granskning','p3_days'),('Påminnelseavgift per påminnelse (fakturans valuta)','fee'),('Dröjsmålsränta per år (%)','interest'),('Anmärkningstid enligt fakturavillkor (dagar)','objection_days'),('Betalningsfrist på påminnelsen (dagar)','payment_deadline_days')]
        entries={}
        for i,(label,key) in enumerate(fields,start=1):
            ttk.Label(form,text=_(label)).grid(row=i,column=0,sticky='w',padx=(0,14),pady=6);e=ttk.Entry(form,width=16);e.grid(row=i,column=1,pady=6);e.insert(0,setting(key));entries[key]=e
            if key=='fee' and setting('fee_locked')=='1':e.configure(state='disabled')
        autostart_var=tk.BooleanVar(value=setting('autostart')=='1')
        ttk.Checkbutton(form,text=_('Starta {app_name} automatiskt när jag loggar in',app_name=APP_NAME),variable=autostart_var).grid(row=len(fields)+2,column=0,columnspan=3,sticky='w',pady=(10,3))
        ttk.Label(form,text=_('Autostart för din användare · {platforms}',platforms=SUPPORTED_PLATFORMS),style='Sub.TLabel').grid(row=len(fields)+3,column=0,columnspan=3,sticky='w')
        automatic_updates_var=tk.BooleanVar(value=setting('update_auto')=='1')
        ttk.Checkbutton(form,text=_('Sök efter och installera uppdateringar automatiskt två gånger per dygn'),variable=automatic_updates_var).grid(row=len(fields)+4,column=0,columnspan=3,sticky='w',pady=(10,3))
        locked=tk.BooleanVar(value=setting('fee_locked')=='1')
        def toggle_lock():
            entries['fee'].configure(state='disabled' if locked.get() else 'normal')
        ttk.Checkbutton(form,text=_('Lås påminnelseavgiften (förhindra oavsiktlig ändring)'),variable=locked,command=toggle_lock).grid(row=len(fields)+5,column=0,columnspan=3,sticky='w',pady=(10,4))
        ttk.Label(form,text=_('Låset skyddar inställningen i appen; lås upp här för att ändra avgiften.'),style='Sub.TLabel').grid(row=len(fields)+6,column=0,columnspan=3,sticky='w')
        ttk.Label(form,text=_('Obs: påminnelseavgiften använder fakturans valuta. Kontrollera att avgift, ränta och villkor gäller för era kunder.'),style='Sub.TLabel').grid(row=len(fields)+7,column=0,columnspan=3,sticky='w',pady=(8,0))
        automatic_import_var=tk.BooleanVar(value=setting('auto_import')=='1')
        ttk.Checkbutton(form,text=_('Bevaka importmappen och importera nya PDF:er automatiskt'),variable=automatic_import_var).grid(row=len(fields)+8,column=0,columnspan=3,sticky='w',pady=(10,3))
        ledger_reminder_var=tk.BooleanVar(value=setting('ledger_friday_reminder')=='1')
        ttk.Checkbutton(form,text=_('Påminn om att importera kundreskontralista varje fredag'),variable=ledger_reminder_var).grid(row=len(fields)+9,column=0,columnspan=3,sticky='w',pady=(10,3))
        automatic_cache_var=tk.BooleanVar(value=setting('cache_auto')=='1')
        ttk.Checkbutton(form,text=_('Rensa appcache automatiskt en gång per dygn samt vid avslut'),variable=automatic_cache_var).grid(row=len(fields)+10,column=0,columnspan=3,sticky='w',pady=(10,3))
        ttk.Label(form,text=_('Under dagen endast cache äldre än 24 timmar; vid avslut all identifierad appcache.\nFakturor och importmappen rörs inte.'),style='Sub.TLabel').grid(row=len(fields)+11,column=0,columnspan=3,sticky='w')
        self._font_scale_var=tk.StringVar(value=font_scale_label(self.ui_font_scale))
        ttk.Label(form,text=_('Textstorlek')).grid(row=len(fields)+12,column=0,sticky='w',padx=(0,14),pady=(12,3))
        font_scale_combo=ttk.Combobox(form,textvariable=self._font_scale_var,state='readonly',values=[font_scale_label(choice) for choice in FONT_SCALE_CHOICES],width=15)
        font_scale_combo.grid(row=len(fields)+12,column=1,sticky='w',pady=(12,3))
        ttk.Label(form,text=_('Textstorleken kan också ändras med Ctrl/Cmd +, Ctrl/Cmd − och Ctrl/Cmd 0.'),style='Sub.TLabel').grid(row=len(fields)+13,column=0,columnspan=3,sticky='w')
        ttk.Label(form,text=_('Högkontrast följer systemets inställning och uppdateras automatiskt.'),style='Sub.TLabel').grid(row=len(fields)+14,column=0,columnspan=3,sticky='w',pady=(8,0))
        def save():
            try:
                for k,e in entries.items():
                    v=e.get().strip()
                    if k in ('p1_days','p2_days','p3_days','objection_days','payment_deadline_days') and int(v)<0:raise ValueError()
                    if k in ('fee','interest') and float(v.replace(',','.'))<0:raise ValueError()
            except (ValueError,TypeError):
                messagebox.showerror(_('Ogiltigt värde'),_('Ange positiva siffror i inställningarna.'),parent=w);return
            try:
                set_autostart(autostart_var.get())
            except AutostartError as exc:
                messagebox.showerror(_('Autostart kunde inte sparas'),_('{error}\n\nPlats: {location}',error=_(str(exc)),location=autostart_location()),parent=w);return
            for k,e in entries.items():set_setting(k,e.get().strip().replace(',','.'))
            new_language=language_code(language_var.get())
            language_changed=new_language!=get_language()
            set_setting('fee_locked','1' if locked.get() else '0')
            set_setting('autostart','1' if autostart_var.get() else '0')
            set_setting('update_auto','1' if automatic_updates_var.get() else '0')
            set_setting('auto_import','1' if automatic_import_var.get() else '0')
            set_setting('ledger_friday_reminder','1' if ledger_reminder_var.get() else '0')
            set_setting('cache_auto','1' if automatic_cache_var.get() else '0')
            set_setting('language',new_language)
            new_font_scale=normalize_font_scale(self._font_scale_var.get())
            set_setting(FONT_SCALE_SETTING,font_scale_storage(new_font_scale))
            self.set_font_scale(new_font_scale,persist=False)
            set_language(new_language)
            refresh_json_journal(parent=w)
            logger.info('Settings saved; fee_locked=%s autostart=%s automatic_updates=%s automatic_import=%s ledger_friday=%s cache_auto=%s language=%s',bool(locked.get()),bool(autostart_var.get()),bool(automatic_updates_var.get()),bool(automatic_import_var.get()),bool(ledger_reminder_var.get()),bool(automatic_cache_var.get()),new_language)
            w.destroy()
            if language_changed:self.rebuild_ui()
            else:self.refresh()
        ttk.Button(form,text=_('Spara inställningar'),command=save,style='Accent.TButton').grid(row=len(fields)+15,column=1,sticky='e',pady=(15,0))

def main():
    try:
        configure_console_free_subprocesses()
        configure_windows_app_identity()
        init_db()
        logger.info('%s %s started on %s',APP_NAME,APP_VERSION,sys.platform)
        log_activity('application','started','completed',version=APP_VERSION,platform=sys.platform,commit=APP_RELEASE_COMMIT)
        try:
            report=_refresh_and_archive_logs()
            logger.info('Consolidated error log refreshed: errors=%d sources=%d',report.error_count,report.source_count)
        except Exception:logger.exception('Consolidated error log refresh failed')
        window=ReminderApp()
        after_idle=getattr(window,'after_idle',None)
        if after_idle is not None:after_idle(mark_update_ready)
        else:mark_update_ready()
        if MINIMIZED_START_ARG in sys.argv[1:]:
            window.hide_to_tray()
            if getattr(window,'_quitting',False):return
        window.mainloop()
    except Exception as e:
        if not isinstance(e,getattr(tk,'TclError',())):
            # The shared GUI launcher turns this into a visible error and startup.log.
            # Keep direct python paypamin_flow.py useful for terminal diagnostics too.
            logger.exception('Application could not start')
            raise
        logger.exception('Application UI could not start')
        try:messagebox.showerror(APP_NAME,_('Appen kunde inte starta. Kontrollera att Python installerats med Tkinter.\n\n{error}',error=e))
        except Exception:print(f'{APP_NAME}: {e}',file=sys.stderr)


if __name__=='__main__':
    main()
