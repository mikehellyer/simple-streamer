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

# Matches the teal/amber "tuning dial" palette from the UI concept review.
TEAL = (37, 126, 114, 255)
TEAL_DARK = (20, 90, 82, 255)
CREAM = (238, 241, 240, 255)
AMBER = (201, 106, 47, 255)


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

    # Dial face.
    face_r = SIZE * 0.30
    cx = cy = SIZE / 2
    draw.ellipse([cx - face_r, cy - face_r, cx + face_r, cy + face_r], fill=CREAM)
    draw.ellipse(
        [cx - face_r, cy - face_r, cx + face_r, cy + face_r],
        outline=TEAL_DARK,
        width=int(SIZE * 0.012),
    )

    # Tuning needle, angled like a dial mid-sweep.
    import math

    needle_len = face_r * 0.82
    angle = math.radians(-35)
    tip = (cx + needle_len * math.cos(angle), cy + needle_len * math.sin(angle))
    draw.line([(cx, cy), tip], fill=AMBER, width=int(SIZE * 0.028))
    hub_r = SIZE * 0.022
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r], fill=AMBER)

    # Preset tick marks around the dial rim.
    for i in range(10):
        tick_angle = math.radians(-90 + i * 36)
        inner = face_r * 0.86
        outer = face_r * 0.98
        x1, y1 = cx + inner * math.cos(tick_angle), cy + inner * math.sin(tick_angle)
        x2, y2 = cx + outer * math.cos(tick_angle), cy + outer * math.sin(tick_angle)
        draw.line([(x1, y1), (x2, y2)], fill=TEAL_DARK, width=int(SIZE * 0.008))

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

    # macOS .icns via iconutil (macOS-only tool; skipped elsewhere — the
    # release workflow's macOS job regenerates it from icon.png instead).
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
