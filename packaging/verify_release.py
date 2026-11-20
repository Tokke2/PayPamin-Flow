"""Prove that a release really carries the commit it claims to carry.

The release job moves the tag and rewrites the page, and then it says it
succeeded - but a step that only reports its own exit status cannot tell
whether GitHub actually accepted the move. A tag can be rejected, a page can
keep an older body, and the app would still be told "there is an update" that
downloads different code than the page describes.

This module reads the result back and compares it with the commit that was just
pushed:

* the tag resolves to that exact commit,
* the page names that commit,
* the release has no uploaded files left (the archive *is* the release),
* the archive GitHub generates can be downloaded, wraps a single
  ``PayPamin-Flow-<version>`` folder, and every file in it is byte-for-byte the
  file in the checkout.

The last check is the one that matters: it compares the code the app would
install with the code that was tested, which no amount of API bookkeeping can
prove on its own. GitHub can serve a stale archive for a few seconds after a tag
moves, so the download is retried before the job is allowed to fail.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_info import APP_VERSION, is_python_package_file  # noqa: E402
from update_installer import source_archive_root  # noqa: E402

ARCHIVE_URL = "https://github.com/{repository}/archive/refs/tags/{tag}.zip"
RETRY_ATTEMPTS = 8
RETRY_DELAY_SECONDS = 10.0


class ReleaseVerificationError(RuntimeError):
    """Raised when the release cannot be read back at all."""


def _api(repository: str, path: str) -> dict:
    """Read one GitHub API endpoint through the authenticated ``gh`` client."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/{path}"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ReleaseVerificationError(result.stderr.strip() or f"gh api {path} failed")
    try:
        return json.loads(result.stdout or "{}")
    except ValueError as error:
        raise ReleaseVerificationError(f"gh api {path} returned no JSON: {error}") from error


def tag_commit(repository: str, tag: str, api=None) -> str:
    """Return the commit a tag points at, following an annotated tag once."""
    read = api or _api
    try:
        reference = read(repository, f"git/ref/tags/{tag}")
    except ReleaseVerificationError:
        return ""
    target = reference.get("object") or {}
    if target.get("type") == "tag" and target.get("sha"):
        try:
            annotated = read(repository, f"git/tags/{target['sha']}")
        except ReleaseVerificationError:
            return ""
        target = annotated.get("object") or {}
    return str(target.get("sha") or "")


def release_page(repository: str, tag: str, api=None) -> dict:
    """Return the release object for a tag, or an empty dict when there is none."""
    read = api or _api
    try:
        return read(repository, f"releases/tags/{tag}")
    except ReleaseVerificationError:
        return {}


