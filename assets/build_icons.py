#!/usr/bin/env python3
"""Generate PayPamin Flow's desktop icons and UI icons from the vector masters.

Run from the repository root:
    python assets/build_icons.py

The vector files are the single source of truth:

* ``assets/paypamin_flow.svg``       – product mark, detail version (40 px and up)
* ``assets/paypamin_flow_small.svg`` – simplified mark for 24–40 px
* ``assets/paypamin_flow_tiny.svg``  – smallest mark for 16–24 px, without the tick
* ``assets/paypamin_logo.svg``       – light-theme screen lockup (wordmark as outlines)
* ``assets/paypamin_logo_dark.svg``  – dark-theme screen lockup (wordmark as outlines)
* ``assets/print/paypamin_logo_print.svg`` – editable flat print lockup
* ``assets/print/paypamin_logo_print_mono.svg`` – editable one-colour print lockup
* ``assets/print/*.pdf`` – vector PDFs at 90 mm width for a print shop

Every PNG, ICO and ICNS file is rasterised from those files, so a change to
the artwork only has to be made once. The UI action icons use a crisp 24-unit
vector grid with two-tone brand ink on light surfaces and pure white on dark
surfaces, rendered at both 16 px and 64 px (@4x HiDPI) with premultiplied RGBa
resampling so every DPI scale stays razor-sharp.
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
UI_HIDPI_ASSETS = UI_ASSETS / "hidpi"
SCALE = 3
SIZE = 512
CANVAS = SIZE * SCALE

ACTION_ICONS = (
    "add", "backup", "cache", "clear", "close", "csv", "customer", "delete",
    "edit", "email", "error", "external", "folder", "folder_export",
    "folder_import", "heart", "help", "ignore", "info", "journal", "ledger",
    "log", "next", "paid", "pdf_add", "power", "print", "reminder", "restore",
    "save", "scan", "sent", "settings", "technical", "trash", "tray", "update",
)


PRINT_ASSETS = ASSETS / "print"

SVG_SOURCES = {
    "icon": ASSETS / "paypamin_flow.svg",
    "icon_small": ASSETS / "paypamin_flow_small.svg",
    "icon_tiny": ASSETS / "paypamin_flow_tiny.svg",
    "logo": ASSETS / "paypamin_logo.svg",
    "logo_dark": ASSETS / "paypamin_logo_dark.svg",
    "logo_print": PRINT_ASSETS / "paypamin_logo_print.svg",
    "logo_print_mono": PRINT_ASSETS / "paypamin_logo_print_mono.svg",
}

PRINT_WIDTH_MM = 90
PRINT_MARGIN_MM = 4
MM_TO_POINT = 72 / 25.4

SMALL_ICON_LIMIT = 40
TINY_ICON_LIMIT = 24
RASTER_OVERSAMPLE = 4
UI_ICON_SIZE = 16
UI_ICON_HIDPI_SIZE = 64


def rasterise_svg(path: Path, width: int, height: int | None = None) -> Image.Image:
    """Render an SVG file to a PIL image at the requested pixel size."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
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
        with pymupdf.open(str(pdf_path)) as document:
            page = document[0]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=True)
            raw = pixmap.samples
            mode = "RGBa" if pixmap.alpha else "RGB"
            image = Image.frombytes(mode, (pixmap.width, pixmap.height), raw)
    if image.mode != "RGBa":
        return image.resize((width, height), Image.Resampling.LANCZOS)
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


LOGO_ASPECT = 788.33 / 132


def logo_height(width: int) -> int:
    """Return the exact proportional height for a lockup of ``width`` pixels."""
    return max(1, round(width / LOGO_ASPECT))


