"""In-app, console-free updates for the Python-source PayPamin Flow app.

The release asset is one cross-platform Python ZIP. Files are verified and
compiled before installation, replaced atomically, and can be rolled back if
starting the updated app fails. User data directories are never package paths.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from app_info import (
    APP_NAME,
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    is_python_package_file,
)
from i18n import _
from update_checker import ReleaseInfo

DOWNLOAD_TIMEOUT = 90
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_CHECKSUM_BYTES = 65_536
MAX_PACKAGE_FILES = 500


class UpdateInstallError(RuntimeError):
    """Raised when an update cannot be downloaded, installed, or restarted."""


@dataclass
class UpdatePlan:
    release: ReleaseInfo
    platform: str
    source_path: Path
    target_path: Path
    work_dir: Path
    log_path: Path


@dataclass
class Replacement:
    target: Path
    backup: Path
    existed: bool


@dataclass
class InstalledUpdate:
    plan: UpdatePlan
    replacements: list[Replacement]


def _log(plan: UpdatePlan, message: str) -> None:
    try:
        plan.log_path.parent.mkdir(parents=True, exist_ok=True)
        with plan.log_path.open("a", encoding="utf-8") as handle:
            timestamp = datetime.now(timezone.utc).isoformat()
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        pass


def platform_key(value: str | None = None) -> str:
    value = value if value is not None else sys.platform
    if value.startswith('win'):return 'windows'
    if value == 'darwin':return 'macos'
    if value.startswith('linux'):return 'linux'
    raise UpdateInstallError(_('Automatiska uppdateringar stöds inte på det här operativsystemet.'))


def _github_https_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    trusted = host in {'github.com', 'www.github.com', 'api.github.com'} or host.endswith('.githubusercontent.com')
    if parsed.scheme != 'https' or not trusted:
        raise UpdateInstallError(_('Uppdateringspaketet har en osäker nedladdningsadress.'))
    return value


def _download(url: str, destination: Path, max_bytes: int = MAX_DOWNLOAD_BYTES, opener=None) -> str:
    _github_https_url(url)
    digest = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{APP_NAME.replace(' ', '-')}-Updater/{APP_VERSION}", "Accept": "application/octet-stream"}
    )
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=DOWNLOAD_TIMEOUT) as response:
            get_url = getattr(response, 'geturl', None)
            if get_url:_github_https_url(get_url())
            status = getattr(response, 'status', 200)
            if status != 200:
                raise UpdateInstallError(_("Nedladdningen misslyckades med HTTP {code}.", code=status))
            with destination.open("wb") as target:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > max_bytes:
                        raise UpdateInstallError(_("Uppdateringspaketet är för stort."))
                    digest.update(block)
                    target.write(block)
    except UpdateInstallError:
        raise
    return digest.hexdigest()


def _download_asset(asset, destination: Path, max_bytes: int = MAX_DOWNLOAD_BYTES, opener=None) -> str:
    try:
        return _download(asset.url, destination, max_bytes=max_bytes, opener=opener)
    except UpdateInstallError:
        raise
    except Exception as exc:
        raise UpdateInstallError(
            _("Uppdateringspaketet kunde inte laddas ner: {error}", error=exc)
        ) from exc


def _package_version(source_path: Path) -> str:
    try:
        tree = ast.parse((source_path / "app_info.py").read_bytes())
    except (OSError, SyntaxError) as exc:
        raise UpdateInstallError(_("Uppdateringspaketets versionsinformation är ogiltig.")) from exc
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise UpdateInstallError(_("Uppdateringspaketets versionsinformation är ogiltig."))


def _extract_python_package(archive_path: Path, source_path: Path, expected_version: str) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos or len(infos) > MAX_PACKAGE_FILES:
                raise UpdateInstallError(_("Uppdateringspaketet har ogiltigt innehåll."))
            if sum(info.file_size for info in infos) > MAX_DOWNLOAD_BYTES:
                raise UpdateInstallError(_("Uppdateringspaketet är för stort."))
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
                raise UpdateInstallError(_("Uppdateringspaketet innehåller dubbletter av filnamn."))
            for info in infos:
                if not is_python_package_file(info.filename):
                    raise UpdateInstallError(
                        _("Filen är inte tillåten i uppdateringspaketet: {name}", name=info.filename)
                    )
                mode = info.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    raise UpdateInstallError(_("Uppdateringspaketet innehåller en symbolisk länk."))
            missing = sorted(set(PYTHON_PACKAGE_REQUIRED_FILES) - set(names))
            if missing:
                raise UpdateInstallError(
                    _("Uppdateringspaketet saknar nödvändiga filer: {files}", files=", ".join(missing))
                )
            for info in infos:
                relative = PurePosixPath(info.filename)
                target = source_path.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    target.chmod(mode)
    except UpdateInstallError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise UpdateInstallError(_("Uppdateringspaketet är skadat: {error}", error=exc)) from exc

    if _package_version(source_path) != expected_version:
        raise UpdateInstallError(
            _(
                "Versionen i uppdateringspaketet stämmer inte med releasen: {version}",
                version=_package_version(source_path),
            )
        )
    for path in source_path.iterdir():
        if path.suffix.lower() in {".py", ".pyw"}:
            try:
                compile(path.read_bytes(), str(path), "exec")
            except (OSError, SyntaxError) as exc:
                raise UpdateInstallError(
                    _("Python-filen i uppdateringen är ogiltig: {name}", name=path.name)
                ) from exc


def stage_update(
    release: ReleaseInfo,
    *,
    platform: str | None = None,
    target_path: Path | None = None,
    log_path: Path | None = None,
    opener=None,
) -> UpdatePlan:
    """Download and validate a Python update without changing the running app."""

    if getattr(sys, "frozen", False) and target_path is None:
        raise UpdateInstallError(
            _("Den här installationen kan inte uppdatera sig själv. Använd Python-versionen av PayPamin Flow.")
        )
    selected_platform = platform or platform_key()
    assets = {asset.name: asset for asset in release.assets}
    asset = assets.get(PYTHON_RELEASE_ASSET)
    checksum_asset = assets.get(PYTHON_RELEASE_ASSET + '.sha256')
    if asset is None or checksum_asset is None:
        raise UpdateInstallError(_("Releasen saknar Python-paket eller SHA-256-kontrollsumma för den här plattformen."))

    work_dir = Path(tempfile.mkdtemp(prefix="paypamin-flow-python-update-"))
    archive_path = work_dir / "update.zip"
    checksum_path = work_dir / "update.sha256"
    source_path = work_dir / "source"
    source_path.mkdir()
    try:
        _download_asset(checksum_asset, checksum_path, max_bytes=MAX_CHECKSUM_BYTES, opener=opener)
        actual_hash = _download_asset(asset, archive_path, opener=opener)
        try:checksum_text = checksum_path.read_text(encoding="ascii")
        except (OSError,UnicodeError) as exc:raise UpdateInstallError(_("Releasens SHA-256-kontrollsumma är ogiltig.")) from exc
        expected_hash = ''
        for line in checksum_text.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[1].lstrip('*') == PYTHON_RELEASE_ASSET:
                expected_hash = parts[0].lower();break
        if len(expected_hash) != 64 or any(character not in "0123456789abcdef" for character in expected_hash):
            raise UpdateInstallError(_("Releasens SHA-256-kontrollsumma är ogiltig."))
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise UpdateInstallError(_("SHA-256-kontrollsumman stämmer inte. Uppdateringen avbröts."))
        _extract_python_package(archive_path, source_path, release.version)
        plan = UpdatePlan(
            release=release,
            platform=selected_platform,
            source_path=source_path,
            target_path=(target_path or Path(__file__).resolve().parent).resolve(),
            work_dir=work_dir,
            log_path=log_path or Path.home() / ".paminnelseapp" / "update.log",
        )
        _log(plan, f"Validated Python update {release.version}")
        return plan
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def _replace_file(source: Path, target: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _check_target_parents(root: Path, relative: PurePosixPath) -> None:
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise UpdateInstallError(_("Uppdateringsmålet innehåller en symbolisk länk: {path}", path=current))


def rollback_update(installed: InstalledUpdate) -> None:
    """Restore every replaced file, including files added by the update."""

    errors = []
    for replacement in reversed(installed.replacements):
        try:
            if replacement.existed:
                _replace_file(replacement.backup, replacement.target)
            else:
                replacement.target.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(str(exc))
    if errors:
        raise UpdateInstallError(_("Uppdateringen kunde inte rullas tillbaka: {error}", error="; ".join(errors)))
    _log(installed.plan, "Rolled back Python update")


def install_update(plan: UpdatePlan) -> InstalledUpdate:
    """Atomically replace application-owned Python files, retaining a rollback copy."""

    installed = InstalledUpdate(plan=plan, replacements=[])
    backup_root = plan.work_dir / "backup"
    try:
        sources = sorted(path for path in plan.source_path.rglob("*") if path.is_file())
        for source in sources:
            relative_text = source.relative_to(plan.source_path).as_posix()
            if not is_python_package_file(relative_text):
                raise UpdateInstallError(
                    _("Filen är inte tillåten i uppdateringspaketet: {name}", name=relative_text)
                )
            relative = PurePosixPath(relative_text)
            _check_target_parents(plan.target_path, relative)
            target = plan.target_path.joinpath(*relative.parts)
            if target.is_symlink() or target.is_dir():
                raise UpdateInstallError(_("Uppdateringsmålet är inte en vanlig fil: {path}", path=target))
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = backup_root.joinpath(*relative.parts)
            backup.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            if existed:
                shutil.copy2(target, backup)
            _replace_file(source, target)
            installed.replacements.append(Replacement(target=target, backup=backup, existed=existed))
        _log(plan, f"Installed Python update {plan.release.version}; restart pending")
        return installed
    except Exception as exc:
        try:
            rollback_update(installed)
        except UpdateInstallError:
            pass
        shutil.rmtree(plan.work_dir, ignore_errors=True)
        if isinstance(exc, UpdateInstallError):
            raise
        raise UpdateInstallError(_("Uppdateringen kunde inte installeras: {error}", error=exc)) from exc


def restart_updated_app(installed: InstalledUpdate):
    """Start the updated Python app without a console and return its process."""

    if getattr(sys, "frozen", False) or not sys.executable:
        raise UpdateInstallError(_("Konsolfri omstart kräver en Python-installation."))
    executable = Path(sys.executable).resolve()
    script = installed.plan.target_path / "paypamin_flow.pyw"
    windows = sys.platform.startswith("win")
    if windows:
        executable = executable.with_name("pythonw.exe")
    if not executable.is_file() or not script.is_file():
        raise UpdateInstallError(
            _("Konsolfri omstart kräver pythonw.exe. Installera Python från python.org.")
            if windows
            else _("Startfilen saknas: {script}", script=script)
        )
    flags = 0
    if windows:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        process = subprocess.Popen(
            [str(executable), str(script)],
            cwd=installed.plan.target_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=not windows,
            creationflags=flags,
        )
    except OSError as exc:
        raise UpdateInstallError(_("Den uppdaterade appen kunde inte startas: {error}", error=exc)) from exc
    _log(installed.plan, f"Restarted updated app with PID {process.pid}")
    return process


def cleanup_update(value: UpdatePlan | InstalledUpdate) -> None:
    """Remove temporary downloads and rollback copies on a best-effort basis."""

    plan = value.plan if isinstance(value, InstalledUpdate) else value
    shutil.rmtree(plan.work_dir, ignore_errors=True)
