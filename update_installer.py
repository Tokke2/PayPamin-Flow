"""In-app, console-free updates for the Python-source PayPamin Flow app.

The release is the source archive GitHub generates for the release tag, so the
app updates from exactly the code the tag points at - nothing is uploaded and
nothing can drift. Only application-owned files are taken from the archive;
tests and CI configuration are ignored. Files are verified and compiled before
installation, replaced atomically, and rolled back if the updated app fails to
start. User data directories are never package paths.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from app_info import (
    APP_NAME,
    APP_SOURCE_ARCHIVE_URL,
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    fingerprint_package_files,
    is_python_package_file,
)
from i18n import _
import update_state
from update_checker import (
    CONTENT_CURRENT,
    CONTENT_DIFFERS,
    CONTENT_SOURCE_DIFFERS,
    CONTENT_STALE,
    CONTENT_UNAVAILABLE,
    STALE_FILE_MARGIN_SECONDS,
    ReleaseInfo,
    is_newer_version,
    release_package_sha256,
    version_key,
)
from quiet_faults import report_fault

DOWNLOAD_TIMEOUT = 90
# GitHub answers 502/503/504 while a release asset is still being generated,
# so a download is retried a few times before it is reported as a failure.
DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_DELAY = 1.5
RETRYABLE_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 522, 524})
TRANSIENT_DOWNLOAD_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
_LOG_ERROR_MARKERS = re.compile(
    r"fail|error|could not|invalid|mismatch|cancel|rolled back", re.IGNORECASE
)
MAX_CHECKSUM_BYTES = 65_536
MAX_PACKAGE_FILES = 500
# A source archive of this project is about 1.2 MB compressed. The limit only
# exists so a wrong URL can never fill the disk.
MAX_SOURCE_ARCHIVE_BYTES = 32 * 1024 * 1024
# A content check downloads the release ZIP, so it is bounded well above the
# real package size (about one megabyte) and never used for installation.
CONTENT_PROBE_MAX_BYTES = 60 * 1024 * 1024
UPDATE_READY_FILE_ENV = "PAYPAMIN_UPDATE_READY_FILE"
UPDATE_READY_TOKEN_ENV = "PAYPAMIN_UPDATE_READY_TOKEN"
UPDATE_RESTART_TIMEOUT_SECONDS = 20.0


class UpdateInstallError(RuntimeError):
    """Raised when an update cannot be downloaded, installed, or restarted."""


class TransientDownloadError(UpdateInstallError):
    """A download failure that is worth retrying, such as HTTP 504."""


@dataclass
class UpdatePlan:
    release: ReleaseInfo
    platform: str
    source_path: Path
    target_path: Path
    work_dir: Path
    log_path: Path
    # SHA-256 of the downloaded archive, kept as a record of what was installed.
    package_sha256: str = ""
    # The commit the archive was generated from: the release's identity.
    source_commit: str = ""


@dataclass
class Replacement:
    target: Path
    backup: Path
    existed: bool


@dataclass
class InstalledUpdate:
    plan: UpdatePlan
    replacements: list[Replacement]
    ready_file: Path | None = None
    ready_token: str = ""
    # The bookkeeping before this install, so a rollback can put it back.
    previous_state: dict | None = None


def _log(plan: UpdatePlan, message: str) -> None:
    """Append an update event to the shared technical log.

    The line uses the application's own record format so the updater writes to
    app.log instead of a separate file, and so errors.log recognises a failed
    step as an error.
    """
    try:
        plan.log_path.parent.mkdir(parents=True, exist_ok=True)
        level = "ERROR" if _LOG_ERROR_MARKERS.search(message) else "INFO"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        with plan.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {level} {message}\n")
    except OSError:
        report_fault()


def platform_key(value: str | None = None) -> str:
    value = value if value is not None else sys.platform
    if value.startswith('win'):return 'windows'
    if value == 'darwin':return 'macos'
    if value.startswith('linux'):return 'linux'
    raise UpdateInstallError(_('Automatiska uppdateringar stöds inte på det här operativsystemet.'))


def _github_https_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    # codeload hosts the archives GitHub generates for a tag; the release is
    # that archive, so following the redirect there is the normal path.
    trusted = (
        host in {'github.com', 'www.github.com', 'api.github.com', 'codeload.github.com'}
        or host.endswith('.githubusercontent.com')
    )
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
                message = _("Nedladdningen misslyckades med HTTP {code}.", code=status)
                if status in RETRYABLE_HTTP_CODES:
                    raise TransientDownloadError(message)
                raise UpdateInstallError(message)
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


def _download_asset(
    asset,
    destination: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    opener=None,
    retries: int | None = None,
    sleep=None,
) -> str:
    """Download one release asset, retrying transient server and network errors.

    GitHub returns 504 while a release asset is still being generated, and a
    dropped connection is equally temporary. Permanent failures (unsafe URL,
    too large package, HTTP 404) are reported immediately.
    """
    attempts = max(1, int(DOWNLOAD_RETRIES if retries is None else retries))
    delay = DOWNLOAD_RETRY_DELAY
    wait = sleep or time.sleep
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _download(asset.url, destination, max_bytes=max_bytes, opener=opener)
        except TransientDownloadError as exc:
            last_error = exc
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise UpdateInstallError(
                    _("Nedladdningen misslyckades med HTTP {code}.", code=exc.code)
                ) from exc
            last_error = exc
        except UpdateInstallError:
            raise
        except TRANSIENT_DOWNLOAD_ERRORS as exc:
            last_error = exc
        except Exception as exc:
            raise UpdateInstallError(
                _("Uppdateringspaketet kunde inte laddas ner: {error}", error=exc)
            ) from exc
        if attempt >= attempts:
            break
        try:
            destination.unlink()
        except OSError:
            report_fault()
        wait(delay)
        delay *= 2
    if isinstance(last_error, UpdateInstallError):
        raise last_error
    raise UpdateInstallError(
        _("Uppdateringspaketet kunde inte laddas ner: {error}", error=last_error)
    ) from last_error


@dataclass(frozen=True)
class PackageContent:
    """What a release ZIP contains, without installing any of it."""

    package_sha256: str
    files: dict


def read_package_content(
    release: ReleaseInfo,
    *,
    opener=None,
    max_bytes: int = CONTENT_PROBE_MAX_BYTES,
) -> PackageContent:
    """Download the release ZIP once and hash the file inside it.

    The ZIP is small and this is the only way to answer "do the files in the
    release differ from mine?" for an install that predates the bookkeeping in
    ``update_state``. Nothing is extracted and nothing is executed.
    """
    asset = next((item for item in release.assets if item.name == PYTHON_RELEASE_ASSET), None)
    if asset is None:
        raise UpdateInstallError(
            _("Releasen saknar Python-paket eller SHA-256-kontrollsumma för den här plattformen. Saknas: {files}", files=PYTHON_RELEASE_ASSET)
        )
    with tempfile.TemporaryDirectory(prefix="paypamin-flow-content-") as folder:
        archive_path = Path(folder) / "package.zip"
        try:
            digest = _download_asset(asset, archive_path, max_bytes=max_bytes, opener=opener)
        except UpdateInstallError:
            raise
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = [info for info in archive.infolist() if not info.is_dir()]
                if not infos or len(infos) > MAX_PACKAGE_FILES:
                    raise UpdateInstallError(_("Uppdateringspaketet har ogiltigt innehåll."))
                files = {}
                for info in infos:
                    if not is_python_package_file(info.filename):
                        raise UpdateInstallError(
                            _("Filen är inte tillåten i uppdateringspaketet: {name}", name=info.filename)
                        )
                    hasher = hashlib.sha256()
                    with archive.open(info) as source:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            hasher.update(block)
                    files[info.filename] = hasher.hexdigest()
        except UpdateInstallError:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise UpdateInstallError(_("Uppdateringspaketet är skadat: {error}", error=exc)) from exc
    return PackageContent(package_sha256=digest, files=files)


@dataclass(frozen=True)
class SourceArchive:
    """A downloaded release archive and the archive root GitHub wrapped it in."""

    path: Path
    root: str
    files: dict


def source_archive_root(names) -> str:
    """Return the single top-level folder a GitHub archive wraps everything in.

    ``https://github.com/<owner>/<repo>/archive/refs/tags/v0.6.0.zip`` unpacks
    to ``PayPamin-Flow-0.6.0/...``. Stripping that one folder is what makes the
    archive usable as an application folder; a ZIP without a single shared root
    keeps its own layout.
    """
    roots = set()
    for name in names:
        parts = PurePosixPath(str(name)).parts
        if len(parts) < 2:
            return ""
        roots.add(parts[0])
        if len(roots) > 1:
            return ""
    return roots.pop() if len(roots) == 1 else ""


def _archive_member_name(name: str, root: str) -> str:
    """Return the path inside the application, or an empty string to skip it."""
    text = str(name).replace("\\", "/").strip("/")
    if root:
        prefix = root + "/"
        if not text.startswith(prefix):
            return ""
        text = text[len(prefix):]
    if not text or text.endswith("/"):
        return ""
    return text


def read_source_content(
    release: ReleaseInfo,
    *,
    work_dir: Path | None = None,
    opener=None,
) -> SourceArchive:
    """Download the release archive once and index the files it ships.

    The archive is GitHub's own source archive for the tag, so its content is
    exactly the commit the release points at. Only files the application owns
    are indexed: the archive also carries tests and CI configuration, which
    belong to the repository but must never be written into an installation.
    Nothing is extracted to the installation from here.
    """
    url = release.source_url or (
        APP_SOURCE_ARCHIVE_URL.format(tag=release.tag_name) if release.tag_name else ""
    )
    if not url:
        raise UpdateInstallError(_("Releasen saknar en nedladdningsadress för källkoden."))
    # A caller that is going to install keeps the archive for extraction; a
    # caller that only compares deletes it as soon as the files are hashed.
    owned = work_dir is None
    folder = Path(tempfile.mkdtemp(prefix="paypamin-flow-source-")) if owned else Path(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    archive_path = folder / "source.zip"
    _download(url, archive_path, max_bytes=MAX_SOURCE_ARCHIVE_BYTES, opener=opener)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            root = source_archive_root(info.filename for info in infos)
            files = {}
            for info in infos:
                name = _archive_member_name(info.filename, root)
                if not name or not is_python_package_file(name):
                    continue
                hasher = hashlib.sha256()
                with archive.open(info) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        hasher.update(block)
                files[name] = hasher.hexdigest()
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if owned:
            shutil.rmtree(folder, ignore_errors=True)
        raise UpdateInstallError(_("Källkodsarkivet är skadat: {error}", error=exc)) from exc
    if not files:
        if owned:
            shutil.rmtree(folder, ignore_errors=True)
        raise UpdateInstallError(_("Källkodsarkivet innehåller inga programfiler."))
    missing = sorted(set(PYTHON_PACKAGE_REQUIRED_FILES) - set(files))
    if missing:
        if owned:
            shutil.rmtree(folder, ignore_errors=True)
        raise UpdateInstallError(
            _("Källkodsarkivet saknar nödvändiga filer: {files}", files=", ".join(missing))
        )
    archive = SourceArchive(path=archive_path, root=root, files=files)
    if owned:
        # Only the index is needed for a comparison.
        shutil.rmtree(folder, ignore_errors=True)
    return archive


def _release_is_older_than_files(release: ReleaseInfo, release_files, directory) -> bool:
    """Return whether the release ZIP predates the installed package files.

    GitHub reports when the ZIP was last replaced. Comparing that with the
    newest shipped file on disk answers which set is newer, which the content
    comparison alone cannot do. A missing or unparsable timestamp means "do
    not guess": the difference is then treated as a normal update.
    """
    stamp = str(
        getattr(release, "source_committed_at", "") or getattr(release, "package_updated_at", "")
    ).strip()
    if not stamp:
        return False
    try:
        released = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return False
    newest = update_state.newest_local_mtime(directory, names=release_files)
    if not newest:
        return False
    return newest > released + STALE_FILE_MARGIN_SECONDS


def evaluate_release(
    release: ReleaseInfo,
    *,
    current_version: str = APP_VERSION,
    directory=None,
    state_file=None,
    opener=None,
    compare_content: bool = True,
) -> ReleaseInfo:
    """Return the release with the outcome of a real file comparison.

    A version number alone says nothing about a release whose files were
    replaced in place, which is exactly how this project ships while it is
    still 0.6.0. So the same-version case is decided by content: the recorded
    package hash first (free), and otherwise by hashing the files inside the
    release once and comparing them with the files on disk. Network and I/O
    problems never raise here - they leave the release undecided, and the
    caller falls back to the version and commit metadata.
    """
    if not compare_content:
        return release
    try:
        if is_newer_version(release.version, current_version):
            return release
        if version_key(release.version) != version_key(current_version):
            return release
    except ValueError:
        return release
    if release.content_state:
        return release

    # The release is the source archive at the tag's commit, so the recorded
    # commit of the installed copy answers the question outright: equal means
    # the same code, different means newer or older, and nothing is downloaded.
    local_commit = update_state.installed_source_commit(state_file)
    if release.source_commit and local_commit:
        state = CONTENT_CURRENT if release.source_commit == local_commit else CONTENT_SOURCE_DIFFERS
        return replace(release, content_state=state)

    local_hash = update_state.installed_package_sha256(state_file)
    release_hash = release_package_sha256(release, opener=opener) if release.assets else ""
    if release_hash and local_hash:
        state = CONTENT_CURRENT if release_hash == local_hash else CONTENT_DIFFERS
        return replace(release, package_sha256=release_hash, content_state=state)

    target = Path(directory) if directory else Path(__file__).resolve().parent
    try:
        content = read_source_content(release, opener=opener)
    except (UpdateInstallError, OSError):
        # Offline, or the archive is still being generated: say so instead of
        # pretending the installed files are up to date.
        return replace(release, content_state=CONTENT_UNAVAILABLE)
    difference = update_state.compare_package_files(content.files, target)
    if difference.files:
        state = CONTENT_DIFFERS
        if _release_is_older_than_files(release, content.files, target):
            # Different, but in the wrong direction: the release predates the
            # installed files, so installing it would be a downgrade.
            state = CONTENT_STALE
        return replace(release, content_state=state, changed_files=difference.files)
    update_state.record_installed_package(
        release_id=release.release_id,
        version=release.version,
        source_commit=release.source_commit,
        path=state_file,
    )
    return replace(release, content_state=CONTENT_CURRENT)


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


def _shipped_fingerprint(source_path: Path) -> str:
    """Hash every application file except the build stamp itself."""
    file_hashes = {
        path.relative_to(source_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_path.rglob("*")
        if path.is_file() and path.name != "build_info.py"
    }
    return fingerprint_package_files(file_hashes)


def stamp_package_build(source_path: Path, release: ReleaseInfo) -> str:
    """Write ``build_info.py`` so the installed copy names its own release.

    The repository's ``build_info.py`` cannot be trusted for this: it is
    committed once and then never changes, while the release moves with every
    push. Stamping it after extraction is what lets the next update check
    answer "is this the same code?" with a single string comparison instead of
    a download.
    """
    fingerprint = _shipped_fingerprint(source_path)
    commit = (release.source_commit or release.release_commit or "").strip().lower()
    release_id = str(release.release_id or "").strip()
    lines = ['"""Official release identity for same-version commit and file checks."""', ""]
    if release_id:
        lines.append(f'APP_RELEASE_ID = "{release_id}"')
    if commit:
        lines.append(f'APP_RELEASE_COMMIT = "{commit}"')
    lines.append(f'APP_PACKAGE_FINGERPRINT = "{fingerprint}"')
    (source_path / "build_info.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fingerprint


def _validate_package_build(source_path: Path, release: ReleaseInfo) -> None:
    """Verify the stamp written after extraction matches the release.

    There is no uploaded manifest any more, so the check is that the archive
    really is the code the tag points at: the commit written into the stamp has
    to be the release's own, and the fingerprint has to describe the files that
    are now on disk.
    """
    expected_commit = (release.source_commit or release.release_commit or "").strip().lower()
    try:
        tree = ast.parse((source_path / "build_info.py").read_bytes())
    except (OSError, SyntaxError) as exc:
        raise UpdateInstallError(_("Uppdateringspaketets byggidentitet stämmer inte med releasen.")) from exc
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value
    if expected_commit and values.get("APP_RELEASE_COMMIT", "").lower() != expected_commit:
        raise UpdateInstallError(_("Uppdateringspaketets byggidentitet stämmer inte med releasen."))
    if not hmac.compare_digest(str(values.get("APP_PACKAGE_FINGERPRINT", "")).lower(), _shipped_fingerprint(source_path)):
        raise UpdateInstallError(_("Uppdateringspaketets byggidentitet stämmer inte med releasen."))


def _extract_source_tree(archive_path: Path, source_path: Path, root: str, expected_version: str) -> None:
    """Write the application's files from a GitHub archive into ``source_path``.

    The archive is the repository, so it also holds tests and CI configuration.
    Only files the application owns are written: an installation must never
    gain a ``tests`` folder or a workflow file, and the allow-list is the same
    one the updater has always used.
    """
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos or len(infos) > MAX_PACKAGE_FILES * 4:
                raise UpdateInstallError(_("Uppdateringspaketet har ogiltigt innehåll."))
            selected = []
            seen = set()
            for info in infos:
                name = _archive_member_name(info.filename, root)
                if not name:
                    continue
                if not is_python_package_file(name):
                    continue
                if name in seen or name.casefold() in seen:
                    raise UpdateInstallError(_("Uppdateringspaketet innehåller dubbletter av filnamn."))
                seen.add(name)
                seen.add(name.casefold())
                mode = info.external_attr >> 16
                if mode and stat.S_ISLNK(mode):
                    raise UpdateInstallError(_("Uppdateringspaketet innehåller en symbolisk länk."))
                selected.append((info, name))
            missing = sorted(set(PYTHON_PACKAGE_REQUIRED_FILES) - seen)
            if missing:
                raise UpdateInstallError(
                    _("Uppdateringspaketet saknar nödvändiga filer: {files}", files=", ".join(missing))
                )
            if sum(info.file_size for info, _ in selected) > MAX_DOWNLOAD_BYTES:
                raise UpdateInstallError(_("Uppdateringspaketet är för stort."))
            for info, name in selected:
                relative = PurePosixPath(name)
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
    for path in source_path.rglob("*.py"):
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
    """Download and validate the release's source archive without changing the app."""

    if getattr(sys, "frozen", False) and target_path is None:
        raise UpdateInstallError(
            _("Den här installationen kan inte uppdatera sig själv. Använd Python-versionen av PayPamin Flow.")
        )
    selected_platform = platform or platform_key()

    work_dir = Path(tempfile.mkdtemp(prefix="paypamin-flow-python-update-"))
    source_path = work_dir / "source"
    source_path.mkdir()
    try:
        archive = read_source_content(release, work_dir=work_dir, opener=opener)
        archive_hash = hashlib.sha256(archive.path.read_bytes()).hexdigest()
        _extract_source_tree(archive.path, source_path, archive.root, release.version)
        # The archive's own build_info.py is the repository's stale copy, so the
        # identity of the release is written here, from the release itself.
        stamp_package_build(source_path, release)
        _validate_package_build(source_path, release)
        plan = UpdatePlan(
            release=release,
            platform=selected_platform,
            source_path=source_path,
            target_path=(target_path or Path(__file__).resolve().parent).resolve(),
            work_dir=work_dir,
            log_path=log_path or Path.home() / ".paminnelseapp" / "logs" / "app.log",
            package_sha256=archive_hash,
            source_commit=(release.source_commit or release.release_commit or "").lower(),
        )
        _log(plan, f"Validated Python update {release.version} from {plan.source_commit or 'the release'}")
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
            report_fault()


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
    # The files are the old ones again, so the record of what is installed has
    # to follow; otherwise the next check would believe the update took effect.
    update_state.restore_state(installed.previous_state)
    if errors:
        raise UpdateInstallError(_("Uppdateringen kunde inte rullas tillbaka: {error}", error="; ".join(errors)))
    _log(installed.plan, "Rolled back Python update")


