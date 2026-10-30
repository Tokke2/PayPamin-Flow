"""Check GitHub Releases for newer PayPamin Flow versions and builds.

This module only retrieves release metadata. It never downloads or installs an
update, and it sends no application or invoice data to GitHub.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app_info import (
    APP_LATEST_RELEASE_API,
    APP_NAME,
    APP_RELEASES_URL,
    APP_VERSION,
    PYTHON_PACKAGE_REQUIRED_FILES,
    PYTHON_RELEASE_MANIFEST,
    fingerprint_package_files,
    is_python_package_file,
)
from build_info import APP_PACKAGE_FINGERPRINT, APP_RELEASE_COMMIT, APP_RELEASE_ID
from i18n import _

UPDATE_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000
MAX_MANIFEST_BYTES = 1_000_000


class UpdateCheckError(Exception):
    """A user-presentable update-check failure."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str


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


def is_update_available(
    release: ReleaseInfo,
    current_version: str = APP_VERSION,
    current_release_id: str = APP_RELEASE_ID,
    current_release_commit: str = APP_RELEASE_COMMIT,
    current_package_fingerprint: str = APP_PACKAGE_FINGERPRINT,
) -> bool:
    """Compare versions, then release commits and shipped-file fingerprints.

    Newer versions are always eligible. For the same version, current builds
    with commit/file metadata update only when either value actually changes.
    A new release ID alone does not reinstall identical content. Older official
    builds without that metadata retain the release-ID fallback so they can
    receive this updater. Source checkouts keep version-only behavior.
    """
    if is_newer_version(release.version, current_version):
        return True
    if version_key(release.version) != version_key(current_version):
        return False

    if current_release_commit and current_package_fingerprint:
        # Wait for complete metadata during release publication instead of
        # reinstalling solely because the numeric release ID changed.
        if not (release.release_commit and release.package_fingerprint):
            return False
        return (
            release.release_commit.lower() != current_release_commit.lower()
            or release.package_fingerprint.lower() != current_package_fingerprint.lower()
        )

    return bool(
        release.release_id
        and current_release_id
        and release.release_id != current_release_id
    )


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
            assets.append(ReleaseAsset(name=name, url=_validated_release_url(url)))
        release = ReleaseInfo(
            version=canonical_version(tag_name),
            tag_name=tag_name,
            url=_validated_release_url(str(payload.get("html_url") or "")),
            assets=tuple(assets),
            release_id=release_id,
            release_commit=release_commit,
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
