#!/usr/bin/env python3
"""Generate PayPamin Flow's product logo, desktop icons and UI icons.

Run from the repository root:
    python assets/build_icons.py

Editable vector originals are assets/paypamin_flow.svg and
assets/paypamin_logo.svg. The small UI icons use a common 24-unit grid and
are rendered at 16 px with transparent backgrounds and light variants.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, PngImagePlugin

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


def point(x: float, y: float) -> tuple[int, int]:
    return round(x * SCALE), round(y * SCALE)


def cubic(start, control1, control2, end, steps=24):
    points = []
    for index in range(1, steps + 1):
        t = index / steps
        u = 1 - t
        points.append((
            u**3 * start[0] + 3 * u**2 * t * control1[0] + 3 * u * t**2 * control2[0] + t**3 * end[0],
            u**3 * start[1] + 3 * u**2 * t * control1[1] + 3 * u * t**2 * control2[1] + t**3 * end[1],
        ))
    return points


def scaled(points):
    return [point(x, y) for x, y in points]


def rounded_line(draw, points, *, fill, width):
    points = scaled(points)
    draw.line(points, fill=fill, width=width * SCALE, joint="curve")
    radius = width * SCALE / 2
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def document_points():
    points = [(148, 64), (316, 64), (384, 132), (384, 388)]
    points += cubic(points[-1], (384, 410), (370, 424), (346, 424))
    points.append((148, 424))
    points += cubic(points[-1], (128, 424), (112, 410), (112, 388))
    points.append((112, 104))
    points += cubic(points[-1], (112, 80), (128, 64), (148, 64))
    return points


def mix(start, end, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def create_icon():
    """Create the invoice/P/check product mark at high resolution."""
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gradient = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(gradient)
    for y in range(CANVAS):
        color = mix((16, 28, 61), (31, 102, 193), y / (CANVAS - 1))
        draw.line((0, y, CANVAS, y), fill=(*color, 255))
    background_mask = Image.new("L", image.size)
    ImageDraw.Draw(background_mask).rounded_rectangle(
        (*point(16, 16), *point(496, 496)), radius=116 * SCALE, fill=255
    )
    image.paste(gradient, (0, 0), background_mask)

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((*point(270, -100), *point(600, 230)), fill=(70, 220, 210, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(48 * SCALE))
    image = Image.alpha_composite(image, glow)

    flow = Image.new("RGBA", image.size)
    flow_points = [(48, 388)]
    flow_points += cubic(flow_points[-1], (140, 462), (272, 454), (360, 394), 48)
    flow_points += cubic(flow_points[-1], (416, 358), (448, 320), (466, 274), 32)
    rounded_line(ImageDraw.Draw(flow), flow_points, fill=(133, 225, 224, 38), width=22)
    image = Image.alpha_composite(image, flow)

    # A subtle light rim keeps the product tile recognisable on dark taskbars.
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (*point(24, 24), *point(488, 488)),
        radius=108 * SCALE,
        outline=(255, 255, 255, 46),
        width=8 * SCALE,
    )

    doc_points = scaled(document_points())
    shadow_mask = Image.new("L", image.size)
    ImageDraw.Draw(shadow_mask).polygon([(x, y + 14 * SCALE) for x, y in doc_points], fill=78)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(14 * SCALE))
    shadow = Image.new("RGBA", image.size, (7, 20, 44, 0))
    shadow.putalpha(shadow_mask)
    image = Image.alpha_composite(image, shadow)

    draw = ImageDraw.Draw(image)
    draw.polygon(doc_points, fill="#FFFFFF")
    draw.polygon(scaled([(316, 64), (316, 112), (332, 132), (384, 132)]), fill="#D8E7F5")

    # Geometric P: recognisable as PayPamin even without the wordmark.
    rounded_line(draw, [(174, 148), (174, 288)], fill="#173F8F", width=24)
    bowl = [(174, 148), (238, 148)]
    bowl += cubic(bowl[-1], (272, 148), (286, 160), (286, 182), 20)
    bowl += cubic(bowl[-1], (286, 204), (272, 216), (238, 216), 20)
    bowl.append((174, 216))
    rounded_line(draw, bowl, fill="#173F8F", width=24)
    rounded_line(draw, [(174, 326), (278, 326)], fill="#7C9CBF", width=15)
    rounded_line(draw, [(174, 360), (238, 360)], fill="#7C9CBF", width=15)

    # Paid/reminder completion badge.
    draw.ellipse((*point(268, 264), *point(444, 440)), fill="#FFFFFF")
    badge_mask = Image.new("L", image.size)
    ImageDraw.Draw(badge_mask).ellipse((*point(280, 276), *point(432, 428)), fill=255)
    badge = Image.new("RGBA", image.size)
    badge_draw = ImageDraw.Draw(badge)
    for y in range(276 * SCALE, 429 * SCALE):
        amount = (y / SCALE - 276) / 152
        badge_draw.line((0, y, CANVAS, y), fill=(*mix((52, 211, 153), (15, 159, 149), amount), 255))
    image.paste(badge, (0, 0), badge_mask)
    draw = ImageDraw.Draw(image)
    rounded_line(draw, [(312, 350), (342, 380), (400, 318)], fill="#FFFFFF", width=18)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def font_path(bold=False):
    candidates = (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"),
    )
    for bold_path, regular_path in candidates:
        path = Path(bold_path if bold else regular_path)
        if path.is_file():
            return str(path)
    return None


def create_horizontal_logo(icon):
    """Create a transparent horizontal wordmark for the app header/about."""
    image = Image.new("RGBA", (576, 128), (0, 0, 0, 0))
    symbol = icon.resize((104, 104), Image.Resampling.LANCZOS)
    image.alpha_composite(symbol, (4, 12))
    draw = ImageDraw.Draw(image)
    bold = font_path(bold=True)
    regular = font_path(bold=False)
    title_font = ImageFont.truetype(bold, 48) if bold else ImageFont.load_default(size=48)
    flow_font = ImageFont.truetype(regular, 48) if regular else title_font
    draw.text((122, 64), "PayPamin", font=title_font, fill="#1D355E", anchor="lm")
    width = draw.textlength("PayPamin", font=title_font)
    draw.text((122 + width + 13, 64), "Flow", font=flow_font, fill="#11998F", anchor="lm")
    return image.crop((0, 0, 512, 128)).resize((256, 64), Image.Resampling.LANCZOS)


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


def draw_action_icon(name, color):
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
    return c.image.resize((16, 16), Image.Resampling.LANCZOS)


def metadata():
    data = PngImagePlugin.PngInfo()
    data.add_text("Title", "PayPamin Flow")
    data.add_text("Author", APP_AUTHOR)
    data.add_text("Copyright", APP_COPYRIGHT)
    return data


def main():
    icon = create_icon()
    data = metadata()
    for size in (16, 32, 48, 256, 512):
        resized = icon if size == SIZE else icon.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(ASSETS / f"paypamin_flow_{size}.png", pnginfo=data, optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "paypamin_flow.png", pnginfo=data, optimize=True)
    create_horizontal_logo(icon).save(ASSETS / "paypamin_logo.png", pnginfo=data, optimize=True)
    icon.save(ASSETS / "paypamin_flow.ico", format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ASSETS / "paypamin_flow.icns", format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
    UI_ASSETS.mkdir(exist_ok=True)
    for name in ACTION_ICONS:
        draw_action_icon(name, "#344054").save(UI_ASSETS / f"{name}.png", pnginfo=data, optimize=True)
        draw_action_icon(name, "#FFFFFF").save(UI_ASSETS / f"{name}_light.png", pnginfo=data, optimize=True)
    print(f"Generated product branding and {len(ACTION_ICONS) * 2} UI icons in {ASSETS}")


if __name__ == "__main__":
    main()
