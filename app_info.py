"""Central product information for PayPamin Flow."""
from pathlib import PurePosixPath

APP_NAME = "PayPamin Flow"
APP_SLUG = "paypamin-flow"
APP_ID = "se.paypamin.flow"
APP_VERSION = "0.6.0"
APP_AUTHOR = "Rickard Länkvist"
COPYRIGHT_YEAR = "2026"
APP_COPYRIGHT = f"Copyright © {COPYRIGHT_YEAR} {APP_AUTHOR}"
APP_DESCRIPTION = "Local invoice and payment reminder app"
APP_DESCRIPTION_SV = "Lokal app för fakturor och betalningspåminnelser"
APP_REPOSITORY = "Tokke2/PayPamin-Flow"
APP_RELEASES_URL = f"https://github.com/{APP_REPOSITORY}/releases"
APP_LATEST_RELEASE_API = f"https://api.github.com/repos/{APP_REPOSITORY}/releases/latest"
PYTHON_RELEASE_ASSET = "PayPamin-Flow-Python.zip"
# Every desktop platform uses the same Python-only release package.
RELEASE_ASSET_NAMES = {
    platform: PYTHON_RELEASE_ASSET for platform in ("windows", "macos", "linux", "python")
}
PYTHON_PACKAGE_REQUIRED_FILES = (
    "app_backup.py",
    "app_info.py",
    "autostart.py",
    "cache_cleaner.py",
    "console_free.py",
    "currency.py",
    "i18n.py",
    "import_watcher.py",
    "invoice_parser.py",
    "paypamin_flow.py",
    "paypamin_flow.pyw",
    "tray.py",
    "update_checker.py",
    "update_installer.py",
    "requirements.txt",
    "assets/paypamin_flow.png",
    "assets/paypamin_flow.ico",
    "assets/paypamin_flow.icns",
    "assets/paypamin_flow_16.png",
    "assets/paypamin_flow_32.png",
    "assets/paypamin_flow_48.png",
    "assets/paypamin_flow_256.png",
    "assets/paypamin_flow_512.png",
)
SUPPORTED_PLATFORMS = "Windows · macOS · Linux"


def is_python_package_file(filename: str) -> bool:
    """Return whether a path is an application-owned file allowed in updates."""
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
        return path.suffix.lower() in {".py", ".pyw", ".txt", ".md", ".vbs", ".sh"}
    if len(path.parts) == 2 and path.parts[0] == "assets":
        return path.suffix.lower() in {".png", ".svg", ".ico", ".icns"}
    if len(path.parts) == 2 and path.parts[0] == "packaging":
        return filename in {
            "packaging/install_linux.sh",
            "packaging/install_macos.sh",
            "packaging/paypamin-flow.desktop",
        }
    return False
