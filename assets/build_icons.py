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


def document_points():
    points = [(150, 84), (324, 84), (394, 154), (394, 388)]
    points += cubic(points[-1], (394, 406), (380, 420), (362, 420))
    points.append((150, 420))
    points += cubic(points[-1], (132, 420), (118, 406), (118, 388))
    points.append((118, 116))
    points += cubic(points[-1], (118, 98), (132, 84), (150, 84))
    return points


def p_points(outer=True):
    if outer:
        points = [(184, 166), (260, 166)]
        points += cubic(points[-1], (316, 166), (350, 194), (350, 241))
        points += cubic(points[-1], (350, 289), (316, 317), (260, 317))
        points += [(230, 317), (230, 378), (184, 378)]
    else:
        points = [(230, 205), (256, 205)]
        points += cubic(points[-1], (286, 205), (303, 217), (303, 241))
        points += cubic(points[-1], (303, 265), (286, 278), (256, 278))
        points += [(230, 278)]
    return points


def mix(start, end, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def create_icon():
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gradient = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(gradient)
    for y in range(CANVAS):
        color = mix((20, 42, 73), (39, 95, 145), y / (CANVAS - 1))
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
    ImageDraw.Draw(flow).line(scaled(flow_points), fill=(143, 184, 213, 36), width=22 * SCALE, joint="curve")
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

    p_mask = Image.new("L", image.size)
    p_draw = ImageDraw.Draw(p_mask)
    p_draw.polygon(scaled(p_points(True)), fill=255)
    p_draw.polygon(scaled(p_points(False)), fill=0)
    p_layer = Image.new("RGBA", image.size, "#214F7D")
    p_layer.putalpha(p_mask)
    image = Image.alpha_composite(image, p_layer)

    draw = ImageDraw.Draw(image)
    draw.ellipse((*point(278, 278), *point(442, 442)), fill="#FFFFFF")
    success_mask = Image.new("L", image.size)
    ImageDraw.Draw(success_mask).ellipse((*point(290, 290), *point(430, 430)), fill=255)
    success = Image.new("RGBA", image.size)
    success_draw = ImageDraw.Draw(success)
    for y in range(290 * SCALE, 431 * SCALE):
        amount = (y / SCALE - 290) / 140
        success_draw.line((0, y, CANVAS, y), fill=(*mix((66, 207, 178), (27, 158, 131), amount), 255))
    image.paste(success, (0, 0), success_mask)
    draw = ImageDraw.Draw(image)
    draw.line(scaled([(326, 360), (351, 385), (397, 333)]), fill="#FFFFFF", width=18 * SCALE, joint="curve")
    for x, y in ((326, 360), (397, 333)):
        draw.ellipse((*point(x - 9, y - 9), *point(x + 9, y + 9)), fill="#FFFFFF")

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
