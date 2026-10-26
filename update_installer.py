"""Download, verify and stage native PayPamin Flow release updates."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app_info import APP_NAME, APP_VERSION, RELEASE_ASSET_NAMES
from i18n import _
from update_checker import ReleaseInfo

MAX_PACKAGE_BYTES = 1_000_000_000
MAX_CHECKSUM_BYTES = 65_536
WINDOWS_EXECUTABLE = "PayPamin Flow.exe"
MACOS_APP = "PayPamin Flow.app"
LINUX_EXECUTABLE = "paypamin-flow"


class UpdateInstallError(Exception):
    """A user-presentable update installation failure."""


@dataclass(frozen=True)
class UpdatePlan:
    platform: str
    work_dir: Path
    source: Path
    target: Path
    log_path: Path


def platform_key(value: str | None = None) -> str:
    value = value if value is not None else sys.platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    if value.startswith("linux"):
        return "linux"
    raise UpdateInstallError(_("Automatiska uppdateringar stöds inte på det här operativsystemet."))


def current_install_target(platform: str) -> Path:
    executable = Path(sys.executable).resolve()
    if platform != "macos":
        return executable
    for candidate in (executable, *executable.parents):
        if candidate.suffix == ".app":
            return candidate
    raise UpdateInstallError(_("Kunde inte hitta den installerade macOS-appen."))


def _github_https_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    trusted = host in {"github.com", "www.github.com", "api.github.com"} or host.endswith(".githubusercontent.com")
    if parsed.scheme != "https" or not trusted:
        raise UpdateInstallError(_("Uppdateringspaketet har en osäker nedladdningsadress."))
    return value


def _download(url: str, destination: Path, max_bytes: int, opener=None) -> str:
    _github_https_url(url)
    request = Request(url, headers={"Accept": "application/octet-stream", "User-Agent": f"{APP_NAME.replace(' ', '-')}-Updater/{APP_VERSION}"})
    open_request = opener or urlopen
    digest = hashlib.sha256()
    written = 0
    try:
        with open_request(request, timeout=30) as response:
            get_url = getattr(response, "geturl", None)
            if get_url:
                _github_https_url(get_url())
            with destination.open("wb") as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise UpdateInstallError(_("Uppdateringspaketet är större än den tillåtna gränsen."))
                    target.write(chunk)
                    digest.update(chunk)
    except UpdateInstallError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise UpdateInstallError(_("Kunde inte ladda ner uppdateringspaketet. Kontrollera internetanslutningen och försök igen.")) from exc
    return digest.hexdigest()


def _expected_checksum(text: str, asset_name: str) -> str:
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line.strip())
        if match and match.group(2).strip() == asset_name:
            return match.group(1).lower()
    raise UpdateInstallError(_("Kontrollsumman för uppdateringspaketet saknas eller är ogiltig."))


def download_verified_package(release: ReleaseInfo, platform: str, destination: Path, opener=None) -> Path:
    assets = {asset.name: asset.url for asset in release.assets}
    package_name = RELEASE_ASSET_NAMES[platform]
    checksum_name = package_name + ".sha256"
    if package_name not in assets or checksum_name not in assets:
        raise UpdateInstallError(_("Det automatiska uppdateringspaketet eller dess kontrollsumma saknas för {platform}.", platform=platform))
    destination.mkdir(parents=True, exist_ok=True)
    checksum_path = destination / checksum_name
    _download(assets[checksum_name], checksum_path, MAX_CHECKSUM_BYTES, opener)
    try:
        expected = _expected_checksum(checksum_path.read_text(encoding="ascii"), package_name)
    except (OSError, UnicodeError) as exc:
        raise UpdateInstallError(_("Kontrollsumman för uppdateringspaketet saknas eller är ogiltig.")) from exc
    package_path = destination / package_name
    actual = _download(assets[package_name], package_path, MAX_PACKAGE_BYTES, opener)
    if not hmac.compare_digest(expected, actual):
        package_path.unlink(missing_ok=True)
        raise UpdateInstallError(_("Uppdateringspaketet kunde inte verifieras mot SHA-256-kontrollsumman."))
    return package_path


def _copy_stream(source, destination: Path) -> None:
    with destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _extract_windows(package: Path, destination: Path) -> Path:
    with zipfile.ZipFile(package) as archive:
        info = archive.getinfo(WINDOWS_EXECUTABLE)
        if info.is_dir() or info.file_size > MAX_PACKAGE_BYTES:
            raise UpdateInstallError(_("Windows-paketet har ett oväntat innehåll."))
        target = destination / WINDOWS_EXECUTABLE
        with archive.open(info) as source:
            _copy_stream(source, target)
    return target


def _extract_linux(package: Path, destination: Path) -> Path:
    with tarfile.open(package, "r:gz") as archive:
        info = archive.getmember(LINUX_EXECUTABLE)
        if not info.isfile() or info.size > MAX_PACKAGE_BYTES:
            raise UpdateInstallError(_("Linux-paketet har ett oväntat innehåll."))
        source = archive.extractfile(info)
        if source is None:
            raise UpdateInstallError(_("Linux-programfilen saknas i uppdateringspaketet."))
        target = destination / LINUX_EXECUTABLE
        with source:
            _copy_stream(source, target)
    target.chmod(0o755)
    return target


def _safe_zip_member(info: zipfile.ZipInfo, destination: Path) -> Path:
    name = info.filename
    path = PurePosixPath(name)
    mode = (info.external_attr >> 16) & 0xFFFF
    if path.is_absolute() or ".." in path.parts or "\\" in name or not path.parts or path.parts[0] != MACOS_APP:
        raise UpdateInstallError(_("macOS-paketet innehåller en osäker sökväg."))
    if stat.S_ISLNK(mode) or info.flag_bits & 0x1:
        raise UpdateInstallError(_("macOS-paketet innehåller filer som inte stöds."))
    target = destination.joinpath(*path.parts)
    if not target.resolve().is_relative_to(destination.resolve()):
        raise UpdateInstallError(_("macOS-paketet innehåller en osäker sökväg."))
    return target


def _extract_macos(package: Path, destination: Path) -> Path:
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > 10_000 or sum(info.file_size for info in infos) > 2 * MAX_PACKAGE_BYTES:
            raise UpdateInstallError(_("macOS-paketet är större än den tillåtna gränsen."))
        for info in infos:
            target = _safe_zip_member(info, destination)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source:
                _copy_stream(source, target)
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                target.chmod(mode)
    app = destination / MACOS_APP
    if not (app / "Contents" / "MacOS" / LINUX_EXECUTABLE).is_file():
        raise UpdateInstallError(_("macOS-appen saknas eller har ett oväntat innehåll."))
    return app


def extract_update_package(package: Path, platform: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        if platform == "windows":
            return _extract_windows(package, destination)
        if platform == "macos":
            return _extract_macos(package, destination)
        return _extract_linux(package, destination)
    except UpdateInstallError:
        raise
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise UpdateInstallError(_("Uppdateringspaketet är skadat eller har ett oväntat format.")) from exc


def stage_update(release: ReleaseInfo, platform: str | None = None, target_path: Path | None = None,
                 log_path: Path | None = None, opener=None) -> UpdatePlan:
    key = platform_key(platform)
    work_dir = Path(tempfile.mkdtemp(prefix="paypamin-flow-update-"))
    try:
        package = download_verified_package(release, key, work_dir / "download", opener)
        source = extract_update_package(package, key, work_dir / "unpacked")
        target = Path(target_path).resolve() if target_path else current_install_target(key)
        valid_target = target.is_dir() if key == "macos" else target.is_file()
        if not valid_target or not os.access(target.parent, os.W_OK):
            raise UpdateInstallError(_("Appens installationsmapp är inte skrivbar. Installera uppdateringen manuellt."))
        log = log_path or Path.home() / ".paminnelseapp" / "update.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        return UpdatePlan(key, work_dir, source, target, log)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


POWERSHELL_UPDATE_SCRIPT = r'''param([int]$ProcessId, [string]$Source, [string]$Target, [string]$LogPath, [string]$WorkDir)
$ErrorActionPreference = 'Stop'
function Log([string]$Message) { Add-Content -LiteralPath $LogPath -Value ((Get-Date -Format s) + ' ' + $Message) }
$backup = "$Target.bak"
$new = "$Target.new"
$swapped = $false
try {
    for ($i = 0; $i -lt 60; $i++) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Seconds 1
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) { throw 'Application did not close' }
    Copy-Item -LiteralPath $Source -Destination $new -Force
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    Move-Item -LiteralPath $Target -Destination $backup -Force
    $swapped = $true
    Move-Item -LiteralPath $new -Destination $Target -Force
    Start-Process -FilePath $Target
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Log 'Update installed and application restarted'
} catch {
    Log ('Update failed: ' + $_.Exception.Message)
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
        if ($swapped -and (Test-Path -LiteralPath $backup)) {
            if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Force }
            Move-Item -LiteralPath $backup -Destination $Target -Force
        }
        if (Test-Path -LiteralPath $Target) { Start-Process -FilePath $Target -ErrorAction SilentlyContinue }
    }
} finally {
    Start-Sleep -Seconds 1
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}
'''

SHELL_UPDATE_SCRIPT = r'''#!/bin/sh
PID=$1
SOURCE=$2
TARGET=$3
PLATFORM=$4
LOG_PATH=$5
WORK_DIR=$6
log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$1" >> "$LOG_PATH"; }
restart_app() { if [ "$PLATFORM" = macos ]; then open "$TARGET"; else nohup "$TARGET" >/dev/null 2>&1 & fi; }
i=0
while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 60 ]; do sleep 1; i=$((i + 1)); done
if kill -0 "$PID" 2>/dev/null; then log 'Application did not close'; cd /; rm -rf "$WORK_DIR"; exit 1; fi
backup="$TARGET.bak"
new="$TARGET.new"
if [ "$PLATFORM" = macos ]; then backup="$TARGET.bak.app"; new="$TARGET.new.app"; fi
rm -rf "$new" "$backup"
if [ "$PLATFORM" = macos ]; then
    ditto "$SOURCE" "$new" && mv "$TARGET" "$backup" && mv "$new" "$TARGET"
else
    cp "$SOURCE" "$new" && chmod 755 "$new" && mv "$TARGET" "$backup" && mv "$new" "$TARGET"
fi
if [ "$?" -eq 0 ]; then
    if restart_app; then
        rm -rf "$backup"
        log 'Update installed and application restarted'
    else
        log 'Update installed but restart failed; backup retained'
    fi
else
    log 'Update failed; restoring previous installation'
    if [ -e "$backup" ]; then rm -rf "$TARGET"; mv "$backup" "$TARGET"; fi
    restart_app
fi
cd /
rm -rf "$WORK_DIR"
'''


def launch_update(plan: UpdatePlan, process_id: int | None = None) -> subprocess.Popen:
    process_id = process_id or os.getpid()
    if plan.platform == "windows":
        script = plan.work_dir / "update.ps1"
        script.write_text(POWERSHELL_UPDATE_SCRIPT, encoding="utf-8")
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", str(script), str(process_id), str(plan.source), str(plan.target), str(plan.log_path), str(plan.work_dir)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        kwargs = {"creationflags": flags}
    else:
        script = plan.work_dir / "update.sh"
        script.write_text(SHELL_UPDATE_SCRIPT, encoding="utf-8")
        script.chmod(0o700)
        command = ["/bin/sh", str(script), str(process_id), str(plan.source), str(plan.target), plan.platform, str(plan.log_path), str(plan.work_dir)]
        kwargs = {"start_new_session": True}
    try:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kwargs)
    except OSError as exc:
        shutil.rmtree(plan.work_dir, ignore_errors=True)
        raise UpdateInstallError(_("Kunde inte starta installationsprogrammet för uppdateringen.")) from exc
