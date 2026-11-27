#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PayPamin Flow – lokal fakturapåminnelseapp för Windows, macOS och Linux.
Kräver Python 3.10+. PDF-textavläsning: pip install pymupdf.
OCR för skannade PDF: se README.

Copyright © 2026 Rickard Längkvist. Skapare: Rickard Längkvist.
"""
from __future__ import annotations
import os, re, sqlite3, sys, webbrowser, subprocess, threading, queue, importlib.util, logging, statistics, base64, hashlib, tempfile, json, time, platform
from logging.handlers import RotatingFileHandler
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog

from app_info import APP_AUTHOR, APP_COPYRIGHT, APP_ID, APP_NAME, APP_SLUG, APP_VERSION, SUPPORTED_PLATFORMS
from activity_log import ACTIVITY_LOG_NAME, ACTIVITY_LOGGER_NAME, instrument_tk_command, log_activity
from build_info import APP_RELEASE_COMMIT, APP_RELEASE_ID
from app_backup import (
    BackupError,
    BackupPaths,
    create_backup as create_local_backup,
    restore_backup as restore_local_backup,
    suggested_backup_filename,
)
from autostart import AutostartError, autostart_location, set_autostart
from cache_cleaner import clean_cache
import donations
import qr_code
from tray import TrayController, TrayUnavailable
from currency import find_currency_code, is_valid_currency, normalize_currency
from fee_rules import (
    AGREEMENT_CONTRACT, AGREEMENT_INVOICE, AGREEMENT_NONE, AGREEMENT_OFFER,
    CUSTOMER_AUTHORITY, CUSTOMER_BUSINESS,
    CUSTOMER_PRIVATE, CUSTOMER_TYPES, DEFAULT_FEE_MODEL, FEE_MODELS,
    FEE_MODEL_PER_REMINDER, FEE_MODEL_STATUTORY, LATE_PAYMENT_COMPENSATION,
    PER_REMINDER_FEE, REMINDER_FEE_CAP,
    assess_fee, chargeable_fee, fee_for_model, fee_kind, fee_label_key, is_business,
    legal_basis_key, normalize_agreement, normalize_customer_type,
    normalize_fee_model,
)
from console_free import configure_console_free_subprocesses, hide_own_console_window
from error_log import (
    ERROR_LOG_NAME,
    list_unresolved_errors,
    refresh_error_log,
    resolve_errors,
    resolve_selected_errors,
)
from log_archive import RETENTION_DAYS, DailySizeRotatingFileHandler, archive_old_logs
from bankdays import (
    adjusted_deadline_date,
    is_swedish_banking_day,
    next_swedish_banking_day,
    non_banking_reason,
)
from customer_contacts import (
    EmailAddressError, ensure_customer_contact_schema, get_customer_contact,
    get_customer_language, normalize_customer_language,
    normalize_email_addresses, parse_email_addresses, save_customer_contact,
)
from i18n import (
    SUPPORTED_LANGUAGES, _, format_long_date, format_money,
    get_language, language_code, language_override, set_language,
)
import appearance
import invoice_export
import invoice_trash
from invoice_parser import (
    clean_customer_zone_text, clean_invoice_note, clean_payment_terms_zone,
    extract_invoice_sections, normalize_date, parse_amount_value,
    parse_invoice_text, parse_payment_terms_days,
)
from import_watcher import (
    ImportFolderMonitor, archive_import_pdf, can_split_pdf_pages,
    extract_section_pdf_to_import, is_archived_import_pdf, iter_import_pdfs,
    restore_archived_import_pdf,
)
import learning
import ledger_export
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
    CONTENT_CURRENT,
    CONTENT_STALE,
    CONTENT_UNAVAILABLE,
    UPDATE_CHECK_INTERVAL_MS,
    UpdateCheckError,
    fetch_latest_release,
    is_update_available,
    missing_release_assets,
    update_change_kind,
)
from update_installer import (
    UPDATE_READY_FILE_ENV,
    UPDATE_READY_TOKEN_ENV,
    UpdateInstallError,
    cleanup_completed_update_backups,
    cleanup_update,
    evaluate_release,
    install_update,
    mark_update_ready,
    restart_updated_app,
    rollback_update,
    stage_update,
    wait_for_update_restart,
)
import update_state
from single_instance import SingleInstance
from python_maintenance import (
    addon_package_specs,
    install_python_addons,
    missing_addon_package_specs,
)
from accessibility import (
    AccessibleStyle,
    FONT_SCALE_CHOICES,
    FONT_SCALE_SETTING,
    SYSTEM_CONTRAST_POLL_INTERVAL_MS,
    ResponsiveGrid,
    ScrollableForm,
    apply_widget_contrast,
    choose_font_family,
    contrast_palette,
    fit_window_to_screen,
    focus_first,
    font_scale_label,
    font_scale_storage,
    monitor_work_area,
    normalize_font_scale,
    prepare_focus_tree,
    stepped_font_scale,
    system_high_contrast,
)
from quiet_faults import log_summary, report_fault

IMPORT_WATCH_INTERVAL_MS = 3000
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
PRINT_DIR = ICON_DIR / "print"


def tray_icon_path(platform_name=None):
    """Return the tray bitmap that matches the platform's icon size.

    Windows draws a 16-32 px tray icon and scales whatever image it is given;
    handing it the 256 px detailed mark produced a blurred, muddy result. The
    simplified master at 32 px lands on the real tray sizes, and macOS/Linux
    menu bars are happiest with the 48 px variant.
    """
    platform_name = platform_name or sys.platform
    name = 'paypamin_flow_32.png' if platform_name.startswith('win') else 'paypamin_flow_48.png'
    candidate = ICON_DIR / name
    return candidate if candidate.is_file() else ICON_DIR / 'paypamin_flow_256.png'


LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True,exist_ok=True)


# Legacy startup/update side logs are merged into app.log on first start.
_LEGACY_SIDE_LOG=re.compile(r'^(?:legacy-(?:\d+-)?)?(?:startup|update)\.log(?:\.\d+)?$')


def _relocate_legacy_logs():
    """Move only known app logs into their own folder without overwriting."""
    moved=[];errors=[]
    try:candidates=sorted(APP_DIR.iterdir())
    except OSError:return moved,['.']
    for source in candidates:
        name=source.name
        known=name in {'app.log','activity.log','errors.log','startup.log','update.log'} or re.fullmatch(r'(?:app|activity|startup|update)\.log\.\d+',name)
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
ACTIVITY_LOG_PATH = LOG_DIR / ACTIVITY_LOG_NAME
ERROR_LOG_PATH = LOG_DIR / ERROR_LOG_NAME
# A running day writes exactly these three files.
DAILY_LOG_NAMES = (LOG_PATH.name, ACTIVITY_LOG_PATH.name, ERROR_LOG_PATH.name)
logger = logging.getLogger(APP_SLUG)
logger.setLevel(logging.INFO)
activity_logger = logging.getLogger(ACTIVITY_LOGGER_NAME)
activity_logger.setLevel(logging.INFO)
# Activity records are a child of the application logger, so both files are
# owned by the same logger. That keeps one place to close on exit, and an
# activity event never duplicates into app.log because each handler filters on
# the record name.
activity_logger.propagate = True
_LOG_FORMAT = logging.Formatter('%(asctime)s %(levelname)s %(message)s')


class _ActivityRecordFilter(logging.Filter):
    """Send activity records to activity.log and technical records to app.log."""

    def __init__(self, activity):
        super().__init__()
        self.activity = activity

    def filter(self, record):
        is_activity = record.name == ACTIVITY_LOGGER_NAME
        return is_activity if self.activity else not is_activity


if not logger.handlers:
    log_handler=DailySizeRotatingFileHandler(LOG_PATH,maxBytes=5_000_000,backupCount=5,encoding='utf-8',delay=True)
    log_handler.setFormatter(_LOG_FORMAT)
    log_handler.addFilter(_ActivityRecordFilter(activity=False))
    logger.addHandler(log_handler)
    activity_handler=DailySizeRotatingFileHandler(ACTIVITY_LOG_PATH,maxBytes=5_000_000,backupCount=5,encoding='utf-8',delay=True)
    activity_handler.setFormatter(_LOG_FORMAT)
    activity_handler.addFilter(_ActivityRecordFilter(activity=True))
    logger.addHandler(activity_handler)


def _merge_legacy_side_logs():
    """Fold startup.log and update.log into app.log so one day has three files.

    The content is appended verbatim behind a comment header before the side
    log is removed, so every historical record stays readable in app.log and
    expires together with the rest of the archive.
    """
    merged=[]
    try:candidates=sorted(LOG_DIR.iterdir())
    except OSError:return merged
    for source in candidates:
        if source.is_symlink() or not source.is_file() or not _LEGACY_SIDE_LOG.fullmatch(source.name):continue
        try:
            content=source.read_text(encoding='utf-8',errors='replace').strip()
            if content:
                with LOG_PATH.open('a',encoding='utf-8') as handle:
                    handle.write(f'\n# Merged from {source.name}\n{content}\n')
            merged.append((source.name,source))
        except OSError:continue
    return merged


_legacy_side_logs=_merge_legacy_side_logs()
for _source_name,_destination_name in _legacy_log_moves:
    logger.info('Legacy log moved into logs folder: %s -> %s',_source_name,_destination_name)
for _source_name in _legacy_log_errors:
    logger.warning('Legacy log could not be moved into logs folder: %s',_source_name)
for _source_name,_source_path in _legacy_side_logs:
    logger.info('Legacy side log merged into app.log: %s',_source_name)
    try:_source_path.unlink()
    except OSError:logger.warning('Legacy side log could not be removed after merge: %s',_source_name)


def _archive_previous_day_logs():
    """Roll idle logs at midnight, then archive and prune earlier days."""
    for handler in logger.handlers:
        if isinstance(handler,DailySizeRotatingFileHandler):
            handler.rollover_for_new_day()
    return archive_old_logs(LOG_DIR,retention_days=RETENTION_DAYS)


def _refresh_and_archive_logs():
    """Capture unresolved errors, then archive yesterday and prune old days."""
    # Faults that were swallowed by a handler are written as they happen; this
    # adds the tally, so a site that fails on every repaint shows up as one
    # line with a count instead of a hundred identical warnings.
    log_summary(logger)
    report=refresh_error_log(LOG_DIR)
    archive=_archive_previous_day_logs()
    if archive.changed:
        log=logger.warning if archive.errors or archive.pruned_errors else logger.info
        log('Log maintenance: archived=%d collisions=%d pruned_days=%d retention_days=%d errors=%d',
            archive.archived,archive.collisions,archive.pruned_days,RETENTION_DAYS,
            archive.errors+archive.pruned_errors)
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


def ui_is_alive(window):
    """True while a window still exists and the application is not closing.

    Tk raises TclError for every widget that has already been destroyed, so
    long background work has to ask this before touching the UI. A plain
    object without ``winfo_exists`` counts as alive, which keeps the pure
    logic testable without a display.
    """
    if getattr(window,'_quitting',False):return False
    exists=getattr(window,'winfo_exists',None)
    if exists is None:return True
    try:return bool(exists())
    except Exception:return False


def configure_windows_dpi_awareness(ctypes_module=None):
    """Render text and artwork at native resolution on a scaled Windows display.

    A DPI-unaware process is told the screen is 96 DPI; Windows then paints the
    window at that size and bitmap-stretches the finished image to the real
    scale factor. That is what makes text, the logo and the icons look soft on
    a 125-200 % display. Declaring awareness before Tk creates its interpreter
    also makes Tk read the true DPI for ``tk scaling``. No-op elsewhere.
    """
    if not sys.platform.startswith('win'):return False
    if ctypes_module is not None:
        ctypes=ctypes_module
    else:
        try:
            import ctypes as _ctypes
            ctypes=_ctypes
        except Exception:
            logger.exception('ctypes is unavailable; Windows DPI awareness was not requested')
            return False
    # Every attempt is guarded on its own and a failure never stops the next
    # one. A single wrong argument or a missing function on an older Windows
    # used to leave the whole process DPI-unaware, and Windows then stretched
    # the finished window bitmap: text and artwork looked soft, never sharp.
    attempts=(('per-monitor v2',_dpi_awareness_per_monitor_v2),
              ('per-monitor',_dpi_awareness_per_monitor),
              ('system',_dpi_awareness_system))
    for name,attempt in attempts:
        try:
            if attempt(ctypes):
                logger.info('Windows DPI awareness enabled: %s',name)
                return True
        except Exception:
            logger.warning('Windows DPI awareness attempt failed: %s',name,exc_info=True)
    logger.warning('Windows DPI awareness could not be enabled; the window may be bitmap-stretched')
    return False


def _dpi_awareness_per_monitor_v2(ctypes):
    """DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703 and later)."""
    function=ctypes.windll.user32.SetProcessDpiAwarenessContext
    function.argtypes=[ctypes.c_void_p];function.restype=ctypes.c_bool
    return bool(function(ctypes.c_void_p(-4)))


def _dpi_awareness_per_monitor(ctypes):
    """PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1 and later)."""
    return ctypes.windll.shcore.SetProcessDpiAwareness(2)==0


def _dpi_awareness_system(ctypes):
    """System-wide DPI awareness, the last resort on very old Windows."""
    return bool(ctypes.windll.user32.SetProcessDPIAware())


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
        # and Task Manager app view read WM_SETICON from root/owner HWNDs.
        root_hwnd=int(get_ancestor(source_hwnd,2) or source_hwnd)  # GA_ROOT
        owner_hwnd=int(get_ancestor(source_hwnd,3) or root_hwnd)  # GA_ROOTOWNER
        for hwnd in dict.fromkeys((root_hwnd,owner_hwnd)):
            send_message(hwnd,0x0080,0,small)
            send_message(hwnd,0x0080,1,large)
        logger.info('Windows product icon applied: source_hwnd=%s root_hwnd=%s owner_hwnd=%s',source_hwnd,root_hwnd,owner_hwnd)
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


_settings_cache_key = None
_settings_cache_map: dict[str, str] = {}


def invalidate_settings_cache() -> None:
    """Drop the in-memory settings cache so the next read reflects SQLite."""
    global _settings_cache_key
    _settings_cache_key = None
    _settings_cache_map.clear()


def _db_settings_signature():
    try:
        st = Path(DB_PATH).stat()
        return (str(DB_PATH), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then close the SQLite handle on every with exit."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            invalidate_settings_cache()
            self.close()


def connect():
    db = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY, customer TEXT NOT NULL, invoice_no TEXT NOT NULL,
            due_date TEXT NOT NULL, invoice_date TEXT DEFAULT '', payment_terms TEXT NOT NULL DEFAULT '',
            template_vendor TEXT DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 1,
            logo_file TEXT,
            amount REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'SEK', paid REAL NOT NULL DEFAULT 0,
            paid_before_marking REAL, paid_marked_at TEXT NOT NULL DEFAULT '', paid_marked_source TEXT NOT NULL DEFAULT '',
            email TEXT DEFAULT '', source TEXT DEFAULT '', source_hash TEXT NOT NULL DEFAULT '', ignored INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '', p1_date TEXT DEFAULT '', p2_date TEXT DEFAULT '', sent_count INTEGER NOT NULL DEFAULT 0,
            reminder_message TEXT NOT NULL DEFAULT '',
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
        # One optional line from the sender on the reminder PDF. It lives on the
        # invoice so the next reminder can reuse it, and in the P1/P2 snapshot
        # so an old reminder keeps exactly the line it was sent with.
        if 'reminder_message' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN reminder_message TEXT NOT NULL DEFAULT ''")
        if 'p1_snapshot' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN p1_snapshot TEXT DEFAULT ''")
        if 'p2_snapshot' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN p2_snapshot TEXT DEFAULT ''")
        for column in ('p1_draft_date','p2_draft_date','p1_sent_date','p2_sent_date'):
            if column not in existing:db.execute(f"ALTER TABLE invoices ADD COLUMN {column} TEXT DEFAULT ''")
        # The fee depends on who the customer is (4 § vs 4 a § lag 1981:739).
        if 'customer_type' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'private'")
        if 'fee_agreement' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN fee_agreement TEXT NOT NULL DEFAULT ''")
        if 'payment_terms' not in existing:db.execute("ALTER TABLE invoices ADD COLUMN payment_terms TEXT NOT NULL DEFAULT ''")
        ensure_ledger_schema(db)
        ensure_journal_schema(db)
        invoice_trash.ensure_trash_schema(db)
        ensure_customer_contact_schema(db)
        learning.ensure_learning_schema(db)
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
        invoice_cols={row['name'] for row in db.execute('PRAGMA table_info(invoices)').fetchall()}
        if 'due_date' in invoice_cols:
            db.execute("CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date)")
        if 'invoice_no' in invoice_cols:
            db.execute("CREATE INDEX IF NOT EXISTS idx_invoices_invoice_no ON invoices(invoice_no)")
        if 'source_hash' in invoice_cols:
            db.execute("CREATE INDEX IF NOT EXISTS idx_invoices_source_hash ON invoices(source_hash)")
        if {'vendor','page_index'}.issubset(zone_cols):
            db.execute("CREATE INDEX IF NOT EXISTS idx_pdf_zones_vendor_page ON pdf_zones(lower(vendor), page_index)")
        # The fee amounts are fixed by law and deliberately absent from settings,
        # so a value stored by an older version can never change what is charged.
        defaults={'p1_days':'5','p2_days':'5','p3_days':'5','fee_agreement':'','objection_days':'5','payment_deadline_days':'5','autostart':'1','learning_enabled':'1','update_auto':'1','auto_import':'1','tray_hint_shown':'0','cache_auto':'1','cache_last_cleanup':'','ledger_friday_reminder':'1','ledger_last_friday_prompt':'','ledger_last_list_date':'','language':'sv',FONT_SCALE_SETTING:'1.0','fee_model':DEFAULT_FEE_MODEL,'invoice_column_order':''}
        for k,v in defaults.items():
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
        # Remove only these obsolete keys; nothing else in the database is
        # touched. They were editable amounts or a rate, and keeping them would
        # let a stale 150 kr or 23 % travel on in journal exports as if it still
        # meant something.
        for obsolete in ('fee','compensation','fee_locked','interest'):
            row=db.execute('SELECT value FROM settings WHERE key=?',(obsolete,)).fetchone()
            if row is not None:
                db.execute('DELETE FROM settings WHERE key=?',(obsolete,))
                logger.info('Removed obsolete setting %s=%s; the fee amounts are fixed by law',obsolete,row['value'])
        # The global export logo is gone. A logo is now chosen in the dialogue
        # that creates the reminder and stored with that invoice instead, so an
        # old default can never quietly brand a new document.
        for obsolete in ('logo_file','logo_path'):
            row=db.execute('SELECT value FROM settings WHERE key=?',(obsolete,)).fetchone()
            if row is not None:
                db.execute('DELETE FROM settings WHERE key=?',(obsolete,))
                logger.info('Removed obsolete setting %s=%s; the logo is chosen when a reminder is created',obsolete,row['value'])


def setting(key):
    global _settings_cache_key, _settings_cache_map
    signature = _db_settings_signature()
    if signature is not None and signature == _settings_cache_key:
        return _settings_cache_map.get(key, '')
    with connect() as db:
        rows = db.execute('SELECT key, value FROM settings').fetchall()
    loaded = {row['key']: row['value'] for row in rows}
    new_sig = _db_settings_signature()
    if new_sig is not None:
        _settings_cache_map = loaded
        _settings_cache_key = new_sig
    return loaded.get(key, '')


def set_setting(key,value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,str(value)))
    invalidate_settings_cache()


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


LEARNING_FIELD_LABELS={
    'email':'E-post',
    'logo_file':'Logotyp',
    'currency':'Valuta',
    'note':'Fakturatext / Avser',
    'payment_term_days':'Betalningsfrist (dagar)',
    'reminder_email':'E-post för påminnelser',
}


def learning_enabled(db=None):
    """Return whether local self-learning is on; defaults to on."""
    try:
        if db is not None:
            row=db.execute("SELECT value FROM settings WHERE key='learning_enabled'").fetchone()
            return row is None or str(row['value'])!='0'
        return setting('learning_enabled')!='0'
    except Exception:
        return True


def invoice_payment_term_days(invoice_date,due_date):
    """Return a plausible invoice-to-due interval, if both dates are valid."""
    start=dparse(invoice_date);end=dparse(due_date)
    if not start or not end:return None
    days=(end-start).days
    return days if 0<=days<=120 else None


def apply_learned_value(values,learned):
    """Apply one learned value to an invoice form, deriving banking-day due dates."""
    if learned.field=='payment_term_days':
        start=dparse(values.get('invoice_date'))
        try:days=int(learned.value)
        except (TypeError,ValueError):return values
        if start is not None:values['due_date']=next_swedish_banking_day(start+timedelta(days=days)).isoformat()
        return values
    values[learned.field]=learned.value
    return values


def learned_invoice_defaults(values):
    """Collect learned suggestions for empty invoice fields.

    The app never fills anything on its own. Returns ``(values, suggestions)``
    where ``values`` is unchanged and every suggestion needs an explicit yes
    from the user, regardless of how much evidence has accumulated.
    """
    filled=dict(values);suggestions=[]
    if not learning_enabled():return filled,suggestions
    customer=str(filled.get('customer') or '').strip()
    vendor=str(filled.get('template_vendor') or '').strip()
    try:
        with connect() as db:
            def consider(learned,field):
                if learned is None:return
                current=filled.get(field)
                empty=current is None if field=='logo_file' else not str(current or '').strip()
                if not empty:return
                suggestions.append(learned)
            # A supplier's currency says more about an invoice than the
            # customer's previous choice, so it is considered first.
            if vendor:consider(learning.recommend(db,learning.KIND_SUPPLIER,vendor,'currency'),'currency')
            if customer:
                for field in ('email','logo_file','note','currency'):
                    consider(learning.recommend(db,learning.KIND_CUSTOMER,customer,field),field)
            if vendor and not dparse(filled.get('due_date')):
                consider(learning.recommend(db,learning.KIND_SUPPLIER,vendor,'payment_term_days'),'due_date')
    except Exception:
        logger.exception('Learned invoice suggestions could not be read')
        return filled,suggestions
    if suggestions:logger.info('Learned invoice suggestions await confirmation: count=%d fields=%s',len(suggestions),','.join(item.field for item in suggestions))
    return filled,suggestions


def record_invoice_learning_db(db,values):
    """Record one saved invoice as evidence for future defaults."""
    if not learning_enabled(db):return
    customer=str(values.get('customer') or '').strip()
    vendor=str(values.get('template_vendor') or '').strip()
    if customer:
        for field in ('email','currency','note'):
            learning.record(db,learning.KIND_CUSTOMER,customer,field,values.get(field),scope_label=customer)
        logo=values.get('logo_file')
        if logo:learning.record(db,learning.KIND_CUSTOMER,customer,'logo_file',Path(str(logo)).name,scope_label=customer)
    if vendor:
        learning.record(db,learning.KIND_SUPPLIER,vendor,'currency',values.get('currency'),scope_label=vendor)
        term=invoice_payment_term_days(values.get('invoice_date'),values.get('due_date'))
        if term is not None:learning.record(db,learning.KIND_SUPPLIER,vendor,'payment_term_days',str(term),scope_label=vendor)


def record_supplier_learning(vendor,text):
    """Store the wording layout of a supplier the user has confirmed."""
    if not vendor or not learning_enabled():return False
    try:
        with connect() as db:added=learning.record_supplier_signature(db,vendor,text)
        if added:logger.info('Learned supplier invoice layout: vendor=%s',vendor)
        return added
    except Exception:
        logger.exception('Supplier invoice layout learning failed')
        return False


def learned_supplier_match(text):
    """Return a supplier suggestion from confirmed invoice layouts.

    The result is only ever prefilled in the review dialog. It never becomes a
    saved supplier choice without the user saving that reviewed invoice.
    """
    if not learning_enabled():return None
    try:
        with connect() as db:matched=learning.match_supplier_signature(db,text)
    except Exception:
        logger.exception('Learned supplier layout matching failed')
        return None
    if matched is None:return None
    # A close second supplier means the layout is ambiguous; suggest nothing.
    if matched.margin<learning.SUPPLIER_MIN_MARGIN:
        logger.warning('Learned supplier layout was ambiguous: first=%s margin=%.3f',matched.vendor,matched.margin)
        return None
    return matched.vendor,matched.similarity


def record_reminder_learning(row,recipients):
    """Remember the recipients actually used for a confirmed reminder."""
    if not recipients or not learning_enabled():return
    try:
        with connect() as db:
            learning.record(
                db,learning.KIND_CUSTOMER,row['customer'],'reminder_email',
                ', '.join(recipients),scope_label=row['customer'],
            )
    except Exception:
        logger.exception('Reminder recipient learning failed')


def reminder_email_addresses(row):
    """Prefer saved contacts, then learned reminder use, then legacy data."""
    with connect() as db:
        contact=get_customer_contact(db,row['customer'])
        email_text=contact['emails'] if contact is not None else row['email']
        addresses=parse_email_addresses(email_text)
        if addresses:return addresses
        try:learned=learning.recommend(db,learning.KIND_CUSTOMER,row['customer'],'reminder_email')
        except Exception:
            logger.exception('Learned reminder recipients could not be read')
            learned=None
    if learned is not None:
        try:return parse_email_addresses(learned.value)
        except EmailAddressError:logger.warning('Learned reminder recipients are invalid: customer=%s',row['customer'])
    return []


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
    'customer', 'invoice_date', 'due_date', 'payment_terms', 'email', 'note', 'template_vendor',
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
                str(values.get('payment_terms') or '').strip()[:80],
                values['template_vendor'],values['amount'],values['currency'],values['paid'],
                values['email'],values['source'],values.get('source_hash',''),values['note'],values['reviewed'],
                values.get('logo_file'),normalize_customer_type(values.get('customer_type')),
                normalize_agreement(values.get('fee_agreement')),
            )
            if row_id is None:
                db.execute('''INSERT INTO invoices(
                    customer,invoice_no,invoice_date,due_date,payment_terms,template_vendor,amount,currency,paid,email,
                    source,source_hash,note,reviewed,logo_file,customer_type,fee_agreement,created
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',params+(datetime.now().isoformat(timespec='seconds'),))
            else:
                db.execute('''UPDATE invoices SET customer=?,invoice_no=?,invoice_date=?,due_date=?,payment_terms=?,
                    template_vendor=?,amount=?,currency=?,paid=?,email=?,source=?,source_hash=?,note=?,reviewed=?,logo_file=?,
                    customer_type=?,fee_agreement=?
                    WHERE id=?''',params+(row_id,))
            save_customer_contact(db,values['customer'],values['email'],values.get('logo_file'))
            try:record_invoice_learning_db(db,values)
            except Exception:logger.exception('Invoice learning update failed; the invoice is still saved')
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


_BUSINESS_NAME_PATTERN=re.compile(
    r'(?i)(?:\b(?:ab|aktiebolag|hb|handelsbolag|kb|kommanditbolag|ek\.\s*för\.?|'
    r'ekonomisk\s+förening|asa|as|oy|oyj|a/s|ltd\.?|limited|gmbh|inc\.?|corp\.?|'
    r'llc|plc|b\.v\.|s\.a\.|kommun|region|myndighet|stiftelse|förening|'
    r'försäkring(?:ar|sbolag)?|glasskador|filial|bank)\b)'
)


def infer_imported_customer_type(customer,db=None):
    """Infer business vs private customer safely from saved history or company suffix."""
    name=str(customer or '').strip()
    if not name:return CUSTOMER_PRIVATE
    own_db=db is None
    conn=connect() if own_db else db
    try:
        prev=conn.execute(
            'SELECT customer_type FROM invoices WHERE lower(customer)=lower(?) ORDER BY id DESC LIMIT 1',
            (name,),
        ).fetchone()
        if prev is not None and prev['customer_type']:
            return normalize_customer_type(prev['customer_type'])
    except sqlite3.Error:
        report_fault()
    finally:
        if own_db:
            conn.close()
    if _BUSINESS_NAME_PATTERN.search(name):
        return CUSTOMER_BUSINESS
    return CUSTOMER_PRIVATE


def _sanitize_auto_emails(raw_value):
    """Keep valid comma/semicolon-separated emails without failing on OCR noise."""
    valid=[]
    for chunk in str(raw_value or '').replace(';',',').split(','):
        part=chunk.strip()
        if not part:continue
        try:
            valid.extend(parse_email_addresses(part))
        except EmailAddressError:
            report_fault()
    return ', '.join(valid)


def try_auto_save_imported_invoice(guess,source,source_hash):
    """Automatically save an imported PDF invoice when core fields are complete.

    Returns ``True`` if saved directly to SQLite without user dialogs, or
    ``False`` if any required field is missing/ambiguous and interactive review
    is needed.
    """
    if not isinstance(guess,dict):return False
    customer=str(guess.get('customer') or '').strip()
    invoice_no=str(guess.get('invoice_no') or '').strip()
    inv_date_raw=str(guess.get('invoice_date') or '').strip()
    inv_date=normalize_date(inv_date_raw) or (inv_date_raw if dparse(inv_date_raw) else '')
    payment_terms=str(guess.get('payment_terms') or '').strip()[:80]
    due_raw=normalize_date(str(guess.get('due_date') or '').strip()) or str(guess.get('due_date') or '').strip()
    if not dparse(due_raw) and inv_date and payment_terms:
        terms_days=parse_payment_terms_days(payment_terms)
        if terms_days is not None:
            due_raw=(date.fromisoformat(inv_date)+timedelta(days=terms_days)).isoformat()
    if not customer or not invoice_no or not dparse(due_raw):
        return False
    raw_amount=guess.get('amount')
    if isinstance(raw_amount,(int,float)):
        amount=float(raw_amount)
    else:
        parsed_amt=parse_amount_value(str(raw_amount or ''))
        amount=float(parsed_amt) if parsed_amt is not None else 0.0
    if amount<=0:
        return False
    currency_candidate=str(guess.get('currency') or 'SEK').strip()
    currency=normalize_currency(currency_candidate) if is_valid_currency(currency_candidate) else 'SEK'
    enriched=apply_saved_customer_contact({
        'customer':customer,
        'invoice_no':invoice_no,
        'invoice_date':inv_date,
        'due_date':due_raw,
        'payment_terms':payment_terms,
        'template_vendor':str(guess.get('template_vendor') or '').strip(),
        'amount':amount,
        'currency':currency,
        'paid':0.0,
        'email':_sanitize_auto_emails(guess.get('email','')),
        'source':source,
        'source_hash':source_hash,
        'note':clean_invoice_note(str(guess.get('note') or '')),
        'reviewed':1,
        'logo_file':guess.get('logo_file'),
        'customer_type':infer_imported_customer_type(customer),
        'fee_agreement':normalize_agreement(setting('fee_agreement')),
    })
    enriched['email']=_sanitize_auto_emails(enriched.get('email',''))
    duplicate=save_invoice_record(enriched)
    if duplicate is not None:
        return False
    try:
        export_reminder_journal(DB_PATH,JOURNAL_PATH)
    except Exception:
        logger.exception('JSON journal refresh after automatic PDF import failed')
    log_activity(
        'import','invoice_auto_imported','completed',
        invoice_no=invoice_no,customer=customer,source=Path(source).name,
    )
    logger.info('Automatically imported invoice from import folder: invoice=%s customer=%s source=%s',invoice_no,customer,source)
    return True


def enrich_ledger_invoice_from_pdf(row,guess,source,source_hash):
    """Enrich an existing ledger-imported invoice from its original invoice PDF.

    Updates customer name (correcting wrong/generic ledger customer names),
    customer_type, payment_terms, invoice text (note), invoice_date, supplier
    template, and linked PDF source/hash while preserving ledger amounts,
    payments, and P1/P2 reminder history.
    """
    if row is None or not isinstance(guess,dict):
        return False
    existing=dict(row)
    old_customer=str(existing.get('customer') or '').strip()
    pdf_customer=str(guess.get('customer') or '').strip()
    new_customer=pdf_customer or old_customer
    customer_changed=bool(pdf_customer and pdf_customer.casefold()!=old_customer.casefold())

    inv_date_raw=str(guess.get('invoice_date') or '').strip()
    pdf_inv_date=normalize_date(inv_date_raw) or (inv_date_raw if dparse(inv_date_raw) else '')
    new_inv_date=pdf_inv_date or str(existing.get('invoice_date') or '').strip()

    pdf_terms=str(guess.get('payment_terms') or '').strip()[:80]
    new_terms=pdf_terms or str(existing.get('payment_terms') or '').strip()[:80]

    new_due=str(existing.get('due_date') or '').strip()
    if not dparse(new_due):
        due_raw=normalize_date(str(guess.get('due_date') or '').strip()) or str(guess.get('due_date') or '').strip()
        if dparse(due_raw):
            new_due=due_raw
        elif new_inv_date and new_terms:
            terms_days=parse_payment_terms_days(new_terms)
            if terms_days is not None:
                new_due=(date.fromisoformat(new_inv_date)+timedelta(days=terms_days)).isoformat()

    pdf_note=clean_invoice_note(str(guess.get('note') or ''))
    new_note=pdf_note or str(existing.get('note') or '').strip()

    pdf_vendor=str(guess.get('template_vendor') or '').strip()
    new_vendor=pdf_vendor or str(existing.get('template_vendor') or '').strip()

    pdf_email=_sanitize_auto_emails(guess.get('email',''))
    if customer_changed:
        contact_probe=apply_saved_customer_contact({
            'customer':new_customer,
            'email':pdf_email,
            'logo_file':guess.get('logo_file'),
        })
        new_email=_sanitize_auto_emails(contact_probe.get('email',''))
        new_logo=contact_probe.get('logo_file') if contact_probe.get('logo_file') is not None else existing.get('logo_file')
    else:
        contact_probe=apply_saved_customer_contact({
            'customer':new_customer,
            'email':pdf_email or str(existing.get('email') or '').strip(),
            'logo_file':guess.get('logo_file') if guess.get('logo_file') is not None else existing.get('logo_file'),
        })
        new_email=_sanitize_auto_emails(contact_probe.get('email',''))
        new_logo=contact_probe.get('logo_file')

    if not str(existing.get('p1_date') or '').strip():
        if customer_changed or normalize_customer_type(existing.get('customer_type'))==CUSTOMER_PRIVATE:
            new_ctype=infer_imported_customer_type(new_customer)
        else:
            new_ctype=normalize_customer_type(existing.get('customer_type'))
    else:
        new_ctype=normalize_customer_type(existing.get('customer_type'))

    record=dict(existing)
    record.update(
        customer=new_customer,
        invoice_date=new_inv_date,
        due_date=new_due,
        payment_terms=new_terms,
        template_vendor=new_vendor,
        email=new_email,
        source=source or str(existing.get('source') or '').strip(),
        source_hash=source_hash or str(existing.get('source_hash') or '').strip(),
        note=new_note,
        reviewed=1,
        logo_file=new_logo,
        customer_type=new_ctype,
        fee_agreement=normalize_agreement(existing.get('fee_agreement')) or normalize_agreement(setting('fee_agreement')),
    )
    duplicate=save_invoice_record(record,existing['id'])
    if duplicate is not None:
        return False
    try:
        export_reminder_journal(DB_PATH,JOURNAL_PATH)
    except Exception:
        logger.exception('JSON journal refresh after ledger invoice PDF enrichment failed')
    log_activity(
        'import','ledger_invoice_enriched_from_pdf','completed',
        invoice_id=existing['id'],invoice_no=existing['invoice_no'],
        customer=new_customer,customer_changed=customer_changed,
        has_note=bool(new_note),payment_terms=new_terms,
    )
    logger.info(
        'Enriched ledger invoice from PDF: invoice=%s old_customer=%s new_customer=%s terms=%s has_note=%s file=%s',
        existing['invoice_no'],old_customer,new_customer,new_terms,bool(new_note),source,
    )
    return True


def is_ledger_paid_row(row):
    """Return True when ``row`` is fully paid and settled/tracked via the ledger."""
    if not is_fully_paid(row):
        return False
    source_kind=str(row_value(row,'paid_marked_source','') or '').strip()
    return source_kind=='ledger' or has_ledger_import_basis(row)


def archive_ledger_paid_import_pdfs(archive_date=None):
    """Archive top-level ``import/`` PDFs into ``import/YYYY/MM/`` once paid via ledger.

    Updates ``invoices.source`` in SQLite to point to the archived destination
    so opening the original PDF from history continues to work seamlessly.
    """
    archived_count=0
    try:
        IMPORT_DIR.mkdir(parents=True,exist_ok=True)
        resolved_import_dir=IMPORT_DIR.resolve()
    except OSError:
        report_fault()
        return 0
    with connect() as db:
        rows=db.execute('SELECT * FROM invoices').fetchall()
        by_source={}
        for row in rows:
            raw_source=str(row['source'] or '').strip()
            if not raw_source:continue
            try:resolved=Path(raw_source).expanduser().resolve()
            except OSError:continue
            if resolved.parent==resolved_import_dir and resolved.is_file():
                by_source.setdefault(resolved,[]).append(row)
        for source_file,linked_rows in by_source.items():
            # Keep a multi-invoice PDF in import/ until all of its invoices are paid.
            if any(not is_fully_paid(item) for item in linked_rows):
                continue
            if not any(is_ledger_paid_row(item) for item in linked_rows):
                continue
            primary=linked_rows[0]
            chosen_date=(
                archive_date
                or str(row_value(primary,'paid_marked_at','') or '')[:10]
                or str(row_value(primary,'ledger_last_seen','') or '')
                or str(row_value(primary,'due_date','') or '')
            )
            try:
                destination=archive_import_pdf(
                    source_file,IMPORT_DIR,archive_date=chosen_date,
                    invoice_no=str(primary['invoice_no'] or ''),
                )
            except OSError:
                logger.exception('Could not archive paid invoice PDF: %s',source_file)
                continue
            if destination is None:
                continue
            archived_count+=1
            new_source=str(destination)
            for item in linked_rows:
                db.execute('UPDATE invoices SET source=? WHERE id=?',(new_source,item['id']))
            logger.info('Archived ledger-paid invoice PDF: invoice=%s to=%s',primary['invoice_no'],new_source)
            log_activity('invoice','import_pdf_archived','completed',invoice_no=primary['invoice_no'],archive_path=new_source)
        # Also match unlinked top-level single-invoice PDFs in import/ whose
        # invoice number belongs to a ledger-paid row without a saved source.
        unlinked_paid={
            normalize_invoice_number(row['invoice_no']):row
            for row in rows
            if is_ledger_paid_row(row) and not str(row['source'] or '').strip()
        }
        if unlinked_paid:
            for pdf_path in iter_import_pdfs(IMPORT_DIR):
                try:candidates=read_invoice_candidates(pdf_path)
                except Exception:
                    report_fault()
                    continue
                if len(candidates)!=1:continue
                _sec,guess,candidate_hash=candidates[0]
                matched=unlinked_paid.get(normalize_invoice_number(guess.get('invoice_no','')))
                if matched is None:continue
                chosen_date=(
                    archive_date
                    or str(row_value(matched,'paid_marked_at','') or '')[:10]
                    or str(row_value(matched,'ledger_last_seen','') or '')
                    or str(row_value(matched,'due_date','') or '')
                )
                try:
                    destination=archive_import_pdf(
                        pdf_path,IMPORT_DIR,archive_date=chosen_date,
                        invoice_no=str(matched['invoice_no'] or ''),
                    )
                except OSError:
                    logger.exception('Could not archive unlinked paid invoice PDF: %s',pdf_path)
                    continue
                if destination is None:continue
                archived_count+=1
                saved_hash=str(matched['source_hash'] or '').strip() or candidate_hash
                db.execute('UPDATE invoices SET source=?,source_hash=? WHERE id=?',(str(destination),saved_hash,matched['id']))
                unlinked_paid.pop(normalize_invoice_number(matched['invoice_no']),None)
                logger.info('Linked and archived ledger-paid invoice PDF: invoice=%s to=%s',matched['invoice_no'],destination)
                log_activity('invoice','import_pdf_archived','completed',invoice_no=matched['invoice_no'],archive_path=str(destination))
    return archived_count


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


CUSTOMER_TYPE_LABELS={
    CUSTOMER_PRIVATE:'Privatperson',
    CUSTOMER_BUSINESS:'Företag',
    CUSTOMER_AUTHORITY:'Myndighet',
}

AGREEMENT_LABELS={
    AGREEMENT_NONE:'(Inget avtal)',
    AGREEMENT_CONTRACT:'I avtalet vid köpet',
    AGREEMENT_OFFER:'I offerten eller anbudet',
    AGREEMENT_INVOICE:'Endast på fakturan',
}

# The two fixed fee models. The amounts themselves are never editable; only
# which of the two fixed models applies is a choice.
FEE_MODEL_LABELS={
    FEE_MODEL_PER_REMINDER:'150 kr per påminnelse (enligt avtal)',
    FEE_MODEL_STATUTORY:'Lagstadgad avgift: 60 kr privatperson, 450 kr företag (4 §, 4 a §)',
}


def row_value(row,key,default=None):
    """Read one column from a sqlite Row, a dict or an older row without it."""
    try:value=row[key]
    except (KeyError,IndexError,TypeError):return default
    return default if value is None else value


def invoice_customer_type(row):
    """Return who the invoice is addressed to; a consumer is the safe default."""
    return normalize_customer_type(row_value(row,'customer_type',''))


def invoice_fee_agreement(row):
    """Return where the right to a reminder fee was agreed for this invoice."""
    return normalize_agreement(row_value(row,'fee_agreement','') or setting('fee_agreement'))


def invoice_currency(row):
    return normalize_currency(row_value(row,'currency','SEK'))


def current_fee_model():
    """Return the selected fee model, defaulting to the per-reminder model."""
    return normalize_fee_model(setting('fee_model') or DEFAULT_FEE_MODEL)


def fee_model_for_terms(terms):
    """Return the model a stored reminder used, inferring it for older data."""
    model=str((terms or {}).get('fee_model') or '').strip().lower()
    if model in FEE_MODELS:return normalize_fee_model(model)
    try:fee=float((terms or {}).get('fee') or 0)
    except (TypeError,ValueError):fee=0.0
    if abs(fee-PER_REMINDER_FEE)<0.005:return FEE_MODEL_PER_REMINDER
    return FEE_MODEL_STATUTORY


def reminder_fee_model_for(row,level='P1'):
    """Return the model that belongs to the fee this reminder will charge.

    P1 fixes the amount for the claim, so P2 uses the model P1 was created
    with even if the setting has changed since. A changed setting therefore
    only affects invoices without a reminder.
    """
    if level=='P2':
        snapshot=read_reminder_snapshot(row_value(row,'p1_snapshot',''))
        if snapshot:return fee_model_for_terms(snapshot.get('terms') or {})
    return current_fee_model()


def reminder_fee_for(row,model=None):
    """Return the one fixed fee this invoice is charged under the chosen model.

    ``per_reminder`` charges a flat 150 kr, the amount stated in the invoice
    terms. ``statutory`` follows 4 § and 4 a §: 60 kr to a consumer and 450 kr
    late-payment compensation to a business or authority. Both models charge
    once per claim, never once per letter.
    """
    return fee_for_model(model or current_fee_model(),invoice_customer_type(row))


def invoice_fee_assessment(row,fee=None,model=None):
    """Check this invoice's fee against the law in its own currency."""
    chosen=model or current_fee_model()
    amount=reminder_fee_for(row,chosen) if fee is None else float(fee or 0)
    return assess_fee(invoice_customer_type(row),amount,invoice_currency(row),invoice_fee_agreement(row),chosen)


