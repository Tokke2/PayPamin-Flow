"""Check GitHub Releases for newer PayPamin Flow versions.

This module only retrieves release metadata. It never downloads or installs an
update, and it sends no application or invoice data to GitHub.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app_info import APP_LATEST_RELEASE_API, APP_NAME, APP_RELEASES_URL, APP_VERSION
from build_info import APP_RELEASE_ID
from i18n import _

UPDATE_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000


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
    # Numeric GitHub release ID stamped into official packages at build time.
    release_id: str = ""


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
) -> bool:
    """Compare versions, then distinguish official builds of the same version.

    A different release ID never makes an older version eligible. Source
    checkouts without a stamped release ID retain the normal version-only
    behavior, while official packages can receive a refreshed same-version
    release without repeatedly reinstalling the build they already run.
    """
    if is_newer_version(release.version, current_version):
        return True
    if version_key(release.version) != version_key(current_version):
        return False
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


def fetch_latest_release(timeout: int = 8, opener=None) -> ReleaseInfo:
    """Return the latest stable public GitHub release or raise UpdateCheckError."""
    request = Request(
        APP_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    open_request = opener or urlopen
    try:
        with open_request(request, timeout=timeout) as response:
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
        return ReleaseInfo(
            version=canonical_version(tag_name),
            tag_name=tag_name,
            url=_validated_release_url(str(payload.get("html_url") or "")),
            assets=tuple(assets),
            release_id=release_id,
        )
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
