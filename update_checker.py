"""Check GitHub Releases for newer PayPamin Flow versions and builds.

This module only retrieves release metadata. It never downloads or installs an
update, and it sends no application or invoice data to GitHub.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, time as day_time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app_info import (
    APP_GIT_TAG_API,
    APP_LATEST_RELEASE_API,
    APP_NAME,
    APP_RELEASES_URL,
    APP_REPOSITORY,
    APP_SOURCE_ARCHIVE_URL,
    APP_TAG_REF_API,
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_ASSET,
    PYTHON_RELEASE_MANIFEST,
    fingerprint_package_files,
    is_python_package_file,
)
from build_info import APP_PACKAGE_FINGERPRINT, APP_RELEASE_COMMIT, APP_RELEASE_ID
from i18n import _

UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000
# A local-clock watchdog, not a network poll. Re-evaluate after sleep or a time
# zone change without waiting a full day on a monotonic UI timer.
UPDATE_CLOCK_WATCHDOG_MS = 15 * 60 * 1000


def next_midnight_delay_ms(now=None):
    """Milliseconds to the next local midnight, including 23/25-hour DST days.

    Naive datetimes use the OS local timezone via timestamp(); aware test inputs
    retain their zone's daylight-saving rules rather than assuming 24 hours.
    """
    now = datetime.now() if now is None else now
    tomorrow = now.date() + timedelta(days=1)
    midnight = datetime.combine(tomorrow, day_time.min, tzinfo=now.tzinfo)
    return max(1, int(round((midnight.timestamp() - now.timestamp()) * 1000)))


MAX_MANIFEST_BYTES = 1_000_000
MAX_CHECKSUM_BYTES = 65_536
# The tag and commit lookups return a few hundred bytes each.
MAX_TAG_BYTES = 65_536
# One commit's metadata (message plus the changed files) can exceed 64 kB.
MAX_COMMIT_BYTES = 1_000_000
# Comparing content tells whether the files differ, never which set is newer.
# A release whose ZIP was last uploaded before the installed files were
# written cannot be an update, whatever the version says.
STALE_FILE_MARGIN_SECONDS = 3600
# The outcome of comparing the release's files with the installed ones.
CONTENT_CURRENT = "current"
CONTENT_DIFFERS = "differs"
# The release is the source archive at a commit, and that commit is not the
# one the installed copy was built from. The files were never compared, so the
# outcome is recorded separately from a file comparison.
CONTENT_SOURCE_DIFFERS = "source_differs"
CONTENT_STALE = "stale"
CONTENT_UNAVAILABLE = "unavailable"


class UpdateCheckError(Exception):
    """A user-presentable update-check failure."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    # GitHub reports "sha256:<hex>" for every asset it stores. When it is
    # present the release can be judged by content without downloading it.
    digest: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    url: str
    assets: tuple[ReleaseAsset, ...] = ()
    # Numeric GitHub release ID remains for compatibility with older installs.
    release_id: str = ""
    release_commit: str = ""
    package_fingerprint: str = ""
    # SHA-256 of the release ZIP itself, the one value that changes when the
    # files in an already published release are replaced.
    package_sha256: str = ""
    # When GitHub last received the ZIP, used to tell an update from an older
    # release that simply does not contain the files on disk.
    package_updated_at: str = ""
    # The commit the release tag points at. The release is the source archive
    # GitHub builds from that commit, so this single value says exactly which
    # code is in the release - no package digest, no manifest and no download.
    source_commit: str = ""
    # When that commit was written, used to tell an update from an older
    # release that merely lacks the files on disk.
    source_committed_at: str = ""
    # Where the archive can be downloaded, filled in from the tag.
    source_url: str = ""
    # Filled in by ``update_installer.evaluate_release`` after the files in the
    # release have actually been compared with the installed ones.
    content_state: str = ""
    changed_files: tuple[str, ...] = ()


def version_key(value: str) -> tuple[int, int, int]:
    """Convert a stable release version such as v0.5.0 to comparable numbers."""
    match = re.fullmatch(r"\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*", str(value or ""), re.I)
    if not match:
        raise ValueError(f"Unsupported release version: {value!r}")
    return tuple(int(part or 0) for part in match.groups())


def canonical_version(value: str) -> str:
    return ".".join(str(part) for part in version_key(value))


def is_newer_version(candidate: str, current: str = APP_VERSION) -> bool:
    return version_key(candidate) > version_key(current)