def create_horizontal_logo(width: int = 512, *, dark: bool = False) -> Image.Image:
    """Return the screen lockup with the outlined wordmark."""
    key = "logo_dark" if dark else "logo"
    return rasterise_svg(SVG_SOURCES[key], width, logo_height(width))


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
    """Write a vector PDF at a real print size for a commercial printer."""
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
    """Supersampled 24 x 24 vector-grid renderer with two-tone brand accents."""

    def __init__(self, color: str, accent: str | None = None):
        self.scale = 8
        self.image = Image.new("RGBA", (24 * self.scale, 24 * self.scale), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.color = color
        self.accent = accent or color

    def pt(self, x, y):
        return round(x * self.scale), round(y * self.scale)

    def box(self, values):
        return tuple(round(value * self.scale) for value in values)

    def line(self, points, width=2.0, accent=False):
        ink = self.accent if accent else self.color
        pts = [self.pt(x, y) for x, y in points]
        self.draw.line(pts, fill=ink, width=round(width * self.scale), joint="curve")
        radius = width * self.scale / 2
        for x, y in pts:
            self.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=ink)

    def rect(self, values, radius=0, width=1.9, accent=False, fill=False):
        ink = self.accent if accent else self.color
        box = self.box(values)
        if radius:
            self.draw.rounded_rectangle(
                box,
                radius=round(radius * self.scale),
                fill=ink if fill else None,
                outline=None if fill else ink,
                width=round(width * self.scale),
            )
        else:
            self.draw.rectangle(
                box,
                fill=ink if fill else None,
                outline=None if fill else ink,
                width=round(width * self.scale),
            )

    def ellipse(self, values, width=1.9, fill=False, accent=False):
        ink = self.accent if accent else self.color
        self.draw.ellipse(
            self.box(values),
            fill=ink if fill else None,
            outline=None if fill else ink,
            width=round(width * self.scale),
        )

    def polygon(self, points, fill=False, width=1.9, accent=False):
        ink = self.accent if accent else self.color
        pts = [self.pt(x, y) for x, y in points]
        if fill:
            self.draw.polygon(pts, fill=ink)
        else:
            self.line(list(points) + [points[0]], width=width, accent=accent)

    def arc(self, values, start, end, width=2.0, accent=False):
        ink = self.accent if accent else self.color
        self.draw.arc(
            self.box(values), start=start, end=end, fill=ink, width=round(width * self.scale)
        )


def folder_shape(canvas: IconCanvas):
    canvas.line([(2.5, 6), (9.5, 6), (11.8, 8.5), (21.5, 8.5), (21.5, 19.8), (2.5, 19.8), (2.5, 6)], 1.9)


def check_shape(canvas: IconCanvas, points=((6.8, 12.4), (10.3, 16.0), (17.6, 8.0)), width=2.2, accent=True):
    canvas.line(list(points), width, accent=accent)


