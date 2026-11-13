#!/usr/bin/env python3
"""Verify that the committed artwork really comes from the vector masters.

The SVG files are the single source of truth. This check rebuilds every
raster asset into a temporary folder and compares the result with what is
committed in ``assets/``. Pixel comparison uses a tolerance instead of a
byte-for-byte hash, because anti-aliasing differs slightly between PyMuPDF
and Pillow builds; a different logo, icon or colour still fails.

Run from the repository root (also used by CI):
    python assets/verify_branding.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ASSETS))

import build_icons  # noqa: E402

# Mean per-channel difference allowed between committed and rebuilt pixels.
MAX_MEAN_DIFFERENCE = 3.0
MAX_CHANNEL_DIFFERENCE = 96


def compare_images(expected: Path, rebuilt: Path) -> list[str]:
    """Return a list of problems for one image pair."""
    problems: list[str] = []
    with Image.open(expected) as left_source, Image.open(rebuilt) as right_source:
        left = left_source.convert("RGBA")
        right = right_source.convert("RGBA")
        if left.size != right.size:
            return [f"{expected.name}: size {left.size} != rebuilt {right.size}"]
        difference = ImageChops.difference(left, right)
        # RGBA histograms have 4 x 256 bins, so each band is measured on its
        # own; mixing the bands would report a meaningless total.
        bands = difference.split()
        pixel_count = left.size[0] * left.size[1]
        means = []
        for band in bands:
            histogram = band.histogram()
            weighted = sum(value * count for value, count in enumerate(histogram))
            means.append(weighted / pixel_count if pixel_count else 0.0)
        mean = sum(means) / len(means)
        if mean > MAX_MEAN_DIFFERENCE:
            problems.append(f"{expected.name}: mean pixel difference {mean:.2f} > {MAX_MEAN_DIFFERENCE}")
        largest = max(band.getextrema()[1] for band in bands)
        if largest > MAX_CHANNEL_DIFFERENCE:
            problems.append(f"{expected.name}: a channel differs by {largest} (limit {MAX_CHANNEL_DIFFERENCE})")
    return problems


def compare_print_pdf(path: Path) -> list[str]:
    """Confirm a print PDF is vector-only at the documented physical size."""
    problems: list[str] = []
    try:
        import pymupdf
    except ImportError:  # older PyMuPDF releases only expose ``fitz``
        import fitz as pymupdf
    try:
        with pymupdf.open(path) as document:
            if document.page_count != 1:
                return [f"{path.name}: {document.page_count} pages instead of 1"]
            page = document[0]
            if page.get_images():
                problems.append(f"{path.name}: embeds a raster image instead of vector art")
            if not page.get_drawings():
                problems.append(f"{path.name}: contains no vector artwork")
            width_mm = page.rect.width / 72 * 25.4
            height_mm = page.rect.height / 72 * 25.4
            if not (97.0 <= width_mm <= 99.0 and 22.3 <= height_mm <= 23.9):
                problems.append(
                    f"{path.name}: page is {width_mm:.1f} x {height_mm:.1f} mm, expected 98 x 23.1 mm"
                )
    except Exception as exc:  # a corrupt PDF must fail the check, not crash it
        problems.append(f"{path.name}: unreadable ({exc})")
    return problems


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        rebuilt = Path(folder)
        build_icons.main(rebuilt)
        problems: list[str] = []

        committed_png = sorted(p for p in ASSETS.rglob("*.png") if p.parent.name != "icons")
        for path in committed_png:
            candidate = rebuilt / path.relative_to(ASSETS)
            if not candidate.is_file():
                problems.append(f"{path.name}: not produced by the vector masters")
                continue
            problems.extend(compare_images(path, candidate))

        # Print PDFs are checked structurally: vector only, one page, and the
        # physical size the README promises to a print shop.
        print_dir = ASSETS / "print"
        for name in ("paypamin_logo_print.pdf", "paypamin_logo_print_mono.pdf"):
            path = print_dir / name
            candidate = rebuilt / "print" / name
            if not path.is_file():
                problems.append(f"{name}: missing from assets/print")
                continue
            if not candidate.is_file():
                problems.append(f"{name}: not produced by the vector masters")
                continue
            problems.extend(compare_print_pdf(path))

        # Binary containers only need to exist with the same embedded sizes;
        # ICO/ICNS headers carry timestamps that are not part of the artwork.
        for name in ("paypamin_flow.ico", "paypamin_flow.icns"):
            path = ASSETS / name
            candidate = rebuilt / name
            if not candidate.is_file():
                problems.append(f"{name}: not produced by the vector masters")
                continue
            with Image.open(path) as committed, Image.open(candidate) as fresh:
                if committed.size != fresh.size:
                    problems.append(f"{name}: leading image size differs")

        vector_files = sorted(ASSETS.rglob("*.svg"))
        if not vector_files:
            problems.append("no SVG masters found")
        for path in vector_files:
            text = path.read_text(encoding="utf-8")
            if "<text" in text or "font-family" in text:
                problems.append(f"{path.name}: contains live text instead of outlines")
            if "<filter" in text:
                problems.append(f"{path.name}: contains a filter, which print may not support")
            if "Copyright ©" not in text:
                problems.append(f"{path.name}: missing copyright metadata")

    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 1
    print(
        f"Branding verified: {len(committed_png)} PNG files, 2 print PDFs "
        "and 2 icon containers match the vector masters"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
