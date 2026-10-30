#!/usr/bin/env python3
"""Generate PayPamin Flow's raster and native icons with Pillow.

Run from the repository root:
    python assets/build_icons.py

The editable vector original is assets/paypamin_flow.svg.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import APP_AUTHOR, APP_COPYRIGHT

ASSETS = Path(__file__).resolve().parent
SCALE = 3
SIZE = 512
CANVAS = SIZE * SCALE


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
    """Draw a line with round caps at the source resolution."""
    points = scaled(points)
    draw.line(points, fill=fill, width=width * SCALE, joint="curve")
    radius = width * SCALE / 2
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def document_points():
    points = [(150, 84), (324, 84), (394, 154), (394, 388)]
    points += cubic(points[-1], (394, 406), (380, 420), (362, 420))
    points.append((150, 420))
    points += cubic(points[-1], (132, 420), (118, 406), (118, 388))
    points.append((118, 116))
    points += cubic(points[-1], (118, 98), (132, 84), (150, 84))
    return points


def mix(start, end, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def create_icon():
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gradient = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(gradient)
    for y in range(CANVAS):
        color = mix((16, 42, 67), (23, 107, 135), y / (CANVAS - 1))
        draw.line((0, y, CANVAS, y), fill=(*color, 255))
    background_mask = Image.new("L", image.size)
    ImageDraw.Draw(background_mask).rounded_rectangle(
        (*point(16, 16), *point(496, 496)), radius=112 * SCALE, fill=255
    )
    image.paste(gradient, (0, 0), background_mask)

    flow = Image.new("RGBA", image.size)
    flow_points = [(60, 375)]
    flow_points += cubic(flow_points[-1], (142, 443), (234, 459), (327, 433), 48)
    flow_points += cubic(flow_points[-1], (387, 416), (430, 382), (458, 338), 32)
    rounded_line(ImageDraw.Draw(flow), flow_points, fill=(158, 212, 223, 40), width=22)
    image = Image.alpha_composite(image, flow)

    doc_points = scaled(document_points())
    shadow_mask = Image.new("L", image.size)
    ImageDraw.Draw(shadow_mask).polygon([(x, y + 14 * SCALE) for x, y in doc_points], fill=72)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(14 * SCALE))
    shadow = Image.new("RGBA", image.size, (7, 24, 44, 0))
    shadow.putalpha(shadow_mask)
    image = Image.alpha_composite(image, shadow)

    draw = ImageDraw.Draw(image)
    draw.polygon(doc_points, fill="#FFFFFF")
    draw.polygon(scaled([(324, 84), (324, 136), (342, 154), (394, 154)]), fill="#D9E7F1")

    rounded_line(draw, [(176, 176), (300, 176)], fill="#24557A", width=20)
    rounded_line(draw, [(176, 230), (318, 230)], fill="#9AB7CC", width=16)
    rounded_line(draw, [(176, 280), (272, 280)], fill="#9AB7CC", width=16)
    rounded_line(draw, [(176, 340), (246, 340)], fill="#159A94", width=14)
    rounded_line(draw, [(226, 320), (248, 340), (226, 360)], fill="#159A94", width=14)

    draw.ellipse((*point(278, 278), *point(442, 442)), fill="#FFFFFF")
    reminder_mask = Image.new("L", image.size)
    ImageDraw.Draw(reminder_mask).ellipse((*point(290, 290), *point(430, 430)), fill=255)
    reminder = Image.new("RGBA", image.size)
    reminder_draw = ImageDraw.Draw(reminder)
    for y in range(290 * SCALE, 431 * SCALE):
        amount = (y / SCALE - 290) / 140
        reminder_draw.line((0, y, CANVAS, y), fill=(*mix((56, 214, 192), (21, 154, 148), amount), 255))
    image.paste(reminder, (0, 0), reminder_mask)
    draw = ImageDraw.Draw(image)
    for points in (
        [(360, 306), (360, 314)],
        [(414, 360), (406, 360)],
        [(360, 414), (360, 406)],
        [(306, 360), (314, 360)],
    ):
        rounded_line(draw, points, fill="#FFFFFF", width=7)
    rounded_line(draw, [(360, 322), (360, 360), (389, 377)], fill="#FFFFFF", width=14)
    draw.ellipse((*point(352, 352), *point(368, 368)), fill="#FFFFFF")

    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main():
    icon = create_icon()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Title", "PayPamin Flow")
    metadata.add_text("Author", APP_AUTHOR)
    metadata.add_text("Copyright", APP_COPYRIGHT)
    for size in (16, 32, 48, 256, 512):
        resized = icon if size == SIZE else icon.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(ASSETS / f"paypamin_flow_{size}.png", pnginfo=metadata, optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "paypamin_flow.png", pnginfo=metadata, optimize=True)
    icon.save(ASSETS / "paypamin_flow.ico", format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ASSETS / "paypamin_flow.icns", format="ICNS", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
    print("Generated PayPamin Flow PNG, ICO and ICNS icons in", ASSETS)


if __name__ == "__main__":
    main()
