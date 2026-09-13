"""One-off script: draws the Simple-Streamer app icon and exports every
size/format the platform installers need. Not part of the app itself and
not run automatically — re-run manually if the icon design ever changes.

Usage: venv/bin/python packaging/icons/generate_icon.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent
SIZE = 1024

# "Headphone World" — chosen from the icon concept review as the mark that
# best reads as radio + international streaming (vs. the original plain
# tuning-dial icon).
TEAL = (37, 126, 114, 255)
CREAM = (238, 241, 240, 255)
AMBER = (222, 140, 60, 255)


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = SIZE * 0.06

    # Rounded-square backplate, like the other app icons it'll sit beside.
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=SIZE * 0.22,
        fill=TEAL,
    )

    cx, cy = SIZE / 2, SIZE * 0.56
    r = SIZE * 0.24
    globe_width = int(SIZE * 0.014)

    # Globe: outline + equator + one meridian.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CREAM, width=globe_width)
    draw.ellipse([cx - r, cy - r * 0.32, cx + r, cy + r * 0.32], outline=CREAM, width=globe_width)
    rx = r * 0.42
    draw.ellipse([cx - rx, cy - r, cx + rx, cy + r], outline=CREAM, width=globe_width)

    # Headphone band arcing over the top, with two ear cups.
    band_r = r * 1.28
    draw.arc(
        [cx - band_r, cy - band_r * 1.05, cx + band_r, cy + band_r * 0.55],
        start=195,
        end=345,
        fill=AMBER,
        width=int(SIZE * 0.032),
    )
    cup_w, cup_h = SIZE * 0.075, SIZE * 0.11
    for side in (-1, 1):
        ex = cx + side * band_r * 0.98
        ey = cy - band_r * 0.05
        draw.rounded_rectangle(
            [ex - cup_w / 2, ey - cup_h / 2, ex + cup_w / 2, ey + cup_h / 2],
            radius=cup_w * 0.4,
            fill=AMBER,
        )

    return img


def main() -> None:
    icon = draw_icon()
    master_png = OUT_DIR / "icon.png"
    icon.save(master_png)
    print(f"wrote {master_png}")

    # Windows .ico (multi-resolution)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = OUT_DIR / "icon.ico"
    icon.save(ico_path, sizes=[(s, s) for s in ico_sizes])
    print(f"wrote {ico_path}")

    # Linux: a few common hicolor sizes as plain PNGs.
    for s in (16, 32, 48, 64, 128, 256, 512):
        icon.resize((s, s), Image.LANCZOS).save(OUT_DIR / f"icon_{s}.png")
    print("wrote icon_16..512.png")

    # macOS .icns via iconutil (macOS-only tool). The generated file is
    # committed alongside the others, so this only needs re-running on a
    # Mac when the icon design changes — CI just uses the committed file.
    if sys.platform == "darwin":
        iconset = OUT_DIR / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            icon.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            icon.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_DIR / "icon.icns")],
            check=True,
        )
        print(f"wrote {OUT_DIR / 'icon.icns'}")
        for f in iconset.iterdir():
            f.unlink()
        iconset.rmdir()


if __name__ == "__main__":
    main()