def _download(url: str, timeout: float = 60.0) -> bytes:
    request = Request(url, headers={"User-Agent": "PayPamin-Flow-release-check"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed host
        return response.read()


def read_archive(payload: bytes) -> tuple[str, dict[str, bytes]]:
    """Return the archive's single root folder and its files by relative name."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        root = source_archive_root(info.filename for info in infos)
        files = {}
        for info in infos:
            name = info.filename
            if root:
                prefix = f"{root}/"
                if not name.startswith(prefix):
                    continue
                name = name[len(prefix):]
            if name:
                files[name] = archive.read(info)
    return root, files


def compare_with_checkout(files: dict[str, bytes], checkout: Path) -> list[str]:
    """Return the files whose content differs from the checkout on disk."""
    differences = []
    for name, content in sorted(files.items()):
        existing = checkout / name
        if not existing.is_file():
            continue
        try:
            if existing.read_bytes() != content:
                differences.append(name)
        except OSError:
            differences.append(name)
    return differences


def _fetch_archive(
    url: str, *, attempts: int, delay: float, fetch=None, sleep=time.sleep
) -> tuple[bytes, str]:
    """Download the archive, retrying while GitHub still serves the old tag."""
    getter = fetch or _download
    last = ""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return getter(url), ""
        except HTTPError as error:
            last = f"HTTP {error.code}"
        except (URLError, OSError) as error:
            last = str(getattr(error, "reason", error))
        if attempt < attempts:
            sleep(delay)
    return b"", last or "no response"


def verify(
    *,
    tag: str,
    repository: str,
    commit: str,
    version: str = APP_VERSION,
    checkout: Path | str = ".",
    api=None,
    fetch=None,
    attempts: int = RETRY_ATTEMPTS,
    delay: float = RETRY_DELAY_SECONDS,
    sleep=time.sleep,
) -> list[str]:
    """Return every way the release disagrees with ``commit``; empty means good.

    Nothing here raises for a broken release: the caller gets a list of
    problems to print, and the last of them decides the exit code.
    """
    problems: list[str] = []
    commit = str(commit or "").strip()
    if len(commit) < 7:
        return ["Ingen commit angavs, så releasen kan inte verifieras."]

    resolved = tag_commit(repository, tag, api=api)
    if not resolved:
        problems.append(f"Taggen {tag} gick inte att läsa från GitHub.")
    elif resolved != commit:
        problems.append(f"Taggen {tag} pekar på {resolved[:7]}, inte på {commit[:7]}.")

    release = release_page(repository, tag, api=api)
    if not release:
        problems.append(f"Releasen för {tag} gick inte att läsa.")
    else:
        body = str(release.get("body") or "")
        if commit[:7] not in body:
            problems.append(
                f"Releasens beskrivning nämner inte commit {commit[:7]}, så sidan beskriver en annan kod."
            )
        assets = release.get("assets") or []
        if assets:
            names = ", ".join(str(asset.get("name") or "?") for asset in assets[:5])
            problems.append(
                f"Releasen har {len(assets)} uppladdade fil(er) ({names}); den ska bara vara källkoden."
            )

    payload, failure = _fetch_archive(
        ARCHIVE_URL.format(repository=repository, tag=tag),
        attempts=attempts, delay=delay, fetch=fetch, sleep=sleep,
    )
    if not payload:
        problems.append(f"Källkodsarkivet för {tag} gick inte att hämta ({failure}).")
        return problems

    try:
        root, files = read_archive(payload)
    except (zipfile.BadZipFile, OSError) as error:
        problems.append(f"Källkodsarkivet för {tag} är skadat: {error}")
        return problems

    if root != f"PayPamin-Flow-{version}":
        problems.append(
            f"Källkodsarkivet har rotmappen {root or '(ingen)'} i stället för PayPamin-Flow-{version}."
        )
    missing = sorted(name for name in ("app_info.py", "paypamin_flow.py") if name not in files)
    if missing:
        problems.append(f"Källkodsarkivet saknar {', '.join(missing)}.")
    if not any(is_python_package_file(name) for name in files):
        problems.append("Källkodsarkivet innehåller inga programfiler.")

    differences = compare_with_checkout(files, Path(checkout))
    if differences:
        shown = ", ".join(differences[:5])
        more = f" och {len(differences) - 5} till" if len(differences) > 5 else ""
        problems.append(
            f"Arkivet skiljer sig från commit {commit[:7]} i {len(differences)} fil(er): {shown}{more}."
        )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument("--checkout", type=Path, default=ROOT)
    parser.add_argument("--attempts", type=int, default=RETRY_ATTEMPTS)
    parser.add_argument("--delay", type=float, default=RETRY_DELAY_SECONDS)
    arguments = parser.parse_args(argv)
    problems = verify(
        tag=arguments.tag,
        repository=arguments.repository,
        commit=arguments.commit,
        version=arguments.version,
        checkout=arguments.checkout,
        attempts=arguments.attempts,
        delay=arguments.delay,
    )
    if not problems:
        print(f"{arguments.tag} pekar på {arguments.commit[:7]} och arkivet är den koden.")
        return 0
    for problem in problems:
        print(f"::error::{problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