def reminder_fee_note(row,model=None):
    """Return the short label explaining what the fee rests on."""
    chosen=model or current_fee_model()
    fee=reminder_fee_for(row,chosen)
    if fee<=0:return _('Ingen avgift debiteras för den här fakturan.')
    return _(legal_basis_key(invoice_customer_type(row),fee,chosen))


def fee_issue_text(issue):
    """Translate one fee rule finding for a dialogue."""
    return _(issue.key,**dict(issue.values))


def charged_fee_for(row):
    """Return the fee that was actually charged with P1, else 0."""
    snapshot=read_reminder_snapshot(row_value(row,'p1_snapshot',''))
    if snapshot:
        try:return float(snapshot['terms'].get('fee') or 0)
        except (TypeError,ValueError):return 0.0
    return reminder_fee_for(row) if row_value(row,'p1_date','') else 0.0


def reminder_fee_for_level(row,level):
    """Return the fee already fixed for this claim, or the lawful default.

    P1 fixes the amount. P2 repeats it, because the law allows one fee per
    claim; a changed setting only applies to invoices that have no P1 yet.
    """
    if level=='P2':
        snapshot=read_reminder_snapshot(row_value(row,'p1_snapshot',''))
        if snapshot:
            try:return float(snapshot['terms'].get('fee') or 0)
            except (TypeError,ValueError):report_fault()
    return reminder_fee_for(row)


CUSTOMER_LANGUAGE_CHOICES=(
    ('','Appens språk (standard)'),
    ('sv','Svenska'),
    ('en','Engelska (English)'),
)


def customer_reminder_language(row):
    """Return explicit saved customer language (``'sv'``/``'en'``) or ``''``."""
    if not row:return ''
    customer=str(row_value(row,'customer','') or '').strip()
    if not customer:return ''
    try:
        with connect() as db:return get_customer_language(db,customer)
    except sqlite3.Error:
        report_fault()
        return ''


def effective_reminder_language(row):
    """Return language for generating a customer's reminder PDF and email draft."""
    explicit=customer_reminder_language(row)
    return explicit if explicit in SUPPORTED_LANGUAGES else get_language()


def reminder_deadline_info(start_day,deadline_days,terms=None,language=None):
    """Return ``(banking_deadline, raw_deadline, skipped_reasons)`` for reminders."""
    days=int(deadline_days)
    raw=start_day+timedelta(days=days)
    if terms is not None and 'bankday_deadlines' not in terms:
        return raw,raw,()
    enabled=bool(terms.get('bankday_deadlines',True)) if terms is not None else setting('bankday_deadlines')!='0'
    if not enabled:
        return raw,raw,()
    return adjusted_deadline_date(start_day,days,language=language or get_language())


def reminder_deadline_date(start_day,deadline_days,terms=None):
    """Return the effective payment deadline adjusted to a Swedish banking day."""
    return reminder_deadline_info(start_day,deadline_days,terms=terms)[0]


def current_reminder_terms(fee,customer_type=CUSTOMER_PRIVATE,currency='SEK',agreement=AGREEMENT_NONE,model=None):
    """Capture the terms that affect a reminder PDF, not just its date."""
    customer_type=normalize_customer_type(customer_type)
    chosen=normalize_fee_model(model or setting('fee_model') or DEFAULT_FEE_MODEL)
    amount=float(fee or 0)
    return {
        'fee':amount,
        'fee_kind':fee_kind(customer_type,amount,chosen),
        'fee_model':chosen,
        'customer_type':customer_type,
        'currency':normalize_currency(currency),
        'fee_agreement':normalize_agreement(agreement),
        'objection_days':str(setting('objection_days') or ''),
        'payment_deadline_days':str(setting('payment_deadline_days') or ''),
        'bankday_deadlines':setting('bankday_deadlines')!='0',
    }