def install_update(plan: UpdatePlan) -> InstalledUpdate:
    """Atomically replace application-owned Python files, retaining a rollback copy."""

    installed = InstalledUpdate(plan=plan, replacements=[], previous_state=update_state.read_state())
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
        if plan.package_sha256 or plan.source_commit:
            update_state.record_installed_package(
                plan.package_sha256,
                release_id=plan.release.release_id,
                version=plan.release.version,
                source_commit=plan.source_commit,
            )
        _log(plan, f"Installed Python update {plan.release.version}; restart pending")
        return installed
    except Exception as exc:
        try:
            rollback_update(installed)
        except UpdateInstallError:
            report_fault()
        shutil.rmtree(plan.work_dir, ignore_errors=True)
        if isinstance(exc, UpdateInstallError):
            raise
        raise UpdateInstallError(_("Uppdateringen kunde inte installeras: {error}", error=exc)) from exc


def mark_update_ready() -> bool:
    """Confirm that the updated app's UI event loop has started.

    The parent supplies a one-off path and token only to the child process. An
    atomic write prevents the parent from reading a partial acknowledgement.
    Normal starts without these environment variables do nothing.
    """
    filename = os.environ.get(UPDATE_READY_FILE_ENV, "")
    token = os.environ.get(UPDATE_READY_TOKEN_ENV, "")
    if not filename or not token:
        return False
    ready_file = Path(filename)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{ready_file.name}.", dir=ready_file.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary.write_text(json.dumps({"token": token, "pid": os.getpid()}), encoding="utf-8")
        os.replace(temporary, ready_file)
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except (FileNotFoundError, OSError):
                report_fault()
    os.environ.pop(UPDATE_READY_FILE_ENV, None)
    os.environ.pop(UPDATE_READY_TOKEN_ENV, None)
    return True