def draw_action_icon(name: str, color: str, size: int = UI_ICON_SIZE, accent: str | None = None) -> Image.Image:
    """Draw one sharp action glyph on the 24 x 24 grid and reduce it to ``size``."""
    c = IconCanvas(color, accent=accent)
    if name == "add":
        c.ellipse((2.5, 2.5, 21.5, 21.5), 1.8)
        c.line([(12, 7), (12, 17)], 2.2, accent=True)
        c.line([(7, 12), (17, 12)], 2.2, accent=True)
    elif name == "backup":
        c.rect((2.5, 8, 21.5, 21), 2.0, 1.9)
        c.line([(2.5, 12), (21.5, 12)], 1.6)
        c.line([(12, 2.5), (12, 16.5)], 2.1, accent=True)
        c.line([(8.6, 13.1), (12, 16.5), (15.4, 13.1)], 2.1, accent=True)
    elif name == "cache":
        c.line([(5, 3.5), (15.5, 14)], 2.3)
        c.polygon([(12, 12), (21, 14.2), (18.8, 21.5), (9, 18)], width=1.9, accent=True)
        c.line([(12.5, 16), (17.8, 17.8)], 1.5, accent=True)
    elif name == "clear":
        c.polygon([(8.6, 5.6), (20.8, 5.6), (20.8, 18.4), (8.6, 18.4), (3.2, 12.0)], width=1.9)
        c.line([(11.6, 9.3), (17.0, 14.7)], 1.9, accent=True)
        c.line([(17.0, 9.3), (11.6, 14.7)], 1.9, accent=True)
    elif name == "close":
        c.line([(5.5, 5.5), (18.5, 18.5)], 2.3)
        c.line([(18.5, 5.5), (5.5, 18.5)], 2.3)
    elif name == "csv":
        c.rect((3.5, 2.5, 20.5, 21.5), 2.0, 1.9)
        c.line([(3.5, 8.5), (20.5, 8.5)], 1.6)
        c.line([(9.5, 8.5), (9.5, 21.5)], 1.5)
        c.line([(14.8, 12.2), (14.8, 18.2)], 2.0, accent=True)
        c.line([(12.4, 15.8), (14.8, 18.2), (17.2, 15.8)], 2.0, accent=True)
    elif name == "customer":
        c.ellipse((7.8, 3.0, 16.2, 11.4), 1.9, accent=True)
        c.arc((3.2, 11.8, 20.8, 23.8), 185, 355, 2.1)
    elif name == "delete":
        c.line([(4, 6), (20, 6)], 2.0)
        c.line([(9, 3), (15, 3), (16, 6)], 1.8)
        c.line([(6.2, 6), (7.2, 21), (16.8, 21), (17.8, 6)], 1.9)
        c.line([(10.2, 10), (10.5, 17)], 1.6, accent=True)
        c.line([(13.8, 10), (13.5, 17)], 1.6, accent=True)
    elif name == "edit":
        c.polygon([(4, 16.5), (5.2, 11.8), (15.8, 2.8), (20.2, 7.2), (9.2, 18.2)], width=1.9)
        c.line([(13.5, 5.2), (17.8, 9.5)], 1.7, accent=True)
        c.line([(3.5, 21.2), (20.5, 21.2)], 1.8, accent=True)
    elif name == "email":
        c.rect((2.5, 5, 21.5, 19), 2.0, 1.9)
        c.line([(3.5, 6.5), (12, 13.2), (20.5, 6.5)], 1.9, accent=True)
    elif name == "error":
        c.polygon([(12, 2.8), (22, 20.5), (2, 20.5)], width=2.0)
        c.line([(12, 8.5), (12, 14.2)], 2.2, accent=True)
        c.ellipse((10.9, 16.4, 13.1, 18.6), fill=True, accent=True)
    elif name == "external":
        c.line([(10, 4.2), (4, 4.2), (4, 20), (19.8, 20), (19.8, 14)], 1.9)
        c.line([(13.2, 3.2), (20.8, 3.2), (20.8, 10.8)], 2.0, accent=True)
        c.line([(11, 13), (20.5, 3.5)], 2.0, accent=True)
    elif name == "folder":
        folder_shape(c)
    elif name == "folder_import":
        folder_shape(c)
        c.line([(12, 10.2), (12, 17.2)], 1.9, accent=True)
        c.line([(9.2, 14.4), (12, 17.2), (14.8, 14.4)], 1.9, accent=True)
    elif name == "folder_export":
        folder_shape(c)
        c.line([(12, 17.2), (12, 10.2)], 1.9, accent=True)
        c.line([(9.2, 13.0), (12, 10.2), (14.8, 13.0)], 1.9, accent=True)
    elif name == "heart":
        pts = []
        for step in range(65):
            t = 2 * math.pi * step / 64
            hx = 12.0 + 8.2 * (math.sin(t) ** 3)
            hy = 12.8 - (
                6.6 * math.cos(t)
                - 2.6 * math.cos(2 * t)
                - 1.0 * math.cos(3 * t)
                - 0.3 * math.cos(4 * t)
            )
            pts.append((hx, hy))
        c.line(pts, 2.0, accent=True)
    elif name == "help":
        c.ellipse((2.8, 2.8, 21.2, 21.2), 1.9)
        c.arc((8.8, 6.2, 15.2, 12.2), 190, 45, 2.0, accent=True)
        c.line([(13.8, 11.2), (12, 13.0), (12, 14.4)], 2.0, accent=True)
        c.ellipse((10.9, 16.5, 13.1, 18.7), fill=True, accent=True)
    elif name == "ignore":
        c.line([(2.2, 12), (6.2, 7.6), (12, 5.8), (17.8, 7.6), (21.8, 12), (17.8, 16.4), (12, 18.2), (6.2, 16.4), (2.2, 12)], 1.7)
        c.ellipse((9.2, 9.2, 14.8, 14.8), 1.7)
        c.line([(3.5, 20.5), (20.5, 3.5)], 2.2, accent=True)
    elif name == "info":
        c.ellipse((2.8, 2.8, 21.2, 21.2), 1.9)
        c.line([(12, 10.2), (12, 17.2)], 2.2, accent=True)
        c.ellipse((10.9, 5.8, 13.1, 8.0), fill=True, accent=True)
    elif name == "journal":
        c.rect((4, 2.5, 19.5, 21.5), 1.8, 1.9)
        c.line([(8, 7), (15.8, 7)], 1.6)
        c.line([(8, 11), (15.8, 11)], 1.6)
        c.line([(8, 16), (15.2, 16)], 1.8, accent=True)
        c.line([(12.6, 13.6), (15.2, 16), (12.6, 18.4)], 1.8, accent=True)
    elif name == "ledger":
        c.rect((2.5, 4, 21.5, 20), 1.8, 1.9)
        c.line([(2.5, 9.2), (21.5, 9.2)], 1.6, accent=True)
        c.line([(2.5, 14.6), (21.5, 14.6)], 1.5)
        c.line([(9, 4), (9, 20)], 1.5)
        c.line([(15.8, 4), (15.8, 20)], 1.5)
    elif name == "log":
        c.rect((4, 2.5, 20, 21.5), 1.8, 1.9)
        c.line([(8, 7.2), (16, 7.2)], 1.7, accent=True)
        c.line([(8, 11.6), (16, 11.6)], 1.6)
        c.line([(8, 16.0), (13.8, 16.0)], 1.6)
    elif name == "next":
        c.line([(3.5, 12), (20, 12)], 2.2, accent=True)
        c.line([(14, 6), (20, 12), (14, 18)], 2.2)
    elif name == "paid":
        c.ellipse((2.8, 2.8, 21.2, 21.2), 1.9)
        check_shape(c)
    elif name == "pdf_add":
        c.line([(4.2, 21), (4.2, 3), (14.8, 3), (19.8, 8), (19.8, 21), (4.2, 21)], 1.9)
        c.line([(14.8, 3), (14.8, 8), (19.8, 8)], 1.6)
        c.line([(12, 10.5), (12, 17.5)], 2.0, accent=True)
        c.line([(8.5, 14), (15.5, 14)], 2.0, accent=True)
    elif name == "power":
        c.arc((4.8, 5.2, 19.2, 19.8), 130, 410, 2.1)
        c.line([(12, 2.6), (12, 11.2)], 2.3, accent=True)
    elif name == "print":
        c.rect((6.5, 3, 17.5, 8.5), 1.0, 1.7)
        c.rect((3, 8.5, 21, 16.8), 2.0, 1.9)
        c.rect((6.5, 14, 17.5, 21), 1.0, 1.8, accent=True)
        c.ellipse((16.8, 10.8, 18.6, 12.6), fill=True, accent=True)
    elif name == "reminder":
        c.line([(4.2, 17), (6.5, 14), (6.5, 9.2), (8.6, 5.2), (12, 4), (15.4, 5.2), (17.5, 9.2), (17.5, 14), (19.8, 17), (4.2, 17)], 1.9)
        c.arc((9.2, 17.2, 14.8, 22.4), 0, 180, 2.0, accent=True)
    elif name == "restore":
        c.arc((4, 4, 20.5, 20.5), 40, 325, 2.1)
        c.line([(4, 3.2), (4, 9.2), (10, 9.2)], 2.1, accent=True)
    elif name == "save":
        c.rect((3.2, 3.2, 20.8, 20.8), 2.0, 1.9)
        c.rect((7.2, 3.2, 16.8, 9.2), 0, 1.6)
        c.rect((6.8, 13.8, 17.2, 20.8), 1.0, 1.7, accent=True)
    elif name == "scan":
        c.ellipse((3.2, 3.2, 15.6, 15.6), 2.1)
        c.line([(14.4, 14.4), (20.8, 20.8)], 2.5, accent=True)
        c.line([(6.8, 9.4), (12.0, 9.4)], 1.7, accent=True)
    elif name == "sent":
        c.polygon([(2.5, 4.2), (21.5, 11.2), (3.2, 20.5), (7.2, 12.8), (15.8, 11.2), (7.2, 9.8)], width=1.9)
        c.line([(7.2, 12.8), (15.8, 11.2)], 1.8, accent=True)
    elif name == "settings":
        c.ellipse((8.4, 8.4, 15.6, 15.6), 2.0, accent=True)
        c.ellipse((5.0, 5.0, 19.0, 19.0), 2.0)
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            c.line([(12 + 7.0 * math.cos(a), 12 + 7.0 * math.sin(a)), (12 + 9.4 * math.cos(a), 12 + 9.4 * math.sin(a))], 2.6)
    elif name == "technical":
        for idx, (y, x) in enumerate(((5.5, 8.5), (12.0, 15.5), (18.5, 10.0))):
            c.line([(3.2, y), (20.8, y)], 1.7)
            c.ellipse((x - 2.2, y - 2.2, x + 2.2, y + 2.2), 1.8, accent=(idx == 1))
    elif name == "trash":
        c.rect((4.5, 6.5, 19.5, 20.8), 2.0, 1.9)
        c.line([(3, 6.5), (21, 6.5)], 2.0)
        c.line([(9, 3.5), (15, 3.5)], 2.0)
        c.arc((8.8, 10.2, 15.2, 16.6), 45, 320, 1.7, accent=True)
        c.line([(14.8, 9.4), (15.0, 12.2), (12.4, 11.8)], 1.6, accent=True)
    elif name == "tray":
        c.line([(12, 2.8), (12, 14.2)], 2.1, accent=True)
        c.line([(8.5, 10.7), (12, 14.2), (15.5, 10.7)], 2.1, accent=True)
        c.line([(3.2, 14.2), (3.2, 20.2), (20.8, 20.2), (20.8, 14.2)], 1.9)
    elif name == "update":
        c.arc((4, 4, 20, 20), 200, 345, 2.1)
        c.arc((4, 4, 20, 20), 20, 165, 2.1, accent=True)
        c.line([(19.5, 5.4), (19.8, 9.9), (15.3, 9.5)], 2.0)
        c.line([(4.5, 18.6), (4.2, 14.1), (8.7, 14.5)], 2.0, accent=True)
    else:
        raise ValueError(name)
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
    ui_hidpi_target = ui_target / "hidpi"
    data = metadata()
    icons = {}
    for size in (16, 24, 32, 40, 48, 64, 128, 256, 512, 1024):
        icons[size] = create_icon(size)

    for size in (16, 32, 48, 256, 512):
        icons[size].save(target / f"paypamin_flow_{size}.png", pnginfo=data, optimize=True)
    icons[256].save(target / "paypamin_flow.png", pnginfo=data, optimize=True)

    # Light-surface and dark-surface horizontal lockups for HiDPI headers and dialogs.
    create_horizontal_logo(1024, dark=False).save(
        target / "paypamin_logo_1024.png", pnginfo=data, optimize=True,
    )
    create_horizontal_logo(256, dark=False).save(
        target / "paypamin_logo.png", pnginfo=data, optimize=True,
    )
    create_horizontal_logo(1024, dark=True).save(
        target / "paypamin_logo_dark_1024.png", pnginfo=data, optimize=True,
    )
    create_horizontal_logo(256, dark=True).save(
        target / "paypamin_logo_dark.png", pnginfo=data, optimize=True,
    )

    print_target = (target / "print") if output_dir else PRINT_ASSETS
    print_target.mkdir(parents=True, exist_ok=True)
    for name, mono in (("paypamin_logo_print.png", False), ("paypamin_logo_print_mono.png", True)):
        save_print_logo(print_target / name, width=2400, mono=mono, data=data)
    save_print_pdf(print_target / "paypamin_logo_print.pdf", mono=False)
    save_print_pdf(print_target / "paypamin_logo_print_mono.pdf", mono=True)

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons[256].save(
        target / "paypamin_flow.ico", format="ICO", sizes=ico_sizes, append_images=[
            icons[16], icons[24], icons[32], icons[48], icons[64], icons[128],
        ],
    )
    icons[512].save(
        target / "paypamin_flow.icns", format="ICNS",
        sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
    )

    ui_target.mkdir(parents=True, exist_ok=True)
    ui_hidpi_target.mkdir(parents=True, exist_ok=True)
    for name in ACTION_ICONS:
        draw_action_icon(name, "#0B2447", size=UI_ICON_SIZE, accent="#0E8C82").save(
            ui_target / f"{name}.png", pnginfo=data, optimize=True,
        )
        draw_action_icon(name, "#FFFFFF", size=UI_ICON_SIZE, accent="#FFFFFF").save(
            ui_target / f"{name}_light.png", pnginfo=data, optimize=True,
        )
        draw_action_icon(name, "#0B2447", size=UI_ICON_HIDPI_SIZE, accent="#0E8C82").save(
            ui_hidpi_target / f"{name}.png", pnginfo=data, optimize=True,
        )
        draw_action_icon(name, "#FFFFFF", size=UI_ICON_HIDPI_SIZE, accent="#FFFFFF").save(
            ui_hidpi_target / f"{name}_light.png", pnginfo=data, optimize=True,
        )
    print(
        f"Generated product branding from vector masters and "
        f"{len(ACTION_ICONS) * 2} UI icons (+ @4x HiDPI masters) in {target}"
    )


if __name__ == "__main__":
    main()
