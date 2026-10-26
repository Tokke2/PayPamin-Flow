"""Swedish and English UI translations for PayPamin Flow.

Swedish source strings are used as stable message keys. Dynamic values are
interpolated after translation so word order can differ between languages.
"""
from __future__ import annotations

from datetime import date

from currency import normalize_currency

SUPPORTED_LANGUAGES = {"sv": "Svenska", "en": "English"}
DEFAULT_LANGUAGE = "sv"
_current_language = DEFAULT_LANGUAGE

_ENGLISH = {
    # Workflow states and filters
    "Aktuella": "Current",
    "Alla": "All",
    "Ignorerade": "Ignored",
    "Ignorerad": "Ignored",
    "IGNORERAD": "IGNORED",
    "Granska uppgifter": "Review details",
    "Avslutad": "Completed",
    "Kontrollera datum": "Check date",
    "P1 att skapa": "Create P1",
    "Väntar P1": "Waiting for P1",
    "P2 att skapa": "Create P2",
    "Väntar P2": "Waiting for P2",
    "Kronofogden – granska": "Kronofogden – review",
    "Väntar – efter P2": "Waiting – after P2",

    # Main window and shared actions
    "Inställningar": "Settings",
    "Om {app_name}": "About {app_name}",
    "Lokal app · dina filer stannar på datorn": "Local app · your files stay on your computer",
    "Lokal app för fakturor och betalningspåminnelser": "Local app for invoices and payment reminders",
    "Version {version}": "Version {version}",
    "Skapare: {author}": "Creator: {author}",
    "{copyright} · Skapare: {author}": "{copyright} · Creator: {author}",
    "Stäng": "Close",
    "Spara": "Save",
    "Spara inställningar": "Save settings",
    "Skanna importmapp": "Scan import folder",
    "Öppna importmapp": "Open import folder",
    "Lägg till faktura-PDF": "Add invoice PDF",
    "Lägg till manuellt": "Add manually",
    "Skapa påminnelse": "Create reminder",
    "Ignorera / återaktivera": "Ignore / reactivate",
    "Redigera vald": "Edit selected",
    "Visa fellogg": "Show error log",
    "Ta bort vald": "Delete selected",
    "Visa:": "Show:",
    "Välj en rad för att förhandsgranska / hantera.": "Select a row to preview / manage.",
    "Logotyp vid export:": "Logo for export:",
    "Uppdatera lista": "Refresh list",
    "Öppna SVG-mapp": "Open SVG folder",
    "Importera PDF eller lägg till en faktura manuellt.": "Import a PDF or add an invoice manually.",
    "Startvärden: P1 +5 dagar · P2 +5 dagar · Kronofogden-granskning +5 dagar · avgift 150 i fakturans valuta · ränta 23%": "Defaults: P1 +5 days · P2 +5 days · Kronofogden review +5 days · fee 150 in the invoice currency · interest 23%",
    "Redigera faktura": "Edit invoice",
    "Ta bort fakturarad": "Delete invoice row",
    "(Ingen logotyp)": "(No logo)",
    "(Lägg SVG i mappen svg)": "(Add an SVG to the svg folder)",
    "(Välj logotyp för mallen)": "(Choose a logo for the template)",
    "Ingen leverantörsmall": "No supplier template",
    "Ingen matchad mall": "No matched template",
    "ingen matchad logotyp": "no matched logo",
    "Granskad": "Reviewed",
    "KRÄVER GRANSKNING": "REVIEW REQUIRED",
    "Ingen fakturatext": "No invoice text",
    "Mall:": "Template:",
    "Logotyp:": "Logo:",
    "Skickad {date}": "Sent {date}",

    # Table columns
    "Fakturanr": "Invoice no.",
    "Kund": "Customer",
    "Förfallodatum": "Due date",
    "Fakturabelopp": "Invoice amount",
    "Kvar att betala": "Amount outstanding",
    "P1 skapades": "P1 created",
    "P2 ska skickas": "P2 due",
    "Status / nästa steg": "Status / next step",
    "Påminnelseavgift": "Reminder fee",

    # GitHub release update checks
    "Sök efter uppdateringar": "Check for updates",
    "Söker…": "Checking…",
    "Uppdateringskontroll": "Update check",
    "En uppdateringskontroll eller installation pågår redan.": "An update check or installation is already running.",
    "Kunde inte söka efter uppdateringar": "Could not check for updates",
    "Ett oväntat fel uppstod vid uppdateringskontrollen.": "An unexpected error occurred during the update check.",
    "Ingen uppdatering tillgänglig": "No update available",
    "Ingen nyare version finns.\n\nInstallerad version: {current}\nSenaste release: {latest}": "No newer version is available.\n\nInstalled version: {current}\nLatest release: {latest}",
    "Uppdatering tillgänglig": "Update available",
    "Version {version} är tillgänglig": "Version {version} is available",
    "Installerad version: {current}\nSenaste release: {latest}\n\nLokala fakturor, inställningar och mallar påverkas inte.": "Installed version: {current}\nLatest release: {latest}\n\nLocal invoices, settings and templates are not affected.",
    "Öppna nedladdningssida": "Open download page",
    "Kunde inte öppna webbläsaren": "Could not open the browser",
    "Öppna nedladdningssidan manuellt:\n{url}": "Open the download page manually:\n{url}",
    "Ingen publicerad stabil release hittades på GitHub.": "No published stable release was found on GitHub.",
    "GitHub tillåter inte fler uppdateringskontroller just nu. Försök igen senare.": "GitHub is not allowing more update checks right now. Try again later.",
    "GitHub returnerade HTTP {status} vid uppdateringskontrollen.": "GitHub returned HTTP {status} during the update check.",
    "Kunde inte kontakta GitHub. Kontrollera internetanslutningen och försök igen.": "Could not contact GitHub. Check your internet connection and try again.",
    "GitHub returnerade ett oväntat svar vid uppdateringskontrollen.": "GitHub returned an unexpected response during the update check.",

    "Uppdaterar…": "Updating…",
    "Installera och starta om": "Install and restart",
    "Uppdateringen kunde inte installeras": "The update could not be installed",
    "{error}\n\nDu kan ladda ner uppdateringen manuellt:\n{url}": "{error}\n\nYou can download the update manually:\n{url}",
    "Ett oväntat fel uppstod vid installationen.": "An unexpected error occurred during installation.",
    "Automatisk installation kräver ett native-programpaket. Källkodskörning uppdateras manuellt.": "Automatic installation requires a native application package. Source checkouts are updated manually.",
    "Sök efter och installera uppdateringar automatiskt två gånger per dygn": "Check for and install updates automatically twice a day",
    "Automatiska uppdateringar stöds inte på det här operativsystemet.": "Automatic updates are not supported on this operating system.",
    "Kunde inte hitta den installerade macOS-appen.": "Could not find the installed macOS app.",
    "Uppdateringspaketet har en osäker nedladdningsadress.": "The update package has an unsafe download URL.",
    "Uppdateringspaketet är större än den tillåtna gränsen.": "The update package exceeds the allowed size limit.",
    "Kunde inte ladda ner uppdateringspaketet. Kontrollera internetanslutningen och försök igen.": "Could not download the update package. Check your internet connection and try again.",
    "Kontrollsumman för uppdateringspaketet saknas eller är ogiltig.": "The update package checksum is missing or invalid.",
    "Det automatiska uppdateringspaketet eller dess kontrollsumma saknas för {platform}.": "The automatic update package or its checksum is missing for {platform}.",
    "Uppdateringspaketet kunde inte verifieras mot SHA-256-kontrollsumman.": "The update package could not be verified against its SHA-256 checksum.",
    "Windows-paketet har ett oväntat innehåll.": "The Windows package has unexpected content.",
    "Linux-paketet har ett oväntat innehåll.": "The Linux package has unexpected content.",
    "Linux-programfilen saknas i uppdateringspaketet.": "The Linux executable is missing from the update package.",
    "macOS-paketet innehåller en osäker sökväg.": "The macOS package contains an unsafe path.",
    "macOS-paketet innehåller filer som inte stöds.": "The macOS package contains unsupported files.",
    "macOS-paketet är större än den tillåtna gränsen.": "The macOS package exceeds the allowed size limit.",
    "macOS-appen saknas eller har ett oväntat innehåll.": "The macOS app is missing or has unexpected content.",
    "Uppdateringspaketet är skadat eller har ett oväntat format.": "The update package is damaged or has an unexpected format.",
    "Appens installationsmapp är inte skrivbar. Installera uppdateringen manuellt.": "The app installation folder is not writable. Install the update manually.",
    "Kunde inte starta installationsprogrammet för uppdateringen.": "Could not start the update installer.",

    # Dependencies and startup
    "Förbereder appen": "Preparing the app",
    "Installerar saknade Python-tillägg": "Installing missing Python add-ons",
    "Detta behövs för att läsa och skapa PDF. Installationen sker i bakgrunden.": "These are required to read and create PDFs. Installation runs in the background.",
    "Ansluter till Python-pakettjänsten…": "Connecting to the Python package service…",
    "Tillägg klara": "Add-ons ready",
    "Nödvändiga PDF-tillägg installerades. Appen är redo.": "The required PDF add-ons were installed. The app is ready.",
    "Kunde inte installera tillägg": "Could not install add-ons",
    "PDF-tilläggen kunde inte installeras automatiskt. Kontrollera internetanslutning och pip.\n\n": "The PDF add-ons could not be installed automatically. Check your internet connection and pip.\n\n",
    "Autostart kunde inte uppdateras": "Autostart could not be updated",
    "Inställningen för autostart kunde inte sparas.\n\nPlats: {location}\n\n{error}": "The autostart setting could not be saved.\n\nLocation: {location}\n\n{error}",
    "Appen kunde inte starta. Kontrollera att Python installerats med Tkinter.\n\n{error}": "The app could not start. Check that Python was installed with Tkinter.\n\n{error}",

    # Selection and invoice details
    "Välj faktura": "Choose invoice",
    "Markera en faktura i listan först.": "Select an invoice in the list first.",
    "{customer} · {invoice_no} · Belopp: {amount} · {stage} · {review} · Mall: {vendor} · Logotyp: {logo} · {note}": "{customer} · {invoice_no} · Amount: {amount} · {stage} · {review} · Template: {vendor} · Logo: {logo} · {note}",

    # PDF preview and field templates
    "Förhandsgranska faktura – markera fält att läsa": "Preview invoice – select fields to read",
    "Leverantör / mallnamn:": "Supplier / template name:",
    "Dra en ruta över värdet. Sparade rutor kan återanvändas för samma mall.": "Drag a box around the value. Saved boxes can be reused for the same template.",
    "Sida 1": "Page 1",
    "Sida {page} av {pages}": "Page {page} of {pages}",
    "Markera fält:": "Select field:",
    "Fakturanummer": "Invoice number",
    "Valuta": "Currency",
    "Belopp (ATT BETALA)": "Amount (TOTAL DUE)",
    "Fakturadatum": "Invoice date",
    "Kundnamn": "Customer name",
    "Fakturatext / Avser": "Invoice text / Reference",
    "Avlästa värden": "Detected values",
    "Logotyp som matchar fakturan": "Logo matching the invoice",
    "Klicka Markera vid ett fält och dra sedan en ruta runt värdet.": "Click Select next to a field, then drag a box around the value.",
    "Markera värdet för: {label}": "Select the value for: {label}",
    "Markera": "Select",
    "{field} · {count} matchningar": "{field} · {count} matches",
    "Rutan blev för liten. Dra en större ruta.": "The box was too small. Drag a larger box.",
    "Ingen text hittades i rutan. Försök igen eller kontrollera OCR.": "No text was found in the box. Try again or check OCR.",
    "{label} avläst: {value}": "{label} read: {value}",
    "Mallnamn saknas": "Template name missing",
    "Ange leverantör eller mallnamn.": "Enter a supplier or template name.",
    "Fortsätt utan att spara mall": "Continue without saving a template",
    "Spara markerade fält som mall och fortsätt": "Save selected fields as a template and continue",

    # Import and invoice editor
    "Importmapp tom": "Import folder empty",
    "Lägg faktura-PDF:er i mappen:\n{folder}": "Place invoice PDFs in the folder:\n{folder}",
    "Skanning klar": "Scan complete",
    "Importerade: {imported}\nDubbletter som inte importerades: {duplicates}\nAvbrutna: {skipped}\nFel: {failed}": "Imported: {imported}\nDuplicates not imported: {duplicates}\nCancelled: {skipped}\nErrors: {failed}",
    "Dubblettfaktura": "Duplicate invoice",
    "Faktura {invoice_no} för {customer} finns redan. Den har inte importerats eller sparats igen.": "Invoice {invoice_no} for {customer} already exists. It was not imported or saved again.",
    "Välj faktura-PDF": "Choose invoice PDF",
    "Kunde inte läsa PDF": "Could not read PDF",
    "Lägg till faktura": "Add invoice",
    "Fakturanummer (obligatoriskt)": "Invoice number (required)",
    "Fakturadatum (ÅÅÅÅ-MM-DD)": "Invoice date (YYYY-MM-DD)",
    "Förfallodatum (ÅÅÅÅ-MM-DD)": "Due date (YYYY-MM-DD)",
    "Valuta (ISO-kod, t.ex. SEK/EUR)": "Currency (ISO code, e.g. SEK/EUR)",
    "Redan betalt": "Already paid",
    "E-post": "Email",
    "Ogiltig valuta": "Invalid currency",
    "Ange en valuta med tre bokstäver, till exempel SEK, EUR eller USD.": "Enter a three-letter currency, for example SEK, EUR or USD.",
    "Jag har granskat och godkänt fakturauppgifterna": "I have reviewed and approved the invoice details",
    "Kontrollera uppgifter": "Check details",
    "Kund, fakturanummer och giltigt förfallodatum krävs.": "Customer, invoice number and a valid due date are required.",
    "Fel belopp": "Invalid amount",
    "Ange belopp som siffror.": "Enter amounts as numbers.",
    "Ta bort faktura": "Delete invoice",
    "Ta bort {invoice_no} permanent från den lokala databasen?": "Permanently delete {invoice_no} from the local database?",

    # Reminder creation and errors
    "Inte redo": "Not ready",
    "Fakturan är inte redo för påminnelse. Status: {stage}": "The invoice is not ready for a reminder. Status: {stage}",
    "Bekräfta påminnelse": "Confirm reminder",
    "Skapa {level} för {invoice_no}?\n\nPåminnelseavgift: {fee}{locked}\nRänta: {interest}% per år\nMall: {template}\nSVG-logotyp: {logo}\n\nAppen skickar inte e-post automatiskt.": "Create {level} for {invoice_no}?\n\nReminder fee: {fee}{locked}\nInterest: {interest}% per year\nTemplate: {template}\nSVG logo: {logo}\n\nThe app does not send email automatically.",
    " (låst)": " (locked)",
    "Ansökan om betalningsföreläggande lämnas in till Kronofogden om betalning inte kommit oss tillhanda senast den {deadline}. Kostnader för att driva ärendet kan tillkomma till dess full betalning har skett.": "An application for a payment order will be submitted to Kronofogden if payment has not reached us by {deadline}. Debt collection costs may be added until full payment has been made.",
    "PDF skapad": "PDF created",
    "PDF:en sparades men kunde inte öppnas automatiskt.\n{path}\n\n{error}": "The PDF was saved but could not be opened automatically.\n{path}\n\n{error}",
    "PDF-tillägg saknas": "PDF add-on missing",
    "Kunde inte skapa PDF eftersom ett PDF-tillägg saknas. Öppna felloggen eller starta om appen med internetanslutning.": "Could not create the PDF because a PDF add-on is missing. Open the error log or restart the app with an internet connection.",
    "PDF kunde inte skapas": "PDF could not be created",
    "Ett fel loggades. Öppna felloggen för detaljer.\n\n{error}": "An error was logged. Open the error log for details.\n\n{error}",

    # Generated reminder document
    "Betalningspåminnelse {level} {invoice_no}": "Payment reminder {level} {invoice_no}",
    "Påminnelsedatum": "Reminder date",
    "Påminnelse nummer {number}": "Reminder number {number}",
    "Betalningspåminnelse nummer {number}": "Payment reminder number {number}",
    "Vi saknar fortfarande betalning för nedanstående faktura. Om betalning redan har gjorts, vänligen bortse från denna påminnelse.": "We have still not received payment for the invoice below. If payment has already been made, please disregard this reminder.",
    "Betalning ska vara oss tillhanda senast {date}.": "Payment must reach us no later than {date}.",
    "Avser:": "Reference:",
    "Överenskommen kostnad enligt fakturan.": "Agreed cost according to the invoice.",
    "Specifikation": "Specification",
    "Belopp": "Amount",
    "Faktura {invoice_no} – obetalt belopp": "Invoice {invoice_no} – unpaid amount",
    "Påminnelseavgift (påminnelse 1)": "Reminder fee (reminder 1)",
    "Påminnelseavgift (påminnelse 2)": "Reminder fee (reminder 2)",
    "ATT BETALA": "TOTAL DUE",
    "Påminnelse": "Reminder",
    "Datum": "Date",
    "Avgift": "Fee",
    "Påminnelse 1": "Reminder 1",
    "Påminnelse 2 (denna)": "Reminder 2 (this one)",
    "Ovanstående påminnelser har skickats för fakturan och samtliga avgifter ingår i beloppet ovan.": "The above reminders have been sent for the invoice and all fees are included in the amount above.",
    "Betalning": "Payment",
    "Betalningsmottagare": "Payee",
    "Ange fakturanumret vid betalning.": "Quote the invoice number when paying.",
    "Varan förblir vår egendom tills full betalning erlagts. Eventuella anmärkningar på fakturan ska göras inom {days} dagar. Avgift per påminnelse: {fee}. Försenad betalning debiteras {interest} % ränta. Vid beställning av specialdelar lämnas ingen returrätt.": "The goods remain our property until full payment has been made. Any objections to the invoice must be made within {days} days. Fee per reminder: {fee}. Late payment is subject to {interest}% interest. Special-order parts cannot be returned.",

    # Settings
    "Språk": "Language",
    "Dagar efter förfallodatum till P1": "Days after due date to P1",
    "Dagar efter P1 till P2": "Days after P1 to P2",
    "Dagar efter P2 till Kronofogden-granskning": "Days after P2 to Kronofogden review",
    "Påminnelseavgift per påminnelse (fakturans valuta)": "Reminder fee per reminder (invoice currency)",
    "Dröjsmålsränta per år (%)": "Late payment interest per year (%)",
    "Anmärkningstid enligt fakturavillkor (dagar)": "Objection period under invoice terms (days)",
    "Betalningsfrist på påminnelsen (dagar)": "Payment deadline on reminder (days)",
    "Starta {app_name} automatiskt när jag loggar in": "Start {app_name} automatically when I log in",
    "Autostart för din användare · {platforms}": "Autostart for your user · {platforms}",
    "Lås påminnelseavgiften (förhindra oavsiktlig ändring)": "Lock the reminder fee (prevent accidental changes)",
    "Låset skyddar inställningen i appen; lås upp här för att ändra avgiften.": "The lock protects the setting in the app; unlock it here to change the fee.",
    "Obs: påminnelseavgiften använder fakturans valuta. Kontrollera att avgift, ränta och villkor gäller för era kunder.": "Note: the reminder fee uses the invoice currency. Check that the fee, interest and terms apply to your customers.",
    "Ogiltigt värde": "Invalid value",
    "Ange positiva siffror i inställningarna.": "Enter positive numbers in the settings.",
    "Autostart kunde inte sparas": "Autostart could not be saved",
    "{error}\n\nPlats: {location}": "{error}\n\nLocation: {location}",

    # Parser and autostart errors shown to users
    "PDF verkar vara skannad. OCR kräver Tesseract, svenska språkdata, pdf2image och Poppler. Se README för installation.": "The PDF appears to be scanned. OCR requires Tesseract, Swedish language data, pdf2image and Poppler. See README for installation.",
    "Ingen läsbar text hittades i PDF:en.": "No readable text was found in the PDF.",
    "PDF-läsning kräver PyMuPDF. Installera med: pip install pymupdf": "PDF reading requires PyMuPDF. Install with: pip install pymupdf",
    "Det går inte att hitta appens programfil.": "The application executable could not be found.",
    "Det går inte att hitta Python-installationen.": "The Python installation could not be found.",
    "Startfilen saknas: {script}": "The launch file is missing: {script}",
    "Plattformen stöds inte": "Platform not supported",
    "Autostart stöds inte på {platform}.": "Autostart is not supported on {platform}.",
}


def set_language(language: str) -> None:
    """Select a supported UI language, falling back to Swedish."""
    global _current_language
    _current_language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current_language


def language_code(language_name: str) -> str:
    """Return the code for a native language name used by the selector."""
    for code, name in SUPPORTED_LANGUAGES.items():
        if name == language_name:
            return code
    return DEFAULT_LANGUAGE


def _(text: str, **values) -> str:
    """Translate a Swedish message key and interpolate named values."""
    if _current_language == "en":
        text = _ENGLISH.get(text, text)
    return text.format(**values) if values else text


def format_money(value: float, currency: str = "SEK") -> str:
    """Format an amount in its invoice currency without converting it."""
    code = normalize_currency(currency)
    if _current_language == "en":
        return f"{code} {value:,.2f}"
    formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return formatted + (" kr" if code == "SEK" else f" {code}")


def format_long_date(value: date) -> str:
    """Format a date without depending on the operating system locale."""
    months = {
        "sv": ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    }
    month = months[_current_language][value.month - 1]
    return f"{value.day} {month} {value.year}"


def translation_keys() -> set[str]:
    """Expose keys for completeness tests without exposing mutable state."""
    return set(_ENGLISH)