def source_archive_url(tag_name: str) -> str:
    """Return the archive GitHub generates for a tag, or an empty string.

    The release carries no uploaded file: the source archive *is* the release.
    Asking GitHub for the tag's archive is the same thing a visitor gets from
    the Source code link, so the app and the download page can never disagree
    about which code is current.
    """
    tag = str(tag_name or "").strip()
    if not tag or "/" in tag or ".." in tag:
        return ""
    return APP_SOURCE_ARCHIVE_URL.format(tag=tag)


def _fetch_tag_identity(tag_name: str, timeout: int, opener) -> tuple[str, str]:
    """Return ``(commit, committed_at)`` for a release tag.

    GitHub's release payload only carries ``target_commitish``, which is a
    branch name once the release has moved with its tag, so the tag's own
    reference is read instead. An annotated tag points at a tag object, which
    has to be followed once more to reach the commit.
    """
    open_request = opener or urlopen
    tag = str(tag_name or "").strip()
    if not tag:
        return "", ""
    try:
        with open_request(_github_request(APP_TAG_REF_API.format(tag=tag)), timeout=timeout) as response:
            payload = json.loads(response.read(MAX_TAG_BYTES).decode("utf-8"))
        if not isinstance(payload, dict):
            return "", ""
        target = payload.get("object") or {}
        if not isinstance(target, dict):
            return "", ""
        sha = str(target.get("sha") or "").strip().lower()
        if str(target.get("type") or "") == "tag":
            with open_request(_github_request(APP_GIT_TAG_API.format(sha=sha)), timeout=timeout) as response:
                annotated = json.loads(response.read(MAX_TAG_BYTES).decode("utf-8"))
            inner = (annotated.get("object") or {}) if isinstance(annotated, dict) else {}
            sha = str(inner.get("sha") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return "", ""
    except Exception:  # noqa: BLE001 - an unreadable tag simply means "unknown"
        return "", ""
    committed_at = _commit_date(sha, timeout, open_request)
    return sha, committed_at


def _commit_date(commit: str, timeout: int, open_request) -> str:
    """Return the commit's own timestamp, or an empty string."""
    try:
        with open_request(
            _github_request(f"https://api.github.com/repos/{APP_REPOSITORY}/commits/{commit}"),
            timeout=timeout,
        ) as response:
            # The commit endpoint carries the full message and a list of
            # changed files, so the cap is generous: a truncated body would
            # fail to parse and lose the date entirely.
            payload = json.loads(response.read(MAX_COMMIT_BYTES).decode("utf-8"))
        detail = (payload.get("commit") or {}) if isinstance(payload, dict) else {}
        author = (detail.get("committer") or detail.get("author") or {}) if isinstance(detail, dict) else {}
        return str(author.get("date") or "").strip()
    except Exception:  # noqa: BLE001 - a missing date must never break a check
        return ""


def is_update_available(
    release: ReleaseInfo,
    current_version: str = APP_VERSION,
    current_release_id: str = APP_RELEASE_ID,
    current_release_commit: str = APP_RELEASE_COMMIT,
    current_package_fingerprint: str = APP_PACKAGE_FINGERPRINT,
) -> bool:
    """Decide whether a release carries anything the installed copy lacks.

    Newer versions are always eligible. For the same version the tag's commit
    is compared with the commit the installed copy was built from, which is
    exact: the release is the source archive at that commit, so equal commits
    mean equal code and nothing has to be downloaded to prove it. When either
    side has no commit, the files are compared instead (see
    ``update_installer.evaluate_release``), and as a last resort the numeric
    release ID is used.
    """
    if is_newer_version(release.version, current_version):
        return True
    if version_key(release.version) != version_key(current_version):
        return False

    # The files themselves were compared. That answer is the strongest one
    # there is, so it decides even when the commit or the release ID differ.
    if release.content_state in (CONTENT_DIFFERS, CONTENT_SOURCE_DIFFERS):
        return True
    if release.content_state == CONTENT_CURRENT:
        return False
    if release.content_state == CONTENT_STALE:
        # The files differ, but the release is older than they are: installing
        # it would replace newer work with older files.
        return False

    if release.source_commit and current_release_commit:
        # The release is the source archive at exactly this commit, so the
        # comparison is exact in both directions and costs no download.
        return release.source_commit.lower() != current_release_commit.lower()

    if (
        current_release_commit
        and current_package_fingerprint
        and release.release_commit
        and release.package_fingerprint
    ):
        # Complete metadata on both sides: compare the shipped content itself.
        return (
            release.release_commit.lower() != current_release_commit.lower()
            or release.package_fingerprint.lower() != current_package_fingerprint.lower()
        )

    # No manifest in the release (the normal case): the release ID changes on
    # every publication, so it still carries a republished same-version build.
    return bool(
        release.release_id
        and current_release_id
        and release.release_id != current_release_id
    )


def missing_release_assets(release: ReleaseInfo) -> tuple[str, ...]:
    """Return what a release lacks before it can be installed.

    The release is the source archive GitHub builds for its tag, so the only
    thing that can be missing is the archive address itself - which is derived
    from the tag and therefore practically always present. The name is kept so
    every caller and log line keeps meaning.
    """
    if release.source_url or release.tag_name:
        return ()
    return (_("källkodsarkivet"),)


def update_change_kind(
    release: ReleaseInfo,
    current_version: str = APP_VERSION,
    current_release_commit: str = APP_RELEASE_COMMIT,
    current_package_fingerprint: str = APP_PACKAGE_FINGERPRINT,
) -> str:
    """Describe the verified reason for an available update."""
    if is_newer_version(release.version, current_version):
        return "version"
    if release.content_state == CONTENT_SOURCE_DIFFERS:
        return "source"
    if release.content_state == CONTENT_DIFFERS:
        return "files"
    if release.source_commit and current_release_commit:
        if release.source_commit.lower() != current_release_commit.lower():
            return "source"
    commit_changed = bool(
        release.release_commit and current_release_commit
        and release.release_commit.lower() != current_release_commit.lower()
    )
    files_changed = bool(
        release.package_fingerprint and current_package_fingerprint
        and release.package_fingerprint.lower() != current_package_fingerprint.lower()
    )
    if commit_changed and files_changed:
        return "commit_and_files"
    if commit_changed:
        return "commit"
    if files_changed:
        return "files"
    return "release"


def _asset_digest(value) -> str:
    """Return the bare SHA-256 from GitHub's ``sha256:<hex>`` asset digest."""
    text = str(value or "").strip().lower()
    if not text.startswith("sha256:"):
        return ""
    candidate = text.split(":", 1)[1]
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else ""


def package_asset_updated_at(assets) -> str:
    """Return GitHub's ``updated_at`` for the update ZIP."""
    for asset in assets:
        if asset.name == PYTHON_RELEASE_ASSET and asset.updated_at:
            return asset.updated_at
    return ""


def package_asset_sha256(assets) -> str:
    """Return the digest GitHub reports for the update ZIP, if any."""
    for asset in assets:
        if asset.name == PYTHON_RELEASE_ASSET and asset.digest:
            return asset.digest.lower()
    return ""


def release_package_sha256(release: ReleaseInfo, timeout: int = 8, opener=None) -> str:
    """Return the SHA-256 of the release ZIP without downloading the ZIP.

    The digest GitHub reports with the release costs no request at all. When
    it is missing (an asset uploaded by an older workflow), the tiny
    ``.zip.sha256`` sidecar is read instead - still a few dozen bytes.
    """
    if release.package_sha256:
        return release.package_sha256.lower()
    asset = next(
        (item for item in release.assets if item.name == PYTHON_RELEASE_ASSET + ".sha256"),
        None,
    )
    if asset is None:
        return ""
    open_request = opener or urlopen
    try:
        request = _github_request(asset.url)
        request.add_header("Accept", "application/octet-stream")
        with open_request(request, timeout=timeout) as response:
            raw = response.read(MAX_CHECKSUM_BYTES)
        text = raw.decode("ascii", "replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[1].lstrip("*") == PYTHON_RELEASE_ASSET:
            candidate = parts[0].strip().lower()
            return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else ""
    return ""


def _validated_release_url(value: str) -> str:
    url = value or APP_RELEASES_URL
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("Untrusted release URL")
    return url


def _github_request(url: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _load_release_build_manifest(release: ReleaseInfo, timeout: int, opener) -> ReleaseInfo:
    """Read release commit and per-file hashes without downloading the ZIP."""
    asset = next((item for item in release.assets if item.name == PYTHON_RELEASE_MANIFEST), None)
    if asset is None:
        return release
    open_request = opener or urlopen
    try:
        request = _github_request(asset.url)
        request.add_header("Accept", "application/octet-stream")
        with open_request(request, timeout=timeout) as response:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("Release build manifest is too large")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != 1:
            raise ValueError("Invalid release build manifest")
        if payload.get("application") != APP_NAME:
            raise ValueError("Build manifest application mismatch")
        if canonical_version(str(payload.get("version") or "")) != release.version:
            raise ValueError("Build manifest version mismatch")
        if str(payload.get("release_id") or "").strip() != release.release_id:
            raise ValueError("Build manifest release ID mismatch")
        commit = str(payload.get("commit") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Build manifest commit is invalid")
        if release.release_commit and release.release_commit != commit:
            raise ValueError("Build manifest commit does not match release tag")

        raw_files = payload.get("files")
        if not isinstance(raw_files, dict) or not raw_files or len(raw_files) > 500:
            raise ValueError("Build manifest files are invalid")
        files = {}
        for name, file_hash in raw_files.items():
            if not isinstance(name, str) or not isinstance(file_hash, str):
                raise ValueError("Build manifest file entry is invalid")
            normalized_hash = file_hash.strip().lower()
            if (
                name == "build_info.py"
                or not is_python_package_file(name)
                or not re.fullmatch(r"[0-9a-f]{64}", normalized_hash)
            ):
                raise ValueError("Build manifest file entry is invalid")
            files[name] = normalized_hash
        if len({name.casefold() for name in files}) != len(files):
            raise ValueError("Build manifest contains duplicate filenames")
        missing = set(PYTHON_PACKAGE_REQUIRED_FILES) - {"build_info.py"} - set(files)
        if missing:
            raise ValueError("Build manifest is incomplete")
        fingerprint = fingerprint_package_files(files)
        claimed = str(payload.get("package_fingerprint") or "").strip().lower()
        if claimed != fingerprint:
            raise ValueError("Build manifest file fingerprint mismatch")
    except UpdateCheckError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        raise
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(_("Releasens byggmanifest är ogiltigt.")) from exc
    return replace(release, release_commit=commit, package_fingerprint=fingerprint)


def fetch_latest_release(timeout: int = 8, opener=None) -> ReleaseInfo:
    """Return the latest stable public GitHub release or raise UpdateCheckError."""
    open_request = opener or urlopen
    try:
        with open_request(_github_request(APP_LATEST_RELEASE_API), timeout=timeout) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Release response is not an object")
        if payload.get("draft") or payload.get("prerelease"):
            raise UpdateCheckError(_("Ingen publicerad stabil release hittades på GitHub."))
        tag_name = str(payload.get("tag_name") or "").strip()
        if not tag_name:
            raise ValueError("Release tag is missing")
        raw_release_id = payload.get("id")
        release_id = "" if raw_release_id is None else str(raw_release_id).strip()
        if release_id and not re.fullmatch(r"[1-9][0-9]*", release_id):
            raise ValueError("Release ID is invalid")
        raw_target = str(payload.get("target_commitish") or "").strip().lower()
        release_commit = raw_target if re.fullmatch(r"[0-9a-f]{40}", raw_target) else ""
        raw_assets = payload.get("assets") or []
        if not isinstance(raw_assets, list):
            raise ValueError("Release assets are not a list")
        assets = []
        for item in raw_assets:
            if not isinstance(item, dict):
                raise ValueError("Invalid release asset")
            name = str(item.get("name") or "").strip()
            url = str(item.get("browser_download_url") or "").strip()
            if not name or not url:
                raise ValueError("Release asset name or URL is missing")
            assets.append(
                ReleaseAsset(
                    name=name,
                    url=_validated_release_url(url),
                    digest=_asset_digest(item.get("digest")),
                    updated_at=str(item.get("updated_at") or "").strip(),
                )
            )
        source_commit, source_committed_at = _fetch_tag_identity(tag_name, timeout, open_request)
        if source_commit:
            # The tag's commit outranks target_commitish, which becomes a
            # branch name as soon as the release follows the branch.
            release_commit = source_commit
        release = ReleaseInfo(
            version=canonical_version(tag_name),
            tag_name=tag_name,
            url=_validated_release_url(str(payload.get("html_url") or "")),
            assets=tuple(assets),
            release_id=release_id,
            release_commit=release_commit,
            package_sha256=package_asset_sha256(assets),
            package_updated_at=package_asset_updated_at(assets) or source_committed_at,
            source_commit=source_commit,
            source_committed_at=source_committed_at,
            source_url=source_archive_url(tag_name),
        )
        return _load_release_build_manifest(release, timeout, open_request)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateCheckError(_("Ingen publicerad stabil release hittades på GitHub.")) from exc
        if exc.code in (403, 429):
            raise UpdateCheckError(_("GitHub tillåter inte fler uppdateringskontroller just nu. Försök igen senare.")) from exc
        raise UpdateCheckError(_("GitHub returnerade HTTP {status} vid uppdateringskontrollen.", status=exc.code)) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateCheckError(_("Kunde inte kontakta GitHub. Kontrollera internetanslutningen och försök igen.")) from exc
    except UpdateCheckError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(_("GitHub returnerade ett oväntat svar vid uppdateringskontrollen.")) from exc