def capture_reminder_snapshot(row,fee,day,level,language=None):
    """Keep original P1/P2 content so a later logo edit changes only the logo."""
    if level not in ('P1','P2'):raise ValueError('Unknown reminder level')
    snapshot_row=dict(row)
    snapshot_row.pop('p1_snapshot',None)
    snapshot_row.pop('p2_snapshot',None)
    snapshot_row[level.lower()+'_date']=day
    chosen_language=language if language in SUPPORTED_LANGUAGES else effective_reminder_language(row)
    return json.dumps({
        'version':1,
        'row':snapshot_row,
        'terms':current_reminder_terms(
            fee,invoice_customer_type(row),invoice_currency(row),
            row_value(row,'fee_agreement','') or setting('fee_agreement'),
            reminder_fee_model_for(row,level),
        ),
        'language':chosen_language,
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


# The support dialogue tells the same story as the support page: what a gift
# pays for and why nothing is hidden behind it. The text lives in the code, so a
# translation and a test can read it and no setting can rewrite it.
DONATION_SUPPORT_POINTS = (
    ('Underhåll', 'Uppdateringar, testade flöden och rättningar som håller appen stabil.'),
    ('Nya funktioner', 'Det du saknar blir nästa version i stället för att ligga kvar på en lista.'),
    ('Oberoende', 'Ingen annonsör, ingen prenumeration och ingen som bestämmer över din data.'),
)
DONATION_TRUST_LINE = 'Gåvan är helt frivillig. Appen är lika komplett utan den, och inget låses upp av en gåva.'
# The support page's trust row, in the app's own words. Every claim is true here:
# nothing is fetched from the internet while donating, the receipt is issued by
# the payment service, and the app sends no usage data anywhere.
DONATION_TRUST_POINTS = (
    'Säker betalning hos betaltjänsten',
    'Kvitto direkt från Swish, PayPal eller Ko-fi',
    'Ingen spårning – appen skickar inga användardata',
    'Svensk utvecklare',
)


# Words in a logo file name that say nothing about the supplier. A file called
# "logo.svg" or "Logotyp 2026.svg" must never become a company name in a
# customer's subject line. A leading filler such as "Standard" is kept, because
# it may be the first word of a real company name.
LOGO_NOISE_WORDS=frozenset({
    'logo','logotyp','logotype','logga','brand','emblem','icon','ikon','symbol',
    'bild','image',
})
LOGO_FILLER_WORDS=frozenset({
    'invoice','faktura','reminder','paminnelse','påminnelse','default','standard',
    'ny','new','gammal','old',
})
GENERIC_LOGO_WORDS=LOGO_NOISE_WORDS|LOGO_FILLER_WORDS


def reminder_logo_company(logo_file):
    """Return the supplier a reminder's chosen logo belongs to.

    The logo chosen for the reminder decides the name in the subject, because
    that is what the user picked in the logo dialogue. A supplier saved for the
    file wins, since it is a name the user typed. Without one, the file name is
    used as it stands — "Limoeurope.svg" becomes "Limoeurope" — unless it is a
    word such as "logo" that names no supplier at all.
    """
    name=Path(str(logo_file or '').strip()).name
    if not name:return ''
    try:
        with connect() as db:
            rows=db.execute('SELECT vendor FROM vendor_logos WHERE logo_file=?',(name,)).fetchall()
    except sqlite3.Error:
        logger.exception('Could not resolve supplier name for reminder email subject: logo=%s',name)
        rows=[]
    companies={str(item['vendor'] or '').strip() for item in rows if str(item['vendor'] or '').strip()}
    if len(companies)==1:return next(iter(companies))
    if companies:
        logger.warning('Reminder email supplier logo is ambiguous: logo=%s matches=%d',name,len(companies))
        return ''
    words=[word for word in re.split(r'[\s._-]+',Path(name).stem) if word]
    # "Limoeurope logo 2026" is still the Limoeurope logo: drop the noise and
    # the year from the ends, never from the middle of a name.
    while len(words)>1 and (words[-1].casefold() in GENERIC_LOGO_WORDS or words[-1].isdigit()):
        words.pop()
    while len(words)>1 and words[0].casefold() in LOGO_NOISE_WORDS:words.pop(0)
    stem=' '.join(words).strip()
    if not stem or stem.casefold() in GENERIC_LOGO_WORDS:return ''
    return stem


def reminder_email_company(row):
    """Return the supplier named in the reminder's subject line.

    The logo chosen for the reminder comes first: choosing the Limoeurope logo
    is the user saying which company the reminder is sent from, even when the
    invoice's supplier template still points somewhere else. Without a logo the
    saved supplier template is used, and the customer's name is never used.
    """
    logo_company=reminder_logo_company(row.get('logo_file'))
    if logo_company:return logo_company
    return str(row.get('template_vendor') or '').strip()


# A reminder must never repeat a fee or interest clause from the invoice text.
# The stored invoice keeps its own wording (it belongs to the original invoice),
# but an old "Avgift per påminnelse: 150:-" or "23 % ränta" would contradict the
# amount the app charges today and the fact that this app states no interest at
# all. Only the reminder is cleaned; nothing in the invoice record changes.
REMINDER_INTEREST_WORDS=re.compile(
    r'\b(?:dröjsmålsränt\w*|ränta|räntan|räntor|räntesats\w*|räntekostnad\w*|interest(?:\s+rate)?)\b',re.I)
REMINDER_FEE_WORDS=re.compile(
    r'\b(?:påminnelseavgift\w*|påminnelseavgiften|förseningsavgift\w*|förseningsersättning\w*|'
    r'inkassoavgift\w*|reminder\s+fee\w*|late[- ]payment\s+(?:fee|compensation)\w*)\b',re.I)
# Break after . ! ? when a new sentence starts. A following lowercase word keeps
# abbreviations such as "Ev." and "t.ex." inside their sentence.
REMINDER_SENTENCE_BREAK=re.compile(r'(?<=[.!?])(?:\s+(?=[A-ZÅÄÖ0-9])|(?=[A-ZÅÄÖ]))')


def reminder_note_sentences(note):
    """Split an invoice text into the sentences a reminder may print."""
    return [part.strip() for part in REMINDER_SENTENCE_BREAK.split(str(note or '')) if part.strip()]


def reminder_note_term_clause(sentence):
    """True for a sentence that states a reminder fee or a late-payment rate."""
    text=str(sentence or '').casefold()
    if REMINDER_INTEREST_WORDS.search(text):return True
    if REMINDER_FEE_WORDS.search(text):return True
    # "Avgift: 150 kr per påminnelse" and "fee for each reminder" in any order.
    if 'avgift' in text and ('påminnelse' in text or 'reminder' in text):return True
    return 'fee' in text and ('påminnelse' in text or 'reminder' in text or 'late payment' in text)


# One optional line from the sender on the reminder PDF. Kept short because it
# is printed in a bordered box on the customer's page.
REMINDER_MESSAGE_MAX_LENGTH=160


def reminder_message_text(value):
    """Return the optional sender line a reminder prints, cleaned for the PDF.

    An empty value means no line at all: nothing may leave a blank paragraph, a
    label or an empty frame on the customer's page, and the P1/P2 snapshot
    stores the value exactly as it was printed.
    """
    text=' '.join(str(value or '').split())
    if not text:return ''
    if len(text)>REMINDER_MESSAGE_MAX_LENGTH:
        return text[:REMINDER_MESSAGE_MAX_LENGTH-1].rstrip()+'…'
    return text


def reminder_level_message(row,level):
    """Return the line a stored reminder was actually printed with.

    A reminder keeps its own line in the P1/P2 snapshot, so editing P2 can never
    rewrite what P1 already said. Older reminders without a snapshot fall back
    to the line stored on the invoice.
    """
    if level not in ('P1','P2'):return reminder_message_text(row_value(row,'reminder_message',''))
    snapshot=read_reminder_snapshot(row_value(row,level.lower()+'_snapshot',''))
    if snapshot:return reminder_message_text(snapshot['row'].get('reminder_message') or '')
    return reminder_message_text(row_value(row,'reminder_message',''))


def reminder_note_text(note):
    """Return the invoice text as a reminder may repeat it.

    Everything the invoice actually documents is kept — payment details,
    retention of title, objection days — while fee and interest clauses are
    left out. The reminder states the lawful fee and its legal basis once,
    separately, so repeating an older amount or a rate would only contradict it.
    """
    return re.sub(r'\s+',' ',' '.join(
        sentence for sentence in reminder_note_sentences(note)
        if not reminder_note_term_clause(sentence)
    )).strip()


def reminder_note_omitted(note):
    """Return the fee and interest sentences a reminder will not repeat."""
    return tuple(
        sentence for sentence in reminder_note_sentences(note)
        if reminder_note_term_clause(sentence)
    )


def build_reminder_email_content(row,level,recipients):
    """Build editable preview content with a fixed BCC; never send automatically."""
    addresses=parse_email_addresses(','.join(recipients))
    if not addresses:raise ValueError('At least one recipient is required')
    email_row=dict(row)
    try:followup=level=='P2' or int(email_row.get('sent_count') or 0)>0
    except (TypeError,ValueError):followup=level=='P2'
    terms=current_reminder_terms(reminder_fee_for(row),invoice_customer_type(row),invoice_currency(row),invoice_fee_agreement(row))
    snapshot_column=level.lower()+'_snapshot'
    snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
    snapshot_language=''
    if snapshot:
        email_row.update(snapshot['row'])
        terms=snapshot['terms']
        snapshot_language=str(snapshot.get('language') or '')
    doc_language=snapshot_language if snapshot_language in SUPPORTED_LANGUAGES else effective_reminder_language(email_row)
    try:fee=float(terms.get('fee') if terms.get('fee') is not None else reminder_fee_for(row))
    except (TypeError,ValueError):fee=reminder_fee_for(row)
    customer_type=normalize_customer_type(terms.get('customer_type') or invoice_customer_type(email_row))
    remaining=max(0,float(email_row['amount'] or 0)-float(email_row['paid'] or 0))
    reminder_day=dparse(email_row.get(level.lower()+'_date')) or date.today()
    try:
        saved_deadline=terms.get('payment_deadline_days')
        deadline_days=int(saved_deadline) if saved_deadline not in (None,'') else 5
    except (TypeError,ValueError):deadline_days=5
    deadline_date=reminder_deadline_date(reminder_day,deadline_days,terms if snapshot else None)
    currency=email_row['currency']
    invoice_no=email_row['invoice_no']
    company=reminder_email_company(email_row)
    with language_override(doc_language):
        fee_label=_(fee_label_key(customer_type,fee,fee_model_for_terms(terms)))
        fee_text=f'{fee_label}: {money(fee,currency)}'
        deadline=format_long_date(deadline_date)
        values={
            'invoice_no':invoice_no,'due_date':email_row['due_date'],
            'remaining':money(remaining,currency),'fee_text':fee_text,
            'total':money(remaining+fee,currency),
            'deadline':deadline,
        }
        subject=_('Faktura {invoice_no} – betalningspåminnelse',invoice_no=invoice_no)
        if company:subject+=f' / {company}'
        if followup:subject=('Re: ' if get_language()=='en' else 'SV: ')+subject
        if level=='P2':
            body=_(
                'Hej!\n\nTrots tidigare påminnelse är faktura {invoice_no}, som förföll {due_date}, fortfarande obetald. Detta är andra påminnelsen.\n\nKvarstående fakturabelopp: {remaining}\n{fee_text}\nAtt betala: {total}\nSista betalningsdag: {deadline}\n\nAvgiften debiteras en gång per faktura och tillkommer inte igen. Betalningen av hela beloppet ska vara oss tillhanda senast {deadline}. Ange fakturanumret som referens. Om betalningen inte har kommit in efter sista betalningsdag kan ärendet lämnas vidare utan ytterligare påminnelse. Påminnelsen skickas som PDF. Om betalningen redan är gjord, kontakta oss med betalningsuppgifter så att vi kan stämma av.',
                invoice_no=invoice_no,due_date=email_row['due_date'],remaining=values['remaining'],
                fee_text=values['fee_text'],total=values['total'],deadline=deadline,
            )
        else:
            body=_(
                'Hej!\n\nFaktura {invoice_no} förföll {due_date} och är fortfarande obetald. Detta är första påminnelsen.\n\nKvarstående fakturabelopp: {remaining}\n{fee_text}\nAtt betala: {total}\nSista betalningsdag: {deadline}\n\nAvgiften debiteras en gång per faktura. Betalningen av hela beloppet ska vara oss tillhanda senast {deadline}. Ange fakturanumret som referens. Påminnelsen skickas som PDF. Om betalningen redan är gjord, kontakta oss med betalningsuppgifter så att vi kan stämma av.',
                invoice_no=invoice_no,due_date=email_row['due_date'],remaining=values['remaining'],
                fee_text=values['fee_text'],total=values['total'],deadline=deadline,
            )
    return {'recipients':addresses,'bcc':REMINDER_BCC,'subject':subject,'body':body}


def window_work_area_height(window):
    """Return the usable height of the monitor holding ``window``."""
    try:
        area=monitor_work_area(window)
        height=int(area[3])
        if height>=200:return height
        return int(window.winfo_screenheight())
    except Exception:
        return 0


def dialog_available_width(window,maximum=1100,margin=24):
    """Return the width a dialog may use on the current screen."""
    try:screen_width=int(window.winfo_screenwidth())
    except Exception:screen_width=maximum
    return max(320,min(int(maximum),screen_width-2*int(margin)))


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
    """Respect both the configured P2 interval and the printed banking-day P1 deadline."""
    p1_date=dparse(row['p1_date'])
    if not p1_date:return None
    interval_days=int(setting('p2_days') or 5)
    deadline_days=int(setting('payment_deadline_days') or 5)
    snapshot=read_p1_snapshot(row['p1_snapshot'] if 'p1_snapshot' in row.keys() else '')
    snapshot_terms=snapshot['terms'] if snapshot else None
    if snapshot:
        try:
            saved_deadline=snapshot_terms.get('payment_deadline_days')
            if saved_deadline not in (None,''):deadline_days=int(saved_deadline)
        except (TypeError,ValueError):
            report_fault()
    printed_deadline=reminder_deadline_date(p1_date,deadline_days,snapshot_terms)
    interval_target=p1_date+timedelta(days=interval_days)
    return max(interval_target,printed_deadline)


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


# Soft but distinct status tints. They read clearly on the white table while
# staying calm next to the navy brand colour, and all keep well above 4.5:1
# contrast with the table text.
INVOICE_ROW_COLORS = {
    'status-not-due':'#DDEFE6',
    'status-p1':'#FBF0D2',
    'status-p2':'#FBE4E4',
}
# The same three signals in the dark theme: deep, desaturated tints that stay
# behind the text instead of glowing, and every one of them keeps the light
# table text well above 4.5:1.
INVOICE_ROW_COLORS_DARK = {
    'status-not-due':'#16302A',
    'status-p1':'#33280F',
    'status-p2':'#3A1D20',
}


def row_colors_for_theme(theme='light'):
    return INVOICE_ROW_COLORS_DARK if appearance.is_dark(theme) else INVOICE_ROW_COLORS


# Columns that carry free text are the ones allowed to grow when the window is
# wider than the table; the numeric columns keep their width so figures never
# drift apart between rows.
INVOICE_FLEX_COLUMNS = (('customer',0.45),('stage',0.30),('email_status',0.25))


def fit_invoice_columns(tree,widths,available,px=None):
    """Distribute extra table width over the columns that read as text.

    A narrow window keeps the base widths and scrolls, because squeezing ten
    columns thinner than they are would make the table unreadable rather than
    useful. A wide window gives the spare room to the customer, status and
    e-mail columns and leaves every figure column exactly where it was.
    """
    to_px=px if callable(px) else (lambda value:value)
    try:available=int(available)
    except (TypeError,ValueError):return {}
    if available<=1:return {}
    fitted={column:to_px(value) for column,value in dict(widths).items()}
    extra=available-sum(fitted.values())
    if extra>0:
        for column,share in INVOICE_FLEX_COLUMNS:
            if column not in fitted:continue
            fitted[column]+=int(extra*share)
        # The last flexible column absorbs the rounding, so the table ends
        # exactly where the window does instead of a few pixels short.
        last=INVOICE_FLEX_COLUMNS[-1][0]
        if last in fitted:fitted[last]+=available-sum(fitted.values())
    for column,value in fitted.items():
        try:tree.column(column,width=value)
        except Exception:report_fault()
    return fitted


def update_is_manual_only(app=None):
    """Return whether replacing the files must always be confirmed first.

    A git checkout is the developer's own copy: it normally holds newer files
    than the release, so the files really do differ and an automatic install
    would silently undo that work. The update is still offered in the dialog.
    """
    directory=getattr(app,'app_dir',None) if app is not None else None
    return update_state.is_source_checkout(directory or APP_DIR)


def restyle_update_button(app):
    """Promote the update button to the accent only when an update exists."""
    button=getattr(app,'update_button',None)
    if button is None:return None
    available=getattr(app,'_available_update',None) is not None
    style='Accent.TButton' if available else 'TButton'
    try:button.configure(style=style)
    except tk.TclError:return None
    return style


SORT_ASC_INDICATOR = '▲'
SORT_DESC_INDICATOR = '▼'


def parse_column_order(raw_order, valid_columns):
    """Validate a saved column order, preserving every valid column once."""
    valid = list(valid_columns)
    seen = set()
    ordered = []
    for item in str(raw_order or '').split(','):
        col = item.strip()
        if col in valid and col not in seen:
            ordered.append(col)
            seen.add(col)
    for col in valid:
        if col not in seen:
            ordered.append(col)
            seen.add(col)
    return tuple(ordered)


def format_sort_heading(label: str, active: bool, reverse: bool = False) -> str:
    """Append a clear sort direction indicator to the active column heading."""
    base = str(label or '').strip()
    if not active:
        return base
    arrow = SORT_DESC_INDICATOR if reverse else SORT_ASC_INDICATOR
    return f'{base} {arrow}'


def _treeview_cell_sort_key(raw_value):
    text = str(raw_value or '').strip()
    if not text or text == '—':
        return (2, 0.0, '')
    cleaned = (
        text.replace('\u00a0', '')
        .replace(' ', '')
        .replace('kr', '')
        .replace('SEK', '')
        .replace('EUR', '')
        .replace('USD', '')
        .replace(',', '.')
    )
    if re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
        return (0, float(cleaned), '')
    return (1, 0.0, text.casefold())


def sort_treeview_items(tree, column, reverse=False):
    """Sort an in-memory ttk.Treeview by ``column`` without losing row tags."""
    columns = list(tree['columns'])
    if column not in columns:
        return
    col_index = columns.index(column)
    items = []
    for iid in tree.get_children(''):
        values = tree.item(iid, 'values')
        cell = values[col_index] if col_index < len(values) else ''
        items.append((_treeview_cell_sort_key(cell), iid))
    items.sort(key=lambda pair: pair[0], reverse=bool(reverse))
    for position, (_key, iid) in enumerate(items):
        tree.move(iid, '', position)


def enable_treeview_features(
    tree,
    columns,
    labels,
    *,
    initial_sort=None,
    initial_reverse=False,
    on_sort=None,
    order_setting_key=None,
):
    """Attach sort indicators and drag/context-menu column reordering to a Treeview."""
    valid_columns = tuple(columns)
    state = {
        'labels': dict(labels),
        'sort_col': initial_sort,
        'sort_rev': bool(initial_reverse),
        'drag_col': None,
        'drag_x': 0,
        'dragged': False,
    }
    tree._column_ui_state = state

    def current_display_columns():
        try:
            raw = tree['displaycolumns']
        except Exception:
            return list(valid_columns)
        if raw in ('#all', ('#all',), '', ()):
            return list(valid_columns)
        return [col for col in raw if col in valid_columns] or list(valid_columns)

    def apply_display_order(new_order, persist=True):
        normalized = parse_column_order(','.join(new_order), valid_columns)
        try:
            tree.configure(displaycolumns=normalized)
        except Exception:
            report_fault()
            return normalized
        if persist and order_setting_key:
            saved = '' if tuple(normalized) == valid_columns else ','.join(normalized)
            try:
                set_setting(order_setting_key, saved)
            except Exception:
                report_fault()
        return normalized

    def refresh_headings(sort_col=None, sort_rev=None):
        if sort_col is not None:
            state['sort_col'] = sort_col
        if sort_rev is not None:
            state['sort_rev'] = bool(sort_rev)
        for col in valid_columns:
            heading_text = format_sort_heading(
                state['labels'].get(col, col),
                col == state['sort_col'],
                state['sort_rev'],
            )
            try:
                tree.heading(col, text=heading_text)
            except Exception:
                report_fault()

    tree._refresh_sort_headings = refresh_headings
    tree._apply_column_order = apply_display_order

    if order_setting_key:
        try:
            stored = setting(order_setting_key)
        except Exception:
            stored = ''
        if stored:
            apply_display_order(stored.split(','), persist=False)

    def column_from_x(x_coord):
        try:
            ident = tree.identify_column(x_coord)
        except Exception:
            return None
        if not ident or not str(ident).startswith('#'):
            return None
        try:
            idx = int(str(ident)[1:]) - 1
        except ValueError:
            return None
        displayed = current_display_columns()
        return displayed[idx] if 0 <= idx < len(displayed) else None

    def trigger_sort(col):
        if on_sort is not None:
            on_sort(col)
            return
        if state['sort_col'] == col:
            state['sort_rev'] = not state['sort_rev']
        else:
            state['sort_col'] = col
            state['sort_rev'] = False
        sort_treeview_items(tree, col, state['sort_rev'])
        refresh_headings()

    for col in valid_columns:
        try:
            tree.heading(col, command=lambda column=col: None if state['dragged'] else trigger_sort(column))
        except Exception:
            report_fault()

    def on_press(event):
        try:
            if tree.identify_region(event.x, event.y) != 'heading':
                state['drag_col'] = None
                state['dragged'] = False
                return
        except Exception:
            return
        state['drag_col'] = column_from_x(event.x)
        state['drag_x'] = int(event.x)
        state['dragged'] = False

    def on_motion(event):
        if not state['drag_col']:
            return
        if abs(int(event.x) - state['drag_x']) >= 8:
            state['dragged'] = True

    def on_release(event):
        source_col = state['drag_col']
        was_dragged = state['dragged']
        state['drag_col'] = None
        if not source_col or not was_dragged:
            return
        target_col = column_from_x(event.x)
        if target_col and target_col != source_col:
            order = current_display_columns()
            if source_col in order and target_col in order:
                target_index = order.index(target_col)
                order.remove(source_col)
                order.insert(target_index, source_col)
                apply_display_order(order, persist=True)
                log_activity('ui', 'column_reordered', 'completed', column=source_col, target=target_col)
        try:
            tree.after_idle(lambda: state.__setitem__('dragged', False))
        except Exception:
            state['dragged'] = False

    def move_column(col, delta):
        order = current_display_columns()
        if col not in order:
            return
        idx = order.index(col)
        new_idx = max(0, min(len(order) - 1, idx + delta))
        if new_idx == idx:
            return
        order.pop(idx)
        order.insert(new_idx, col)
        apply_display_order(order, persist=True)
        log_activity('ui', 'column_reordered', 'completed', column=col, direction=delta)

    def on_heading_context_menu(event):
        try:
            if tree.identify_region(event.x, event.y) != 'heading':
                return
        except Exception:
            return
        col = column_from_x(event.x)
        if not col:
            return
        menu = tk.Menu(tree, tearoff=0)
        order = current_display_columns()
        idx = order.index(col) if col in order else 0
        menu.add_command(
            label=_('Flytta kolumn vänster'),
            command=lambda: move_column(col, -1),
            state='normal' if idx > 0 else 'disabled',
        )
        menu.add_command(
            label=_('Flytta kolumn höger'),
            command=lambda: move_column(col, 1),
            state='normal' if idx < len(order) - 1 else 'disabled',
        )
        menu.add_separator()
        menu.add_command(
            label=_('Återställ kolumnordning'),
            command=lambda: apply_display_order(valid_columns, persist=True),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                report_fault()
        return 'break'

    try:
        tree.bind('<ButtonPress-1>', on_press, add='+')
        tree.bind('<B1-Motion>', on_motion, add='+')
        tree.bind('<ButtonRelease-1>', on_release, add='+')
        tree.bind('<Button-3>', on_heading_context_menu, add='+')
        tree.bind('<Button-2>', on_heading_context_menu, add='+')
    except Exception:
        report_fault()

    refresh_headings()
    return state


def repaint_app_palette(app):
    """Re-apply the current theme to every open window, widget and menu.

    It reads the app through plain attributes, so the same function paints the
    real window and a dialogue built on a test double.
    """
    style=getattr(app,'_accessibility_style',None)
    high_contrast=getattr(app,'_high_contrast',False)
    theme=getattr(app,'_theme','light')
    palette=window_palette(app)
    if style is not None:
        style.apply(
            getattr(app,'ui_font_scale',1.0),high_contrast=high_contrast,
            pixel_scale=getattr(app,'dpi_scale',1.0),theme=theme,
        )
    try:app.configure(bg=palette['background'])
    except tk.TclError:report_fault()
    select_logo=getattr(app,'_active_brand_logo',None)
    active_logo=select_logo() if callable(select_logo) else getattr(app,'_brand_logo',None)
    if active_logo is not None:
        app._brand_logo=active_logo
    for label in list(getattr(app,'_brand_logo_widgets',()) or ()):
        try:
            if active_logo is not None:label.configure(image=active_logo)
        except tk.TclError:report_fault()
    for label in list(getattr(app,'_header_backgrounds',()) or ()):
        try:label.configure(bg=palette['background'])
        except tk.TclError:report_fault()
    tree=getattr(app,'tree',None)
    if tree is not None:configure_invoice_row_colors(tree,high_contrast,theme)
    windows=[app]+[child for child in app.winfo_children() if child.winfo_class()=='Toplevel']
    for window in windows:
        try:window.configure(bg=palette['background'])
        except (tk.TclError,AttributeError):report_fault()
        apply_widget_contrast(window,high_contrast,theme)
        prepare_focus_tree(window,high_contrast)
    for menu in (getattr(app,'main_menu',None),getattr(app,'file_menu',None),getattr(app,'help_menu',None),getattr(app,'row_menu',None)):
        if menu is not None:apply_widget_contrast(menu,high_contrast,theme)


def window_palette(app):
    """Return the colours any window object should paint itself with.

    It reads the two attributes with defaults, so a dialogue built on a test
    double gets the same light palette as the real window instead of failing
    on an attribute that only exists at runtime.
    """
    return contrast_palette(getattr(app,'_high_contrast',False),getattr(app,'_theme','light'))


def configure_invoice_row_colors(tree,high_contrast=False,theme='light'):
    """Keep status text readable in every theme and in high contrast."""
    palette=contrast_palette(high_contrast,theme)
    colors=INVOICE_ROW_COLORS if high_contrast else row_colors_for_theme(theme)
    for tag,background in colors.items():
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


# The search understands the same field names the list shows. A prefix limits
# one word to one field ("kund:acme"), and both languages are accepted so the
# syntax does not change when the UI is switched to English.
SEARCH_FIELD_PREFIXES = {
    'kund':'customer','customer':'customer',
    'nr':'invoice_no','faktura':'invoice_no','invoice':'invoice_no',
    'belopp':'amount','amount':'amount',
    'datum':'date','date':'date','förfaller':'date','due':'date',
    'status':'stage',
    'epost':'email','e-post':'email','email':'email',
    'not':'note','note':'note',
    'valuta':'currency','currency':'currency',
}
SEARCH_HELP_EXAMPLES = (
    'kund:limoeurope',
    'nr:6475',
    'belopp:1500',
    'datum:2026-11',
    'status:granska',
    'epost:anna@',
)


def split_search_query(query):
    """Split a query into (field, word) pairs.

    Words are separated by any whitespace, and a quoted phrase stays one word
    so a customer name with a space can be searched as one term. A known
    ``field:`` prefix limits that word to one field; an unknown prefix is kept
    as ordinary text instead of silently matching nothing.
    """
    tokens=[]
    word=[];quoted=False
    for character in str(query or ''):
        if character=='"':
            quoted=not quoted
            continue
        if character.isspace() and not quoted:
            if word:tokens.append(''.join(word));word=[]
            continue
        word.append(character)
    if word:tokens.append(''.join(word))
    terms=[]
    for token in tokens:
        field=None;text=token
        prefix,separator,rest=token.partition(':')
        if separator and rest:
            candidate=SEARCH_FIELD_PREFIXES.get(prefix.casefold())
            if candidate is not None:
                field=candidate;text=rest
        text=' '.join(str(text).casefold().split())
        if text:terms.append((field,text))
    return tuple(terms)


def _amount_search_text(value):
    """Return every spelling of one amount that a user might type."""
    try:number=float(value)
    except (TypeError,ValueError):return ''
    point=f'{number:.2f}'
    spellings={point,point.rstrip('0').rstrip('.'),point.replace('.',',')}
    grouped=f'{number:,.2f}'
    spellings.add(grouped)
    spellings.add(grouped.replace(',',' ').replace('.',','))
    spellings.add(grouped.replace(',','\u00a0').replace('.',','))
    return ' '.join(sorted(spelling for spelling in spellings if spelling)).casefold()


def _date_search_text(value):
    """Return the stored date and the long localised form of it."""
    text=str(value or '').strip()
    if not text:return ''
    parts=[text]
    try:parts.append(format_long_date(date.fromisoformat(text)))
    except ValueError:report_fault()
    return ' '.join(parts).casefold()


def invoice_search_fields(row,stage='',remaining=None):
    """Return one lowercase searchable string per field of one invoice.

    Only what is already stored is searched - nothing is fetched from disk and
    no invoice is changed. The stage is included in both languages, so a user
    on the English UI can type "review" and find "Granska uppgifter".
    """
    keys=row.keys() if hasattr(row,'keys') else ()
    def value(name):
        return str(row[name] or '') if name in keys else ''
    amount=float(row['amount'] or 0) if 'amount' in keys else 0.0
    paid=float(row['paid'] or 0) if 'paid' in keys else 0.0
    remain=amount-paid if remaining is None else float(remaining)
    stage_text=' '.join(part for part in (str(stage or ''),_(str(stage or ''))) if part)
    return {
        'customer':value('customer').casefold(),
        'invoice_no':value('invoice_no').casefold(),
        'email':value('email').casefold(),
        'note':value('note').casefold(),
        'currency':value('currency').casefold(),
        'amount':f"{_amount_search_text(amount)} {_amount_search_text(remain)}",
        'date':f"{_date_search_text(value('due_date'))} {_date_search_text(value('invoice_date'))} {_date_search_text(value('p1_date'))} {_date_search_text(value('p2_date'))}",
        'stage':stage_text.casefold(),
    }


def invoice_matches_search(fields,terms):
    """Require every term to be found; each term may sit in a different field."""
    for field,text in terms:
        haystack=fields.get(field,'') if field else ' '.join(fields.values())
        if text not in haystack:return False
    return True


def invoice_search_summary(shown,total,query='',elsewhere=0):
    """Describe the list in one line: how much is shown, and what was searched.

    ``total`` is how many invoices the open tab holds on its own, so "Visar 2 av
    4" always compares against the same tab rather than against every invoice.
    Hits in another tab are always named, so an empty tab never reads as if the
    invoice had disappeared.
    """
    query=' '.join(str(query or '').split())
    if not query:return _('Visar {shown} av {total}',shown=shown,total=total)
    more=0
    if elsewhere:
        more=_('{elsewhere} träff i andra vyer',elsewhere=elsewhere) if elsewhere==1 else _('{elsewhere} träffar i andra vyer',elsewhere=elsewhere)
    if shown:
        if more:return _('Visar {shown} av {total} · sökning: {query} · {more}',shown=shown,total=total,query=query,more=more)
        return _('Visar {shown} av {total} · sökning: {query}',shown=shown,total=total,query=query)
    if more:return _('Inga träffar i den här vyn · {more}',more=more)
    return _('Inga träffar för ”{query}”',query=query)


def invoice_view(flt,query='',sort_column='due_date',sort_reverse=False):
    """Return the invoices exactly as the list shows them right now.

    One place answers "what is in the list": the open tab, the search and the
    order. The table and the CSV export both read this, so an export can never
    disagree with what the user is looking at.
    """
    with connect() as db: rows=db.execute('SELECT * FROM invoices ORDER BY due_date').fetchall()
    terms=split_search_query(query)

    def in_view(r,stage,remain):
        if flt=='current':return not (r['ignored'] or stage in ('Avslutad','Kronofogden – granska'))
        if flt=='history':return bool(r['ignored'] or remain<=0.005)
        if flt=='ignored':return bool(r['ignored'])
        if flt=='debt_review':return stage=='Kronofogden – granska'
        return True

    prepared=[]
    for r in rows:
        stage=next_stage(r)
        remain=max(0,float(r['amount'] or 0)-float(r['paid'] or 0))
        prepared.append((r,stage,remain,invoice_search_fields(r,stage,remain)))
    visible=[];in_view_total=0
    for r,stage,remain,fields in prepared:
        if not in_view(r,stage,remain):continue
        in_view_total+=1
        if not invoice_matches_search(fields,terms):continue
        visible.append((r,stage,remain))
    # A search also reports hits outside the open tab, so nobody concludes
    # that an invoice is gone when it is only in another view.
    elsewhere=0
    if terms:
        elsewhere=sum(
            1 for r,stage,remain,fields in prepared
            if not in_view(r,stage,remain) and invoice_matches_search(fields,terms)
        )
    def sort_key(item):
        r,stage,remain=item
        if sort_column=='remaining':return remain
        if sort_column=='amount':return float(r['amount'] or 0)
        if sort_column=='fee':return charged_fee_for(r) if r['p1_date'] else -1.0
        if sort_column=='invoice_no':
            value=str(r['invoice_no'] or '')
            return (0,int(value)) if value.isdigit() else (1,value.casefold())
        if sort_column=='stage':return _(stage).casefold()
        if sort_column=='email_status':return reminder_email_status(r).casefold()
        if sort_column=='p2_send_date':return str(r['p2_date'] or '')
        if sort_column in r.keys():return str(r[sort_column] or '').casefold()
        return ''
    visible.sort(key=sort_key,reverse=sort_reverse)
    return visible,in_view_total,elsewhere


def current_view_options(app):
    """Read the tab, search and sort order that the window is showing."""
    search_var=getattr(app,'invoice_search_var',None)
    query=search_var.get().strip() if search_var is not None else ''
    return (
        getattr(app,'current_filter_key','current'),query,
        getattr(app,'invoice_sort_column','due_date'),
        getattr(app,'invoice_sort_reverse',False),
    )


def due_reminder_invoices():
    """Return unpaid, reviewed invoices whose normal workflow is ready for P1/P2."""
    with connect() as db:
        rows=db.execute('SELECT * FROM invoices ORDER BY due_date,invoice_no').fetchall()
    return [row for row in rows if next_stage(row) in ('P1 att skapa','P2 att skapa')]


def reminder_was_opened(row,level):
    """Return whether this level's e-mail draft has already been opened.

    A reminder that has been sent is finished, and one whose draft was opened
    once does not need to interrupt the user again - it is still in the e-mail
    client, unsent or already sent. Only a level nobody has touched is news.
    """
    prefix=level.lower();keys=row.keys()
    for column in (prefix+'_sent_date',prefix+'_draft_date'):
        if column in keys and str(row[column] or '').strip():return True
    return False


def due_reminder_level(row):
    """Return the reminder step an invoice is ready for, or an empty string."""
    stage=next_stage(row)
    if stage=='P1 att skapa':return 'P1'
    if stage=='P2 att skapa':return 'P2'
    return ''


def due_reminder_rows(include_opened=False):
    """Group the invoices that are due now, with the oldest deadline first.

    An invoice that has waited longest on its reminder is the one that costs
    the most to forget, so the list is ordered by how many days overdue the
    reminder is rather than by invoice number. A level whose draft has already
    been opened is not news and is left out, so the dialog cannot nag about
    work the user has already started; ``include_opened`` brings it back.
    """
    today=date.today()
    items=[]
    for row in due_reminder_invoices():
        level=due_reminder_level(row)
        if not level:continue
        if not include_opened and reminder_was_opened(row,level):continue
        if level=='P1':
            due=dparse(row['due_date'])
            days=max(0,(today-due).days) if due else 0
        else:
            p2_due=p2_due_date(row)
            days=max(0,(today-p2_due).days) if p2_due else 0
        items.append((days,row,level))
    items.sort(key=lambda item:(-item[0],str(item[1]['invoice_no'])))
    return items


def due_reminder_summary(rows):
    """Return the counts and the total claim shown in the dialog header."""
    p1=[item for item in rows if item[2]=='P1']
    p2=[item for item in rows if item[2]=='P2']
    total=0.0
    mixed=False
    currencies=set()
    for _days,row,_level in rows:
        currencies.add(str(row['currency'] or 'SEK'))
        try:total+=float(row['amount'] or 0)-float(row['paid'] or 0)
        except (TypeError,ValueError):report_fault()
    mixed=len(currencies)>1
    return {'p1':len(p1),'p2':len(p2),'total':max(0.0,total),'mixed':mixed,
            'currency':sorted(currencies)[0] if currencies else 'SEK'}


def _show_due_reminder_text(parent,rows):
    """Fallback summary when no window is available to open the list from."""
    lines=[]
    for _days,row,level in rows[:12]:
        lines.append(f"{level}: {row['invoice_no']} – {row['customer']}")
    if len(rows)>12:lines.append(_('… och {count} till',count=len(rows)-12))
    messagebox.showinfo(
        _('Dags att skapa P1/P2'),
        _('Följande fakturor är redo för P1 eller P2:\n\n{reminders}\n\nVälj en faktura i listan och klicka på Skapa påminnelse.',reminders='\n'.join(lines)),
        parent=parent,
    )
    return True


def show_due_reminder_dialog(parent=None):
    """Open the reminder dialog for the invoices that are due right now.

    The list is built before any window is opened, so the same function can be
    tested without Tk and the dialog never appears empty. Every row can be
    opened directly: the dialog calls back into the window's normal
    ``make_reminder`` flow rather than creating a second way to send a reminder,
    so the logo dialogue, the fee rules and the journal write stay in one place.
    """
    rows=due_reminder_rows()
    if not rows:return False
    app=parent if hasattr(parent,'make_reminder') else None
    if app is None or not hasattr(app,'_new_toplevel'):
        # Without a window there is nothing to click, so the plain summary is
        # still shown rather than silently returning.
        return _show_due_reminder_text(parent,rows)
    return app.show_due_reminder_window(rows)


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
        super().__init__()
        self._startup_withdrawn=False;self._window_hidden=False
        try:
            self.withdraw()
            self._startup_withdrawn=True
        except tk.TclError:
            report_fault()
        self.title(APP_NAME)
        self.dpi_scale=self._display_scale()
        self._apply_initial_main_geometry()
        self._style(); self.configure(bg=window_palette(self)['background']); self._configure_icons(); self.current_filter_key='current'
        self.invoice_sort_column='due_date';self.invoice_sort_reverse=False
        self._update_check_running=False;self._update_install_running=False;self._update_install_stage=None;self._available_update=None;self._update_helper_process=None;self.update_button=None
        self.tray=None;self._quitting=False;self._contrast_check_running=False
        self._import_monitor=ImportFolderMonitor(IMPORT_DIR);self._import_scan_running=False;self._python_addons_ready=False
        self._python_addon_install_running=False;self._python_addon_updates_running=False
        self.build(); self._apply_initial_main_geometry(); self.refresh()
        self.after(SYSTEM_CONTRAST_POLL_INTERVAL_MS,self._poll_system_contrast)
        self.protocol('WM_DELETE_WINDOW',self.hide_to_tray)
        self.bind('<Unmap>',self._on_main_window_unmap,add='+')
        self._configure_macos_desktop_events()
        self.start_tray()
        self.after(100,self.sync_autostart)
        # Startup only recovers missing dependencies; upgrades are user-confirmed.
        self.after(250,self.check_python_addons)
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
        """Start the tray icon lazily so unsupported desktops can still run the app.

        The tray is the only permanent entry point on all three platforms, so a
        failure is logged with the platform-specific remedy instead of only the
        backend exception.
        """
        if self.tray is not None and self.tray.running:return
        self.tray=TrayController(
            name=APP_NAME,identifier=APP_SLUG,icon_path=tray_icon_path(),
            scheduler=lambda callback:self.after(0,callback),on_open=self.show_from_tray,
            on_update=self.update_from_tray,on_exit=self.quit_app,
            on_scan=self.scan_import_folder,
            on_export=self.open_export_folder,
            scan_label=lambda:_('Skanna importmapp nu'),
            export_label=lambda:_('Öppna exportmapp'),
            status_label=self.tray_status_text,
            open_label=lambda:_('Öppna {app_name}',app_name=APP_NAME),
            update_label=self._update_tray_label,exit_label=lambda:_('Avsluta helt'),on_error=self.handle_tray_error)
        try:
            self.tray.start();self._configure_macos_dock_icon();logger.info('System tray icon started (%s)',sys.platform)
            self.tray.set_title(self.tray_status_text())
        except TrayUnavailable as exc:
            logger.warning('System tray is unavailable: %s',exc)
            hint=getattr(exc,'hint','')
            if hint:logger.warning('System tray remedy: %s',hint)
            log_activity('tray','unavailable','failed',error=str(exc),platform=sys.platform)

    def tray_status_text(self,row=None):
        """Return the tray tooltip and menu header for the current workload.

        The text is short on purpose: Windows truncates tooltips around 128
        characters and macOS around 64, so the counts come first and the app
        name is only added when nothing is pending.
        """
        if row is not None:
            counts=self._tray_counts_from_row(row)
        else:
            try:
                with connect() as db:
                    rows=db.execute('SELECT * FROM invoices').fetchall()
                counts={}
                for item in rows:
                    stage=next_stage(item)
                    counts[stage]=counts.get(stage,0)+1
            except Exception:
                logger.exception('Could not compute the tray status text')
                return APP_NAME
        p1=counts.get('P1 att skapa',0)
        p2=counts.get('P2 att skapa',0)
        review=counts.get('Kronofogden – granska',0)
        parts=[]
        if p1:parts.append(_('{count} väntar P1',count=p1))
        if p2:parts.append(_('{count} väntar P2',count=p2))
        if review:parts.append(_('{count} att granska',count=review))
        return f"{APP_NAME} · "+' · '.join(parts) if parts else APP_NAME

    @staticmethod
    def _tray_counts_from_row(row):
        counts={}
        for item in row:
            stage=next_stage(item)
            counts[stage]=counts.get(stage,0)+1
        return counts

    def refresh_tray(self,rows=None):
        """Push the latest workload into the tray without rebuilding it."""
        tray_icon=getattr(self,'tray',None)
        if tray_icon is None or not tray_icon.running:return
        try:
            tray_icon.refresh()
            tray_icon.set_title(self.tray_status_text(rows))
        except Exception:
            logger.exception('Could not refresh the system tray')

    def handle_tray_error(self,error):
        if self._quitting:return
        logger.error('System tray stopped unexpectedly: %s',error)
        if self.tray is not None:self.tray.stop()
        self._window_hidden=False
        self.deiconify()
        messagebox.showwarning(_('Systemfältet är inte tillgängligt'),_('Systemfältet slutade fungera. Fönstret visas igen.'),parent=self)

    def show_from_tray(self):
        log_activity('tray','open_window','started')
        self._window_hidden=False
        self._startup_withdrawn=False
        self.deiconify();self.lift()
        try:self.focus_force()
        except tk.TclError:report_fault()
        poll_contrast=getattr(self,'_poll_system_contrast',None)
        if callable(poll_contrast):poll_contrast()
        if sys.platform.startswith('win'):
            self.after_idle(lambda:configure_windows_window_icon(self))
        self.after_idle(self._maybe_show_ledger_reminder)
        log_activity('tray','open_window','completed')

    def start_minimized(self):
        """Start hidden in the tray without blocking startup on a dialog."""
        if self._quitting:return False
        if self.tray is None or not self.tray.running:self.start_tray()
        if self.tray is None or not self.tray.running:
            if getattr(self,'_startup_withdrawn',False):
                deiconify=getattr(self,'deiconify',None)
                if callable(deiconify):
                    try:deiconify()
                    except tk.TclError:report_fault()
                self._startup_withdrawn=False
            logger.warning('Minimized start requested but the system tray is unavailable; the window stays visible')
            log_activity('tray','startup_minimized','failed')
            return False
        self._window_hidden=True
        self.withdraw()
        logger.info('Application started minimized in the system tray')
        log_activity('tray','startup_minimized','completed')
        # Nothing was visible during startup, so say once where the window is.
        explain=getattr(self,'_explain_tray_hide',None)
        if callable(explain):explain()
        return True

    def _poll_single_instance_activation(self):
        """Open this window when a later start activates the existing app."""
        if self._quitting:return
        event=getattr(self,'_single_instance_activation',None)
        if event is not None and event.is_set():
            event.clear()
            logger.info('Existing PayPamin Flow window activated by a later start')
            self.show_from_tray()
        self.after(200,self._poll_single_instance_activation)

    def _claim_single_instance_after_update(self,started):
        """Take over instance ownership after the old update process exits."""
        if self._quitting:return
        instance=getattr(self,'_single_instance',None)
        if instance is None:
            self._poll_single_instance_activation();return
        try:
            if instance.try_acquire():
                logger.info('Updated app acquired single-instance ownership')
                self._poll_single_instance_activation();return
        except Exception:
            logger.exception('Updated app could not acquire single-instance ownership')
        if time.monotonic()-started>=10:
            # Never leave two GUI instances if the old process did not hand over.
            instance.activate_existing()
            self.quit_app();return
        self.after(100,lambda:self._claim_single_instance_after_update(started))

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

    def _defaults_summary_text(self):
        """Describe the current defaults without restating numbers that can drift."""
        model=current_fee_model()
        if model==FEE_MODEL_PER_REMINDER:
            fees=_('avgift {fee} per påminnelse',fee=money(PER_REMINDER_FEE))
        else:
            fees=_('{fee} för privatpersoner, {compensation} för företag',fee=money(REMINDER_FEE_CAP),compensation=money(LATE_PAYMENT_COMPENSATION))
        return _('Startvärden: P1 +{p1} dagar · P2 +{p2} dagar · Kronofogden-granskning +{p3} dagar · {fees}',
                 p1=setting('p1_days') or '5', p2=setting('p2_days') or '5', p3=setting('p3_days') or '5',
                 fees=fees)

    def _refresh_defaults_summary(self):
        """Keep the footer defaults in step with the saved settings."""
        summary=getattr(self,'_footer_summary',None)
        if summary is None:return
        text=self._defaults_summary_text()
        try:
            if str(summary.cget('text'))!=text:summary.configure(text=text)
        except tk.TclError:report_fault()

    def confirm_quit(self):
        """Ask once before the whole application, including the tray, exits."""
        if getattr(self,'_quitting',False):return
        if messagebox.askyesno(
            _('Avsluta helt'),
            _('Avsluta {app_name} helt?\n\nAppen stängs även i systemfältet. Använd Dölj i systemfältet om den ska fortsätta bevaka importmappen i bakgrunden.',app_name=APP_NAME),
            parent=self,
        ):self.quit_app()

    def hide_to_tray(self):
        """Close and minimize hide the window until the user chooses full exit."""
        if self._quitting:return
        if self.tray is None or not self.tray.running:self.start_tray()
        if self.tray is None or not self.tray.running:
            try:
                if self.state()=='iconic':self.deiconify()
            except tk.TclError:report_fault()
            hint=''
            try:
                from tray import backend_hint
                hint=backend_hint(RuntimeError(''))
            except Exception:
                hint=''
            if messagebox.askyesno(_('Systemfältet är inte tillgängligt'),_('Fönstret kan inte döljas i systemfältet på den här datorn. Vill du avsluta appen helt?')+(('\n\n'+hint) if hint else ''),parent=self):self.quit_app()
            return
        self._window_hidden=True
        self.withdraw();logger.info('Main window hidden to system tray')
        log_activity('tray','window_hidden','completed')
        explain=getattr(self,'_explain_tray_hide',None)
        if callable(explain):explain()

    def _explain_tray_hide(self):
        """Tell a first-time user where the window went, once per install.

        A balloon message is used when the backend supports it; otherwise the
        fact is written to the activity log so support can see it. The hint is
        never shown again after the first acknowledged hide.
        """
        if setting('tray_hint_shown')=='1':return
        message=_('{app_name} fortsätter i systemfältet. Högerklicka på ikonen för att öppna fönstret eller avsluta helt.',app_name=APP_NAME)
        tray_icon=getattr(self,'tray',None)
        shown=False
        if tray_icon is not None and hasattr(tray_icon,'notify'):
            try:shown=bool(tray_icon.notify(message,_('Fönstret ligger i systemfältet')))
            except Exception:shown=False
        try:set_setting('tray_hint_shown','1')
        except Exception:report_fault()
        logger.info('First hide to system tray explained; balloon shown=%s',shown)
        log_activity('tray','first_hide_hint','completed',balloon=shown)

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

    def _scaled_photo(self,source,target_width):
        """Load ``source`` resized to the pixels this display actually draws.

        Tk cannot rescale a PhotoImage smoothly, so a bitmap that is drawn at a
        different size than its own is either stretched by the window manager
        (soft) or subsampled by Tk (blocky). Downscaling once from the largest
        master with a good filter is what keeps the wordmark crisp at 125-200 %.
        """
        try:scale=float(getattr(self,'dpi_scale',1.0))
        except (TypeError,ValueError):scale=1.0
        width=max(1,int(round(float(target_width)*scale)))
        try:
            from PIL import Image,ImageTk
        except ImportError:
            # Pillow is an optional add-on; the plain bitmap is still sharp at 100 %.
            fallback=ICON_DIR/Path(source).name
            try:return tk.PhotoImage(master=self,file=str(fallback))
            except tk.TclError:return None
        try:
            with Image.open(source) as original:
                source_width=max(1,original.width)
                height=max(1,int(round(original.height*width/source_width)))
                premultiplied=original.convert('RGBA').convert('RGBa')
                resized=premultiplied.resize((width,height),Image.Resampling.LANCZOS).convert('RGBA')
            return ImageTk.PhotoImage(resized,master=self)
        except Exception:
            logger.exception('Icon could not be scaled for the display: %s',source)
            try:return tk.PhotoImage(master=self,file=str(source))
            except tk.TclError:return None

    def _active_brand_logo(self):
        """Choose the light-surface or dark-surface wordmark for the active palette."""
        palette=window_palette(self)
        dark_surface=appearance.is_dark(getattr(self,'_theme','light')) or str(palette.get('background','')).upper()=='#000000'
        if dark_surface and getattr(self,'_brand_logo_dark',None) is not None:
            return self._brand_logo_dark
        return getattr(self,'_brand_logo_light',None) or getattr(self,'_brand_logo',None)

    def _register_brand_logo_widget(self,widget):
        widgets=list(getattr(self,'_brand_logo_widgets',()) or ())
        alive=[]
        for existing in widgets:
            try:
                if existing.winfo_exists():alive.append(existing)
            except Exception:
                continue
        alive.append(widget)
        self._brand_logo_widgets=alive
        return widget

    def _configure_icons(self):
        """Use the product identity for windows, OS icons and the header logo."""
        self._window_icons=[];self._header_icon=None;self._brand_logo=None
        self._brand_logo_light=None;self._brand_logo_dark=None;self._brand_logo_widgets=[]
        self._action_icons={}
        self._configure_macos_dock_icon()
        scaled_photo=getattr(self,'_scaled_photo',None)
        def load_photo(path,width):
            """Downscale when the display scaling helper is available."""
            if callable(scaled_photo):return scaled_photo(path,width)
            return tk.PhotoImage(master=self,file=str(path))
        try:
            # Every size the window manager may ask for, up to 512 px, so a
            # HiDPI taskbar and the Alt-Tab switcher get a real bitmap instead
            # of an upscaled 32 px one.
            for size in (16,32,48,256,512):
                path=ICON_DIR/f'paypamin_flow_{size}.png'
                if path.is_file():self._window_icons.append(tk.PhotoImage(master=self,file=str(path)))
            if self._window_icons:self.iconphoto(True,*self._window_icons)
            # Draw the header mark from the largest square master, at 52 design
            # pixels, so a 150-200 % display downsamples instead of upscaling.
            header_master=next(
                (ICON_DIR/f'paypamin_flow_{size}.png' for size in (512,256,48)
                 if (ICON_DIR/f'paypamin_flow_{size}.png').is_file()),
                ICON_DIR/'paypamin_flow_48.png',
            )
            if header_master.is_file():self._header_icon=load_photo(header_master,52)
            # The 1024 px masters (light and dark wordmark) are downscaled cleanly.
            logo_master=ICON_DIR/'paypamin_logo_1024.png'
            logo_path=logo_master if logo_master.is_file() else ICON_DIR/'paypamin_logo.png'
            if logo_path.is_file():self._brand_logo_light=load_photo(logo_path,272)
            dark_master=ICON_DIR/'paypamin_logo_dark_1024.png'
            dark_path=dark_master if dark_master.is_file() else ICON_DIR/'paypamin_logo_dark.png'
            if dark_path.is_file():self._brand_logo_dark=load_photo(dark_path,272)
            select_logo=getattr(self,'_active_brand_logo',None)
            self._brand_logo=select_logo() if callable(select_logo) else self._brand_logo_light
            # Keep the native Windows icon last so it is not replaced by the
            # generic pythonw.exe taskbar icon on older Tk/Windows versions.
            if sys.platform.startswith('win') and (ICON_DIR/'paypamin_flow.ico').is_file():
                self.iconbitmap(default=str(ICON_DIR/'paypamin_flow.ico'))
                configure_windows_window_icon(self)
                # Reapply after the native top-level window has been mapped.
                self.after_idle(lambda:configure_windows_window_icon(self))
        except Exception:
            # A missing or unreadable icon must never stop the app from starting.
            logger.exception('Application icon could not be loaded')

    def _ui_icon(self,name,inverse=False):
        """Load and retain one shared transparent action icon (HiDPI-aware)."""
        if not name:return None
        key=(name,bool(inverse))
        if key in self._action_icons:return self._action_icons[key]
        suffix='_light' if inverse else ''
        scaled_photo=getattr(self,'_scaled_photo',None)
        hidpi_path=ICON_DIR/'icons'/f'{name}{suffix}_4x.png'
        if getattr(self,'dpi_scale',1.0)>1.0 and callable(scaled_photo) and hidpi_path.is_file():
            image=scaled_photo(hidpi_path,16)
            if image is not None:
                self._action_icons[key]=image
                return image
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
        theme=getattr(self,'_theme','light')
        apply_widget_contrast(focus_window,high_contrast,theme)
        prepare_focus_tree(focus_window,high_contrast)
        for menu in (getattr(self,'main_menu',None),getattr(self,'file_menu',None),getattr(self,'help_menu',None),getattr(self,'row_menu',None)):
            if menu is not None:apply_widget_contrast(menu,high_contrast,theme)
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

    def _finalize_toplevel(self,window,_from_idle=False):
        if _from_idle and getattr(window,'__dict__',{}).get('_toplevel_finalized') is True:
            return
        # Repeat native branding after mapping so Windows cannot retain the
        # generic pythonw.exe icon in the taskbar or window switcher.
        self._set_window_icon(window)
        self._finalize_window_actions(window)
        scrollable=getattr(window,'__dict__',{}).get('_accessibility_scrollable_form')
        if scrollable is not None and callable(getattr(scrollable,'fit_to_content',None)):
            try:
                avail_w=dialog_available_width(window)
                area_h=window_work_area_height(window)
                scrollable.fit_to_content(
                    max_width=max(480,avail_w),
                    max_height=max(300,area_h-90) if area_h else 760,
                )
            except Exception:
                report_fault()
        fit_window_to_screen(window)
        try:window._toplevel_finalized=True
        except Exception:report_fault()

    def _prepare_modal_toplevel(self,window):
        """Size, center and style a modal dialog before grabbing pointer/focus."""
        finalize=getattr(self,'_finalize_toplevel',None)
        if callable(finalize):finalize(window)
        try:window.grab_set()
        except tk.TclError:report_fault()

    def _new_toplevel(self,title):
        window=tk.Toplevel(self)
        window.title(title);window.transient(self);window.resizable(True,True)
        self._set_window_icon(window)
        window.after_idle(lambda: self._finalize_toplevel(window,_from_idle=True))
        return window

    def _dialog_form(self,window,padding=20):
        """Return a scrollable form so large text never hides dialog actions."""
        return ScrollableForm(window,tk,ttk,padding=padding).form

    def _apply_initial_main_geometry(self):
        """Open the main window at full usable screen height and content-adapted width.

        The height fills the monitor's usable work area (excluding taskbar/dock)
        so long invoice lists need minimal vertical scrolling, while the width
        adapts to the table and toolbar content without stretching across empty
        ultrawide space. User resize is never blocked.
        """
        try:
            screen_width=max(1,int(self.winfo_screenwidth()))
            screen_height=max(1,int(self.winfo_screenheight()))
        except Exception:
            screen_width,screen_height=1280,800
        area_left,area_top,area_width,area_height=monitor_work_area(self)
        if area_width<240 or area_height<200:
            area_left,area_top,area_width,area_height=0,0,screen_width,screen_height
        scale=getattr(self,'dpi_scale',1.0)
        to_px=getattr(self,'_px',None)
        if not callable(to_px):
            to_px=lambda value:max(1,int(round(float(value)*scale)))
        col_widths=getattr(self,'_invoice_column_widths',None)
        if col_widths:
            base_table_width=sum(to_px(w) for w in col_widths.values())+to_px(120)
        else:
            base_table_width=int(round(1460*scale))
        req_width=0
        if callable(getattr(self,'winfo_reqwidth',None)):
            try:
                if callable(getattr(self,'update_idletasks',None)):self.update_idletasks()
                req_width=int(self.winfo_reqwidth())
            except Exception:
                req_width=0
        natural_width=max(int(round(980*scale)),base_table_width,req_width)
        comfortable_width=max(natural_width,min(int(round(1760*scale)),int(round(area_width*0.78))))
        margin=48 if area_width>=800 else 0
        max_width=max(min(720,area_width),area_width-margin)
        width=min(comfortable_width,max_width)
        height=area_height
        x=area_left+max(0,(area_width-width)//2)
        y=area_top
        try:self.geometry(f'{width}x{height}+{x}+{y}')
        except Exception:report_fault()
        try:self.minsize(min(int(round(900*scale)),width),min(int(round(520*scale)),height))
        except Exception:report_fault()

    # Columns that carry free text are the ones allowed to grow when the window
    # is wider than the table; the numeric columns keep their width so figures
    # never drift apart between rows.
    INVOICE_FLEX_COLUMNS = INVOICE_FLEX_COLUMNS

    def _fit_invoice_columns(self,width=None):
        """Let the table fill the window width instead of ending mid-screen."""
        tree=getattr(self,'tree',None)
        widths=getattr(self,'_invoice_column_widths',None)
        if not widths or tree is None:return {}
        try:available=int(width if width is not None else tree.winfo_width())
        except (tk.TclError,TypeError,ValueError):return {}
        return fit_invoice_columns(tree,widths,available,getattr(self,'_px',None))

    def _on_invoice_tree_configure(self,event=None):
        """Re-fit the columns once the window has stopped resizing."""
        tree=getattr(self,'tree',None)
        widths=getattr(self,'_invoice_column_widths',None)
        if tree is None or not widths:return
        try:width=int(getattr(event,'width',0) or tree.winfo_width())
        except (tk.TclError,TypeError,ValueError):return
        if width<=1 or width==getattr(self,'_last_invoice_tree_width',None):return
        self._last_invoice_tree_width=width
        pending=getattr(self,'_invoice_fit_job',None)
        if pending is not None:
            try:self.after_cancel(pending)
            except (tk.TclError,ValueError):report_fault()
        px=getattr(self,'_px',None)
        try:self._invoice_fit_job=self.after_idle(lambda:fit_invoice_columns(tree,widths,width,px))
        except tk.TclError:report_fault()

    def _configure_macos_desktop_events(self):
        """Match macOS conventions without changing the cross-platform flow.

        Clicking the Dock icon must bring back a window that was closed to the
        menu bar, and Cmd+Q must be a real exit. Both are native Tk commands
        that only exist on Aqua; elsewhere the methods are simply not called.
        """
        if sys.platform!='darwin':return
        for command,callback in (('tk::mac::ReopenApplication',self.show_from_tray),('tk::mac::Quit',self.quit_app)):
            try:self.createcommand(command,callback)
            except Exception:
                logger.info('macOS desktop event %s is not available in this Tk build',command)

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
        w=self._new_toplevel(_('Om {app_name}',app_name=APP_NAME));w.resizable(True,True);w.configure(bg=window_palette(self)['background'])
        form=self._dialog_form(w,padding=24)
        if self._brand_logo:
            logo_label=ttk.Label(form,image=self._brand_logo)
            logo_label.pack(pady=(0,10))
            reg=getattr(self,'_register_brand_logo_widget',None)
            if callable(reg):reg(logo_label)
        else:
            if self._header_icon:ttk.Label(form,image=self._header_icon).pack(pady=(0,10))
            ttk.Label(form,text=APP_NAME,style='Title.TLabel').pack()
        ttk.Label(form,text=_('Version {version}',version=APP_VERSION),style='Sub.TLabel').pack(pady=(3,12))
        if APP_RELEASE_COMMIT:ttk.Label(form,text=_('Byggcommit: {commit}',commit=APP_RELEASE_COMMIT[:12]),style='Sub.TLabel').pack(pady=(0,8))
        ttk.Label(form,text=_('Lokal app för fakturor och betalningspåminnelser')).pack()
        ttk.Label(form,text=SUPPORTED_PLATFORMS,style='Sub.TLabel').pack(pady=(5,16))
        ttk.Label(form,text=APP_COPYRIGHT).pack()
        ttk.Label(form,text=_('Skapare: {author}',author=APP_AUTHOR)).pack(pady=(4,0))
        ttk.Label(
            form,text=_('Gratis att använda privat och kommersiellt. Ändringar kräver skriftligt tillstånd. Se LICENSE.'),
            wraplength=430,justify='center',style='Sub.TLabel',
        ).pack(pady=(10,0))
        ttk.Button(form,text=_('Stäng'),command=w.destroy,style='Accent.TButton').pack(pady=(20,0))

    def _donation_qr_size(self):
        """Return (pixels, scale) for the Swish code at the current text size.

        The module count comes from a real encode of the default amount, so the
        canvas is the right size even if the payload or the amounts change.
        """
        scale=max(2,int(round(self._px(4))))
        try:modules=len(qr_code.encode(donations.swish_payload(donations.default_amount())))
        except Exception:modules=25
        return (modules+8)*scale,scale

    def _draw_donation_qr(self, amount=None):
        """Draw the standard Swish code on the dialogue's canvas.

        The code is built here and encoded by :mod:`qr_code`, so it works
        offline and never asks anyone else to render it. The canvas is painted
        white first: a QR code must stay dark on light even in high contrast.
        """
        canvas=getattr(self,'donation_canvas',None)
        if canvas is None:return False
        chosen=getattr(self,'donation_amount',donations.default_amount()) if amount is None else amount
        try:
            matrix=qr_code.encode(donations.swish_payload(chosen))
        except Exception:
            logger.exception('The Swish QR code could not be built')
            return False
        quiet=4
        _,scale=self._donation_qr_size()
        total=(len(matrix)+2*quiet)*scale
        try:
            canvas.configure(width=total,height=total)
            canvas.delete('all')
            canvas.create_rectangle(0,0,total,total,fill='#FFFFFF',outline='')
            for row_index,row in enumerate(matrix):
                for column_index,dark in enumerate(row):
                    if not dark:continue
                    x=(column_index+quiet)*scale;y=(row_index+quiet)*scale
                    canvas.create_rectangle(x,y,x+scale,y+scale,fill='#000000',outline='')
        except tk.TclError:
            logger.info('The Swish QR code was not drawn because the dialogue closed')
            return False
        return True

    def _choose_donation_amount(self, amount):
        """Select one of the locked amounts and redraw the code."""
        if not donations.is_fixed_amount(amount):return
        self.donation_amount=amount
        for value,button in getattr(self,'donation_buttons',{}).items():
            try:button.configure(style='Accent.TButton' if value==amount else 'TButton')
            except tk.TclError:report_fault()
        label=getattr(self,'donation_amount_label',None)
        if label is not None:
            try:label.configure(text=_('Valt belopp: {amount} kr',amount=amount))
            except tk.TclError:report_fault()
        self._draw_donation_qr(amount)

    def _copy_swish_number(self):
        """Put the locked Swish number on the clipboard."""
        window=getattr(self,'_donation_window',None)
        target=window if window is not None else self
        try:
            target.clipboard_clear();target.clipboard_append(donations.swish_number())
            self.donation_copy_label.configure(text=_('Numret ligger i urklipp.'))
        except tk.TclError:
            logger.info('The Swish number could not be copied to the clipboard')
        log_activity('donation','copy_number','completed',channel='swish')

    def _open_donation_link(self,url,channel_key):
        """Open one of the locked donation pages, never an arbitrary URL."""
        if not donations.is_locked_address(url):
            logger.warning('Refused to open an unknown donation address: %s',url)
            return False
        try:opened=bool(webbrowser.open(url,new=2))
        except Exception:
            logger.exception('The donation page could not be opened')
            opened=False
        if not opened:
            log_activity('donation','open','error',level=logging.WARNING,channel=channel_key,url=url)
            messagebox.showwarning(_('Kunde inte öppna webbläsaren'),_('Öppna adressen manuellt: {url}',url=url),parent=self)
            return False
        log_activity('donation','open','completed',channel=channel_key,url=url)
        return True

    def _wrap_to_width(self,label,minimum=200,offset=4):
        """Wrap a label to the width it is actually given.

        A fixed ``wraplength`` is a promise the layout cannot keep: a card gets
        narrower when the window or a column shrinks and the last words are
        clipped. The label is packed with ``fill='x'``, so its width is stable
        and the wrap can follow it without fighting back.
        """
        def rewrap(event):
            limit=max(minimum,event.width-offset)
            try:
                if int(label.cget('wraplength'))!=limit:label.configure(wraplength=limit)
            except (tk.TclError,ValueError):report_fault()
        try:label.bind('<Configure>',rewrap)
        except (tk.TclError,AttributeError):report_fault()
        return label

    def _donation_card(self,parent,padx=16,pady=14,side=None,gap=10):
        """Return one raised card on the dialogue background."""
        card=ttk.Frame(parent,style='Card.TFrame',padding=(padx,pady))
        if side is None:card.pack(fill='x',pady=(0,gap))
        else:card.pack(side=side,fill='both',expand=True,padx=(0,gap))
        return card

    def _donation_channel_card(self,parent,channel,title,description,button_text,style,command,gap=10):
        """Add one payment channel as a card with a single large button.

        PayPal and Ko-fi are buttons only. They open the payment page in the
        browser, so no code is drawn for them - a QR belongs to Swish alone.
        """
        card=self._donation_card(parent,side='left',gap=gap)
        ttk.Label(card,text=channel.upper(),style='CardKicker.TLabel').pack(anchor='w')
        ttk.Label(card,text=title,style='CardHeading.TLabel').pack(anchor='w',pady=(2,2))
        description_label=ttk.Label(card,text=description,style='CardSub.TLabel',wraplength=210,justify='left')
        description_label.pack(anchor='w',fill='x');self._wrap_to_width(description_label,minimum=150)
        ttk.Button(card,text=button_text,command=command,style=style).pack(fill='x',pady=(10,0))
        return card

    def show_donations(self):
        """Open the support dialogue: Swish code, PayPal and Ko-fi.

        Every amount and address comes from :mod:`donations`, which has no
        setter and no settings key. Nothing here is editable, and an imported
        backup can never point a donation somewhere else. The layout follows the
        support page: Swish with a real code, the other two channels as buttons.
        """
        existing=getattr(self,'_donation_window',None)
        if existing is not None:
            try:
                existing.deiconify();existing.lift();existing.focus_force()
                return existing
            except tk.TclError:
                report_fault()
        w=self._new_toplevel(_('Stöd PayPamin Flow'))
        self._donation_window=w
        w.resizable(True,True);w.configure(bg=window_palette(self)['background'])
        def close():
            self._donation_window=None
            w.destroy()
        w.protocol('WM_DELETE_WINDOW',close)
        form=self._dialog_form(w,padding=0)
        head=ttk.Frame(form,padding=(24,20,24,12));head.pack(fill='x')
        brand=ttk.Frame(head);brand.pack(anchor='w')
        if self._brand_logo:
            logo_label=ttk.Label(brand,image=self._brand_logo)
            logo_label.pack(side='left',padx=(0,10))
            reg=getattr(self,'_register_brand_logo_widget',None)
            if callable(reg):reg(logo_label)
        elif self._header_icon:ttk.Label(brand,image=self._header_icon).pack(side='left',padx=(0,10))
        titles=ttk.Frame(brand);titles.pack(side='left')
        ttk.Label(titles,text=_('Stöd PayPamin Flow'),style='Title.TLabel').pack(anchor='w')
        ttk.Label(titles,text=_('Gratis · reklamfritt · inga prenumerationer'),style='Sub.TLabel').pack(anchor='w')
        intro=ttk.Label(
            head,
            text=_('Appen är gratis för alla, utan reklam och utan betalvägg. Din gåva går direkt till utvecklingen — nya funktioner, testade flöden och den tid det tar att hålla allt igång. Ingenting låses upp av en gåva, och appen fungerar precis likadant utan.'),
            wraplength=660,justify='left',
        )
        intro.pack(anchor='w',fill='x',pady=(12,0));self._wrap_to_width(intro,minimum=320)
        body=ttk.Frame(form,padding=(24,0,24,0));body.pack(fill='x')
        left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True)
        right=ttk.Frame(body);right.pack(side='left',anchor='n',padx=(16,0))

        # The amount decides the Swish code and the PayPal link, which is why it
        # sits above both. The four amounts are fixed in the code.
        amount_card=self._donation_card(left)
        ttk.Label(amount_card,text=_('Välj belopp'),style='CardKicker.TLabel').pack(anchor='w')
        hint=ttk.Label(amount_card,text=_('Beloppet fylls i Swish-koden och PayPal-länken. Hos betaltjänsten kan du alltid ändra det.'),style='CardSub.TLabel',wraplength=400,justify='left')
        hint.pack(anchor='w',fill='x',pady=(2,8));self._wrap_to_width(hint,minimum=200)
        chips=ttk.Frame(amount_card,style='Card.TFrame');chips.pack(anchor='w')
        self.donation_buttons={}
        for value in donations.amounts():
            button=ttk.Button(chips,text=_('{amount} kr',amount=value),command=lambda amount=value:self._choose_donation_amount(amount))
            button.pack(side='left',padx=(0,6));self.donation_buttons[value]=button
        self.donation_amount_label=ttk.Label(amount_card,text='',style='CardSub.TLabel')
        self.donation_amount_label.pack(anchor='w',pady=(8,0))

        channels=ttk.Frame(left);channels.pack(fill='x')
        self._donation_channel_card(
            channels,'PayPal',_('Engångsgåva i SEK'),
            _('Betalning med kort. Inget konto behövs.'),
            _('Öppna PayPal'),'PayPal.TButton',
            lambda:self._open_donation_link(donations.paypal_link(self.donation_amount),'paypal'),
        )
        self._donation_channel_card(
            channels,'Ko-fi',_('Valfritt belopp, även månadsvis'),
            _('Avsluta när du vill, ingen bindning.'),
            _('Öppna Ko-fi'),'Kofi.TButton',
            lambda:self._open_donation_link(donations.kofi_link(),'kofi'),gap=0,
        )

        # Swish is the only channel with a code, and the code is drawn by the
        # app itself in the standard payload format.
        swish=self._donation_card(right,padx=18,pady=16)
        ttk.Label(swish,text='Swish',style='CardKicker.TLabel').pack(anchor='w')
        ttk.Label(swish,text=_('Skanna med Swish-appen'),style='CardHeading.TLabel').pack(anchor='w',pady=(2,2))
        swish_hint=ttk.Label(swish,text=_('Beloppet är förifyllt och går att ändra i appen. Numret är låst.'),style='CardSub.TLabel',wraplength=230,justify='left')
        swish_hint.pack(anchor='w',fill='x',pady=(0,8));self._wrap_to_width(swish_hint,minimum=120)
        self.donation_canvas=tk.Canvas(swish,width=self._donation_qr_size()[0],height=self._donation_qr_size()[0],highlightthickness=0,bd=0,background='#FFFFFF')
        self.donation_canvas.pack(anchor='w')
        self.donation_number_label=ttk.Label(swish,text=_('Swishnummer: {number}',number=donations.formatted_number()),style='CardBody.TLabel')
        self.donation_number_label.pack(anchor='w',pady=(8,0))
        ttk.Button(swish,text=_('Kopiera nummer'),command=self._copy_swish_number).pack(anchor='w',pady=(4,0))
        self.donation_copy_label=ttk.Label(swish,text='',style='CardSub.TLabel')
        self.donation_copy_label.pack(anchor='w')

        # The story sits under the channels, beside the code, so the dialogue
        # stays short instead of leaving an empty column next to Swish.
        why=self._donation_card(left,padx=24,pady=14,gap=0)
        ttk.Label(why,text=_('Varför din gåva gör skillnad'),style='CardKicker.TLabel').pack(anchor='w')
        ttk.Label(why,text=_('Du stödjer en utvecklare, inte ett bolag.'),style='CardHeading.TLabel').pack(anchor='w',pady=(2,8))
        points=ttk.Frame(why,style='Card.TFrame');points.pack(fill='x')
        for index,(title,text) in enumerate(DONATION_SUPPORT_POINTS):
            column=ttk.Frame(points,style='Card.TFrame')
            column.pack(side='left',fill='both',expand=True,padx=(0,12) if index<len(DONATION_SUPPORT_POINTS)-1 else 0)
            ttk.Label(column,text=_(title),style='CardBody.TLabel').pack(anchor='w',fill='x')
            point=ttk.Label(column,text=_(text),style='CardSub.TLabel',wraplength=155,justify='left')
            point.pack(anchor='w',fill='x');self._wrap_to_width(point,minimum=110)
        trust_points=ttk.Label(why,text=' · '.join(_(item) for item in DONATION_TRUST_POINTS),style='CardSub.TLabel',justify='left')
        trust_points.pack(anchor='w',fill='x',pady=(10,0));self._wrap_to_width(trust_points,minimum=200)
        ttk.Separator(form,orient='horizontal').pack(fill='x',pady=(12,0))
        foot=ttk.Frame(form,padding=(24,10,24,16));foot.pack(fill='x')
        trust=ttk.Label(foot,text=_(DONATION_TRUST_LINE),style='Sub.TLabel',wraplength=660,justify='left')
        trust.pack(anchor='w',fill='x');self._wrap_to_width(trust,minimum=320)
        locked=ttk.Label(foot,text=_('Låst: mottagare, länkar och belopp är fasta i koden och kan inte ändras i appen.'),style='Sub.TLabel',wraplength=660,justify='left')
        locked.pack(anchor='w',fill='x',pady=(6,0));self._wrap_to_width(locked,minimum=320)
        ttk.Label(foot,text=_('{copyright} · Skapare: {author}',copyright=APP_COPYRIGHT,author=APP_AUTHOR),style='Sub.TLabel').pack(anchor='w',pady=(6,10))
        buttons=ttk.Frame(foot);buttons.pack(fill='x')
        ttk.Button(buttons,text=_('Stäng'),command=close,style='Accent.TButton').pack(side='right')
        self.donation_amount=donations.default_amount()
        self._choose_donation_amount(donations.default_amount())
        log_activity('donation','dialogue_opened','completed',amount=self.donation_amount)
        return w

    def _run_scheduled_update_check(self):
        if not ui_is_alive(self):return
        try:
            if setting('update_auto')=='1':self.check_for_updates(manual=False)
        except tk.TclError:
            logger.info('Scheduled update check stopped because the window closed')
            return
        try:self.after(UPDATE_CHECK_INTERVAL_MS,self._run_scheduled_update_check)
        except tk.TclError:report_fault()

    def _update_button_idle_text(self):
        return _('Uppdatering tillgänglig') if getattr(self,'_available_update',None) is not None else _('Uppdatera appen')

    def _update_button_style(self):
        """Only a real update draws the accent; a routine check stays quiet."""
        return 'Accent.TButton' if getattr(self,'_available_update',None) is not None else 'TButton'

    def _restyle_update_button(self):
        return restyle_update_button(self)

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
        except tk.TclError:report_fault()
        restyle_update_button(self)

    def _set_update_check_busy(self,busy):
        self._refresh_tray_menu()
        button=getattr(self,'update_button',None)
        if not button:return
        try:button.configure(text=_('Söker…') if busy else self._update_button_idle_text(),state='disabled' if busy else 'normal')
        except tk.TclError:report_fault()
        if not busy:restyle_update_button(self)

    def _set_update_install_busy(self,busy,stage=None):
        if busy and stage:self._update_install_stage=stage
        elif not busy:self._update_install_stage=None
        self._refresh_tray_menu()
        button=getattr(self,'update_button',None)
        if not button:return
        labels={'download':_('Hämtar och verifierar…'),'install':_('Installerar filer…'),'restart':_('Startar om…')}
        text=labels.get(getattr(self,'_update_install_stage',None),_('Uppdaterar…')) if busy else self._update_button_idle_text()
        try:button.configure(text=text,state='disabled' if busy else 'normal')
        except tk.TclError:report_fault()
        if not busy:restyle_update_button(self)

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
            try:
                release=fetch_latest_release()
                # The version is compared first; for the same version the files
                # in the release are compared with the installed ones, so a
                # rebuilt 0.6.0 is still offered.
                try:release=evaluate_release(release)
                except Exception:logger.exception('Release content could not be compared')
                result_queue.put(('ok',manual,release))
            except Exception as exc:result_queue.put(('error',manual,exc))
        threading.Thread(target=check,daemon=True).start()
        log_activity('update','check_requested','completed',manual=manual,force=force,cached=False)
        self.after(200,lambda:self._poll_update_check(result_queue))

    def _poll_update_check(self,result_queue):
        if not ui_is_alive(self):
            logger.info('Update check result discarded because the window closed')
            return
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
            log_activity('update','check_finished','update_available',manual=manual,version=release.version,release_id=release.release_id,commit=release.release_commit,content=release.content_state,changed_files=list(release.changed_files),missing_assets=missing)
            logger.info('New PayPamin Flow release available: current=%s latest=%s release_id=%s commit=%s content=%s changed_files=%s missing_assets=%s',APP_VERSION,release.version,release.release_id,release.release_commit,release.content_state,','.join(release.changed_files[:12]) or '-',missing)
            if missing:
                logger.warning('Release package is not ready; automatic installation waits')
                if manual:self.show_update_available(release)
                return
            if manual:self.show_update_available(release)
            elif setting('update_auto')=='1' and not update_is_manual_only(self):
                self.start_update_installation(release,manual=False)
            elif setting('update_auto')=='1':
                logger.info('Automatic installation skipped: the running files are a source checkout')
            return
        self._set_update_available(None)
        log_activity('update','check_finished','current',manual=manual,version=release.version,release_id=release.release_id,commit=release.release_commit,content=release.content_state)
        logger.info('No newer PayPamin Flow release: current=%s latest=%s content=%s',APP_VERSION,release.version,release.content_state or 'not compared')
        if manual:
            commit=release.release_commit[:12] or APP_RELEASE_COMMIT[:12] or _('okänd')
            messagebox.showinfo(_('Ingen uppdatering tillgänglig'),self._no_update_message(release,commit),parent=self)

    def _no_update_message(self,release,commit):
        """Explain what was compared, so "no update" is a fact and not a guess."""
        if release.content_state==CONTENT_CURRENT:
            reason=_('Filerna i releasen är identiska med de installerade.')
        elif release.content_state==CONTENT_STALE:
            reason=_('Dina filer är nyare än releasen, så det finns inget att hämta därifrån.')
        elif release.content_state==CONTENT_UNAVAILABLE:
            reason=_('Filerna i releasen kunde inte jämföras just nu; versionen och commiten jämfördes i stället.')
        else:
            reason=_('Ingen ny version eller ändrade releasefiler finns.')
        return _('{reason}\n\nInstallerad version: {current}\nSenaste release: {latest}\nRelease-commit: {commit}',reason=reason,current=APP_VERSION,latest=release.version,commit=commit)

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
                plan=stage_update(release,log_path=LOG_PATH)
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
        if not ui_is_alive(self):
            logger.info('Update installation result discarded because the window closed')
            return
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
        w=self._new_toplevel(_('Uppdatering tillgänglig'));w.resizable(True,True);w.configure(bg=window_palette(self)['background'])
        form=ttk.Frame(w,padding=24);form.pack()
        heading=_('Uppdaterat bygge av version {version} är tillgänglig',version=release.version) if release.version==APP_VERSION else _('Version {version} är tillgänglig',version=release.version)
        ttk.Label(form,text=heading,style='Title.TLabel').pack(anchor='w')
        change_labels={'version':_('Ny programversion'),'commit':_('Ny commit'),'files':_('Ändrade appfiler'),'source':_('Ny källkod i releasen'),'commit_and_files':_('Ny commit och ändrade appfiler'),'release':_('Nytt release-bygge')}
        change=change_labels[update_change_kind(release)]
        current_commit=APP_RELEASE_COMMIT[:12] or _('okänd');release_commit=release.release_commit[:12] or _('okänd')
        ttk.Label(form,text=_('Installerad version: {current}\nSenaste release: {latest}',current=APP_VERSION,latest=release.version),justify='left').pack(anchor='w',pady=(8,4))
        ttk.Label(form,text=_('Typ av uppdatering: {change}',change=change),justify='left').pack(anchor='w',pady=(0,4))
        # The files that actually differ, so the reason is visible and not
        # something the user has to take on faith.
        if release.changed_files:
            files=update_state.describe_files(release.changed_files)
            ttk.Label(form,text=_('Ändrade filer: {files}',files=files),style='Sub.TLabel',wraplength=520,justify='left').pack(anchor='w',pady=(0,4))
        ttk.Label(form,text=_('Installerad commit: {current}\nRelease-commit: {latest}',current=current_commit,latest=release_commit),style='Sub.TLabel',justify='left').pack(anchor='w',pady=(0,8))
        if update_is_manual_only(self):
            ttk.Label(form,text=_('Du kör en källkopia. Releasen är normalt äldre än dina filer, så en installation ersätter appfilerna med releasens version.'),style='Sub.TLabel',wraplength=520,justify='left').pack(anchor='w',pady=(0,8))
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
        button=getattr(self,'clear_search_button',None)
        if button is not None:
            try:button.state(['!disabled'] if query else ['disabled'])
            except tk.TclError:report_fault()
        log_activity('ui','invoice_search_changed','completed',query=query)
        self.refresh()

    def clear_invoice_search(self):
        """Empty the search field and show the whole selected tab again."""
        variable=getattr(self,'invoice_search_var',None)
        if variable is None:return False
        if not variable.get():return False
        variable.set('')
        focus=getattr(self,'invoice_search',None)
        if focus is not None:
            try:focus.focus_set()
            except tk.TclError:report_fault()
        log_activity('ui','invoice_search_cleared','completed')
        return True

    def show_search_help(self):
        """Explain the search syntax with examples that really work."""
        examples='\n'.join(f'    {example}' for example in SEARCH_HELP_EXAMPLES)
        body=_(
            'Skriv ett eller flera ord. Alla ord måste finnas, men de kan finnas i olika fält.\n\n'
            'Fälten som söks: kund, fakturanummer, belopp, datum, status, e-post, fakturatext och valuta.\n\n'
            'Begränsa ett ord till ett fält med ett prefix:\n{examples}\n\n'
            'Ett citattecken håller ihop ett namn med mellanslag: kund:"Acme AB".\n'
            'Esc tömmer sökfältet.',
            examples=examples,
        )
        messagebox.showinfo(_('Sökhjälp'),body,parent=self)
        log_activity('ui','invoice_search_help_opened','completed')

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

    def update_python_addons(self):
        """Offer an explicit add-on upgrade in the current Python environment."""
        if getattr(self,'_python_addon_install_running',False):
            messagebox.showinfo(
                _('Uppdatera Python-tillägg'),
                _('Python-tillägg uppdateras eller installeras redan.'),
                parent=self,
            )
            return False
        confirmed=messagebox.askyesno(
            _('Uppdatera Python-tillägg'),
            _('Vill du uppdatera appens Python-tillägg i befintlig Python-miljö? Ingen ny Python-runtime eller virtuell miljö installeras. Fakturor och inställningar ändras inte.'),
            parent=self,
        )
        if not confirmed:return False
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
                logger.info('User-confirmed Python add-on update completed in the existing environment')
                messagebox.showinfo(
                    _('Tillägg uppdaterade'),
                    _('Python-tilläggen har uppdaterats. Starta om appen för att använda de nya versionerna.'),
                    parent=self,
                )
            else:
                logger.error('User-confirmed Python add-on update failed: %s',details[-1200:])
                messagebox.showerror(_('Kunde inte uppdatera Python-tillägg'),_('Python-tilläggen kunde inte uppdateras. Appen fortsätter med befintliga tillägg. Kontrollera internetanslutning och pip.\n\n')+details[-1200:],parent=self)
        self.after(350,poll)
        return True

    def _display_scale(self):
        """Return how many physical pixels one 96-DPI design pixel occupies."""
        try:dpi=float(self.winfo_fpixels('1i'))
        except Exception:return 1.0
        if dpi<=0:return 1.0
        return max(1.0,min(4.0,round(dpi/96.0,2)))

    def _px(self,value):
        """Scale a 96-DPI design pixel to the display and the chosen text size."""
        try:factor=float(self.dpi_scale)
        except (AttributeError,TypeError):factor=1.0
        try:text=float(self.ui_font_scale)
        except (AttributeError,TypeError):text=1.0
        return max(1,int(round(abs(float(value))*factor*text)))

    def _ui_font_family(self):
        """Pick one UI font that this desktop really has, rather than a guess."""
        try:families=tkfont.families(self)
        except Exception:families=()
        default=tkfont.nametofont('TkDefaultFont').cget('family')
        return choose_font_family(families,fallback=default) or default

    def _palette(self):
        """Return the colours the window should be painted with right now."""
        return window_palette(self)

    def _style(self):
        s=ttk.Style(self); s.theme_use('clam')
        self.font_family=self._ui_font_family()
        self.ui_font_scale=normalize_font_scale(setting(FONT_SCALE_SETTING))
        self._high_contrast=system_high_contrast()
        self._theme_setting=appearance.normalize_theme(setting(appearance.THEME_SETTING))
        self._theme=appearance.effective_theme(self._theme_setting)
        self._accessibility_style=AccessibleStyle(s,tkfont,self.font_family)
        self._accessibility_style.apply(
            self.ui_font_scale,high_contrast=self._high_contrast,
            pixel_scale=self.dpi_scale,theme=self._theme,
        )

    def set_theme(self,value,persist=True):
        """Switch between the light and dark theme without rebuilding the UI.

        Every colour in the app comes from one palette, so a theme change is a
        repaint: the ttk styles, the invoice row tints, the classic Tk widgets
        and the open windows all move together, and nothing is left half dark.
        """
        self._theme_setting=appearance.normalize_theme(value)
        self._theme=appearance.effective_theme(self._theme_setting)
        if persist:
            set_setting(appearance.THEME_SETTING,self._theme_setting)
            refresh_json_journal(parent=self)
        repaint_app_palette(self)
        logger.info('UI theme changed: choice=%s applied=%s',self._theme_setting,self._theme)
        log_activity('ui','theme_changed','completed',choice=self._theme_setting,theme=self._theme)
        return self._theme

    def _apply_accessibility_palette(self):
        """Re-style open windows after a theme or high-contrast change."""
        repaint_app_palette(self)

    def _poll_system_contrast(self):
        """Follow the desktop's high-contrast flag and, if chosen, its theme."""
        if getattr(self,'_quitting',False) or getattr(self,'_contrast_check_running',False):return
        if getattr(self,'_window_hidden',False):
            try:self.after(SYSTEM_CONTRAST_POLL_INTERVAL_MS,self._poll_system_contrast)
            except tk.TclError:report_fault()
            return
        self._contrast_check_running=True
        follow_system=getattr(self,'_theme_setting',appearance.DEFAULT_THEME)==appearance.THEME_SYSTEM
        result_queue=queue.Queue()
        def check():
            try:enabled=system_high_contrast()
            except Exception:enabled=getattr(self,'_high_contrast',False)
            system=None
            if follow_system:
                try:system=appearance.system_theme()
                except Exception:system=None
            result_queue.put((enabled,system))
        threading.Thread(target=check,daemon=True).start()
        def poll():
            if getattr(self,'_quitting',False):return
            try:enabled,system=result_queue.get_nowait()
            except queue.Empty:
                try:self.after(100,poll)
                except tk.TclError:report_fault()
                return
            self._contrast_check_running=False
            changed=False
            if enabled!=getattr(self,'_high_contrast',False):
                self._high_contrast=enabled
                changed=True
                logger.info('System high-contrast mode changed: enabled=%s',enabled)
            if system is not None:
                resolved=appearance.effective_theme(self._theme_setting,system)
                if resolved!=getattr(self,'_theme','light'):
                    self._theme=resolved
                    changed=True
                    logger.info('Desktop theme changed: choice=%s applied=%s',self._theme_setting,resolved)
            if changed:self._apply_accessibility_palette()
            try:self.after(SYSTEM_CONTRAST_POLL_INTERVAL_MS,self._poll_system_contrast)
            except tk.TclError:report_fault()
        poll()

    def set_font_scale(self,value,persist=True):
        """Apply a bounded text zoom immediately without rebuilding open dialogs."""
        self.ui_font_scale=normalize_font_scale(value)
        if persist:
            set_setting(FONT_SCALE_SETTING,font_scale_storage(self.ui_font_scale))
            refresh_json_journal(parent=self)
        style=getattr(self,'_accessibility_style',None)
        if style is not None:
            style.apply(
                self.ui_font_scale,high_contrast=getattr(self,'_high_contrast',False),
                pixel_scale=getattr(self,'dpi_scale',1.0),theme=getattr(self,'_theme','light'),
            )
        tree=getattr(self,'tree',None)
        if tree is not None:
            for column,width in getattr(self,'_invoice_column_widths',{}).items():
                try:tree.column(column,width=self._px(width))
                except tk.TclError:report_fault()
            self._fit_invoice_columns()
        scale_var=getattr(self,'_font_scale_var',None)
        if scale_var is not None:
            try:scale_var.set(font_scale_label(self.ui_font_scale))
            except tk.TclError:report_fault()
        help_label=getattr(self,'_keyboard_help_scale_label',None)
        if help_label is not None:
            try:help_label.configure(text=_('Textstorlek: {scale}. Alla kontroller nås med Tab och har synlig fokusmarkering.',scale=font_scale_label(self.ui_font_scale)))
            except tk.TclError:report_fault()
        high_contrast=getattr(self,'_high_contrast',False)
        theme=getattr(self,'_theme','light')
        for window in [self]+[child for child in self.winfo_children() if child.winfo_class()=='Toplevel']:
            apply_widget_contrast(window,high_contrast,theme)
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
            # A callback that answers False wants the key to keep its normal
            # meaning in the widget (Ctrl+Z inside a text field, for instance).
            return 'break' if callback() is not False else None
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
            bind(f'<{modifier}-z>',self.undo_last_delete)
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
        except tk.TclError:report_fault()
        menu.tk_popup(self.winfo_rootx()+12,self.winfo_rooty()+30)
        try:menu.grab_release()
        except tk.TclError:report_fault()
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
            except tk.TclError:report_fault()
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
            except tk.TclError:report_fault()
        previous_grab=self.grab_current() or None
        w=self._new_toplevel(_('Kortkommandon och tillgänglighet'));w.resizable(True,True);w.configure(bg=window_palette(self)['background'])
        self._keyboard_help_window=w
        def close_help():
            w.destroy()
            if previous_grab is not None:
                try:
                    if previous_grab.winfo_exists():previous_grab.grab_set()
                except (tk.TclError,AttributeError):report_fault()
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
            (_('Ångra senaste borttagning'),f'{modifier}+Z'),
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
        file_menu.add_command(label=_('Exportera reskontra'),command=self.export_ledger)
        file_menu.add_command(label=_('Öppna exportmapp'),command=self.open_export_folder)
        file_menu.add_command(label=_('Exportera listan till CSV'),command=self.export_invoices_csv)
        file_menu.add_command(label=_('Öppna tryckfiler'),command=self.open_print_folder)
        file_menu.add_command(label=_('Öppna logotypmapp'),command=self.open_svg_folder)
        file_menu.add_command(label=_('Rensa cache nu'),command=self.clear_cache_now)
        file_menu.add_separator()
        file_menu.add_command(label=_('Papperskorg'),command=self.show_trash)
        file_menu.add_separator()
        file_menu.add_command(label=_('Dölj i systemfältet'),command=self.hide_to_tray)
        file_menu.add_command(label=_('Avsluta helt'),command=self.quit_app)
        menu.add_cascade(label=_('Arkiv'),menu=file_menu)
        help_menu=tk.Menu(menu,tearoff=0)
        self.help_menu=help_menu
        help_menu.add_command(label=_('Visa samlad fellogg'),command=self.open_log)
        help_menu.add_command(label=_('Hantera aktiva fel…'),command=self.manage_error_log)
        help_menu.add_command(label=_('Markera fellogg som åtgärdad'),command=self.resolve_error_log)
        help_menu.add_command(label=_('Visa teknisk logg'),command=self.open_technical_log)
        help_menu.add_command(label=_('Visa aktivitetslogg'),command=self.open_activity_log)
        help_menu.add_command(label=_('Öppna loggmappen'),command=self.open_log_folder)
        help_menu.add_command(label=_('Uppdatera appen'),command=lambda:self.check_for_updates(manual=True))
        help_menu.add_command(label=_('Uppdatera Python-tillägg'),command=self.update_python_addons)
        help_menu.add_command(label=_('Kortkommandon och tillgänglighet'),command=self.show_keyboard_help,accelerator='F1')
        help_menu.add_command(label=_('Stöd PayPamin Flow'),command=self.show_donations)
        help_menu.add_command(label=_('Om {app_name}',app_name=APP_NAME),command=self.show_about)
        menu.add_cascade(label=_('Hjälp'),menu=help_menu)
        self._apply_menu_icons(file_menu);self._apply_menu_icons(help_menu);self._apply_menu_icons(menu)
        self._instrument_menu_actions(file_menu);self._instrument_menu_actions(help_menu);self._instrument_menu_actions(menu)
        self.configure(menu=menu)

    def build(self):
        self._build_menu()
        background=window_palette(self)['background']
        header=ttk.Frame(self,padding=(24,18,24,12)); header.pack(fill='x')
        # The brand band is painted by Tk itself, so the two image labels keep
        # their own reference: a theme change repaints them with the window.
        self._header_backgrounds=[]
        if self._brand_logo:
            label=tk.Label(header,image=self._brand_logo,bg=background,borderwidth=0)
            label.pack(side='left',padx=(0,10))
            self._header_backgrounds.append(label)
            reg=getattr(self,'_register_brand_logo_widget',None)
            if callable(reg):reg(label)
        else:
            if self._header_icon:
                label=tk.Label(header,image=self._header_icon,bg=background,borderwidth=0)
                label.pack(side='left',padx=(0,12))
                self._header_backgrounds.append(label)
            ttk.Label(header,text=APP_NAME,style='Title.TLabel').pack(side='left')
        # The tagline is centred against the wordmark instead of being pushed
        # down by its own padding, so the brand band has one baseline.
        ttk.Label(header,text=_('Lokal app · dina filer stannar på datorn'),style='Sub.TLabel').pack(side='left',padx=(18,0))
        ttk.Button(header,text=_('Inställningar'),command=self.settings).pack(side='right')
        # A hairline under the brand band separates it from the work without
        # boxing the window in.
        ttk.Separator(self).pack(fill='x')
        ttk.Button(header,text=_('Om {app_name}',app_name=APP_NAME),command=self.show_about).pack(side='right',padx=(0,8))
        self.update_button=ttk.Button(header,text=self._update_button_idle_text(),command=lambda:self.check_for_updates(manual=True),style=self._update_button_style())
        self.update_button.pack(side='right',padx=(0,8))
        if self._update_install_running:self._set_update_install_busy(True)
        elif self._update_check_running:self._set_update_check_busy(True)
        def _bind_wrapping_action_bar(bar,buttons):
            last_sig=[None]
            def reflow(_event=None):
                try:avail=int(bar.winfo_width())
                except Exception:avail=0
                if avail<=60:
                    try:avail=max(640,int(self.winfo_width())-48)
                    except Exception:avail=1200
                gap=8
                row_idx=0;col_idx=0;used=0;placements=[]
                for btn in buttons:
                    try:req=max(76,int(btn.winfo_reqwidth()))
                    except Exception:req=128
                    if col_idx>0 and used+req+gap>avail:
                        row_idx+=1;col_idx=0;used=0
                    placements.append((btn,row_idx,col_idx))
                    used+=req+gap
                    col_idx+=1
                sig=tuple((r,c) for _b,r,c in placements)
                if sig==last_sig[0]:return
                last_sig[0]=sig
                for btn,r,c in placements:
                    btn.grid(row=r,column=c,sticky='w',padx=(0,gap),pady=(0,4))
            reflow()
            bar.bind('<Configure>',reflow,add='+')

        primary_actions=[('Skanna importmapp',self.scan_import_folder,'Accent.TButton'),('Öppna importmapp',self.open_import_folder,'TButton'),('Öppna exportmapp',self.open_export_folder,'TButton'),('Exportera reskontra',self.export_ledger,'TButton'),('Lägg till faktura-PDF',self.import_invoice,'TButton'),('Lägg till manuellt',self.add_invoice,'TButton'),('Skapa påminnelse',self.make_reminder,'TButton')]
        secondary_actions=[('Redigera P1',self.edit_p1,'TButton'),('Redigera P2',self.edit_p2,'TButton'),('Markera som betald',self.mark_invoice_paid,'TButton'),('Ångra betalmarkering',self.undo_invoice_paid,'TButton'),('Ignorera / återaktivera',self.toggle_ignore,'TButton'),('Redigera vald',self.edit_invoice,'TButton'),('Visa samlad fellogg',self.open_log,'TButton')]
        for actions,padding in ((primary_actions,(24,7,24,5)),(secondary_actions,(24,0,24,14))):
            bar=ttk.Frame(self,padding=padding);bar.pack(fill='x')
            bar_buttons=[ttk.Button(bar,text=_(key),command=cmd,style=style) for key,cmd,style in actions]
            _bind_wrapping_action_bar(bar,bar_buttons)
        controls=ttk.Frame(self,padding=(22,0,22,8));controls.pack(fill='x')
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
        # The search gets its own row: the tabs keep their width in a narrow
        # window, and the result count sits right beside the field that caused
        # it instead of disappearing under the buttons.
        searchrow=ttk.Frame(self,padding=(22,0,22,4));searchrow.pack(fill='x')
        self.search_status=ttk.Label(searchrow,text='',style='Sub.TLabel',justify='left',anchor='w')
        self.search_status.pack(side='left',fill='x',expand=True)
        ttk.Button(searchrow,text=_('Sökhjälp'),command=self.show_search_help).pack(side='right')
        # Clearing is a visible action, not something to be guessed, and it is
        # disabled when there is nothing to clear.
        self.clear_search_button=ttk.Button(searchrow,text=_('Rensa'),command=self.clear_invoice_search,state='disabled')
        self.clear_search_button.pack(side='right',padx=(6,0))
        self.invoice_search_var=tk.StringVar()
        search=ttk.Entry(searchrow,textvariable=self.invoice_search_var,width=26)
        self.invoice_search=search
        search.pack(side='right',padx=(0,6))
        search.bind('<Escape>',lambda event:self.clear_invoice_search())
        ttk.Label(searchrow,text=_('Sök:')).pack(side='right',padx=(10,6))
        self.invoice_search_var.trace_add('write',self.on_invoice_search)
        wrap=ttk.Frame(self,padding=(22,8,22,12));wrap.pack(fill='both',expand=True)
        cols=('invoice_no','customer','due_date','amount','remaining','p1_date','p2_send_date','email_status','stage','fee')
        self.tree=ttk.Treeview(wrap,columns=cols,show='headings',selectmode='browse')
        configure_invoice_row_colors(self.tree,getattr(self,'_high_contrast',False),getattr(self,'_theme','light'))
        labels={'invoice_no':_('Fakturanr'),'customer':_('Kund'),'due_date':_('Förfallodatum'),'amount':_('Fakturabelopp'),'remaining':_('Kvar att betala'),'p1_date':_('P1 skapades'),'p2_send_date':_('P2-datum'),'email_status':_('E-post (senaste)'),'stage':_('Status / nästa steg'),'fee':_('Påminnelseavgift')}
        widths={'invoice_no':110,'customer':170,'due_date':105,'amount':115,'remaining':120,'p1_date':105,'p2_send_date':125,'email_status':190,'stage':180,'fee':120}
        # Money reads down a column: the amount columns end at the same edge,
        # and every heading sits over the text it describes instead of floating
        # in the middle of the cell.
        numeric_columns={'amount','remaining','fee'}
        self._invoice_column_widths=widths.copy()
        self._invoice_column_labels=labels.copy()
        for c in cols:
            anchor='e' if c in numeric_columns else 'w'
            self.tree.heading(c,text=labels[c],anchor=anchor,command=lambda column=c:self.sort_invoice_column(column))
            self.tree.column(c,width=self._px(widths[c]),anchor=anchor)
        self.tree.pack(side='top',fill='both',expand=True); sb=ttk.Scrollbar(wrap,orient='vertical',command=self.tree.yview);sb.pack(side='right',fill='y');xsb=ttk.Scrollbar(wrap,orient='horizontal',command=self.tree.xview);xsb.pack(side='bottom',fill='x');self.tree.configure(yscrollcommand=sb.set,xscrollcommand=xsb.set)
        self.tree.bind('<Configure>',self._on_invoice_tree_configure,add='+')
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.show_detail())
        self.tree.bind('<Delete>',lambda e:self.delete_invoice())
        self.tree.bind('<Shift-F10>',self.show_selected_row_context_menu)
        self.tree.bind('<App>',self.show_selected_row_context_menu)
        self.tree.bind('<Button-3>',self.show_row_context_menu)
        self.tree.bind('<Button-2>',self.show_row_context_menu)
        enable_treeview_features(
            self.tree,
            cols,
            labels,
            initial_sort=self.invoice_sort_column,
            initial_reverse=self.invoice_sort_reverse,
            on_sort=self.sort_invoice_column,
            order_setting_key='invoice_column_order',
        )
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
        # The undo offer lives above the footer and is only packed while it is
        # relevant: a delete always leaves a visible way back, without a dialog
        # that has to be answered before anything else can be done.
        self.undo_bar=ttk.Frame(self,padding=(22,4,22,4))
        self.undo_label=ttk.Label(self.undo_bar,text='',style='Sub.TLabel',justify='left')
        self.undo_label.pack(side='left',fill='x',expand=True)
        ttk.Button(self.undo_bar,text=_('Öppna papperskorgen'),command=self.show_trash).pack(side='right',padx=(7,0))
        ttk.Button(self.undo_bar,text=_('Ångra'),command=self.undo_last_delete,style='Accent.TButton').pack(side='right')
        foot=ttk.Frame(self,padding=(22,0,22,12));foot.pack(fill='x')
        self._footer=foot
        # Two rows keep every word readable: the defaults summary never has to
        # fight the buttons for horizontal space, not even at the smallest
        # allowed window size or the largest text zoom.
        summary=ttk.Label(foot,text=self._defaults_summary_text(),style='Sub.TLabel',justify='left')
        summary.pack(anchor='w',fill='x')
        def wrap_summary(event):
            """Wrap instead of clipping when the window is narrow."""
            limit=max(240,event.width-4)
            try:
                if int(summary.cget('wraplength'))!=limit:summary.configure(wraplength=limit)
            except (tk.TclError,ValueError):report_fault()
        summary.bind('<Configure>',wrap_summary)
        row=ttk.Frame(foot);row.pack(fill='x',pady=(6,0))
        ttk.Button(row,text=_('Ta bort vald'),command=self.delete_invoice,style='Danger.TButton').pack(side='left')
        # Both ways out are visible here, so closing to the tray is a choice
        # rather than something the user has to discover in a menu.
        ttk.Button(row,text=_('Avsluta helt'),command=self.confirm_quit).pack(side='right')
        ttk.Button(row,text=_('Dölj i systemfältet'),command=self.hide_to_tray).pack(side='right',padx=(0,7))
        self._footer_summary=summary
        ttk.Label(self,text=_('{copyright} · Skapare: {author}',copyright=APP_COPYRIGHT,author=APP_AUTHOR),padding=(24,0,24,9),style='Sub.TLabel').pack(fill='x')
        self._finalize_window_actions(self,main_window=True)

    def export_records(self,visible):
        """Turn the visible rows into the plain values a CSV file holds."""
        records=[]
        for r,stage,remain in visible:
            records.append({
                'invoice_no':r['invoice_no'],
                'customer':r['customer'],
                'invoice_date':r['invoice_date'] or '',
                'due_date':r['due_date'],
                'amount':float(r['amount'] or 0),
                'currency':r['currency'],
                'paid':float(r['paid'] or 0),
                'balance':remain,
                'stage':(_('IGNORERAD')+' · ' if r['ignored'] else '')+_(stage),
                'p1_date':r['p1_date'] or '',
                'p2_date':r['p2_date'] or '',
                'fee':charged_fee_for(r) if r['p1_date'] else '',
                'email_status':reminder_email_status(r),
                'note':r['note'] or '',
            })
        return records

    def export_invoices_csv(self):
        """Write the list as it looks right now to a CSV file."""
        view=invoice_view(*current_view_options(self))
        visible=view[0]
        if not visible:
            messagebox.showinfo(_('Inget att exportera'),_('Listan är tom, så det finns ingenting att exportera.'),parent=self)
            return None
        selected=filedialog.asksaveasfilename(
            parent=self,title=_('Exportera till CSV'),initialdir=str(EXPORT_DIR),
            initialfile=invoice_export.suggested_name(),defaultextension='.csv',
            filetypes=[(_('CSV-fil'),'*.csv'),(_('Alla filer'),'*.*')],
        )
        if not selected:return None
        records=self.export_records(visible)
        columns=[(key,_(label)) for key,label in invoice_export.COLUMNS]
        try:
            written=invoice_export.write(selected,records,columns)
        except OSError as exc:
            logger.error('CSV export failed: %s',exc)
            messagebox.showerror(_('Kunde inte exportera'),_('CSV-filen kunde inte skrivas: {error}',error=exc),parent=self)
            return None
        log_activity('invoice','csv_exported','completed',count=written,path=str(selected))
        if written==1:summary=_('1 faktura exporterad till:\n{path}',path=selected)
        else:summary=_('{count} fakturor exporterade till:\n{path}',count=written,path=selected)
        messagebox.showinfo(
            _('CSV-filen är klar'),
            summary+'\n\n'+_('Filen innehåller listan som den ser ut nu: flik, sökning och sortering.'),
            parent=self,
        )
        return Path(selected)

    def ledger_export_records(self,scope='all'):
        """Build complete ledger records including reminder counts and all dates."""
        flt,query,sort_col,sort_rev=current_view_options(self)
        if scope=='view':
            selected_rows=invoice_view(flt,query,sort_col,sort_rev)[0]
        else:
            all_rows=invoice_view('all','',sort_col,sort_rev)[0]
            if scope=='open':
                selected_rows=[(r,stage,remain) for r,stage,remain in all_rows if remain>0.005 and not r['ignored']]
            elif scope=='reminded':
                selected_rows=[(r,stage,remain) for r,stage,remain in all_rows if ledger_export.reminder_count_for(r)>0]
            else:
                selected_rows=all_rows
        records=[]
        for r,stage,remain in selected_rows:
            records.append({
                'invoice_no':r['invoice_no'],
                'customer':r['customer'],
                'invoice_date':r['invoice_date'] or '',
                'due_date':r['due_date'] or '',
                'amount':float(r['amount'] or 0),
                'paid':float(r['paid'] or 0),
                'balance':remain,
                'currency':r['currency'] or 'SEK',
                'fee':charged_fee_for(r) if r['p1_date'] else '',
                'payment_status':ledger_export.payment_status_label(r),
                'stage':(_('IGNORERAD')+' · ' if r['ignored'] else '')+_(stage),
                'reminder_count':ledger_export.reminder_count_for(r),
                'p1_date':r['p1_date'] or '',
                'p1_sent_date':str(row_value(r,'p1_sent_date','') or ''),
                'p2_date':r['p2_date'] or '',
                'p2_sent_date':str(row_value(r,'p2_sent_date','') or ''),
                'latest_reminder_date':ledger_export.latest_reminder_date_for(r),
                'paid_date':ledger_export.paid_date_for(r),
                'ledger_last_seen':str(row_value(r,'ledger_last_seen','') or ''),
                'note':r['note'] or '',
            })
        return records

    def _choose_ledger_export_scope(self):
        """Ask which invoices should be included in the ledger export."""
        chosen={'scope':None}
        w=self._new_toplevel(_('Exportera reskontra'))
        form=self._dialog_form(w,padding=20)
        ttk.Label(form,text=_('Välj vilka fakturor som ska ingå i reskontraexporten:')).pack(anchor='w',pady=(0,10))
        scope_var=tk.StringVar(value='all')
        options=(
            ('all',_('Hela reskontran (öppna och betalda fakturor)')),
            ('open',_('Endast öppna / obetalda fakturor')),
            ('reminded',_('Endast fakturor med påminnelser')),
            ('view',_('Aktuell vy och sökning')),
        )
        for code,label in options:
            ttk.Radiobutton(form,text=label,value=code,variable=scope_var).pack(anchor='w',pady=3)
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(14,0))
        def confirm():
            chosen['scope']=scope_var.get()
            w.destroy()
        ttk.Button(buttons,text=_('Exportera…'),command=confirm,style='Accent.TButton').pack(side='right')
        ttk.Button(buttons,text=_('Avbryt'),command=w.destroy).pack(side='right',padx=(0,8))
        prep=getattr(self,'_prepare_modal_toplevel',None)
        if callable(prep):prep(w)
        else:w.grab_set()
        w.wait_window()
        return chosen['scope']

    def export_ledger(self,scope=None,target_path=None):
        """Export the customer ledger with reminder counts and dates (CSV or PDF)."""
        chosen_scope=scope or self._choose_ledger_export_scope()
        if not chosen_scope:return None
        records=self.ledger_export_records(chosen_scope)
        if not records:
            messagebox.showinfo(_('Inget att exportera'),_('Det finns inga fakturor i det valda reskontraurvalet.'),parent=self)
            return None
        EXPORT_DIR.mkdir(parents=True,exist_ok=True)
        selected=str(target_path) if target_path else filedialog.asksaveasfilename(
            parent=self,title=_('Exportera reskontra'),initialdir=str(EXPORT_DIR),
            initialfile=ledger_export.suggested_name(scope=chosen_scope),
            defaultextension='.csv',
            filetypes=[(_('CSV-fil (Excel)'),'*.csv'),(_('PDF-rapport'),'*.pdf'),(_('Alla filer'),'*.*')],
        )
        if not selected:return None
        columns=[(key,_(label)) for key,label in ledger_export.COLUMNS]
        try:
            written=ledger_export.write(selected,records,columns=columns,title=_('Kundreskontra — PayPamin Flow'))
        except OSError as exc:
            logger.error('Ledger export failed: %s',exc)
            messagebox.showerror(_('Kunde inte exportera'),_('Reskontrafilen kunde inte skrivas: {error}',error=exc),parent=self)
            return None
        stats=ledger_export.summary_stats(records)
        log_activity(
            'ledger','ledger_exported','completed',
            count=written,scope=chosen_scope,reminders=stats['total_reminders'],path=str(selected),
        )
        messagebox.showinfo(
            _('Reskontra exporterad'),
            _(
                '{count} fakturor exporterade till:\n{path}\n\nPåminda fakturor: {reminded} · Totalt antal påminnelser: {reminders}',
                count=written,path=selected,reminded=stats['reminded_invoices'],reminders=stats['total_reminders'],
            ),
            parent=self,
        )
        return Path(selected)

    def refresh(self):
        if not ui_is_alive(self):
            logger.info('Invoice list refresh skipped because the window is closing')
            return
        try:
            for i in self.tree.get_children():self.tree.delete(i)
        except tk.TclError:
            logger.info('Invoice list refresh skipped because the tree view was destroyed')
            return
        flt,query,sort_column,sort_reverse=current_view_options(self)
        visible,in_view_total,elsewhere=invoice_view(flt,query,sort_column,sort_reverse)
        for r,stage,remain in visible:
            fee=money(charged_fee_for(r),r['currency']) if r['p1_date'] else '—'
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
        refresh_headings=getattr(self.tree,'_refresh_sort_headings',None)
        if callable(refresh_headings):refresh_headings(sort_column,sort_reverse)
        self.show_detail()
        status=getattr(self,'search_status',None)
        if status is not None:
            try:status.configure(text=invoice_search_summary(len(visible),in_view_total,query,elsewhere))
            except tk.TclError:report_fault()
        refresh_summary=getattr(self,'_refresh_defaults_summary',None)
        if callable(refresh_summary):refresh_summary()
        # Tray refresh is best effort: a missing or stopped tray must never
        # stop the invoice list from updating.
        refresh_tray=getattr(self,'refresh_tray',None)
        if callable(refresh_tray):refresh_tray()

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
            terms_str=str(row_value(r,'payment_terms','') or '').strip()
            if terms_str:
                detail_text+=' · '+_('Betalningsvillkor: {terms}',terms=terms_str)
            email_status=' · '.join(
                reminder_email_status(r,level) for level in ('P1','P2') if r[level.lower()+'_date']
            )
            if email_status:detail_text+='\n'+_('E-post: {status}',status=email_status)
            detail_text+='\n'+_('Kundtyp: {type} · {note}',type=_(CUSTOMER_TYPE_LABELS[invoice_customer_type(r)]),note=reminder_fee_note(r))
            self.detail.configure(text=detail_text)

    def show_row_context_menu(self,event):
        try:
            if self.tree.identify_region(event.x,event.y)=='heading':return
        except Exception:
            report_fault()
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
        except tk.TclError:report_fault()
        try:menu.grab_release()
        except tk.TclError:report_fault()

    def close_invoice_preview(self,win,doc):
        """Release the modal grab and close both PDF and window on every exit."""
        try:win.grab_release()
        except tk.TclError:report_fault()
        try:doc.close()
        finally:
            try:
                if win.winfo_exists():win.destroy()
            except tk.TclError:report_fault()

    def reminder_logo_files(self):
        """Return every SVG logo the user can choose for a reminder."""
        SVG_DIR.mkdir(exist_ok=True)
        return sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())

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
        """Return the invoice's stored logo, then its template and customer logo.

        There is deliberately no global default. Every invoice carries the
        logo it was imported, matched or edited with, and a reminder asks the
        user which logo to print before the PDF is created.
        """
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
        return '',_('(Ingen logotyp)')

    def reminder_logo_options(self,row):
        """Return the reminder logo choices, the preselected one and a missing file.

        The invoice's own logo, its supplier template's logo or the customer's
        saved logo is suggested. A logo the invoice points at but whose SVG file
        is gone stays in the list, so the PDF step can report it instead of
        quietly printing something else.
        """
        files=self.reminder_logo_files()
        _path,suggested=self.invoice_logo(row)
        no_logo=_('(Ingen logotyp)')
        missing=suggested if suggested and suggested!=no_logo and suggested not in files else ''
        choices=[no_logo]+([missing] if missing else [])+files
        return choices,(suggested if suggested in choices else no_logo),missing

    def show_due_reminder_window(self,rows=None):
        """Show the invoices that are ready for P1/P2 as a working list.

        A message box says "something is due" and then leaves the user to find
        the invoice in a table of two hundred rows. This window is the list: the
        level, the customer, how many days the reminder is overdue and the
        amount, with one button per row that opens the normal reminder flow. The
        window is opened once - a second check raises the one already open
        instead of stacking another - and it refreshes itself after a reminder
        has been created, so the row disappears when it is done.
        """
        rows=list(rows if rows is not None else due_reminder_rows())
        existing=getattr(self,'_due_reminder_window',None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify();existing.lift();existing.focus_force()
                    return True
            except tk.TclError:report_fault()
        window=self._new_toplevel(_('Dags att skapa P1/P2'))
        self._due_reminder_window=window
        window.minsize(self._px(560),self._px(360))
        form=ttk.Frame(window,padding=22);form.pack(fill='both',expand=True)
        ttk.Label(form,text=_('Dags att skapa P1/P2'),style='Title.TLabel').pack(anchor='w')
        summary=due_reminder_summary(rows)
        heading=[]
        if summary['p1']:heading.append(_('{count} väntar P1',count=summary['p1']))
        if summary['p2']:heading.append(_('{count} väntar P2',count=summary['p2']))
        if summary['mixed']:
            total_text=_('Blandade valutor – summeras inte')
        else:
            total_text=_('{amount} att få in',amount=money(summary['total'],summary['currency']))
        header=tk.StringVar(value=' · '.join(heading)+' · '+total_text if heading else total_text)
        ttk.Label(form,textvariable=header,style='Sub.TLabel').pack(anchor='w',pady=(4,10))

        columns=('level','invoice_no','customer','days','amount')
        labels={'level':_('Steg'),'invoice_no':_('Fakturanr'),'customer':_('Kund'),
                'days':_('Försenad (dagar)'),'amount':_('Kvar att betala')}
        tree=ttk.Treeview(form,columns=columns,show='headings',selectmode='browse',height=min(14,max(4,len(rows))))
        for column in columns:
            tree.heading(column,text=labels[column],anchor='e' if column in ('days','amount') else 'w')
            tree.column(column,width=self._px({'level':60,'invoice_no':105,'customer':220,'days':110,'amount':130}[column]),
                        anchor='e' if column in ('days','amount') else 'w',stretch=column=='customer')
        for _days,row,level in rows:
            tree.insert('','end',iid=str(row['id']),values=(
                level,row['invoice_no'],row['customer'],_days,
                money(max(0.0,float(row['amount'] or 0)-float(row['paid'] or 0)),row['currency']),
            ))
        enable_treeview_features(tree,columns,labels,initial_sort='days',initial_reverse=True)
        tree.pack(fill='both',expand=True)
        tree.bind('<Double-1>',lambda event:self.open_due_reminder(tree))
        show_all=tk.BooleanVar(value=False)
        def reload_rows():
            # Rebuilding from the database is what makes a created reminder
            # disappear from the list instead of lingering as a stale row.
            fresh=due_reminder_rows(include_opened=show_all.get())
            for item in tree.get_children():tree.delete(item)
            for days,row,level in fresh:
                tree.insert('','end',iid=str(row['id']),values=(
                    level,row['invoice_no'],row['customer'],days,
                    money(max(0.0,float(row['amount'] or 0)-float(row['paid'] or 0)),row['currency']),
                ))
            if fresh:
                tree.selection_set(str(fresh[0][1]['id']));tree.focus(str(fresh[0][1]['id']))
            summary=due_reminder_summary(fresh)
            parts=[]
            if summary['p1']:parts.append(_('{count} väntar P1',count=summary['p1']))
            if summary['p2']:parts.append(_('{count} väntar P2',count=summary['p2']))
            if not summary['mixed']:
                parts.append(_('{amount} att få in',amount=money(summary['total'],summary['currency'])))
            else:
                parts.append(_('Blandade valutor – summeras inte'))
            header.set(' · '.join(parts))
        ttk.Checkbutton(form,text=_('Visa även påminnelser som redan öppnats'),variable=show_all,
                        command=reload_rows).pack(anchor='w',pady=(8,0))

        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(12,0))
        ttk.Button(buttons,text=_('Skapa påminnelse'),command=lambda:self.open_due_reminder(tree),style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Visa i listan'),command=lambda:self.locate_due_reminder(tree)).pack(side='left',padx=(8,0))
        ttk.Button(buttons,text=_('Stäng'),command=window.destroy).pack(side='right')
        window.bind('<Escape>',lambda event:window.destroy())

        def close():
            self._due_reminder_window=None
            window.destroy()
        window.protocol('WM_DELETE_WINDOW',close)
        if rows:tree.selection_set(str(rows[0][1]['id']));tree.focus(str(rows[0][1]['id']))
        self._due_reminder_refresh=reload_rows
        log_activity('reminder','due_dialog','opened',count=len(rows),p1=summary['p1'],p2=summary['p2'])
        return True

    def _selected_due_row(self,tree):
        """Return the invoice behind the selected row of the due list."""
        selection=tree.selection()
        if not selection:return None
        try:invoice_id=int(selection[0])
        except (TypeError,ValueError):return None
        with connect() as db:
            return db.execute('SELECT * FROM invoices WHERE id=?',(invoice_id,)).fetchone()

    def open_due_reminder(self,tree):
        """Create the reminder for the selected row through the normal flow."""
        row=self._selected_due_row(tree)
        if row is None:return False
        window=getattr(self,'_due_reminder_window',None)
        try:
            if window is not None and window.winfo_exists():window.destroy()
        except tk.TclError:report_fault()
        self._due_reminder_window=None
        self.refresh()
        # The invoice may sit in another tab than the open one, so select it
        # only when it is really in the table that is showing.
        if str(row['id']) in self.tree.get_children():self.tree.selection_set(str(row['id']))
        try:
            self.make_reminder()
        finally:
            # Whether the reminder was created or cancelled, the list is rebuilt
            # so a finished invoice cannot stay in a window that says it is due.
            refresh=getattr(self,'_due_reminder_refresh',None)
            if callable(refresh):refresh()
            self.refresh_tray()
        return True

    def locate_due_reminder(self,tree):
        """Close the list and select the invoice in the main table instead."""
        row=self._selected_due_row(tree)
        if row is None:return False
        window=getattr(self,'_due_reminder_window',None)
        self._due_reminder_window=None
        try:
            if window is not None and window.winfo_exists():window.destroy()
        except tk.TclError:report_fault()
        self.select_invoice_filter('all')
        self.refresh()
        try:
            self.tree.selection_set(str(row['id']));self.tree.see(str(row['id']))
        except tk.TclError:report_fault()
        self.deiconify();self.lift()
        return True

    def choose_reminder_details(self,row,level):
        """Ask which logo and which optional line the reminder PDF should carry.

        The invoice's own logo, its supplier template or the customer's saved
        logo is preselected, so the normal case is a single click. The answer is
        what the PDF gets, which is why no global logo selector is needed. A
        cancelled dialogue returns ``None`` and nothing is created.
        """
        no_logo=_('(Ingen logotyp)')
        choices,suggested_name,missing=self.reminder_logo_options(row)
        state={'choices':choices,'missing':missing}
        window=self._new_toplevel(_('Skapa {level}',level=level))
        window.resizable(True,True)
        form=self._dialog_form(window,padding=22)
        ttk.Label(form,text=_('Skapa {level}',level=level),style='Title.TLabel').pack(anchor='w')
        ttk.Label(
            form,
            text=_('Välj logotyp och en frivillig meddelanderad innan {level}-PDF:en skapas. Valet sparas med påminnelsen och ändrar inte fakturan. Du kan ändra det senare via Redigera {level}.',level=level),
            wraplength=430,justify='left',
        ).pack(anchor='w',pady=(6,12))
        ttk.Label(form,text=_('Logotyp'),style='BodyBold.TLabel').pack(anchor='w')
        logo_var=tk.StringVar(value=suggested_name)
        combo=ttk.Combobox(form,textvariable=logo_var,state='readonly',values=choices,width=42)
        combo.pack(fill='x',pady=(3,0))
        hint=tk.StringVar()
        def update_hint(*_args):
            selected=logo_var.get()
            if selected and selected==state['missing']:
                hint.set(_('Logotypen {logo} som hör till fakturan finns inte i mappen svg. Lägg tillbaka filen eller välj en annan logotyp.',logo=selected))
            elif selected and selected!=no_logo:hint.set(_('Vald logotyp: {logo}',logo=selected))
            elif len(state['choices'])>1:hint.set(_('Ingen logotyp väljs. PDF:en skapas med appens textlogotyp.'))
            else:hint.set(_('Ingen SVG-logotyp finns i mappen svg ännu. Lägg till en fil och uppdatera listan.'))
        logo_var.trace_add('write',update_hint);update_hint()
        ttk.Label(form,textvariable=hint,wraplength=430,justify='left',style='Sub.TLabel').pack(anchor='w',pady=(6,0))
        # The optional line. An empty field means no line at all on the PDF.
        ttk.Label(form,text=_('Meddelanderad (frivillig)'),style='BodyBold.TLabel').pack(anchor='w',pady=(14,0))
        message_var=tk.StringVar(value=reminder_message_text(row_value(row,'reminder_message','')))
        message_entry=ttk.Entry(form,textvariable=message_var,width=52)
        message_entry.pack(fill='x',pady=(3,0))
        message_hint=tk.StringVar()
        def update_message_hint(*_args):
            remaining=REMINDER_MESSAGE_MAX_LENGTH-len(message_var.get())
            if message_var.get().strip():
                message_hint.set(_('Raden skrivs på PDF:en. {remaining} tecken kvar.',remaining=max(0,remaining)))
            else:
                message_hint.set(_('Lämnas fältet tomt tas raden bort helt ur PDF:en.'))
        message_var.trace_add('write',update_message_hint);update_message_hint()
        ttk.Label(form,textvariable=message_hint,wraplength=430,justify='left',style='Sub.TLabel').pack(anchor='w',pady=(6,0))
        links=ttk.Frame(form);links.pack(fill='x',pady=(12,0))
        def reload_choices():
            # A logo added while the dialogue is open must be selectable.
            state['choices'],_suggested,state['missing']=self.reminder_logo_options(row)
            combo.configure(values=state['choices'])
            if logo_var.get() not in state['choices']:logo_var.set(no_logo)
            update_hint()
        ttk.Button(links,text=_('Uppdatera lista'),command=reload_choices).pack(side='left')
        ttk.Button(links,text=_('Öppna SVG-mapp'),command=self.open_svg_folder).pack(side='left',padx=(6,0))
        saved_cust_lang=customer_reminder_language(row)
        lang_labels=[_(label) for _code,label in CUSTOMER_LANGUAGE_CHOICES]
        initial_lang_label=next((_(label) for code,label in CUSTOMER_LANGUAGE_CHOICES if code==saved_cust_lang),lang_labels[0])
        ttk.Label(form,text=_('Språk för kundens påminnelser'),style='BodyBold.TLabel').pack(anchor='w',pady=(14,0))
        cust_lang_var=tk.StringVar(value=initial_lang_label)
        cust_lang_combo=ttk.Combobox(form,textvariable=cust_lang_var,state='readonly',values=lang_labels,width=42)
        cust_lang_combo.pack(fill='x',pady=(3,0))
        choice={'value':None,'message':'','language':saved_cust_lang}
        def accept():
            selected=logo_var.get()
            choice['value']=selected if selected and selected!=no_logo and selected in state['choices'] else ''
            choice['message']=reminder_message_text(message_var.get())
            selected_lang=next((code for code,label in CUSTOMER_LANGUAGE_CHOICES if _(label)==cust_lang_var.get()),'')
            choice['language']=selected_lang
            window.destroy()
        def cancel():
            window.destroy()
        window.protocol('WM_DELETE_WINDOW',cancel)
        window.bind('<Escape>',lambda event:cancel())
        window.bind('<Return>',lambda event:accept())
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(14,0))
        ttk.Button(buttons,text=_('Fortsätt med {level}',level=level),command=accept,style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Avbryt'),command=cancel).pack(side='right')
        prep=getattr(self,'_prepare_modal_toplevel',None)
        if callable(prep):prep(window)
        else:window.grab_set()
        combo.focus_set()
        window.wait_window()
        if choice['value'] is None:
            logger.info('Reminder creation cancelled in the logo dialogue: invoice=%s level=%s',row['id'],level)
            return None
        customer_name=str(row_value(row,'customer','') or '').strip()
        if customer_name and choice['language']!=saved_cust_lang:
            try:
                with connect() as db:
                    existing_contact=get_customer_contact(db,customer_name)
                    existing_emails=existing_contact['emails'] if existing_contact is not None else str(row_value(row,'email','') or '')
                    save_customer_contact(db,customer_name,existing_emails,language=choice['language'])
            except Exception:
                logger.exception('Could not persist customer reminder language choice: customer=%s',customer_name)
        logo_path,logo_name=self.logo_file_path(choice['value'])
        logger.info(
            'Reminder details chosen: invoice=%s level=%s logo=%s message=%s',
            row['id'],level,logo_name,bool(choice['message']),
        )
        log_activity(
            'reminder','details_chosen','completed',invoice_id=row['id'],invoice_no=row['invoice_no'],
            level=level,logo=logo_name,has_message=bool(choice['message']),
        )
        return choice['value'],logo_path,logo_name,choice['message']

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

    def manage_error_log(self):
        """Inspect active unresolved errors and mark selected or all items resolved."""
        logger.info('User opened active error management dialog')
        try:
            _refresh_and_archive_logs()
            items=list_unresolved_errors(LOG_DIR)
        except Exception:
            logger.exception('Could not load active errors')
            messagebox.showerror(APP_NAME,_('Felloggen kunde inte läsas. Se den tekniska loggen.'),parent=self)
            return None
        if not items:
            messagebox.showinfo(APP_NAME,_('Det finns inga olösta fel i felloggen.'),parent=self)
            return None
        existing=getattr(self,'_error_manager_window',None)
        if existing is not None:
            try:
                if existing.winfo_exists():existing.deiconify();existing.lift();existing.focus_force();return existing
            except tk.TclError:report_fault()
        w=self._new_toplevel(_('Hantera aktiva fel'))
        self._error_manager_window=w
        w.minsize(self._px(720),self._px(460))
        def close():
            self._error_manager_window=None
            w.destroy()
        w.protocol('WM_DELETE_WINDOW',close)
        form=ttk.Frame(w,padding=20);form.pack(fill='both',expand=True)
        ttk.Label(form,text=_('Aktiva olösta fel'),style='Title.TLabel').pack(anchor='w')
        summary_var=tk.StringVar(value='')
        ttk.Label(form,textvariable=summary_var,style='Sub.TLabel').pack(anchor='w',pady=(4,10))
        columns=('timestamp','level','source','summary')
        labels={'timestamp':_('Tidpunkt'),'level':_('Nivå'),'source':_('Källa'),'summary':_('Sammanfattning')}
        widths={'timestamp':155,'level':90,'source':115,'summary':420}
        tree_wrap=ttk.Frame(form);tree_wrap.pack(fill='both',expand=True)
        tree=ttk.Treeview(tree_wrap,columns=columns,show='headings',selectmode='extended',height=10)
        for col in columns:
            tree.heading(col,text=labels[col],anchor='w')
            tree.column(col,width=self._px(widths[col]),anchor='w',stretch=col=='summary')
        enable_treeview_features(tree,columns,labels,initial_sort='timestamp',initial_reverse=True)
        ysb=ttk.Scrollbar(tree_wrap,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.pack(side='left',fill='both',expand=True);ysb.pack(side='right',fill='y')
        detail_box=tk.Text(form,height=7,wrap='word',state='disabled')
        detail_box.pack(fill='x',pady=(10,8))
        apply_widget_contrast(w,getattr(self,'_high_contrast',False),getattr(self,'_theme','light'))
        item_map={}
        def show_selected_detail(_event=None):
            sel=tree.selection()
            item=item_map.get(sel[0]) if sel else None
            text=item.body if item is not None else ''
            detail_box.configure(state='normal')
            detail_box.delete('1.0','end')
            if text:detail_box.insert('1.0',text)
            detail_box.configure(state='disabled')
        tree.bind('<<TreeviewSelect>>',show_selected_detail)
        def reload_items():
            for child in tree.get_children():tree.delete(child)
            item_map.clear()
            fresh=list_unresolved_errors(LOG_DIR)
            for idx,entry in enumerate(fresh):
                iid=f'err-{idx}'
                item_map[iid]=entry
                tree.insert('','end',iid=iid,values=(entry.timestamp,entry.level,entry.source,entry.summary))
            summary_var.set(_('{count} olösta fel i den aktiva felloggen. Äldre än 30 dagar rensas automatiskt.',count=len(fresh)))
            if fresh:
                first=tree.get_children()[0]
                tree.selection_set(first);tree.focus(first)
            show_selected_detail()
            return fresh
        def resolve_selected():
            sel=tree.selection()
            hashes=[item_map[iid].entry_hash for iid in sel if iid in item_map]
            if not hashes:
                messagebox.showinfo(APP_NAME,_('Markera ett eller flera fel i listan först.'),parent=w)
                return
            res=resolve_selected_errors(LOG_DIR,hashes)
            self._last_error_log_sig=None
            log_activity('log','errors_resolved_selected','completed',count=res.resolved_count)
            remaining=reload_items()
            if not remaining:
                messagebox.showinfo(APP_NAME,_('Alla aktiva fel är nu markerade som åtgärdade.'),parent=w)
                close()
        def resolve_all():
            if not messagebox.askyesno(APP_NAME,_('Markera alla fel i felloggen som åtgärdade?\n\nEn kopia sparas i loggarkivet. De tekniska källoggarna ändras inte.'),parent=w):
                return
            res=resolve_errors(LOG_DIR)
            self._last_error_log_sig=None
            log_activity('log','errors_resolved_all','completed',count=res.resolved_count)
            messagebox.showinfo(APP_NAME,_('Felloggen markerades som åtgärdad. {count} fel sparades i loggarkivet.',count=res.resolved_count),parent=w)
            close()
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(6,0))
        ttk.Button(buttons,text=_('Markera valda som åtgärdade'),command=resolve_selected,style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Markera alla som åtgärdade'),command=resolve_all).pack(side='left',padx=(8,0))
        ttk.Button(buttons,text=_('Visa samlad fellogg'),command=self.open_log).pack(side='left',padx=(8,0))
        ttk.Button(buttons,text=_('Stäng'),command=close).pack(side='right')
        reload_items()
        return w

    def open_technical_log(self):
        """Open the complete local log, including successful PDF diagnostics."""
        logger.info('User opened technical diagnostic log')
        try:open_path(LOG_PATH)
        except Exception:logger.exception('Could not open technical diagnostic log')

    def open_activity_log(self):
        """Open the structured activity trail for the current day."""
        log_activity('log','activity_log_opened','completed',path=str(ACTIVITY_LOG_PATH))
        try:open_path(ACTIVITY_LOG_PATH)
        except Exception:
            logger.exception('Could not open the activity log')
            messagebox.showwarning(_('Aktivitetsloggen'),_('Aktivitetsloggen finns ännu inte. Den skapas vid första registrerade åtgärden.'),parent=self)

    def open_log_folder(self):
        """Open the log folder with today's three files and the dated archive."""
        logger.info('User opened the log folder')
        try:open_path(LOG_DIR)
        except Exception:logger.exception('Could not open the log folder')

    def _run_scheduled_error_log_refresh(self):
        """Keep the consolidated local view current without touching source logs."""
        if self._quitting:return
        try:
            sig=None
            try:
                files=[]
                for entry in sorted(LOG_DIR.iterdir(),key=lambda p:p.name):
                    if entry.is_file() and entry.name!=ERROR_LOG_NAME:
                        st=entry.stat()
                        files.append((entry.name,st.st_mtime_ns,st.st_size))
                sig=(date.today().isoformat(),tuple(files))
            except OSError:
                sig=None
            if sig is None or getattr(self,'_last_error_log_sig',object())!=sig:
                _refresh_and_archive_logs()
                if sig is not None:self._last_error_log_sig=sig
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
        self._supplier_learning_note=None
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
        learned=learned_supplier_match(text)
        if learned:
            vendor,similarity=learned
            self._supplier_learning_note=(vendor,similarity)
            logger.info('Supplier suggestion from learned invoice layout awaits confirmation: file=%s pages=%s vendor=%s similarity=%.3f',source,pages,vendor,similarity)
            return vendor
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
        if field=='customer':return clean_customer_zone_text(raw)
        if field=='payment_terms':return clean_payment_terms_zone(raw)
        if field=='note':return clean_invoice_note(raw)
        return raw[:300]

    def apply_saved_zones(self,path,vendor,guess,page_indexes=None):
        """Reuse the learned field positions for one supplier template.

        The logo is deliberately not touched here. It lives with the invoice,
        the supplier template or the customer, and a reminder asks for it
        explicitly before the PDF is created.
        """
        if not vendor:return guess
        try:
            import fitz
            vendor_key=vendor.strip().casefold()
            with connect() as db:
                zones=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?)',(vendor_key,)).fetchall()
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
                    raw=page.get_text('text',clip=r)
                    if not raw.strip():
                        try:
                            import pytesseract
                            from PIL import Image
                            import io
                            pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=r,alpha=False)
                            raw=pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png'))),lang='swe+eng')
                        except Exception:
                            logger.debug('OCR fallback in apply_saved_zones unavailable or failed',exc_info=True)
                    val=self.parse_zone_value(z['field'],raw)
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
        win=self._new_toplevel(_('Förhandsgranska faktura – markera fält att läsa'))
        area_left,area_top,area_w,area_h=monitor_work_area(self)
        preview_w=min(max(780,area_w-48),self._px(1160))
        preview_h=min(max(560,area_h-48),self._px(860))
        win.geometry(f'{preview_w}x{preview_h}+{area_left+max(0,(area_w-preview_w)//2)}+{area_top+max(0,(area_h-preview_h)//2)}')
        win.minsize(min(preview_w,self._px(780)),min(preview_h,self._px(540)))
        top=ttk.Frame(win,padding=(12,8));top.pack(fill='x')
        ttk.Label(top,text=_('Leverantör / mallnamn:')).pack(side='left')
        vendor_var=tk.StringVar(value=original_vendor)
        vendor_combo=ttk.Combobox(top,textvariable=vendor_var,width=32,values=sorted((profile['vendor'] for profile in supplier_profiles),key=str.casefold))
        vendor_combo.pack(side='left',padx=7)
        ttk.Label(top,text=_('Dra en ruta över värdet. Sparade rutor kan återanvändas för samma mall.')).pack(side='left',padx=8)
        identifiers=ttk.Frame(win,padding=(12,0,12,4));identifiers.pack(fill='x')
        learning_note=getattr(self,'_supplier_learning_note',None)
        self._supplier_learning_note=None
        if learning_note and learning_note[0]==original_vendor:
            ttk.Label(
                win,text=_('Förslag från tidigare fakturor ({similarity} % likhet). Inget sparas utan din bekräftelse.',similarity=f'{learning_note[1]*100:.0f}'),
                style='Sub.TLabel',
            ).pack(fill='x',padx=12,pady=(0,4))
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
        zoom_var=tk.StringVar(value='100 %')
        ttk.Button(nav,text='◀',command=lambda:change_page(-1)).pack(side='left')
        ttk.Label(nav,textvariable=page_var).pack(side='left',padx=10)
        ttk.Button(nav,text='▶',command=lambda:change_page(1)).pack(side='left')
        ttk.Button(nav,text='−',command=lambda:change_zoom(-0.25)).pack(side='left',padx=(12,2))
        ttk.Label(nav,textvariable=zoom_var).pack(side='left',padx=4)
        ttk.Button(nav,text='+',command=lambda:change_zoom(0.25)).pack(side='left',padx=(2,4))
        ttk.Button(nav,text=_('Passa sida'),command=lambda:reset_zoom()).pack(side='left')
        ttk.Label(nav,text=_('Markera fält:')).pack(side='left',padx=(18,5))
        fields={_('Fakturanummer'):'invoice_no',_('Belopp (ATT BETALA)'):'amount',_('Valuta'):'currency',_('Fakturadatum'):'invoice_date',_('Förfallodatum'):'due_date',_('Betalningsvillkor'):'payment_terms',_('Kundnamn'):'customer',_('Fakturatext / Avser'):'note',_('Org.nr (leverantör)'):'org_number',_('Bankgiro (leverantör)'):'bankgiro_number'}
        field_labels={key:label for label,key in fields.items()}
        field_var=tk.StringVar(value=_('Belopp (ATT BETALA)'))
        ttk.Combobox(nav,textvariable=field_var,state='readonly',values=list(fields),width=24).pack(side='left')
        canvas_wrap=ttk.Frame(left);canvas_wrap.pack(fill='both',expand=True,pady=5)
        canvas=tk.Canvas(canvas_wrap,width=self._px(640),height=self._px(650),bg='#dfe3ea',highlightthickness=2,highlightcolor='#005a9c',takefocus=1)
        canvas_ysb=ttk.Scrollbar(canvas_wrap,orient='vertical',command=canvas.yview)
        canvas_xsb=ttk.Scrollbar(canvas_wrap,orient='horizontal',command=canvas.xview)
        canvas.configure(yscrollcommand=canvas_ysb.set,xscrollcommand=canvas_xsb.set)
        canvas_ysb.pack(side='right',fill='y');canvas_xsb.pack(side='bottom',fill='x')
        canvas.pack(side='left',fill='both',expand=True)
        right_panel_w=max(255,self._px(265))
        right_wrap_w=right_panel_w-28
        right=ttk.Frame(body,width=right_panel_w,padding=(10,4));right.pack(side='right',fill='y')
        ttk.Label(right,text=_('Avlästa värden'),style='Heading.TLabel').pack(anchor='w',pady=(0,8))
        logo_files=sorted(p.name for p in SVG_DIR.glob('*.svg') if p.is_file())
        mapped_logo=initial_profile.get('logo_file') if initial_profile else ''
        logo_choices=[_('(Välj logotyp för mallen)'),_('(Ingen logotyp)')]+logo_files
        initial_logo=mapped_logo if mapped_logo in logo_files else logo_choices[0]
        preview_logo_var=tk.StringVar(value=initial_logo)
        ttk.Label(right,text=_('Logotyp som matchar fakturan'),style='BodyBold.TLabel').pack(anchor='w',pady=(3,0))
        logo_combo=ttk.Combobox(right,textvariable=preview_logo_var,state='readonly',values=logo_choices,width=27)
        logo_combo.pack(fill='x',pady=(2,2))
        ttk.Label(right,text=_('Logotypen kopplas till vald leverantör/mall ovan.'),wraplength=right_wrap_w,style='Sub.TLabel').pack(anchor='w',pady=(0,2))
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
            lab=ttk.Label(right,text=str(guess.get(key,'') or '—'),wraplength=right_wrap_w,style='Sub.TLabel');lab.pack(anchor='w')
            result_labels[key]=lab
        ttk.Label(right,textvariable=status,wraplength=right_wrap_w,style='Sub.TLabel').pack(anchor='w',pady=8)
        pending={};state={'page':available_pages[0],'scale':1.0,'zoom':1.0,'photo':None,'start':None,'rect':None,'image_w':1,'image_h':1,'closed':False}
        def close_preview():
            if state['closed']:return
            state['closed']=True
            try:canvas.delete('all')
            except Exception:report_fault()
            state['photo']=None
            self.close_invoice_preview(win,doc)
        def draw_saved():
            canvas.delete('zone')
            current_vendor=vendor_var.get().strip()
            relative_page=available_pages.index(state['page'])
            p=doc[state['page']]
            with connect() as db:zs=db.execute('SELECT * FROM pdf_zones WHERE lower(vendor)=lower(?) AND page_index=?',(current_vendor,relative_page)).fetchall()
            for z in zs:
                if z['field'] in pending and pending[z['field']].get('page_index')==relative_page:
                    continue
                x0=z['x0']*p.rect.width*state['scale'];y0=z['y0']*p.rect.height*state['scale'];x1=z['x1']*p.rect.width*state['scale'];y1=z['y1']*p.rect.height*state['scale']
                canvas.create_rectangle(x0,y0,x1,y1,outline='#e13f43',width=2,tags='zone')
                canvas.create_text(x0+3,y0+3,text=_('{field} · {count} matchningar',field=field_labels.get(z['field'],z['field']),count=z['samples']),anchor='nw',fill='#9b2024',tags='zone')
            for field,zone in pending.items():
                if zone.get('page_index')!=relative_page:continue
                x0=zone['x0']*p.rect.width*state['scale'];y0=zone['y0']*p.rect.height*state['scale']
                x1=zone['x1']*p.rect.width*state['scale'];y1=zone['y1']*p.rect.height*state['scale']
                canvas.create_rectangle(x0,y0,x1,y1,outline='#1d8c66',width=2,tags='zone')
                canvas.create_text(x0+3,y0+3,text=field_labels.get(field,field),anchor='nw',fill='#1d8c66',tags='zone')
        def render_page():
            if state['closed']:return
            page=doc[state['page']]
            try:
                avail_cw=max(self._px(520),int(canvas.winfo_width())-12)
                avail_ch=max(self._px(520),int(canvas.winfo_height())-12)
            except Exception:
                avail_cw,avail_ch=self._px(640),self._px(640)
            base_scale=min(avail_cw/max(1.0,page.rect.width),avail_ch/max(1.0,page.rect.height))
            state['scale']=max(0.4,min(4.0,base_scale*state['zoom']))
            zoom_var.set(f"{int(round(state['zoom']*100))} %")
            pix=page.get_pixmap(matrix=fitz.Matrix(state['scale'],state['scale']),alpha=False)
            state['image_w'],state['image_h']=pix.width,pix.height
            state['photo']=tk.PhotoImage(data=base64.b64encode(pix.tobytes('png')).decode('ascii'))
            canvas.delete('all');canvas.config(scrollregion=(0,0,pix.width,pix.height))
            canvas.create_image(0,0,image=state['photo'],anchor='nw',tags='page')
            page_var.set(_('Sida {page} av {pages}',page=state['page']+1,pages=len(doc)));draw_saved()
        def change_zoom(delta):
            state['zoom']=max(0.5,min(3.0,round(state['zoom']+delta,2)))
            render_page()
        def reset_zoom():
            state['zoom']=1.0
            render_page()
        canvas.bind('<Control-MouseWheel>',lambda e:change_zoom(0.25 if getattr(e,'delta',0)>0 else -0.25))
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
            if mall:record_supplier_learning(mall,preview_text)
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
        if not ui_is_alive(self):return
        try:
            if self._python_addons_ready and not self._import_scan_running and setting('auto_import')=='1':
                files=self._import_monitor.poll()
                if files:
                    logger.info('Automatic import detected %d stable PDF file(s)',len(files))
                    if self.state()=='withdrawn':self.deiconify()
                    self.scan_import_folder(automatic=True,paths=files)
        except tk.TclError:
            # Closing the window during a scan is a normal way to stop it, not
            # a failure: Tk raises TclError for every widget that just went away.
            logger.info('Automatic import scan stopped because the window closed')
        except Exception:
            logger.exception('Automatic import folder watch failed')
        if not ui_is_alive(self):return
        try:self.after(IMPORT_WATCH_INTERVAL_MS,self._run_scheduled_import_scan)
        except tk.TclError:report_fault()

    def scan_import_folder(self,automatic=False,paths=None):
        if getattr(self,'_import_scan_running',False):return
        if not ui_is_alive(self):
            logger.info('Import scan skipped because the window is closing')
            return
        self._import_scan_running=True
        try:
            IMPORT_DIR.mkdir(parents=True,exist_ok=True)
            if paths is not None:
                files=[]
                for candidate_path in sorted(Path(p) for p in paths):
                    if is_archived_import_pdf(candidate_path,IMPORT_DIR):
                        logger.info('Archived invoice PDF ignored during scan: file=%s',candidate_path)
                        continue
                    files.append(candidate_path)
            else:
                files=iter_import_pdfs(IMPORT_DIR)
            if not files:
                if not automatic:messagebox.showinfo(_('Importmapp tom'),_('Lägg faktura-PDF:er i mappen:\n{folder}',folder=IMPORT_DIR),parent=self)
                return
            imported=skipped=failed=duplicates=paid_skipped=0
            for path in files:
                if not ui_is_alive(self):
                    logger.info('Import scan stopped because the window closed: imported=%d remaining=%d',imported,len(files)-imported)
                    break
                if is_archived_import_pdf(path,IMPORT_DIR):
                    logger.info('Archived invoice PDF skipped: file=%s',path)
                    continue
                try:
                    candidates=read_invoice_candidates(path)
                    logger.info('PDF import found %d invoice section(s): file=%s',len(candidates),path.name)
                    try:in_import_root=path.resolve().parent==IMPORT_DIR.resolve()
                    except OSError:in_import_root=False
                    split_batch=len(candidates)>1 and in_import_root and can_split_pdf_pages(path)
                    file_failed=0
                    all_sections_resolved=True
                    monitor=getattr(self,'_import_monitor',None)
                    mark_handled=getattr(monitor,'mark_handled',None)
                    for section,guess,candidate_hash in candidates:
                        if not ui_is_alive(self):
                            all_sections_resolved=False
                            logger.info('Import scan stopped before the next invoice section')
                            break
                        try:
                            source=str(path.resolve())
                            duplicate=find_duplicate_invoice(guess.get('invoice_no',''),candidate_hash)
                            if duplicate and is_fully_paid(duplicate):
                                paid_skipped+=1
                                logger.info('Paid invoice import skipped: existing_id=%s file=%s pages=%s',duplicate['id'],path.name,','.join(str(index+1) for index in section.page_indexes))
                                if is_ledger_paid_row(duplicate):
                                    chosen_date=(
                                        str(row_value(duplicate,'paid_marked_at','') or '')[:10]
                                        or str(row_value(duplicate,'ledger_last_seen','') or '')
                                        or str(row_value(duplicate,'due_date','') or '')
                                    )
                                    if len(candidates)==1:
                                        try:
                                            archived_dest=archive_import_pdf(path,IMPORT_DIR,archive_date=chosen_date,invoice_no=str(duplicate['invoice_no'] or ''))
                                            if archived_dest is not None:
                                                with connect() as db:
                                                    saved_hash=str(duplicate['source_hash'] or '').strip() or candidate_hash
                                                    db.execute('UPDATE invoices SET source=?,source_hash=? WHERE id=?',(str(archived_dest),saved_hash,duplicate['id']))
                                        except OSError:
                                            logger.exception('Could not archive already-paid invoice PDF: %s',path)
                                    elif split_batch and not str(duplicate['source'] or '').strip():
                                        extracted_paid=extract_section_pdf_to_import(path,IMPORT_DIR,section.page_indexes,invoice_no=str(duplicate['invoice_no'] or ''))
                                        if extracted_paid is not None:
                                            try:
                                                archived_dest=archive_import_pdf(extracted_paid,IMPORT_DIR,archive_date=chosen_date,invoice_no=str(duplicate['invoice_no'] or ''))
                                                if archived_dest is not None:
                                                    with connect() as db:
                                                        saved_hash=str(duplicate['source_hash'] or '').strip() or file_sha256(archived_dest)
                                                        db.execute('UPDATE invoices SET source=?,source_hash=? WHERE id=?',(str(archived_dest),saved_hash,duplicate['id']))
                                            except OSError:
                                                logger.exception('Could not archive split paid invoice PDF: %s',extracted_paid)
                                continue
                            if duplicate:
                                saved_dup_hash=str(duplicate['source_hash'] or '').strip()
                                if has_ledger_import_basis(duplicate) and saved_dup_hash!=candidate_hash:
                                    guess_fn=getattr(self,'guess_supplier',None)
                                    zones_fn=getattr(self,'apply_saved_zones',None)
                                    vendor=guess_fn(section.text,path=str(path) if (len(candidates)==1 or split_batch) else None,page_indexes=section.page_indexes) if callable(guess_fn) else ''
                                    guess=dict(guess)
                                    if vendor:guess['template_vendor']=vendor
                                    if callable(zones_fn):guess=zones_fn(str(path),vendor,guess,page_indexes=section.page_indexes)
                                    link_source=source
                                    link_hash=candidate_hash
                                    if split_batch:
                                        extracted_link=extract_section_pdf_to_import(path,IMPORT_DIR,section.page_indexes,invoice_no=str(duplicate['invoice_no'] or ''))
                                        if extracted_link is not None:
                                            if callable(mark_handled):mark_handled(extracted_link)
                                            link_source=str(extracted_link.resolve())
                                            link_hash=file_sha256(extracted_link)
                                        else:
                                            all_sections_resolved=False
                                    if enrich_ledger_invoice_from_pdf(duplicate,guess,link_source,link_hash):
                                        imported+=1
                                        continue
                                duplicates+=1
                                logger.info('Duplicate import blocked: existing_id=%s file=%s pages=%s',duplicate['id'],path.name,','.join(str(index+1) for index in section.page_indexes))
                                continue
                            vendor=self.guess_supplier(section.text,path=str(path) if (len(candidates)==1 or split_batch) else None,page_indexes=section.page_indexes)
                            guess['template_vendor']=vendor
                            guess=self.apply_saved_zones(str(path),vendor,guess,page_indexes=section.page_indexes)
                            if split_batch:
                                post_zone_dup=find_duplicate_invoice(guess.get('invoice_no',''),candidate_hash)
                                if post_zone_dup and is_fully_paid(post_zone_dup):
                                    paid_skipped+=1
                                    continue
                                if post_zone_dup:
                                    if has_ledger_import_basis(post_zone_dup) and str(post_zone_dup['source_hash'] or '').strip()!=candidate_hash:
                                        extracted_link=extract_section_pdf_to_import(path,IMPORT_DIR,section.page_indexes,invoice_no=str(post_zone_dup['invoice_no'] or ''))
                                        link_source=source
                                        link_hash=candidate_hash
                                        if extracted_link is not None:
                                            if callable(mark_handled):mark_handled(extracted_link)
                                            link_source=str(extracted_link.resolve())
                                            link_hash=file_sha256(extracted_link)
                                        else:
                                            all_sections_resolved=False
                                        if enrich_ledger_invoice_from_pdf(post_zone_dup,guess,link_source,link_hash):
                                            imported+=1
                                            continue
                                    duplicates+=1
                                    continue
                            preview_path=str(path)
                            preview_pages=section.page_indexes
                            if split_batch:
                                extracted_pdf=extract_section_pdf_to_import(path,IMPORT_DIR,section.page_indexes,invoice_no=str(guess.get('invoice_no') or ''))
                                if extracted_pdf is not None:
                                    source=str(extracted_pdf.resolve())
                                    candidate_hash=file_sha256(extracted_pdf)
                                    preview_path=str(extracted_pdf)
                                    preview_pages=tuple(range(len(section.page_indexes)))
                                    if callable(mark_handled):mark_handled(extracted_pdf)
                                else:
                                    all_sections_resolved=False
                            if try_auto_save_imported_invoice(guess,source,candidate_hash):
                                imported+=1
                                continue
                            guess=self.preview_invoice(preview_path,guess,vendor,page_indexes=preview_pages)
                            self.add_invoice(source=source,guess=guess,source_hash=candidate_hash)
                            with connect() as db:
                                saved=db.execute('SELECT 1 FROM invoices WHERE source_hash=? LIMIT 1',(candidate_hash,)).fetchone()
                            if saved:imported+=1
                            else:skipped+=1
                        except Exception:
                            file_failed+=1
                            logger.exception('Invoice section import failed for %s pages=%s',path.name,section.page_indexes);failed+=1
                    if split_batch and file_failed==0 and all_sections_resolved:
                        try:
                            path.unlink(missing_ok=True)
                            logger.info('Split batch PDF %s into %d individual invoice PDF(s) in import/',path.name,len(candidates))
                            log_activity('import','batch_pdf_split','completed',source=path.name,sections=len(candidates))
                        except OSError:
                            logger.exception('Could not remove original batch PDF after splitting: %s',path)
                except Exception:
                    logger.exception('Import folder scan failed for %s',path.name);failed+=1
            logger.info('Import folder scan complete: automatic=%s imported=%d duplicates=%d paid_skipped=%d skipped=%d failed=%d',automatic,imported,duplicates,paid_skipped,skipped,failed)
            self.refresh()
            # Automatic background imports stay non-blocking unless an error occurred;
            # manual scans always display the summary dialog.
            if not automatic or failed:
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

    def open_print_folder(self):
        """Open the print files that travel inside the release package."""
        try:
            if not PRINT_DIR.is_dir():
                raise FileNotFoundError(PRINT_DIR)
            open_path(PRINT_DIR)
            log_activity('branding','print_files_opened',folder=str(PRINT_DIR))
        except Exception:
            logger.exception('Could not open the print folder')
            messagebox.showwarning(_('Tryckfiler'),
                _('Tryckfilerna saknas i den här installationen. Kör python assets/build_icons.py i appmappen och försök igen.'),
                parent=self)

    def show_ledger_history(self,window):
        search=getattr(self,'invoice_search_var',None)
        if search is not None:search.set('')
        self.select_invoice_filter('history')
        self.refresh()
        window.destroy()
        log_activity('ledger','receipt_history_opened','completed')

    def show_ledger_receipt(self,source_name,report,result,plan,archived_pdfs=None):
        """Show every applied paid change and explain an unchanged import."""
        actual_plan=result.plan or plan
        if archived_pdfs is None:
            archived_pdfs=int(getattr(self,'_last_archived_ledger_pdfs',0) or 0)
        win=self._new_toplevel(_('Reskontrakvitto'))
        win.geometry('900x560');win.minsize(650,400)
        form=ttk.Frame(win,padding=18);form.pack(fill='both',expand=True)
        commit=APP_RELEASE_COMMIT[:12] or _('källkörning')
        summary=_('Lista per {date} · {source}\nNya fakturor: {new} · Befintliga: {existing} · Betalmarkerade: {paid} · Uppdaterade betalbelopp: {updated}\nBuild: {commit}',date=report.list_date,source=source_name,new=result.imported,existing=result.existing,paid=result.marked_paid,updated=result.payment_updates,commit=commit)
        if archived_pdfs:
            summary+='\n'+_('Arkiverade faktura-PDF:er (ÅÅÅÅ/MM): {archived}',archived=archived_pdfs)
        ttk.Label(form,text=summary,style='Sub.TLabel',justify='left',wraplength=840).pack(anchor='w',pady=(0,12))
        body=ttk.Frame(form);body.pack(fill='both',expand=True)
        receipt_palette=window_palette(self)
        text=tk.Text(
            body,wrap='word',font='TkTextFont',background=receipt_palette['field_background'],
            foreground=receipt_palette['text'],insertbackground=receipt_palette['text'],
            selectbackground=receipt_palette['selected_background'],selectforeground=receipt_palette['selected_text'],
            relief='solid',borderwidth=1,padx=12,pady=12,
            highlightthickness=2,highlightcolor=receipt_palette['focus'],highlightbackground=receipt_palette['border'],
        )
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
        archived_pdfs=archive_ledger_paid_import_pdfs(archive_date=report.list_date)
        self._last_archived_ledger_pdfs=archived_pdfs
        refresh_json_journal(parent=self)
        logger.info('Customer ledger imported: %s',_ledger_log_json({
            'source':source_name,'list_date':report.list_date,'new':result.imported,
            'existing':result.existing,'marked_paid':result.marked_paid,
            'payment_updates':result.payment_updates,
        }))
        if archived_pdfs:
            logger.info('Customer ledger archived %d paid invoice PDF(s) into year/month folders',archived_pdfs)
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
        if is_archived_import_pdf(path,IMPORT_DIR):
            logger.info('Blocked manual import of archived invoice PDF: %s',path)
            messagebox.showinfo(_('Arkiverad faktura'),_('Den här PDF-filen ligger i en arkivmapp under importmappen och importeras inte på nytt.'),parent=self)
            return
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
                    saved_dup_hash=str(duplicate['source_hash'] or '').strip()
                    if has_ledger_import_basis(duplicate) and saved_dup_hash!=candidate_hash:
                        guess_fn=getattr(self,'guess_supplier',None)
                        zones_fn=getattr(self,'apply_saved_zones',None)
                        vendor=str(duplicate['template_vendor'] or '').strip()
                        if not vendor and callable(guess_fn):
                            vendor=guess_fn(section.text,path=path if len(candidates)==1 else None,page_indexes=section.page_indexes)
                        guess=dict(guess)
                        if vendor:guess['template_vendor']=vendor
                        if callable(zones_fn):guess=zones_fn(path,vendor,guess,page_indexes=section.page_indexes)
                        resolved_source=str(Path(path).resolve())
                        if multiple:
                            if enrich_ledger_invoice_from_pdf(duplicate,guess,resolved_source,candidate_hash):
                                imported+=1
                                continue
                        else:
                            guess=self.preview_invoice(path,guess,vendor,page_indexes=section.page_indexes)
                            if normalize_invoice_number(guess.get('invoice_no'))==normalize_invoice_number(duplicate['invoice_no']):
                                saved_enrich=self.invoice_dialog(
                                    'Komplettera faktura från original-PDF',
                                    row=duplicate,source=resolved_source,guess=guess,
                                    source_hash=candidate_hash,enrich_original=True,
                                )
                                if saved_enrich:
                                    self.refresh()
                            else:
                                messagebox.showerror(
                                    _('Originalfakturan matchar inte'),
                                    _('Fakturanumret i originalfakturan måste vara {invoice_no} innan informationen kan sparas.',invoice_no=duplicate['invoice_no']),
                                    parent=self,
                                )
                            return
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
        """Enrich one existing invoice row from its reviewed original invoice PDF."""

        row=self.selected()
        if row is None:return None
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
        """Edit the selected invoice's customer, reusable recipients and reminder language."""
        r=self.selected()
        if not r:return
        values=apply_saved_customer_contact(dict(r))
        saved_cust_lang=customer_reminder_language(r)
        lang_labels=[_(label) for _code,label in CUSTOMER_LANGUAGE_CHOICES]
        initial_lang_label=next((_(label) for code,label in CUSTOMER_LANGUAGE_CHOICES if code==saved_cust_lang),lang_labels[0])
        w=self._new_toplevel(_('Redigera kund'));w.resizable(True,True)
        form=self._dialog_form(w,padding=20)
        ttk.Label(form,text=_('Kundnamn')).grid(row=0,column=0,sticky='w',padx=(0,12),pady=5)
        customer_entry=ttk.Entry(form,width=52);customer_entry.grid(row=0,column=1,pady=5);customer_entry.insert(0,r['customer'])
        ttk.Label(form,text=_('E-postadresser')).grid(row=1,column=0,sticky='w',padx=(0,12),pady=5)
        email_entry=ttk.Entry(form,width=52);email_entry.grid(row=1,column=1,pady=5);email_entry.insert(0,values.get('email',''))
        ttk.Label(form,text=_('Språk för påminnelser')).grid(row=2,column=0,sticky='w',padx=(0,12),pady=5)
        cust_lang_var=tk.StringVar(value=initial_lang_label)
        cust_lang_combo=ttk.Combobox(form,textvariable=cust_lang_var,state='readonly',values=lang_labels,width=49)
        cust_lang_combo.grid(row=2,column=1,sticky='w',pady=5)
        ttk.Label(
            form,text=_('Flera adresser: separera med kommatecken (,). Kundens adresser återanvänds på nästa faktura till samma kund.'),
            wraplength=470,
        ).grid(row=3,column=0,columnspan=2,sticky='w',pady=(5,12))
        def save():
            customer=customer_entry.get().strip()
            if not customer:
                messagebox.showerror(_('Kontrollera uppgifter'),_('Ange ett kundnamn.'),parent=w);return
            try:emails=normalize_email_addresses(email_entry.get())
            except EmailAddressError as exc:
                messagebox.showerror(_('Ogiltig e-postadress'),_('Kontrollera adressen: {email}',email=exc.address),parent=w);return
            chosen_lang=next((code for code,label in CUSTOMER_LANGUAGE_CHOICES if _(label)==cust_lang_var.get()),'')
            record=dict(r);record['customer']=customer;record['email']=emails
            duplicate=save_invoice_record(record,r['id'])
            if duplicate:
                show_duplicate_invoice(duplicate,parent=w);return
            with connect() as db:
                save_customer_contact(db,customer,emails,record.get('logo_file'),language=chosen_lang)
            refresh_json_journal(parent=w)
            logger.info('Customer contact updated: invoice=%s recipients=%d language=%s',r['id'],len(parse_email_addresses(emails)),chosen_lang or 'default')
            w.destroy();self.refresh()
        buttons=ttk.Frame(form);buttons.grid(row=4,column=0,columnspan=2,sticky='e')
        ttk.Button(buttons,text=_('Spara'),command=save,style='Accent.TButton').pack(side='left',padx=(0,7))
        ttk.Button(buttons,text=_('Stäng'),command=w.destroy).pack(side='left')
        prep=getattr(self,'_prepare_modal_toplevel',None)
        if callable(prep):prep(w)
        else:w.grab_set()
        w.wait_window()

    def invoice_dialog(self,title,row=None,source='',guess=None,source_hash='',enrich_original=False):
        w=self._new_toplevel(_(title));w.resizable(True,True);w.configure(bg=window_palette(self)['background'])
        fields=[('Kundnamn','customer'),('Fakturanummer','invoice_no'),('Fakturadatum (ÅÅÅÅ-MM-DD)','invoice_date'),('Förfallodatum (ÅÅÅÅ-MM-DD)','due_date'),('Betalningsvillkor','payment_terms'),('Fakturabelopp','amount'),('Valuta (ISO-kod, t.ex. SEK/EUR)','currency'),('Redan betalt','paid'),('E-post','email'),('Fakturatext / Avser','note')]
        enriched=merge_original_invoice_values(row,guess) if enrich_original and row is not None else None
        vals={k:(enriched.get(k,'') if enriched is not None else (row_value(row,k,'') if row else (guess or {}).get(k,''))) for _label,k in fields}
        vals['currency']=normalize_currency(vals.get('currency'))
        vals['source']=source if enrich_original else (row['source'] if row else source)
        vals['source_hash']=source_hash if enrich_original else (row['source_hash'] if row else source_hash)
        vals['template_vendor']=enriched['template_vendor'] if enriched is not None else (row['template_vendor'] if row else (guess or {}).get('template_vendor',''))
        vals['logo_file']=enriched['logo_file'] if enriched is not None else (row['logo_file'] if row else (guess or {}).get('logo_file'))
        apply_saved_customer_contact(vals)
        learned_applied=[];learned_suggestions=[]
        if row is None and not enrich_original:
            vals,learned_suggestions=learned_invoice_defaults(vals)
        reviewed_var=tk.BooleanVar(value=bool(row['reviewed']) if row else not bool(source))
        entries={};form=self._dialog_form(w,padding=18)
        for i,(lab,k) in enumerate(fields):
            ttk.Label(form,text=_(lab)).grid(row=i,column=0,sticky='w',pady=5,padx=(0,12));e=ttk.Entry(form,width=43);e.grid(row=i,column=1,pady=5);e.insert(0,str(vals.get(k,'') or ''));entries[k]=e
            if enrich_original and k in ORIGINAL_INVOICE_PROTECTED_FIELDS:e.configure(state='readonly')
        type_row=len(fields)
        if row is None:
            saved_type=infer_imported_customer_type(vals.get('customer',''))
        elif enrich_original and not str(row_value(row,'p1_date','') or '').strip():
            old_cust=str(row_value(row,'customer','') or '').strip()
            new_cust=str(vals.get('customer','') or '').strip()
            if new_cust and (new_cust.casefold()!=old_cust.casefold() or invoice_customer_type(row)==CUSTOMER_PRIVATE):
                saved_type=infer_imported_customer_type(new_cust)
            else:
                saved_type=invoice_customer_type(row)
        else:
            saved_type=invoice_customer_type(row)
        saved_agreement=normalize_agreement(
            row_value(row,'fee_agreement','') if row is not None else ''
        ) or normalize_agreement(setting('fee_agreement'))
        customer_type_var=tk.StringVar(value=_(CUSTOMER_TYPE_LABELS[saved_type]))
        agreement_var=tk.StringVar(value=_(AGREEMENT_LABELS[saved_agreement]))
        ttk.Label(form,text=_('Kundtyp')).grid(row=type_row,column=0,sticky='w',pady=5,padx=(0,12))
        type_combo=ttk.Combobox(form,textvariable=customer_type_var,state='readonly',width=40,
            values=[_(CUSTOMER_TYPE_LABELS[code]) for code in CUSTOMER_TYPES])
        type_combo.grid(row=type_row,column=1,sticky='w',pady=5)
        ttk.Label(form,text=_('Var avtalades påminnelseavgiften?')).grid(row=type_row+1,column=0,sticky='w',pady=5,padx=(0,12))
        agreement_combo=ttk.Combobox(form,textvariable=agreement_var,state='readonly',width=40,
            values=[_(label) for label in AGREEMENT_LABELS.values()])
        agreement_combo.grid(row=type_row+1,column=1,sticky='w',pady=5)
        fee_hint=ttk.Label(form,text='',style='Sub.TLabel',wraplength=520,justify='left')
        fee_hint.grid(row=type_row+2,column=0,columnspan=2,sticky='w',pady=(2,6))
        def chosen_type():
            for code,label in CUSTOMER_TYPE_LABELS.items():
                if _(label)==customer_type_var.get():return code
            return CUSTOMER_PRIVATE
        def chosen_agreement():
            for code,label in AGREEMENT_LABELS.items():
                if _(label)==agreement_var.get():return code
            return AGREEMENT_NONE
        def update_fee_hint(*_args):
            ctype=chosen_type()
            model=current_fee_model()
            fee=fee_for_model(model,ctype)
            currency=normalize_currency(entries['currency'].get() if 'currency' in entries else 'SEK')
            if model==FEE_MODEL_PER_REMINDER:
                agreement_combo.configure(state='readonly')
                fee_hint.configure(text=_('{label}: {fee}, en gång per fordran. Mot en privatperson gäller 4 § med högst 60 kr.',label=_(fee_label_key(ctype,fee,model)),fee=money(fee,currency)))
            elif is_business(ctype):
                agreement_combo.configure(state='disabled')
                fee_hint.configure(text=_('{label}: {fee}. Företag och myndigheter får förseningsersättning i stället; påminnelseavgiften blir 0 kr.',label=_(fee_label_key(ctype,fee,model)),fee=money(fee,currency)))
            else:
                agreement_combo.configure(state='readonly')
                fee_hint.configure(text=_('{label}: {fee}, högst 60 kr och en gång per fordran. Rätten till avgiften måste avtalas senast när skulden uppstod.',label=_(fee_label_key(ctype,fee,model)),fee=money(fee,currency)))
        type_combo.bind('<<ComboboxSelected>>',update_fee_hint)
        agreement_combo.bind('<<ComboboxSelected>>',update_fee_hint)
        entries['currency'].bind('<FocusOut>',update_fee_hint)
        update_fee_hint()
        if learned_suggestions:
            # Ask only after the form is visible, and never overwrite typing.
            w.update_idletasks()
            if self._confirm_learned_suggestions(learned_suggestions,w):
                for learned in learned_suggestions:
                    apply_learned_value(vals,learned)
                    target=entries.get('due_date') if learned.field=='payment_term_days' else entries.get(learned.field)
                    if target is not None and (learned.field=='payment_term_days' or not target.get().strip()):
                        target.delete(0,'end');target.insert(0,vals.get(learned.field if learned.field!='payment_term_days' else 'due_date',''))
                learned_applied.extend(learned_suggestions)
                log_activity('learning','suggestions_applied','completed',fields=','.join(item.field for item in learned_suggestions))
            else:
                try:
                    with connect() as db:
                        for learned in learned_suggestions:learning.decline(db,learned)
                except Exception:logger.exception('Declined learning suggestions could not be recorded')
                log_activity('learning','suggestions_declined','completed',fields=','.join(item.field for item in learned_suggestions))
        review_row=len(fields)+3
        due_bankday_frame=ttk.Frame(form)
        due_bankday_label=ttk.Label(due_bankday_frame,text='',style='Sub.TLabel',wraplength=380,justify='left')
        due_bankday_label.pack(side='left',padx=(0,8))
        def shift_due_to_bankday():
            parsed_due=dparse(entries['due_date'].get().strip())
            if parsed_due is None or is_swedish_banking_day(parsed_due):return
            next_bday=next_swedish_banking_day(parsed_due)
            entries['due_date'].delete(0,'end')
            entries['due_date'].insert(0,next_bday.isoformat())
            update_due_bankday_hint()
        due_bankday_btn=ttk.Button(due_bankday_frame,text=_('Flytta till nästa bankdag'),command=shift_due_to_bankday)
        due_bankday_btn.pack(side='left')
        due_bankday_row=review_row
        review_row+=1
        def update_due_bankday_hint(*_args):
            if enrich_original:
                due_bankday_frame.grid_remove()
                return
            parsed_due=dparse(entries['due_date'].get().strip())
            reason=non_banking_reason(parsed_due,get_language()) if parsed_due is not None else ''
            if parsed_due is not None and reason:
                next_bday=next_swedish_banking_day(parsed_due)
                due_bankday_label.configure(
                    text=_('Förfallodatumet infaller på {reason} ({raw}). Nästa svenska bankdag är {bankday}.',
                           reason=reason,raw=parsed_due.isoformat(),bankday=next_bday.isoformat())
                )
                due_bankday_frame.grid(row=due_bankday_row,column=0,columnspan=2,sticky='w',pady=(2,4))
            else:
                due_bankday_frame.grid_remove()
        def maybe_fill_due_from_terms(*_args):
            if enrich_original or entries['due_date'].get().strip():
                return
            inv_d=dparse(normalize_date(entries['invoice_date'].get().strip()) or entries['invoice_date'].get().strip())
            days=parse_payment_terms_days(entries['payment_terms'].get().strip())
            if inv_d is not None and days is not None:
                entries['due_date'].insert(0,(inv_d+timedelta(days=days)).isoformat())
                update_due_bankday_hint()
        entries['payment_terms'].bind('<FocusOut>',maybe_fill_due_from_terms)
        entries['invoice_date'].bind('<FocusOut>',maybe_fill_due_from_terms)
        entries['due_date'].bind('<KeyRelease>',update_due_bankday_hint)
        entries['due_date'].bind('<FocusOut>',update_due_bankday_hint)
        update_due_bankday_hint()
        if learned_applied:
            applied_fields=', '.join(sorted({_(LEARNING_FIELD_LABELS.get(item.field,item.field)) for item in learned_applied}))
            ttk.Label(form,text=_('Inlärda förslag som du godkände: {fields}',fields=applied_fields),style='Sub.TLabel',wraplength=520).grid(row=review_row,column=0,columnspan=2,sticky='w',pady=(6,0))
            review_row+=1
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
                customer_type=chosen_type(),
                fee_agreement=chosen_agreement() if not is_business(chosen_type()) else '',
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
        prep=getattr(self,'_prepare_modal_toplevel',None)
        if callable(prep):prep(w)
        else:w.grab_set()
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
            restored_source=None
            raw_pdf_source=str(r['source'] or '').strip()
            if raw_pdf_source and is_archived_import_pdf(raw_pdf_source,IMPORT_DIR):
                try:restored_source=restore_archived_import_pdf(raw_pdf_source,IMPORT_DIR)
                except OSError:logger.exception('Could not restore archived PDF on paid undo: %s',raw_pdf_source)
            if restored_source is not None:
                db.execute(
                    "UPDATE invoices SET paid=?,paid_before_marking=NULL,paid_marked_at='',paid_marked_source='',source=? WHERE id=?",
                    (previous,str(restored_source),r['id']),
                )
            else:
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
        """Move the selected invoice to the trash, where it can be restored."""
        r=self.selected()
        if not r:return None
        if not messagebox.askyesno(
            _('Ta bort faktura'),
            _('Flytta {invoice_no} till papperskorgen? Fakturan kan återställas därifrån.',invoice_no=r['invoice_no']),
            parent=self,
        ):return None
        with connect() as db:
            trash_id=invoice_trash.delete_invoice_to_trash(db,r['id'])
        if trash_id is None:return None
        log_activity('invoice','deleted','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],trash_id=trash_id)
        self._last_deleted={'trash_id':trash_id,'invoice_no':r['invoice_no'],'customer':r['customer'],'invoice_id':r['id']}
        refresh_json_journal(parent=self)
        self.refresh()
        self._offer_undo_delete()
        return trash_id

    def _offer_undo_delete(self):
        """Show one visible way back after a delete, for a minute."""
        bar=getattr(self,'undo_bar',None)
        label=getattr(self,'undo_label',None)
        deleted=getattr(self,'_last_deleted',None)
        if bar is None or label is None or not deleted:return False
        label.configure(text=_('Faktura {invoice_no} ligger i papperskorgen.',invoice_no=deleted['invoice_no']))
        footer=getattr(self,'_footer',None)
        try:
            if footer is not None:bar.pack(fill='x',before=footer)
            else:bar.pack(fill='x')
        except tk.TclError:
            return False
        job=getattr(self,'_undo_job',None)
        if job is not None:
            try:self.after_cancel(job)
            except (tk.TclError,ValueError):report_fault()
        self._undo_job=self.after(60000,self._hide_undo_delete)
        return True

    def _hide_undo_delete(self):
        """Take the undo offer away; the trash keeps the invoice either way."""
        job=getattr(self,'_undo_job',None)
        self._undo_job=None
        if job is not None:
            try:self.after_cancel(job)
            except (tk.TclError,ValueError):report_fault()
        bar=getattr(self,'undo_bar',None)
        if bar is not None:
            try:bar.pack_forget()
            except tk.TclError:report_fault()

    def _focus_is_text_input(self):
        """True when the keyboard is in a field that has its own undo."""
        try:widget=self.focus_get()
        except (tk.TclError,KeyError):return False
        if widget is None:return False
        try:return str(widget.winfo_class()) in ('Entry','TEntry','Text','Spinbox','TSpinbox','TCombobox')
        except (tk.TclError,AttributeError):return False

    def undo_last_delete(self):
        """Restore the invoice that was deleted last, if the trash still has it.

        Ctrl+Z inside a text field belongs to that field, so the shortcut does
        nothing there; the invoice is still waiting in the trash.
        """
        if self._focus_is_text_input():return False
        deleted=getattr(self,'_last_deleted',None)
        if not deleted:
            messagebox.showinfo(_('Inget att ångra'),_('Ingen faktura har tagits bort i den här sessionen.'),parent=self)
            return False
        with connect() as db:result=invoice_trash.restore(db,deleted['trash_id'])
        if not result['restored']:
            messagebox.showinfo(
                _('Kunde inte återställa'),
                _('Faktura {invoice_no} finns inte kvar i papperskorgen.',invoice_no=deleted['invoice_no']),
                parent=self,
            )
            self._last_deleted=None
            self._hide_undo_delete()
            return False
        self._last_deleted=None
        self._hide_undo_delete()
        log_activity('invoice','delete_undone','completed',invoice_no=result['invoice_no'],invoice_id=result['id'])
        refresh_json_journal(parent=self)
        self.refresh()
        messagebox.showinfo(_('Återställd'),_('Faktura {invoice_no} är tillbaka i listan.',invoice_no=result['invoice_no']),parent=self)
        return True

    def show_trash(self):
        """Open the trash: restore, or remove for good after an explicit answer."""
        existing=getattr(self,'_trash_window',None)
        if existing is not None:
            try:
                existing.deiconify();existing.lift();existing.focus_force()
                return existing
            except tk.TclError:
                report_fault()
        w=self._new_toplevel(_('Papperskorg'));w.resizable(True,True)
        self._trash_window=w
        def close():
            self._trash_window=None
            w.destroy()
        w.protocol('WM_DELETE_WINDOW',close)
        form=ttk.Frame(w,padding=20);form.pack(fill='both',expand=True)
        ttk.Label(form,text=_('Papperskorgen'),style='Heading.TLabel').pack(anchor='w')
        summary=ttk.Label(form,text='',style='Sub.TLabel',justify='left',wraplength=620)
        summary.pack(anchor='w',pady=(4,10))
        columns=('invoice_no','customer','amount','deleted_at')
        tree=ttk.Treeview(form,columns=columns,show='headings',selectmode='extended',height=12)
        labels={'invoice_no':_('Fakturanr'),'customer':_('Kund'),'amount':_('Fakturabelopp'),'deleted_at':_('Borttagen')}
        widths={'invoice_no':110,'customer':220,'amount':120,'deleted_at':160}
        for column in columns:
            tree.heading(column,text=labels[column])
            tree.column(column,width=self._px(widths[column]),anchor='w')
        enable_treeview_features(tree,columns,labels,initial_sort='deleted_at',initial_reverse=True)
        tree.pack(fill='both',expand=True)
        note=ttk.Label(form,text=_('Inget tas bort automatiskt. En faktura ligger kvar här tills du återställer den eller tar bort den permanent.'),style='Sub.TLabel',justify='left',wraplength=620)
        note.pack(anchor='w',pady=(8,0))
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(12,0))

        def selected_ids():
            ids=[]
            for item in tree.selection():
                try:ids.append(int(item))
                except ValueError:continue
            return ids

        def reload():
            for item in tree.get_children():tree.delete(item)
            with connect() as db:items=invoice_trash.trash_items(db)
            for entry in items:
                tree.insert('','end',iid=str(entry['id']),values=(
                    entry['invoice_no'],entry['customer'],
                    money(float(entry['amount'] or 0),entry['currency']),
                    str(entry['deleted_at']).replace('T',' '),
                ))
            summary.configure(text=invoice_trash.trash_summary(items))
            state=('!disabled',) if items else ('disabled',)
            for button in (restore_button,permanent_button,empty_button):
                try:button.state(state)
                except tk.TclError:report_fault()
            return items

        def restore_selected():
            ids=selected_ids()
            if not ids:
                messagebox.showinfo(_('Välj faktura'),_('Markera en faktura i papperskorgen först.'),parent=w)
                return 0
            restored=0;renumbered=[]
            with connect() as db:
                for trash_id in ids:
                    result=invoice_trash.restore(db,trash_id)
                    if result['restored']:
                        restored+=1
                        if result.get('renumbered'):renumbered.append(result['invoice_no'])
                        log_activity('invoice','restored_from_trash','completed',invoice_no=result['invoice_no'],invoice_id=result['id'])
            if restored:
                refresh_json_journal(parent=w)
                self.refresh()
            last=getattr(self,'_last_deleted',None)
            if last and last['trash_id'] in ids:
                # Restored from the trash window: the undo offer has done its job.
                self._last_deleted=None
                self._hide_undo_delete()
            reload()
            text=_('{count} fakturor återställda.',count=restored)
            if renumbered:text+=' '+_('Ett nytt id användes för: {numbers}.',numbers=', '.join(renumbered))
            messagebox.showinfo(_('Återställda'),text,parent=w)
            return restored

        def permanent_delete():
            ids=selected_ids()
            if not ids:
                messagebox.showinfo(_('Välj faktura'),_('Markera en faktura i papperskorgen först.'),parent=w)
                return 0
            if not messagebox.askyesno(
                _('Ta bort permanent'),
                _('{count} fakturor tas bort för gott. Det går inte att ångra.',count=len(ids)),
                parent=w,
            ):return 0
            with connect() as db:removed=invoice_trash.purge(db,ids)
            log_activity('invoice','trash_purged','completed',count=removed)
            reload()
            return removed

        def empty_all():
            with connect() as db:remaining=invoice_trash.trash_count(db)
            if not remaining:
                messagebox.showinfo(_('Papperskorgen är tom'),_('Det finns ingenting att tömma.'),parent=w)
                return 0
            if not messagebox.askyesno(
                _('Töm papperskorgen'),
                _('Allt i papperskorgen tas bort för gott. Det går inte att ångra.'),
                parent=w,
            ):return 0
            with connect() as db:removed=invoice_trash.empty_trash(db)
            log_activity('invoice','trash_emptied','completed',count=removed)
            reload()
            return removed

        restore_button=ttk.Button(buttons,text=_('Återställ valda'),command=restore_selected,style='Accent.TButton')
        restore_button.pack(side='left')
        permanent_button=ttk.Button(buttons,text=_('Ta bort permanent'),command=permanent_delete,style='Danger.TButton')
        permanent_button.pack(side='left',padx=(7,0))
        empty_button=ttk.Button(buttons,text=_('Töm papperskorgen'),command=empty_all,style='Danger.TButton')
        empty_button.pack(side='left',padx=(7,0))
        ttk.Button(buttons,text=_('Stäng'),command=close).pack(side='right')
        reload()
        log_activity('ui','trash_opened','completed')
        return w

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
        record_reminder_learning(r,recipients)
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
        logo_choice=None
        while stage in ('P1 att skapa','P2 att skapa'):
            level='P1' if stage.startswith('P1') else 'P2'
            if level == 'P1':
                source_differences=[]
                try:
                    apply_zones = getattr(self, 'apply_saved_zones', None)
                    zone_applier = None
                    if r['template_vendor'] and apply_zones:
                        def zone_applier(path, section, pdf_values):
                            # Reuse learned fields; the logo is chosen separately.
                            return apply_zones(
                                path, r['template_vendor'], pdf_values,
                                page_indexes=section.page_indexes,
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
            fee=reminder_fee_for_level(r,level)
            fee_model=reminder_fee_model_for(r,level)
            assessment=assess_fee(invoice_customer_type(r),fee,invoice_currency(r),invoice_fee_agreement(r),fee_model)
            # A fee already charged with P1 stays fixed. P2 repeats it and does
            # not increase the claim, so an old, too high amount is reported
            # instead of blocking the second reminder the customer is waiting for.
            frozen=level=='P2' and bool(read_reminder_snapshot(row_value(r,'p1_snapshot','')))
            if assessment.blocked and not frozen:
                problem=fee_issue_text(assessment.problems[0])
                logger.warning('Reminder blocked by the fee rules: invoice=%s level=%s fee=%s problem=%s',r['id'],level,fee,problem)
                log_activity('reminder','fee_blocked','failed',invoice_id=r['id'],invoice_no=r['invoice_no'],level=level,fee=fee)
                messagebox.showerror(
                    _('Avgiften följer inte lagen'),
                    _('{problem}\n\nVälj den lagstadgade modellen i Inställningar eller rätt kundtyp på fakturan. Ingen påminnelse skapades.',problem=problem),
                    parent=self,
                )
                break
            frozen_note=''
            if assessment.blocked:
                frozen_note=_('Avgiften {fee} debiterades redan med P1 och ligger över dagens tak. P2 lägger inte till något, men kontrollera fakturan.',fee=money(fee,r['currency']))
                logger.warning('P2 keeps a fee above the cap that was already charged with P1: invoice=%s fee=%s',r['id'],fee)
                log_activity('reminder','fee_frozen_above_cap','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],fee=fee)
            template_name=r['template_vendor'] or _('Ingen matchad mall')
            if logo_choice is None:
                # Asked once per run: a P2 created moments later keeps the same
                # logo and line, and Redigera P2 changes them afterwards.
                logo_choice=self.choose_reminder_details(r,level)
                if logo_choice is None:break
            logo_file,logo_path,logo_name,reminder_message=logo_choice
            doc_language=effective_reminder_language(r)
            deadline_days_cfg=int(setting('payment_deadline_days') or 5)
            deadline_bday,raw_deadline,skipped_reasons=reminder_deadline_info(date.today(),deadline_days_cfg,language=get_language())
            if skipped_reasons and deadline_bday!=raw_deadline:
                deadline_line=_('Sista betalningsdag: {date} (framflyttad från {raw} – {reason} till nästa svenska bankdag)',
                                date=deadline_bday.isoformat(),raw=raw_deadline.isoformat(),reason=', '.join(skipped_reasons))
            else:
                deadline_line=_('Sista betalningsdag: {date}',date=deadline_bday.isoformat())
            confirmation=_('Skapa {level} för {invoice_no}?\n\n{label}: {fee}\n{note}\nMall: {template}\nSVG-logotyp: {logo}\n\nEn e-postförhandsgranskning visas om kunden har adresser. E-postappen öppnas först efter ditt godkännande. När Thunderbird är standardapp i Windows bifogas PDF:en automatiskt; annars bifogas den manuellt. Inget mejl skickas automatiskt.',level=level,invoice_no=r['invoice_no'],label=_(fee_label_key(invoice_customer_type(r),fee,fee_model)),fee=money(fee,r['currency']),note=reminder_fee_note(r),template=template_name,logo=logo_name)
            confirmation+='\n'+deadline_line
            if doc_language!=get_language():
                doc_lang_label=SUPPORTED_LANGUAGES.get(doc_language,doc_language)
                confirmation+='\n'+_('Påminnelsespråk: {language}',language=doc_lang_label)
            if reminder_message:
                confirmation+='\n'+_('Meddelanderad: {message}',message=reminder_message)
            for issue in assessment.warnings:
                confirmation+='\n\n'+fee_issue_text(issue)
            if frozen_note:confirmation+='\n\n'+frozen_note
            omitted_terms=reminder_note_omitted(r['note'])
            if omitted_terms:
                # Transparency: the user sees why the reminder text differs from
                # the invoice text, before anything is created.
                confirmation+='\n\n'+_(
                    'Fakturatexten innehåller ett avgifts- eller räntevillkor. Det skrivs inte ut på påminnelsen, som i stället anger den lagstadgade avgiften och ingen ränta. Fakturatexten på fakturan ändras inte.'
                )
                logger.info('Reminder note contains %d fee/interest clauses that the reminder omits: invoice=%s',len(omitted_terms),r['invoice_no'])
            if ledger_fallback_used and level=='P1':
                confirmation+='\n\n'+_('Underlag: reskontraimporten. Original-PDF-kontrollen har kringgåtts efter ditt godkännande.')
            if not messagebox.askyesno(_('Bekräfta påminnelse'),confirmation):
                break
            day=date.today().isoformat()
            # The chosen logo and line are part of the reminder itself: the
            # snapshot keeps them for history and the invoice remembers them for
            # the next reminder and for a regeneration.
            reminder_row=dict(r)
            reminder_row['logo_file']=logo_file;reminder_row['reminder_message']=reminder_message
            snapshot=capture_reminder_snapshot(reminder_row,fee,day,level,language=doc_language)
            with connect() as db:
                if level=='P1':
                    db.execute('UPDATE invoices SET p1_date=?,p1_snapshot=?,sent_count=sent_count+1,logo_file=?,reminder_message=? WHERE id=?',(day,snapshot,logo_file,reminder_message,r['id']))
                else:
                    db.execute('UPDATE invoices SET p2_date=?,p2_snapshot=?,sent_count=sent_count+1,logo_file=?,reminder_message=? WHERE id=?',(day,snapshot,logo_file,reminder_message,r['id']))
            result=self.write_letter(reminder_row,level,fee,logo_path)
            if result:
                latest=(r,level,result)
                try:
                    record_reminder_journal(
                        DB_PATH,JOURNAL_PATH,r['id'],level,day,fee,current_reminder_terms(fee,invoice_customer_type(r),invoice_currency(r),invoice_fee_agreement(r),fee_model),
                        doc_language,Path(logo_path).name if logo_path else (logo_file or ''),Path(str(result)).name,
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
        # Recreate the P1 exactly as it was sent, even if a later P2 used
        # another logo.
        snapshot=read_reminder_snapshot(row_value(r,'p1_snapshot',''))
        snapshot_logo=snapshot['row'].get('logo_file') if snapshot else None
        logo_file=snapshot_logo if snapshot_logo is not None else (r['logo_file'] if 'logo_file' in r.keys() else None)
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
        w=self._new_toplevel(_('Redigera {level}',level=level));w.resizable(True,True)
        form=self._dialog_form(w,padding=20)
        ttk.Label(form,text=_('Välj logotyp och meddelanderad för {level}. PDF:en skrivs om med ursprungligt påminnelsedatum.',level=level),wraplength=390).pack(anchor='w',pady=(0,10))
        ttk.Label(form,text=_('Logotyp'),style='BodyBold.TLabel').pack(anchor='w')
        logo_var=tk.StringVar(value=current_logo if current_logo in logo_files else choices[0])
        combo=ttk.Combobox(form,textvariable=logo_var,state='readonly',values=choices,width=42)
        combo.pack(fill='x',pady=(3,14))
        ttk.Label(form,text=_('Meddelanderad (frivillig)'),style='BodyBold.TLabel').pack(anchor='w')
        message_var=tk.StringVar(value=reminder_level_message(r,level))
        ttk.Entry(form,textvariable=message_var,width=52).pack(fill='x',pady=(3,0))
        ttk.Label(
            form,text=_('Lämnas fältet tomt tas raden bort helt ur PDF:en.'),
            wraplength=390,justify='left',style='Sub.TLabel',
        ).pack(anchor='w',pady=(6,0))
        def save():
            selected=logo_var.get()
            result=self.update_reminder_logo(
                r,level,selected if selected in logo_files else '',parent=w,
                message=reminder_message_text(message_var.get()),
            )
            if not result:return
            w.destroy();self.refresh()
            messagebox.showinfo(
                _('{level} uppdaterad',level=level),
                _('{level} har skrivits om med vald logotyp och meddelanderad. Påminnelsedatum och historik är oförändrade.',level=level),parent=self,
            )
        buttons=ttk.Frame(form);buttons.pack(fill='x')
        ttk.Button(buttons,text=_('Spara och skriv om {level}',level=level),command=save,style='Accent.TButton').pack(side='left')
        ttk.Button(buttons,text=_('Stäng'),command=w.destroy).pack(side='right')
        prep=getattr(self,'_prepare_modal_toplevel',None)
        if callable(prep):prep(w)
        else:w.grab_set()
        w.wait_window()

    def update_p1_logo(self,row,logo_file,parent=None):
        return self.update_reminder_logo(row,'P1',logo_file,parent=parent)

    def update_p2_logo(self,row,logo_file,parent=None):
        return self.update_reminder_logo(row,'P2',logo_file,parent=parent)

    def update_reminder_logo(self,row,level,logo_file,parent=None,message=None):
        """Regenerate P1/P2 without changing original content, date or history.

        ``message`` is the optional sender line. ``None`` keeps the line the
        reminder already carried, which is what a recreation of a missing PDF
        must do; an empty string removes it.
        """
        if level not in ('P1','P2'):return None
        date_column=level.lower()+'_date';snapshot_column=level.lower()+'_snapshot'
        original_date=dparse(row[date_column])
        if not original_date:return None
        snapshot=read_reminder_snapshot(row[snapshot_column] if snapshot_column in row.keys() else '')
        updated=dict(row)
        reminder_terms=current_reminder_terms(reminder_fee_for(row),invoice_customer_type(row),invoice_currency(row),invoice_fee_agreement(row))
        snapshot_language=''
        if snapshot:
            updated.update(snapshot['row'])
            reminder_terms=snapshot['terms']
            snapshot_language=str(snapshot.get('language') or '')
        updated['id']=row['id'];updated['logo_file']=logo_file
        if message is not None:updated['reminder_message']=reminder_message_text(message)
        else:updated['reminder_message']=reminder_message_text(updated.get('reminder_message') or '')
        fee_value=reminder_terms.get('fee')
        fee=reminder_fee_for(row) if fee_value is None else float(fee_value or 0)
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
                db.execute(
                    'UPDATE invoices SET logo_file=?,reminder_message=? WHERE id=?',
                    (logo_file,updated['reminder_message'],row['id']),
                )
            else:
                # Older reminders have no snapshot. Freeze the values used for
                # this successful regeneration before any later edit.
                snapshot_text=capture_reminder_snapshot(updated,fee,original_date.isoformat(),level)
                db.execute(
                    f'UPDATE invoices SET logo_file=?,reminder_message=?,{snapshot_column}=? WHERE id=?',
                    (logo_file,updated['reminder_message'],snapshot_text,row['id']),
                )
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
        effective_terms=reminder_terms or current_reminder_terms(fee,invoice_customer_type(r),invoice_currency(r),invoice_fee_agreement(r))
        customer_type=normalize_customer_type(effective_terms.get('customer_type') or invoice_customer_type(r))
        if reminder_terms is None:
            # A new reminder is capped by law. A regenerated one keeps the
            # amount that was already printed, so history never changes.
            fee=chargeable_fee(customer_type,fee,fee_model_for_terms(effective_terms))
        # One fee per claim: P2 repeats the P1 fee, it never adds a second one.
        total=remaining+float(fee or 0)
        deadline_days_val=int(effective_terms.get('payment_deadline_days') or 5)
        deadline_date=reminder_deadline_date(today,deadline_days_val,effective_terms if reminder_terms is not None else None)
        doc_language=get_language() if reminder_terms is not None else effective_reminder_language(r)
        logger.info('Reminder generated: level=%s language=%s',level,doc_language)
        pdf_out=Path(output_path) if output_path else reminder_file_path(r,level,today)
        temporary_pdf=None;dialog_options={'parent':parent} if parent is not None else {}
        try:
            descriptor,temporary_name=tempfile.mkstemp(prefix='.paypamin-reminder-',suffix='.pdf',dir=EXPORT_DIR)
            os.close(descriptor);temporary_pdf=Path(temporary_name)
            with language_override(doc_language):
                deadline=format_long_date(deadline_date)
                p2_warning=_('Ansökan om betalningsföreläggande lämnas in till Kronofogden om betalning inte kommit oss tillhanda senast den {deadline}. Kostnader för att driva ärendet kan tillkomma till dess full betalning har skett.',deadline=deadline) if level=='P2' else ''
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
                except FileNotFoundError:report_fault()
                except OSError:logger.warning('Temporary reminder PDF could not be removed: %s',temporary_pdf)

    def write_pdf(self,path,r,level,fee,today,remaining,total,p2_warning,logo_path='',reminder_terms=None):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Flowable
        from xml.sax.saxutils import escape
        effective_terms=reminder_terms or current_reminder_terms(fee,invoice_customer_type(r),invoice_currency(r),invoice_fee_agreement(r))
        customer_type=normalize_customer_type(effective_terms.get('customer_type') or invoice_customer_type(r))
        fee_model=fee_model_for_terms(effective_terms)
        fee_label=_(fee_label_key(customer_type,fee,fee_model))
        currency=normalize_currency(r['currency'])
        styles=getSampleStyleSheet()
        styles.add(ParagraphStyle(name='LetterTitle',parent=styles['Heading1'],fontName='Times-Bold',fontSize=17,leading=21,textColor=colors.HexColor('#202020'),spaceBefore=9,spaceAfter=8))
        styles.add(ParagraphStyle(name='SmallText',parent=styles['BodyText'],fontName='Helvetica',fontSize=8.5,leading=12,spaceAfter=5))
        styles.add(ParagraphStyle(name='RightSmall',parent=styles['SmallText'],alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='AlertText',parent=styles['SmallText'],fontName='Helvetica-Bold',fontSize=9.2,leading=13,borderColor=colors.HexColor('#777777'),borderWidth=.6,borderPadding=8,spaceBefore=8,spaceAfter=10))
        # A short personal line from the sender. A light left border marks it as
        # a note without turning it into a warning.
        styles.add(ParagraphStyle(name='MessageText',parent=styles['SmallText'],fontName='Helvetica-Oblique',fontSize=9.4,leading=13,borderColor=colors.HexColor('#0B2447'),borderWidth=.6,borderPadding=8,spaceBefore=7,spaceAfter=9))
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
                        except Exception:report_fault()
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
        deadline_days_val=int(effective_terms.get('payment_deadline_days') or 5)
        deadline_date=reminder_deadline_date(today,deadline_days_val,effective_terms if reminder_terms is not None else None)
        deadline_text=format_long_date(deadline_date)
        story.append(Paragraph(f"<b>{escape(_('Betalning ska vara oss tillhanda senast {date}.',date=deadline_text))}</b>",styles['SmallText']))
        if level=='P2': story.append(Paragraph(escape(p2_warning),styles['AlertText']))
        reminder_message=reminder_message_text(row_value(r,'reminder_message',''))
        if reminder_message:
            # An empty message adds nothing at all - no label, no frame, no gap.
            story.append(Paragraph(escape(reminder_message),styles['MessageText']))
        raw_note=str(r['note'] or '').strip()
        note=reminder_note_text(raw_note)
        if note!=raw_note:
            logger.info('Reminder note leaves out fee/interest wording: invoice=%s omitted=%d',r['invoice_no'],len(reminder_note_omitted(raw_note)))
            log_activity('reminder','note_terms_omitted','completed',invoice_id=r['id'],invoice_no=r['invoice_no'],omitted=len(reminder_note_omitted(raw_note)))
        if note:
            story.append(Paragraph(f"<b>{_('Avser:')}</b> "+escape(note),styles['SmallText']))
        fee_line=fee_label if level=='P1' else _('{label} (påminnelse 1)',label=fee_label)
        rows=[[Paragraph(f"<b>{_('Specifikation')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Belopp')}</b>",styles['RightSmall'])],
              [Paragraph(_('Faktura {invoice_no} – obetalt belopp',invoice_no=escape(str(r['invoice_no']))),styles['SmallText']),Paragraph(money(remaining,currency),styles['RightSmall'])]]
        if fee>0:rows.append([Paragraph(escape(fee_line),styles['SmallText']),Paragraph(money(fee,currency),styles['RightSmall'])])
        rows.append([Paragraph(f"<b>{_('ATT BETALA')}</b>",styles['SmallText']),Paragraph(f'<b>{money(total,currency)}</b>',styles['RightSmall'])])
        tab=Table(rows,colWidths=[112*mm,54*mm]);tab.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#444444')),('LINEBELOW',(0,1),(-1,-2),.3,colors.HexColor('#cccccc')),('LINEABOVE',(0,-1),(-1,-1),.8,colors.HexColor('#444444')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [Spacer(1,4*mm),tab,Spacer(1,4*mm)]
        hist=[[Paragraph(f"<b>{_('Påminnelse')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Datum')}</b>",styles['SmallText']),Paragraph(f"<b>{_('Avgift')}</b>",styles['RightSmall'])],
              [Paragraph(_('Påminnelse 1'),styles['SmallText']),Paragraph(escape(str(r['p1_date'] or today.isoformat())),styles['SmallText']),Paragraph(money(fee,currency) if fee>0 else '—',styles['RightSmall'])]]
        if level=='P2':hist.append([Paragraph(_('Påminnelse 2 (denna)'),styles['SmallText']),Paragraph(today.isoformat(),styles['SmallText']),Paragraph('—',styles['RightSmall'])])
        ht=Table(hist,colWidths=[78*mm,54*mm,34*mm]);ht.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#aaaaaa')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f1f1f1')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),2)]));story += [ht,Spacer(1,3*mm)]
        if fee>0:
            story.append(Paragraph(_('Ovanstående påminnelser har skickats för fakturan. Avgiften debiteras en gång per fordran och ingår i beloppet ovan.'),styles['SmallText']))
            story.append(Paragraph(escape(_(legal_basis_key(customer_type,fee,fee_model))),styles['SmallText']))
        else:
            story.append(Paragraph(_('Ingen avgift debiteras för den här fakturan.'),styles['SmallText']))
        payment_text=f"<b>{_('Betalning')}</b><br/>Bankgiro: 5660-4200 · Swish: 123 188 42 87<br/>{_('Betalningsmottagare')}: Tadega AB. {_('Ange fakturanumret vid betalning.')}<br/>IBAN: SE26 6000 0000 0005 3862 3322 · BIC: HANDSESS"
        story.append(Paragraph(payment_text,styles['SmallText']))
        if fee>0:
            terms=_('Varan förblir vår egendom tills full betalning erlagts. Eventuella anmärkningar på fakturan ska göras inom {days} dagar. {label}: {fee}, högst en gång per fordran. Vid beställning av specialdelar lämnas ingen returrätt.',days=escape(str(effective_terms.get('objection_days') or '')),label=escape(fee_label),fee=money(fee,currency))
        else:
            terms=_('Varan förblir vår egendom tills full betalning erlagts. Eventuella anmärkningar på fakturan ska göras inom {days} dagar. Ingen påminnelseavgift debiteras. Vid beställning av specialdelar lämnas ingen returrätt.',days=escape(str(effective_terms.get('objection_days') or '')))
        story += [Spacer(1,2*mm),HRFlowable(width='100%',thickness=.4,color=colors.HexColor('#999999')),Spacer(1,2*mm),Paragraph(terms,styles['SmallText'])]
        doc.build(story)
    def _confirm_learned_suggestions(self,suggestions,parent=None):
        """Ask once before using weaker, learned invoice defaults."""
        names=[]
        for learned in suggestions:
            if learned.scope_label not in names:names.append(learned.scope_label)
        lines=[]
        for learned in suggestions:
            value=learned.value.replace('\n',' · ')
            if len(value)>120:value=value[:117]+'…'
            lines.append(_('{field}: {value} ({count} gånger)',field=_(LEARNING_FIELD_LABELS.get(learned.field,learned.field)),value=value,count=learned.observations))
        return messagebox.askyesno(
            _('Inlärda förslag'),
            _('Appen har sett samma mönster flera gånger för {name}, men fyller aldrig i något på egen hand. Vill du använda förslagen den här gången?\n\n{suggestions}\n\nInget sparas förrän du själv sparar fakturan. Du kan granska och glömma inlärda värden i Inställningar.',
              name=', '.join(names),suggestions='\n'.join(lines)),
            parent=parent,
        )

    def review_learning(self,parent=None):
        """Show everything the app has learned and allow forgetting it."""
        win=self._new_toplevel(_('Granska inlärning'));win.geometry('1000x600');win.minsize(780,430)
        try:
            if parent is not None:parent.grab_release()
        except Exception:report_fault()
        buttons=ttk.Frame(win,padding=(16,10));buttons.pack(side='bottom',fill='x')
        ttk.Separator(win,orient='horizontal').pack(side='bottom',fill='x')
        form=ttk.Frame(win,padding=16);form.pack(fill='both',expand=True)
        ttk.Label(form,text=_('Appen lär sig endast av värden du själv har sparat eller valt. Allt finns lokalt i databasen.'),style='Sub.TLabel',wraplength=930,justify='left').pack(anchor='w')
        summary=tk.StringVar(value='')
        ttk.Label(form,textvariable=summary,style='Sub.TLabel').pack(anchor='w',pady=(6,10))
        ttk.Label(form,text=_('Alla inlärda värden är förslag. Inget används utan att du svarar ja.'),style='BodyBold.TLabel').pack(anchor='w',pady=(4,8))
        columns=('kind','scope','field','value','evidence')
        headings={'kind':'Område','scope':'Namn','field':'Uppgift','value':'Inlärt värde','evidence':'Antal'}
        widths={'kind':110,'scope':230,'field':200,'value':330,'evidence':70}
        tree=ttk.Treeview(form,columns=columns,show='headings',selectmode='browse')
        translated_headings={col:_(headings[col]) for col in columns}
        for column in columns:
            tree.heading(column,text=translated_headings[column])
            tree.column(column,width=self._px(widths[column]),stretch=column in ('scope','value'))
        enable_treeview_features(tree,columns,translated_headings,initial_sort='evidence',initial_reverse=True)
        tree.pack(fill='both',expand=True)
        rows={}
        def refresh():
            for item in tree.get_children():tree.delete(item)
            rows.clear()
            with connect() as db:
                items=learning.entries(db)
                stats=learning.counts(db)
                suppliers=db.execute('SELECT COUNT(*) FROM vendor_logos').fetchone()[0]
                zones=db.execute('SELECT COUNT(*) FROM pdf_zones').fetchone()[0]
                reminders=db.execute("SELECT COUNT(*) FROM invoices WHERE p1_date<>'' OR p2_date<>''").fetchone()[0]
            summary.set(_('Inlärda värden: {values} · Leverantörsmallar: {suppliers} · PDF-zonmallar: {zones} · Påminnelser: {reminders}',values=stats['values'],suppliers=suppliers,zones=zones,reminders=reminders))
            for entry in items:
                value=entry.value.replace('\n',' · ')
                if len(value)>110:value=value[:107]+'…'
                item=tree.insert('', 'end', values=(
                    _('Kund') if entry.kind==learning.KIND_CUSTOMER else _('Leverantör'),
                    entry.scope_label,_(LEARNING_FIELD_LABELS.get(entry.field,entry.field)),value,
                    entry.evidence,
                ))
                rows[item]=entry
        def forget_selected():
            selection=tree.selection()
            if not selection:return
            entry=rows.get(selection[0])
            if entry is None:return
            preview=entry.value.replace('\n',' · ')[:150]
            if not messagebox.askyesno(_('Glöm inlärt värde'),_('Glöm {value} för {name}? Fakturor, påminnelser och mallar ändras inte.',value=preview,name=entry.scope_label),parent=win):return
            with connect() as db:learning.forget(db,kind=entry.kind,scope=entry.scope,field=entry.field,value=entry.value)
            logger.info('Learned value forgotten: kind=%s field=%s',entry.kind,entry.field)
            log_activity('learning','forget_value','completed',kind=entry.kind,field=entry.field)
            refresh()
        def forget_all():
            if not messagebox.askyesno(_('Glöm all inlärning'),_('Ta bort alla inlärda värden och leverantörslayouter? Fakturor, kunder, påminnelser och mallar ändras inte.'),parent=win):return
            with connect() as db:
                learning.forget(db)
                db.execute('DELETE FROM learning_signatures')
            logger.info('All learned values were forgotten by user')
            log_activity('learning','forget_all','completed')
            refresh()
        ttk.Button(buttons,text=_('Glöm valt'),command=forget_selected).pack(side='left')
        ttk.Button(buttons,text=_('Glöm allt'),command=forget_all).pack(side='left',padx=(8,0))
        def close():
            win.destroy()
            try:
                if parent is not None and parent.winfo_exists():parent.grab_set()
            except Exception:report_fault()
        ttk.Button(buttons,text=_('Stäng'),command=close).pack(side='right')
        win.protocol('WM_DELETE_WINDOW',close)
        refresh()
        if parent is not None:
            try:win.transient(parent)
            except Exception:report_fault()
        win.focus_force()
        log_activity('learning','review_opened','completed')

    def settings(self):
        """Show every setting, laid out to fit the current window.

        The form reflows between one and three field columns as the dialogue
        is resized, help texts wrap, and the footer with Save/Close stays
        outside the scrolling area. Nothing is hidden in tabs or collapsed
        sections; scrolling is only used for what genuinely cannot fit.
        """
        w=self._new_toplevel(_('Inställningar'));w.grab_set();w.resizable(True,True)
        footer=ttk.Frame(w,padding=(16,10));footer.pack(side='bottom',fill='x')
        ttk.Separator(w,orient='horizontal').pack(side='bottom',fill='x')
        surface=ScrollableForm(w,tk,ttk,padding=16)
        form=surface.form
        grid=ResponsiveGrid(form)
        available_width=dialog_available_width(w)
        area_height=window_work_area_height(w)

        def heading(text):
            grid.add_heading(ttk.Label(form,text=_(text),style='Heading.TLabel'))
        def hint(text,**values):
            grid.add_hint(ttk.Label(
                form,text=_(text,**values),style='Sub.TLabel',
                justify='left',wraplength=max(240,available_width-32),
            ))
        def check(text,variable,**values):
            return grid.add_full(ttk.Checkbutton(
                form,text=_(text,**values),variable=variable,
            ))
        def cell(label,key):
            frame=ttk.Frame(form)
            label_widget=ttk.Label(frame,text=_(label),style='Sub.TLabel',justify='left')
            label_widget.grid(row=0,column=0,sticky='w')
            entry=ttk.Entry(frame,width=14)
            entry.grid(row=1,column=0,sticky='w',pady=(2,0))
            entry.insert(0,setting(key))
            grid.add_cell(frame,label=label_widget,entry=entry)
            return entry
        # Appearance comes first: it is the setting most people change on the
        # first day, and it repaints the whole window the moment it is saved.
        self._theme_var=tk.StringVar(value=_(appearance.THEME_LABELS[appearance.normalize_theme(getattr(self,'_theme_setting',appearance.DEFAULT_THEME))]))
        theme_frame=ttk.Frame(form)
        theme_label=ttk.Label(theme_frame,text=_('Tema'),style='Sub.TLabel')
        theme_label.grid(row=0,column=0,sticky='w')
        ttk.Combobox(
            theme_frame,textvariable=self._theme_var,state='readonly',width=26,
            values=[_(label) for label in appearance.THEME_LABELS.values()],
        ).grid(row=1,column=0,sticky='w',pady=(2,0))
        grid.add_cell(theme_frame,label=theme_label)
        hint('Ljust är appens grund. Mörkt dämpar ljuset i ett mörkt rum, och Följ systemet byter automatiskt när skrivbordet byter tema.')
        hint('Högkontrast går före temat: när skrivbordet begär hög kontrast används alltid den svartvita paletten.')
        language_var=tk.StringVar(value=SUPPORTED_LANGUAGES[get_language()])
        heading('Språk')
        language_frame=ttk.Frame(form)
        language_label=ttk.Label(language_frame,text=_('Språk'),style='Sub.TLabel')
        language_label.grid(row=0,column=0,sticky='w')
        ttk.Combobox(
            language_frame,textvariable=language_var,state='readonly',
            values=list(SUPPORTED_LANGUAGES.values()),width=18,
        ).grid(row=1,column=0,sticky='w',pady=(2,0))
        grid.add_cell(language_frame,label=language_label)
        fields=[
            ('Dagar efter förfallodatum till P1','p1_days'),
            ('Dagar efter P1 till P2','p2_days'),
            ('Dagar efter P2 till Kronofogden-granskning','p3_days'),
            ('Anmärkningstid enligt fakturavillkor (dagar)','objection_days'),
            ('Betalningsfrist på påminnelsen (dagar)','payment_deadline_days'),
        ]
        heading('Påminnelser')
        entries={}
        for label,key in fields:
            entries[key]=cell(label,key)
        # Two fixed models are selectable; neither amount can be typed. The
        # statutory model stays one click away so 4 § and 4 a § are never lost.
        fee_model_var=tk.StringVar(value=_(FEE_MODEL_LABELS[current_fee_model()]))
        model_frame=ttk.Frame(form)
        model_label=ttk.Label(model_frame,text=_('Avgiftsmodell'),style='Sub.TLabel',justify='left')
        model_label.grid(row=0,column=0,sticky='w')
        model_combo=ttk.Combobox(
            model_frame,textvariable=fee_model_var,state='readonly',width=52,
            values=[_(label) for label in FEE_MODEL_LABELS.values()],
        )
        model_combo.grid(row=1,column=0,sticky='w',pady=(2,0))
        grid.add_cell(model_frame,label=model_label)
        fee_summary=ttk.Label(form,text='',style='BodyBold.TLabel',justify='left',wraplength=max(240,available_width-32))
        grid.add_full(fee_summary)
        fee_model_hint=ttk.Label(form,text='',style='Sub.TLabel',justify='left',wraplength=max(240,available_width-32))
        grid.add_hint(fee_model_hint)
        def chosen_fee_model():
            for code,label in FEE_MODEL_LABELS.items():
                if _(label)==fee_model_var.get():return code
            return DEFAULT_FEE_MODEL
        def update_fee_summary(*_args):
            if chosen_fee_model()==FEE_MODEL_PER_REMINDER:
                fee_summary.configure(text=_('Avgift per påminnelse: {fee}',fee=money(PER_REMINDER_FEE)))
                fee_model_hint.configure(text=_('150 kr per påminnelse enligt avtal, en gång per fordran. Mot en privatperson gäller 4 § med högst 60 kr, så välj den lagstadgade modellen när påminnelsen ska gälla en privatperson.'))
            else:
                fee_summary.configure(text=_('Påminnelseavgift: {fee} · Förseningsersättning: {compensation}',
                                             fee=money(REMINDER_FEE_CAP),compensation=money(LATE_PAYMENT_COMPENSATION)))
                fee_model_hint.configure(text=_('Beloppen följer lag (1981:739): privatpersoner får påminnelseavgift enligt 4 § och företag eller myndigheter förseningsersättning enligt 4 a §.'))
        model_combo.bind('<<ComboboxSelected>>',update_fee_summary)
        update_fee_summary()
        hint('Avgiften debiteras en gång per fordran, aldrig en gång per påminnelse. En redan skapad påminnelse behåller sitt belopp.')
        agreement_var=tk.StringVar(value=_(AGREEMENT_LABELS[normalize_agreement(setting('fee_agreement'))]))
        agreement_frame=ttk.Frame(form)
        agreement_label=ttk.Label(agreement_frame,text=_('Var avtalas påminnelseavgiften som standard?'),style='Sub.TLabel',justify='left')
        agreement_label.grid(row=0,column=0,sticky='w')
        ttk.Combobox(
            agreement_frame,textvariable=agreement_var,state='readonly',width=26,
            values=[_(label) for label in AGREEMENT_LABELS.values()],
        ).grid(row=1,column=0,sticky='w',pady=(2,0))
        grid.add_cell(agreement_frame,label=agreement_label)
        hint('Påminnelseavgiften kräver att rätten till den avtalades senast när skulden uppstod. Företag och myndigheter får förseningsersättning i stället, utan avtal.')
        hint('Modellen gäller nya påminnelser. Redan skapade påminnelser behåller sitt belopp och sin grund.')
        hint('Taket gäller i SEK. På en faktura i annan valuta kontrollerar appen inte beloppet automatiskt.')
        heading('Start och uppdateringar')
        autostart_var=tk.BooleanVar(value=setting('autostart')=='1')
        check('Starta {app_name} automatiskt när jag loggar in',autostart_var,app_name=APP_NAME)
        hint('Autostart för din användare · {platforms}',platforms=SUPPORTED_PLATFORMS)
        automatic_updates_var=tk.BooleanVar(value=setting('update_auto')=='1')
        check('Sök efter och installera uppdateringar automatiskt två gånger per dygn',automatic_updates_var)
        # Starting in the tray is not a choice any more, so there is no
        # checkbox for it - only a line that says what will happen.
        hint('PayPamin Flow startar alltid minimerad i systemfältet. Klicka på ikonen, eller starta appen igen, för att öppna fönstret.')
        heading('Import, reskontra och cache')
        automatic_import_var=tk.BooleanVar(value=setting('auto_import')=='1')
        check('Bevaka importmappen och importera nya PDF:er automatiskt',automatic_import_var)
        ledger_reminder_var=tk.BooleanVar(value=setting('ledger_friday_reminder')=='1')
        check('Påminn om att importera kundreskontralista varje fredag',ledger_reminder_var)
        automatic_cache_var=tk.BooleanVar(value=setting('cache_auto')=='1')
        check('Rensa appcache automatiskt en gång per dygn samt vid avslut',automatic_cache_var)
        hint('Under dagen endast cache äldre än 24 timmar; vid avslut all identifierad appcache.\nFakturor och importmappen rörs inte.')
        heading('Tillgänglighet')
        self._font_scale_var=tk.StringVar(value=font_scale_label(self.ui_font_scale))
        text_frame=ttk.Frame(form)
        text_label=ttk.Label(text_frame,text=_('Textstorlek'),style='Sub.TLabel')
        text_label.grid(row=0,column=0,sticky='w')
        ttk.Combobox(
            text_frame,textvariable=self._font_scale_var,state='readonly',
            values=[font_scale_label(choice) for choice in FONT_SCALE_CHOICES],width=16,
        ).grid(row=1,column=0,sticky='w',pady=(2,0))
        grid.add_cell(text_frame,label=text_label)
        hint('Textstorleken kan också ändras med Ctrl/Cmd +, Ctrl/Cmd − och Ctrl/Cmd 0.')
        hint('Högkontrast följer systemets inställning och uppdateras automatiskt.')
        heading('Självlärande')
        learning_var=tk.BooleanVar(value=setting('learning_enabled')!='0')
        learning_row=ttk.Frame(form)
        ttk.Checkbutton(
            learning_row,text=_('Lär sig av sparade fakturor och leverantörsval (endast lokalt)'),
            variable=learning_var,
        ).pack(side='left')
        ttk.Button(
            learning_row,text=_('Granska inlärning'),command=lambda:self.review_learning(w),
        ).pack(side='left',padx=(14,0))
        grid.add_full(learning_row)
        hint('Inga inlärda värden används utan att du bekräftar dem varje gång. Allt kan glömmas.')
        def reflow(width=None):
            try:
                current=int(width if width is not None else surface.canvas.winfo_width()-32)
            except Exception:
                current=0
            if current<=1:current=available_width
            if area_height:
                grid.compact=area_height<640
            grid.apply(current)
        def schedule_reflow(event=None):
            source=getattr(event,'widget',None)
            if source is not None and source is not w and source is not surface.canvas:return
            pending=getattr(w,'_settings_reflow_job',None)
            if pending:
                try:w.after_cancel(pending)
                except Exception:report_fault()
            w._settings_reflow_job=w.after_idle(reflow)
        surface.canvas.bind('<Configure>',schedule_reflow,add='+')
        reflow(available_width)
        try:
            surface.fit_to_content(
                max_width=max(520,available_width),
                max_height=max(320,area_height-140) if area_height else 720,
            )
        except Exception:report_fault()
        fit_window_to_screen(w,min_width=520,min_height=360)
        def save():
            try:
                for k,e in entries.items():
                    v=e.get().strip()
                    if k in ('p1_days','p2_days','p3_days','objection_days','payment_deadline_days') and int(v)<0:raise ValueError()
            except (ValueError,TypeError):
                messagebox.showerror(_('Ogiltigt värde'),_('Ange positiva siffror i inställningarna.'),parent=w);return
            try:
                set_autostart(autostart_var.get())
            except AutostartError as exc:
                messagebox.showerror(_('Autostart kunde inte sparas'),_('{error}\n\nPlats: {location}',error=_(str(exc)),location=autostart_location()),parent=w);return
            for k,e in entries.items():set_setting(k,e.get().strip().replace(',','.'))
            for code,label in AGREEMENT_LABELS.items():
                if _(label)==agreement_var.get():set_setting('fee_agreement',code)
            new_language=language_code(language_var.get())
            language_changed=new_language!=get_language()
            new_theme=appearance.DEFAULT_THEME
            for code,label in appearance.THEME_LABELS.items():
                if _(label)==self._theme_var.get():new_theme=code
            set_setting('autostart','1' if autostart_var.get() else '0')
            set_setting('update_auto','1' if automatic_updates_var.get() else '0')
            set_setting('auto_import','1' if automatic_import_var.get() else '0')
            set_setting('ledger_friday_reminder','1' if ledger_reminder_var.get() else '0')
            set_setting('cache_auto','1' if automatic_cache_var.get() else '0')
            set_setting('learning_enabled','1' if learning_var.get() else '0')
            set_setting('language',new_language)
            set_setting(appearance.THEME_SETTING,new_theme)
            set_setting('fee_model',chosen_fee_model())
            new_font_scale=normalize_font_scale(self._font_scale_var.get())
            set_setting(FONT_SCALE_SETTING,font_scale_storage(new_font_scale))
            self.set_font_scale(new_font_scale,persist=False)
            self.set_theme(new_theme,persist=False)
            set_language(new_language)
            refresh_json_journal(parent=w)
            logger.info('Settings saved; theme=%s autostart=%s learning=%s automatic_updates=%s automatic_import=%s ledger_friday=%s cache_auto=%s language=%s fee_model=%s',new_theme,bool(autostart_var.get()),bool(learning_var.get()),bool(automatic_updates_var.get()),bool(automatic_import_var.get()),bool(ledger_reminder_var.get()),bool(automatic_cache_var.get()),new_language,chosen_fee_model())
            w.destroy()
            if language_changed:self.rebuild_ui()
            else:self.refresh()
        ttk.Button(footer,text=_('Stäng'),command=w.destroy).pack(side='right')
        ttk.Button(footer,text=_('Spara inställningar'),command=save,style='Accent.TButton').pack(side='right',padx=(0,8))

def _tk_version():
    """Return the Tk patch level for the startup record without opening a window."""
    try:return str(tk.TkVersion)
    except Exception:return 'unknown'


def main():
    instance=None
    try:
        # A start through python.exe still has a console attached; hide it and
        # make sure every child process is created without one, before anything
        # else in the app runs.
        hide_own_console_window()
        configure_console_free_subprocesses()
        configure_windows_dpi_awareness()
        configure_windows_app_identity()
        activation_requested=threading.Event()
        instance=SingleInstance(APP_DIR,on_activate=activation_requested.set)
        # An updated child must confirm its UI before the old app exits. It
        # claims ownership immediately afterwards instead of activating the old app.
        update_handoff=bool(os.environ.get(UPDATE_READY_FILE_ENV) and os.environ.get(UPDATE_READY_TOKEN_ENV))
        if not update_handoff and not instance.acquire():
            if instance.activated_existing:
                logger.info('A later start activated the existing PayPamin Flow instance')
            else:
                logger.warning('PayPamin Flow is already running but could not be activated; no duplicate was started')
            return
        init_db()
        logger.info('%s %s started on %s',APP_NAME,APP_VERSION,sys.platform)
        logger.info(
            'Runtime: release_id=%s commit=%s python=%s tk=%s data_dir=%s log_dir=%s '
            'log_files=%s retention_days=%d',
            APP_RELEASE_ID or 'source',APP_RELEASE_COMMIT or 'source',platform.python_version(),
            _tk_version(),APP_DIR,LOG_DIR,','.join(DAILY_LOG_NAMES),RETENTION_DAYS,
        )
        log_activity('application','started','completed',version=APP_VERSION,platform=sys.platform,commit=APP_RELEASE_COMMIT)
        try:
            report=_refresh_and_archive_logs()
            logger.info('Consolidated error log refreshed: errors=%d sources=%d',report.error_count,report.source_count)
        except Exception:logger.exception('Consolidated error log refresh failed')
        try:
            target_root=Path(sys.executable).resolve() if getattr(sys,'frozen',False) else APP_FOLDER
            cleaned_backups=cleanup_completed_update_backups(target_path=target_root)
            if cleaned_backups:logger.info('Removed %d completed update backup artifact(s)',cleaned_backups)
        except Exception:logger.exception('Completed update backup cleanup failed')
        window=ReminderApp()
        window._single_instance=instance
        window._single_instance_activation=activation_requested
        if update_handoff:
            claim_instance=getattr(window,'_claim_single_instance_after_update',None)
            if claim_instance is not None:claim_instance(time.monotonic())
        else:
            poll_activation=getattr(window,'_poll_single_instance_activation',None)
            if poll_activation is not None:poll_activation()
        after_idle=getattr(window,'after_idle',None)
        if after_idle is not None:after_idle(mark_update_ready)
        else:mark_update_ready()
        # The app always starts in the system tray. It is not a preference any
        # more: the window is opened by clicking the tray icon or by starting
        # PayPamin Flow a second time, and starting hidden is what keeps the
        # desktop clean after a login start. --minimized is still accepted so an
        # older shortcut keeps working, but it no longer changes anything.
        starter=getattr(window,'start_minimized',None)
        if starter is not None:starter()
        elif hasattr(window,'hide_to_tray'):window.hide_to_tray()
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
    finally:
        if instance is not None:instance.release()


if __name__=='__main__':
    main()
