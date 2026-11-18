"""Central product information for PayPamin Flow."""
import hashlib
from collections.abc import Mapping
from pathlib import PurePosixPath

APP_NAME = "PayPamin Flow"
APP_SLUG = "paypamin-flow"
APP_ID = "se.paypamin.flow"
APP_VERSION = "0.6.0"
APP_AUTHOR = "Rickard Längkvist"
COPYRIGHT_YEAR = "2026"
APP_COPYRIGHT = f"Copyright © {COPYRIGHT_YEAR} {APP_AUTHOR}"
APP_DESCRIPTION = "Local invoice and payment reminder app"
APP_DESCRIPTION_SV = "Lokal app för fakturor och betalningspåminnelser"
APP_REPOSITORY = "Tokke2/PayPamin-Flow"
APP_RELEASES_URL = f"https://github.com/{APP_REPOSITORY}/releases"
APP_LATEST_RELEASE_API = f"https://api.github.com/repos/{APP_REPOSITORY}/releases/latest"
MINIMIZED_START_ARG = "--minimized"
PYTHON_RELEASE_ASSET = "PayPamin-Flow-Python.zip"
PYTHON_RELEASE_MANIFEST = "PayPamin-Flow-Python.manifest.json"
# Every desktop platform uses the same Python-only release package.
RELEASE_ASSET_NAMES = {
    platform: PYTHON_RELEASE_ASSET for platform in ("windows", "macos", "linux", "python")
}
PYTHON_PACKAGE_REQUIRED_FILES = (
    "activity_log.py",
    "accessibility.py",
    "app_backup.py",
    "app_info.py",
    "autostart.py",
    "build_info.py",
    "cache_cleaner.py",
    "console_free.py",
    "currency.py",
    "donations.py",
    "customer_contacts.py",
    "error_log.py",
    "fee_rules.py",
    "i18n.py",
    "import_watcher.py",
    "invoice_parser.py",
    "invoice_trash.py",
    "learning.py",
    "ledger_import.py",
    "logo_matching.py",
    "mail_compose.py",
    "paypamin_flow.py",
    "paypamin_flow_launcher.py",
    "paypamin_flow.pyw",
    "python_maintenance.py",
    "qr_code.py",
    "reminder_archive.py",
    "reminder_journal.py",
    "single_instance.py",
    "supplier_matching.py",
    "tray.py",
    "ui_icons.py",
    "update_checker.py",
    "update_installer.py",
    "requirements.txt",
    # The terms of use travel inside the package, not as a web page.
    "LICENSE",
    "NOTICE",
    # One start file per platform, all shipped and all required.
    "start_paypamin_flow.command",
    "start_paypamin_flow.sh",
    "start_paypamin_flow.vbs",
    "assets/paypamin_flow.png",
    "assets/paypamin_flow.ico",
    "assets/paypamin_flow.icns",
    "assets/paypamin_flow_16.png",
    "assets/paypamin_flow_32.png",
    "assets/paypamin_flow_48.png",
    "assets/paypamin_flow_256.png",
    "assets/paypamin_flow_512.png",
    "assets/paypamin_logo.png",
    "assets/paypamin_logo.svg",
    "assets/paypamin_flow_small.svg",
    "assets/paypamin_flow_tiny.svg",
    "assets/print/paypamin_logo_print.svg",
    "assets/print/paypamin_logo_print_mono.svg",
    "assets/print/paypamin_logo_print.pdf",
    "assets/print/paypamin_logo_print_mono.pdf",
    "assets/print/paypamin_logo_print.png",
    "assets/print/paypamin_logo_print_mono.png",
    "assets/print/README.txt",
)
SUPPORTED_PLATFORMS = "Windows · macOS · Linux"


def fingerprint_package_files(file_hashes: Mapping[str, str]) -> str:
    """Fingerprint every shipped filename and content hash deterministically.

    ``build_info.py`` is excluded by the caller because it contains this
    fingerprint and the release identity itself.
    """
    digest = hashlib.sha256()
    for name in sorted(file_hashes):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hashes[name]))
    return digest.hexdigest()


def is_python_package_file(filename: str) -> bool:
    """Return whether a path is an application-owned file allowed in updates."""
    # CI writes this transient report before packaging; it is not app content.
    if filename == "test-results.txt":
        return False
    path = PurePosixPath(filename)
    if (
        not filename
        or filename.endswith("/")
        or "\\" in filename
        or path.is_absolute()
        or ".." in path.parts
        or any(not part or part == "." or part.startswith(".") for part in path.parts)
    ):
        return False
    if len(path.parts) == 1:
        # The licence and the copyright notice have no file extension and must
        # travel with every copy, so they are allowed by their exact names.
        if filename in {"LICENSE", "NOTICE"}:
            return True
        # .command is the double-clickable start file on macOS. A Windows .bat
        # is deliberately not accepted: start_paypamin_flow.vbs is the one
        # Windows start file, and no separate installer script is shipped.
        return path.suffix.lower() in {".py", ".pyw", ".txt", ".md", ".vbs", ".sh", ".command"}
    if len(path.parts) == 2 and path.parts[0] == "assets":
        return path.suffix.lower() in {".png", ".svg", ".ico", ".icns"}
    if len(path.parts) == 3 and path.parts[:2] in (("assets", "icons"), ("assets", "print")):
        return path.suffix.lower() in {".png", ".pdf", ".svg", ".txt"}
    if len(path.parts) == 2 and path.parts[0] == "packaging":
        return filename in {
            "packaging/install_linux.sh",
            "packaging/paypamin-flow.desktop",
        }
    return False
