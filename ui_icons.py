"""Shared action-icon registry for PayPamin Flow's menus and buttons."""
from __future__ import annotations

from app_info import APP_NAME
from i18n import _

ICON_NAMES = frozenset({
    "add", "backup", "cache", "close", "customer", "delete", "edit",
    "email", "error", "external", "folder", "folder_export",
    "folder_import", "ignore", "info", "journal", "ledger", "log",
    "next", "paid", "pdf_add", "power", "reminder", "restore", "save",
    "scan", "sent", "settings", "technical", "tray", "update",
})

# Keys are the original Swedish UI labels. Lookup uses the active language,
# so the same icons are applied after an English/Swedish UI rebuild.
LABEL_ICONS = {
    "Arkiv": "folder",
    "Hjälp": "info",
    "Säkerhetskopiera inställningar och påminnelser": "backup",
    "Återställ säkerhetskopia": "restore",
    "Importera JSON-journal": "journal",
    "Importera reskontralista": "ledger",
    "Öppna exportmapp": "folder_export",
    "Öppna importmapp": "folder_import",
    "Öppna SVG-mapp": "folder",
    "Rensa cache nu": "cache",
    "Dölj i systemfältet": "tray",
    "Avsluta helt": "power",
    "Visa samlad fellogg": "error",
    "Visa teknisk logg": "technical",
    "Uppdatera appen": "update",
    "Uppdatering tillgänglig": "update",
    "Uppdatera lista": "update",
    "Söker…": "update",
    "Hämtar och verifierar…": "update",
    "Installerar filer…": "update",
    "Startar om…": "update",
    "Uppdaterar…": "update",
    "Sök igen": "update",
    "Inställningar": "settings",
    "Skanna importmapp": "scan",
    "Lägg till faktura-PDF": "pdf_add",
    "Lägg till manuellt": "add",
    "Skapa påminnelse": "reminder",
    "Redigera P1": "edit",
    "Redigera P2": "edit",
    "Redigera vald": "edit",
    "Redigera faktura": "edit",
    "Redigera kund": "customer",
    "Markera som betald": "paid",
    "Ignorera / återaktivera": "ignore",
    "Skapa e-postutkast": "email",
    "Öppna i e-postappen": "email",
    "Markera e-post som skickad": "sent",
    "Ta bort fakturarad": "delete",
    "Ta bort vald": "delete",
    "Spara": "save",
    "Spara inställningar": "save",
    "Spara leverantörsmall och fortsätt": "save",
    "Installera och starta om": "update",
    "Öppna nedladdningssida": "external",
    "Fortsätt utan att spara mall": "next",
    "Markera": "paid",
    "Stäng": "close",
    "Avbryt": "close",
}


def icon_name_for_label(label) -> str:
    """Return an action icon for a localized button/menu label, if known."""
    label = str(label or "").strip()
    if not label:
        return ""
    for source, icon_name in LABEL_ICONS.items():
        if label == _(source):
            return icon_name
    if label == _("Om {app_name}", app_name=APP_NAME):
        return "info"
    for level in ("P1", "P2"):
        if label == _("Spara och skriv om {level}", level=level):
            return "save"
    return ""
