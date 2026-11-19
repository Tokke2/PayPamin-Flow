#!/usr/bin/env python3
"""Rewrite the package block of the release description from the real ZIP.

The release is rebuilt in place while the application is still 0.6.0, so the
release page can otherwise describe a file that is no longer there: an old
checksum, an old file count and an old size, which makes a refreshed release
look untouched. This writes the facts about the ZIP that was just uploaded and
leaves every other sentence in the description alone.

The block is delimited so it can be replaced instead of appended on the next
build:

    <!-- paket -->
    ...
    <!-- /paket -->

Everything outside the markers is kept byte for byte, so the release notes that
were written by hand survive every refresh.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

OPENING = "<!-- paket -->"
CLOSING = "<!-- /paket -->"


def archive_facts(archive: Path, sidecar: Path | None = None) -> dict:
    """Return size, file count and checksum for a release ZIP.

    The checksum is read from the sidecar when it is present, because that file
    is what a downloader checks against, and it is verified against the ZIP so a
    stale sidecar can never be published as if it described the upload.
    """
    archive = Path(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    entries = 0
    with zipfile.ZipFile(archive) as package:
        entries = len([name for name in package.namelist() if not name.endswith("/")])
    sidecar = Path(sidecar) if sidecar else archive.with_suffix(archive.suffix + ".sha256")
    if sidecar.is_file():
        recorded = sidecar.read_text(encoding="utf-8").split()
        if recorded and recorded[0] != digest:
            raise SystemExit(
                f"{sidecar.name} describes {recorded[0]}, but {archive.name} is {digest}"
            )
    return {
        "name": archive.name,
        "entries": entries,
        "size": archive.stat().st_size,
        "sha256": digest,
    }


def package_block(facts: dict, commit: str) -> str:
    """Build the replacement block for one uploaded package."""
    short = commit[:7] if commit else ""
    built = f" (byggt av `{short}`)" if short else ""
    kilobytes = facts["size"] / 1024
    return "\n".join((
        OPENING,
        f"**Paketet i releasen**{built}",
        "",
        f"- `{facts['name']}` – {facts['entries']} filer, {kilobytes:.0f} kB",
        f"- sha256: `{facts['sha256']}`",
        "- Releasen består av exakt dessa två filer; `.sha256` innehåller samma "
        "kontrollsumma som ZIP:en.",
        CLOSING,
    ))


def replace_block(body: str, block: str) -> str:
    """Swap the delimited block, or put one first when there is none yet.

    A description written before this existed has no markers, so the block is
    placed at the top and the original text follows unchanged. Text that
    happens to contain only one of the markers is treated as if it had none:
    guessing which half to keep would silently delete someone's notes.
    """
    body = body or ""
    if OPENING in body and CLOSING in body:
        head, rest = body.split(OPENING, 1)
        tail = rest.split(CLOSING, 1)[1]
        return f"{head}{block}{tail}"
    return f"{block}\n\n{body}".rstrip() + "\n"


def describe_package(
    *,
    tag: str,
    repository: str,
    archive: Path,
    commit: str = "",
    sidecar: Path | None = None,
) -> str:
    """Read the release body from GitHub and return the rewritten description."""
    body = subprocess.run(
        ["gh", "api", f"repos/{repository}/releases/tags/{tag}", "--jq", ".body // \"\""],
        check=True, capture_output=True, text=True,
    ).stdout
    return replace_block(body, package_block(archive_facts(archive, sidecar), commit))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--commit", default="")
    parser.add_argument("--output", type=Path, help="Write the description here instead of stdout")
    arguments = parser.parse_args(argv)
    description = describe_package(
        tag=arguments.tag,
        repository=arguments.repository,
        archive=arguments.archive,
        commit=arguments.commit,
        sidecar=arguments.sidecar,
    )
    if arguments.output:
        arguments.output.write_text(description, encoding="utf-8")
    else:
        json.dump({"body": description}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
