#!/usr/bin/env python3
"""Rewrite the description of a release that carries the source code.

The release has no uploaded files any more: GitHub generates a source archive
for the tag, and that archive is what the app updates from. The page therefore
describes the commit, not a ZIP - and it must say when the tag last moved,
because GitHub keeps showing the release's original publication date while the
code underneath is replaced.

The block is delimited so it can be replaced instead of appended:

    <!-- release -->
    ...
    <!-- /release -->

Everything outside the markers is kept byte for byte, so hand-written release
notes survive every refresh.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OPENING = "<!-- release -->"
CLOSING = "<!-- /release -->"


def package_block(commit: str, tag: str = "", built: str | None = None) -> str:
    """Build the block that describes the source archive on the release page."""
    short = str(commit or "").strip()[:7]
    built = built or datetime.now(timezone.utc).date().isoformat()
    lines = [OPENING, "**Releasen är källkoden på taggen.**", ""]
    lines.append(f"- Uppdaterad: {built}")
    if short:
        lines.append(f"- Commit: `{short}`")
    if tag:
        lines.append(f"- Tag: `{tag}`")
    lines.append(
        "- Uppdatera direkt inifrån PayPamin Flow (**Hjälp → Sök efter uppdateringar**), "
        "eller ladda ner `PayPamin-Flow-Python.zip` respektive **Source code (zip)** nedan."
    )
    lines.append(CLOSING)
    return "\n".join(lines)


def replace_block(body: str, block: str) -> str:
    """Swap the delimited block, or put one first when there is none yet.

    A description written before this existed has no markers, so the block is
    placed at the top and the original text follows unchanged. Text that holds
    only one of the markers is treated as if it had none: guessing which half
    to keep would silently delete someone's notes.
    """
    body = body or ""
    if OPENING in body and CLOSING in body:
        head, rest = body.split(OPENING, 1)
        tail = rest.split(CLOSING, 1)[1]
        return f"{head}{block}{tail}"
    return f"{block}\n\n{body}".rstrip() + "\n"


DEFAULT_NOTES = """## PayPamin Flow {version}

### Nyheter i denna version
- **Förbättrad avläsning av kundnamn vid PDF-import**: Läser automatiskt av kundnamn från svenska och engelska faktura-PDF:er (Fortnox, Cabas, Visma m.fl.) inklusive fönsterkuvert i tvåkolumnslayout, `Box`/`Postbox`/`FE`-adresser, `c/o`-rader, gårds-/byadresser utan gatunummer samt väljer `Fakturaadress` framför `Leveransadress` och avsändarens sidfot.
- **Spara fakturor som klump-PDF eller enskilda PDF:er i `import/`**: En PDF med flera olika fakturor delas automatiskt upp (1 faktura per sida om inget annat anges) och totalimporteras direkt.
- **Automatisk års-/månadsarkivering & reskontraexport**: Betalda reskontrafakturor flyttas till `import/ÅÅÅÅ/MM/` och reskontran kan exporteras till `.csv` och liggande A4-`.pdf`.
"""


def describe_release(
    *,
    tag: str,
    repository: str,
    commit: str = "",
    built: str | None = None,
) -> str:
    """Read the release body from GitHub and return the rewritten description."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/releases/tags/{tag}", "--jq", ".body // \"\""],
        check=False, capture_output=True, text=True,
    )
    version = str(tag or "").lstrip("v") or "0.7.0"
    body = result.stdout if result.returncode == 0 and result.stdout.strip() else DEFAULT_NOTES.format(version=version)
    return replace_block(body, package_block(commit, tag, built))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", default="")
    parser.add_argument("--built", help="Date the tag moved (default: today, UTC)")
    parser.add_argument("--output", type=Path, help="Write the description here instead of stdout")
    arguments = parser.parse_args(argv)
    description = describe_release(
        tag=arguments.tag,
        repository=arguments.repository,
        commit=arguments.commit,
        built=arguments.built,
    )
    if arguments.output:
        arguments.output.write_text(description, encoding="utf-8")
    else:
        json.dump({"body": description}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