def update_restart_ready(installed: InstalledUpdate, process) -> bool:
    """Return only a matching PID/token acknowledgement, never a mere file."""
    ready_file = getattr(installed, "ready_file", None)
    token = getattr(installed, "ready_token", "")
    if not ready_file or not token or not ready_file.is_file():
        return False
    try:
        payload = json.loads(ready_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("token") == token and payload.get("pid") == process.pid


def stop_updated_app(process) -> None:
    """Stop a child that failed its readiness handshake, without harming the parent."""
    try:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except Exception:
            process.kill()
            process.wait(timeout=2)
    except Exception:
        # Rollback must still run if a child already exited or cannot be killed.
        report_fault()


def wait_for_update_restart(installed: InstalledUpdate, process, timeout=UPDATE_RESTART_TIMEOUT_SECONDS) -> None:
    """Wait for real UI readiness and stop the child on every failed attempt."""
    deadline = time.monotonic() + float(timeout)
    try:
        while True:
            if update_restart_ready(installed, process):
                _log(installed.plan, f"Updated app confirmed UI readiness with PID {process.pid}")
                return
            return_code = process.poll()
            if return_code is not None:
                raise UpdateInstallError(
                    _("Den uppdaterade appen stängdes innan starten bekräftades (kod {code}).", code=return_code)
                )
            if time.monotonic() >= deadline:
                raise UpdateInstallError(_("Den uppdaterade appen bekräftade inte att den startade i tid."))
            time.sleep(0.1)
    except Exception:
        stop_updated_app(process)
        raise


def restart_updated_app(installed: InstalledUpdate):
    """Start the updated Python app without a console and return its process."""

    if getattr(sys, "frozen", False) or not sys.executable:
        raise UpdateInstallError(_("Konsolfri omstart kräver en Python-installation."))
    executable = Path(sys.executable).resolve()
    script = installed.plan.target_path / "paypamin_flow_launcher.py"
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
    ready_file = installed.plan.work_dir / "restart-ready.json"
    ready_token = secrets.token_hex(24)
    installed.ready_file = ready_file
    installed.ready_token = ready_token
    environment = os.environ.copy()
    environment[UPDATE_READY_FILE_ENV] = str(ready_file)
    environment[UPDATE_READY_TOKEN_ENV] = ready_token
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
            env=environment,
        )
    except OSError as exc:
        raise UpdateInstallError(_("Den uppdaterade appen kunde inte startas: {error}", error=exc)) from exc
    _log(installed.plan, f"Restarted updated app with PID {process.pid}; waiting for UI readiness")
    return process


def cleanup_update(value: UpdatePlan | InstalledUpdate) -> None:
    """Remove temporary downloads and rollback copies on a best-effort basis."""

    plan = value.plan if isinstance(value, InstalledUpdate) else value
    shutil.rmtree(plan.work_dir, ignore_errors=True)
