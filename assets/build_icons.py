#!/usr/bin/env python3
"""Generate PayPamin Flow's desktop icons and UI icons from the vector masters.

Run from the repository root:
    python assets/build_icons.py

The vector files are the single source of truth:

* ``assets/paypamin_flow.svg``       – product mark, detail version (40 px and up)
* ``assets/paypamin_flow_small.svg`` – simplified mark for 24–40 px
* ``assets/paypamin_flow_tiny.svg``  – smallest mark for 16–24 px, without the tick
* ``assets/paypamin_logo.svg``       – screen lockup (wordmark as outlines)
* ``assets/print/paypamin_logo_print.svg`` – flat print lockup
* ``assets/print/paypamin_logo_print_mono.svg`` – one-colour print lockup
* ``assets/print/*.pdf`` – vector PDFs at 90 mm width for a print shop

Every PNG, ICO and ICNS file is rasterised from those files, so a change to
the artwork only has to be made once. The small UI icons use a common
24-unit grid and are rendered at 16 px with transparent backgrounds and
light variants.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile

from PIL import Image, ImageDraw, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import APP_AUTHOR, APP_COPYRIGHT

ASSETS = Path(__file__).resolve().parent
UI_ASSETS = ASSETS / "icons"
SCALE = 3
SIZE = 512
CANVAS = SIZE * SCALE

ACTION_ICONS = (
    "add", "backup", "cache", "close", "customer", "delete", "edit",
    "email", "error", "external", "folder", "folder_export",
    "folder_import", "ignore", "info", "journal", "ledger", "log",
    "next", "paid", "pdf_add", "power", "reminder", "restore", "save",
    "scan", "sent", "settings", "technical", "tray", "update",
)


PRINT_ASSETS = ASSETS / "print"

SVG_SOURCES = {
    "icon": ASSETS / "paypamin_flow.svg",
    "icon_small": ASSETS / "paypamin_flow_small.svg",
    "icon_tiny": ASSETS / "paypamin_flow_tiny.svg",
    "logo": ASSETS / "paypamin_logo.svg",
    "logo_print": PRINT_ASSETS / "paypamin_logo_print.svg",
    "logo_print_mono": PRINT_ASSETS / "paypamin_logo_print_mono.svg",
}

# The lockups ship as three formats so a print shop never has to convert
# anything: SVG (editable), PDF (vector, with the physical size in mm) and a
# high-resolution PNG preview. They travel inside the release package; no
# separate download is needed.
PRINT_WIDTH_MM = 90
PRINT_MARGIN_MM = 4
MM_TO_POINT = 72 / 25.4

# Below this size the detailed mark turns into mush, so the simplified
# artwork is used instead. Windows uses 16/24/32 px in the taskbar and tray.
# At 16 px even the tick inside the badge becomes a smudge, so the smallest
# master drops it and keeps only the P and the teal sweep.
SMALL_ICON_LIMIT = 40
TINY_ICON_LIMIT = 24
RASTER_OVERSAMPLE = 4
# Menu and button glyphs are 16 px in Tk; drawing them at 4x and reducing them
# keeps the strokes solid instead of grey.
UI_ICON_SIZE = 16


def rasterise_svg(path: Path, width: int, height: int | None = None) -> Image.Image:
    """Render an SVG file to a PIL image at the requested pixel size.

    svglib produces a vector PDF and PyMuPDF rasterises it, so the result uses
    the same crisp geometry as the SVG instead of a re-drawn approximation.
    Rendering happens at 4x and is downsampled, which gives clean edges at the
    16-32 px sizes used by the tray and the taskbar.
    """
    import fitz
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(str(path))
    if drawing is None or not drawing.width or not drawing.height:
        raise SystemExit(f"Could not read SVG artwork: {path}")
    aspect = drawing.height / drawing.width
    height = height or max(1, round(width * aspect))
    scale_x = (width * RASTER_OVERSAMPLE) / drawing.width
    scale_y = (height * RASTER_OVERSAMPLE) / drawing.height
    drawing.width *= scale_x
    drawing.height *= scale_y
    drawing.scale(scale_x, scale_y)
    with tempfile.TemporaryDirectory() as folder:
        pdf_path = Path(folder) / "artwork.pdf"
        renderPDF.drawToFile(drawing, str(pdf_path))
        with fitz.open(str(pdf_path)) as document:
            page = document[0]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=True)
            raw = pixmap.samples
            if pixmap.alpha:
                # PyMuPDF stores the samples premultiplied; the "RGBa" mode is
                # Pillow's name for exactly that. Reading them as straight RGBA
                # and multiplying by alpha again darkens every soft edge.
                mode = "RGBa"
            else:
                mode = "RGB"
            image = Image.frombytes(mode, (pixmap.width, pixmap.height), raw)
    if image.mode != "RGBa":
        return image.resize((width, height), Image.Resampling.LANCZOS)
    # Resample in premultiplied alpha and only then divide by alpha. Resizing
    # straight RGBA blends the colour of fully transparent pixels (black) into
    # the edge, which shows up as a grey halo around the icon - the "muddy"
    # look at 16-48 px.
    return image.resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")


def create_icon(size: int = SIZE) -> Image.Image:
    """Return the product mark at the given size, using the right artwork."""
    if size <= TINY_ICON_LIMIT:
        name = "icon_tiny"
    elif size <= SMALL_ICON_LIMIT:
        name = "icon_small"
    else:
        name = "icon"
    return rasterise_svg(SVG_SOURCES[name], size, size)


# The lockup's own aspect ratio (viewBox 788.33 x 132). Deriving the height
# from it keeps the wordmark from being stretched, which looks soft even when
# the pixels themselves are sharp. The viewBox is cropped to the artwork, so
# there is no dead space above or below the mark.
LOGO_ASPECT = 788.33 / 132


def logo_height(width: int) -> int:
    """Return the exact proportional height for a lockup of ``width`` pixels."""
    return max(1, round(width / LOGO_ASPECT))


def create_horizontal_logo(width: int = 512) -> Image.Image:
    """Return the screen lockup with the outlined wordmark."""
    return rasterise_svg(SVG_SOURCES["logo"], width, logo_height(width))


def create_print_logo(path: Path, width: int = 1600, mono: bool = False):
    """Rasterise a print lockup and put it on white paper."""
    source = SVG_SOURCES["logo_print_mono" if mono else "logo_print"]
    height = round(width / LOGO_ASPECT)
    image = rasterise_svg(source, width, height).convert("RGBA")
    paper = Image.new("RGBA", image.size, (255, 255, 255, 255))
    paper.alpha_composite(image)
    return paper


def save_print_logo(path: Path, width: int = 1600, mono: bool = False, data=None) -> Path:
    image = create_print_logo(path, width=width, mono=mono)
    image.convert("RGB").save(path, format="PNG", pnginfo=data, optimize=True)
    return path


def save_print_pdf(path: Path, mono: bool = False) -> Path:
    """Write a vector PDF at a real print size for a commercial printer.

    The SVG is placed with 4 mm of clear space on a page sized to the artwork,
    so the PDF opens at the right physical dimensions. Text and shapes stay
    vector: no raster image is embedded, which keeps edges sharp at any size.
    """
    from reportlab.graphics import renderPDF
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas
    from svglib.svglib import svg2rlg

    source = SVG_SOURCES["logo_print_mono" if mono else "logo_print"]
    drawing = svg2rlg(str(source))
    if drawing is None:
        raise SystemExit(f"Could not read SVG artwork: {source}")
    scale = (PRINT_WIDTH_MM * mm) / drawing.width
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    margin = PRINT_MARGIN_MM * mm
    page_width = drawing.width + 2 * margin
    page_height = drawing.height + 2 * margin
    sheet = pdf_canvas.Canvas(str(path), pagesize=(page_width, page_height))
    sheet.setTitle("PayPamin Flow logotyp")
    sheet.setAuthor(APP_AUTHOR)
    sheet.setSubject("Tryckfärdig vektorlogotyp för PayPamin Flow")
    renderPDF.draw(drawing, sheet, margin, margin)
    sheet.showPage()
    sheet.save()
    return path


class IconCanvas:
    """Small rounded line drawing helpers on a 24 x 24 design grid."""

    def __init__(self, color):
        self.scale = 4
        self.image = Image.new("RGBA", (24 * self.scale, 24 * self.scale), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.color = color

    def pt(self, x, y):
        return round(x * self.scale), round(y * self.scale)

    def box(self, values):
        return tuple(round(value * self.scale) for value in values)

    def line(self, points, width=1.9):
        points = [self.pt(x, y) for x, y in points]
        self.draw.line(points, fill=self.color, width=round(width * self.scale), joint="curve")
        radius = width * self.scale / 2
        for x, y in points:
            self.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=self.color)

    def rect(self, values, radius=0, width=1.8):
        box = self.box(values)
        if radius:
            self.draw.rounded_rectangle(box, radius=radius * self.scale, outline=self.color, width=round(width * self.scale))
        else:
            self.draw.rectangle(box, outline=self.color, width=round(width * self.scale))

    def ellipse(self, values, width=1.8, fill=False):
        self.draw.ellipse(self.box(values), fill=self.color if fill else None, outline=None if fill else self.color, width=round(width * self.scale))

    def polygon(self, points, fill=False):
        points = [self.pt(x, y) for x, y in points]
        if fill:
            self.draw.polygon(points, fill=self.color)
        else:
            self.draw.line(points + [points[0]], fill=self.color, width=round(1.8 * self.scale), joint="curve")

    def arc(self, values, start, end, width=1.9):
        self.draw.arc(self.box(values), start=start, end=end, fill=self.color, width=round(width * self.scale))


def folder(canvas):
    canvas.line([(2.5, 6), (9.5, 6), (12, 8.5), (21.5, 8.5), (21.5, 20), (2.5, 20), (2.5, 6)])


def check(canvas, points=((6.5, 12.2), (10.2, 16), (17.8, 7.5)), width=2.1):
    canvas.line(list(points), width)


def draw_action_icon(name, color, size=UI_ICON_SIZE):
    """Draw one action glyph on the 24 x 24 grid and reduce it to ``size``."""
    c = IconCanvas(color)
    if name == "add":
        c.line([(12, 4), (12, 20)], 2.2); c.line([(4, 12), (20, 12)], 2.2)
    elif name == "backup":
        c.rect((2.5, 7, 21.5, 21), 1.5); c.line([(2.5, 11), (21.5, 11)])
        c.line([(12, 2.5), (12, 16)]); c.line([(8.5, 12.5), (12, 16), (15.5, 12.5)])
    elif name == "cache":
        c.line([(5, 3), (16, 14)], 2.3); c.polygon([(12, 12), (21, 14), (19, 22), (9, 18)])
        c.line([(12, 16), (18, 18)], 1.4)
    elif name == "close":
        c.line([(5, 5), (19, 19)], 2.2); c.line([(19, 5), (5, 19)], 2.2)
    elif name == "customer":
        c.ellipse((8, 3, 16, 11)); c.arc((3, 11, 21, 24), 185, 355, 2)
    elif name == "delete":
        c.line([(4, 6), (20, 6)]); c.line([(9, 3), (15, 3), (16, 6)])
        c.line([(6, 6), (7, 21), (17, 21), (18, 6)]); c.line([(10, 10), (10.5, 17)], 1.5); c.line([(14, 10), (13.5, 17)], 1.5)
    elif name == "edit":
        c.polygon([(4, 16), (5, 11), (16, 2.5), (20.5, 7), (9, 18)], False)
        c.line([(4, 16), (9, 18)]); c.line([(13.5, 5.5), (18, 10)]); c.line([(3, 21.5), (21, 21.5)], 1.5)
    elif name == "email":
        c.rect((2.5, 5, 21.5, 19), 1.5); c.line([(3.5, 6.5), (12, 13), (20.5, 6.5)])
    elif name == "error":
        c.polygon([(12, 2.5), (22.5, 21), (1.5, 21)]); c.line([(12, 8), (12, 14)], 2.1); c.ellipse((11.2, 16.5, 12.8, 18.1), fill=True)
    elif name == "external":
        c.line([(10, 4), (4, 4), (4, 20), (20, 20), (20, 14)])
        c.line([(13, 3), (21, 3), (21, 11)]); c.line([(11, 13), (21, 3)])
    elif name == "folder":
        folder(c)
    elif name == "folder_import":
        folder(c); c.line([(12, 10), (12, 17)], 1.6); c.line([(9.5, 14.5), (12, 17), (14.5, 14.5)], 1.6)
    elif name == "folder_export":
        folder(c); c.line([(12, 17), (12, 10)], 1.6); c.line([(9.5, 12.5), (12, 10), (14.5, 12.5)], 1.6)
    elif name == "ignore":
        c.line([(2, 12), (6, 7.5), (12, 5.5), (18, 7.5), (22, 12), (18, 16.5), (12, 18.5), (6, 16.5), (2, 12)], 1.5)
        c.ellipse((9, 9, 15, 15), 1.5); c.line([(3, 21), (21, 3)], 2.1)
    elif name == "info":
        c.ellipse((3, 3, 21, 21)); c.line([(12, 10), (12, 17)], 2.1); c.ellipse((11.1, 5.8, 12.9, 7.6), fill=True)
    elif name == "journal":
        c.rect((4, 2.5, 19, 21.5), 1); c.line([(8, 7), (16, 7)], 1.5); c.line([(8, 11), (16, 11)], 1.5)
        c.line([(8, 16), (15, 16)], 1.5); c.line([(12.5, 13.5), (15, 16), (12.5, 18.5)], 1.5)
    elif name == "ledger":
        c.rect((2.5, 4, 21.5, 20), 1); c.line([(2.5, 9), (21.5, 9)], 1.4); c.line([(2.5, 14.5), (21.5, 14.5)], 1.4)
        c.line([(9, 4), (9, 20)], 1.4); c.line([(16, 4), (16, 20)], 1.4)
    elif name == "log":
        c.rect((4, 2.5, 20, 21.5), 1); c.line([(8, 7), (16, 7)], 1.5); c.line([(8, 11), (16, 11)], 1.5); c.line([(8, 15), (14, 15)], 1.5)
    elif name == "next":
        c.line([(3, 12), (20, 12)], 2.1); c.line([(14, 6), (20, 12), (14, 18)], 2.1)
    elif name == "paid":
        c.ellipse((3, 3, 21, 21)); check(c)
    elif name == "pdf_add":
        c.line([(4, 21), (4, 3), (15, 3), (20, 8), (20, 21), (4, 21)])
        c.line([(15, 3), (15, 8), (20, 8)], 1.5); c.line([(12, 10), (12, 18)], 1.8); c.line([(8, 14), (16, 14)], 1.8)
    elif name == "power":
        c.arc((5, 5, 19, 20), 130, 410, 2); c.line([(12, 2.5), (12, 11)], 2.2)
    elif name == "reminder":
        c.line([(4, 17), (6.5, 14), (6.5, 9), (8.5, 5), (12, 4), (15.5, 5), (17.5, 9), (17.5, 14), (20, 17), (4, 17)])
        c.line([(3, 18), (21, 18)], 1.5); c.arc((9, 17, 15, 23), 0, 180, 1.8)
    elif name == "restore":
        c.arc((4, 4, 21, 21), 40, 330, 2); c.line([(4, 3), (4, 9), (10, 9)], 2)
    elif name == "save":
        c.rect((3, 3, 21, 21), 1); c.rect((7, 3, 17, 9), 0, 1.5); c.rect((7, 14, 17, 21), 0, 1.5); c.line([(14, 5), (14, 7)], 1.5)
    elif name == "scan":
        c.ellipse((3, 3, 15, 15), 2); c.line([(14, 14), (21, 21)], 2.3); c.line([(7, 9), (11, 9)], 1.5)
    elif name == "sent":
        c.polygon([(2.5, 4), (22, 11), (3, 21), (7, 13), (16, 11), (7, 10)]); c.line([(7, 13), (7, 17)], 1.4)
    elif name == "settings":
        c.ellipse((8, 8, 16, 16), 1.8); c.ellipse((5, 5, 19, 19), 1.6)
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            c.line([(12 + 7.2 * math.cos(a), 12 + 7.2 * math.sin(a)), (12 + 10 * math.cos(a), 12 + 10 * math.sin(a))], 1.8)
    elif name == "technical":
        for y, x in ((5, 8), (12, 16), (19, 10)):
            c.line([(3, y), (21, y)], 1.6); c.ellipse((x - 2, y - 2, x + 2, y + 2), 1.6)
    elif name == "tray":
        c.line([(12, 2.5), (12, 14)], 2); c.line([(8.5, 10.5), (12, 14), (15.5, 10.5)], 2)
        c.line([(3, 14), (3, 20), (21, 20), (21, 14)], 1.8); c.line([(3, 17), (8, 17), (10, 19), (14, 19), (16, 17), (21, 17)], 1.4)
    elif name == "update":
        c.arc((4, 4, 20, 20), 195, 355, 1.9); c.arc((4, 4, 20, 20), 15, 175, 1.9)
        c.line([(19, 3), (20, 8), (15, 8)], 1.8); c.line([(5, 21), (4, 16), (9, 16)], 1.8)
    else:
        raise ValueError(name)
    # Premultiplied downsampling keeps the edges the icon colour instead of
    # blending them with the transparent black pixels around them.
    return c.image.convert("RGBa").resize(
        (size, size), Image.Resampling.LANCZOS
    ).convert("RGBA")


def metadata():
    data = PngImagePlugin.PngInfo()
    data.add_text("Title", "PayPamin Flow")
    data.add_text("Author", APP_AUTHOR)
    data.add_text("Copyright", APP_COPYRIGHT)
    return data


def main(output_dir: Path | None = None):
    target = Path(output_dir) if output_dir else ASSETS
    target.mkdir(parents=True, exist_ok=True)
    ui_target = target / "icons" if output_dir else UI_ASSETS
    data = metadata()
    icons = {}
    for size in (16, 24, 32, 40, 48, 64, 128, 256, 512, 1024):
        icons[size] = create_icon(size)

    for size in (16, 32, 48, 256, 512):
        icons[size].save(target / f"paypamin_flow_{size}.png", pnginfo=data, optimize=True)
    icons[256].save(target / "paypamin_flow.png", pnginfo=data, optimize=True)

    # One high-resolution lockup for HiDPI and previews, plus the small header
    # version. Both keep the artwork's own proportions.
    create_horizontal_logo(1024).save(
        target / "paypamin_logo_1024.png", pnginfo=data, optimize=True,
    )
    create_horizontal_logo(256).save(
        target / "paypamin_logo.png", pnginfo=data, optimize=True,
    )

    print_target = (target / "print") if output_dir else PRINT_ASSETS
    print_target.mkdir(parents=True, exist_ok=True)
    for name, mono in (("paypamin_logo_print.png", False), ("paypamin_logo_print_mono.png", True)):
        save_print_logo(print_target / name, width=2400, mono=mono, data=data)
    save_print_pdf(print_target / "paypamin_logo_print.pdf", mono=False)
    save_print_pdf(print_target / "paypamin_logo_print_mono.pdf", mono=True)

    # Windows: every size Windows may request, small sizes from the simple mark.
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons[256].save(
        target / "paypamin_flow.ico", format="ICO", sizes=ico_sizes, append_images=[
            icons[16], icons[24], icons[32], icons[48], icons[64], icons[128],
        ],
    )
    # macOS: the full icon ladder incl. @2x for Retina.
    icons[512].save(
        target / "paypamin_flow.icns", format="ICNS",
        sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
    )

    ui_target.mkdir(parents=True, exist_ok=True)
    for name in ACTION_ICONS:
        # The same navy as the brand ink keeps menus and buttons crisp instead
        # of a washed-out grey on the light background.
        draw_action_icon(name, "#0B2447").save(ui_target / f"{name}.png", pnginfo=data, optimize=True)
        draw_action_icon(name, "#FFFFFF").save(ui_target / f"{name}_light.png", pnginfo=data, optimize=True)
    print(f"Generated product branding from vector masters and {len(ACTION_ICONS) * 2} UI icons in {target}")


if __name__ == "__main__":
    main()
