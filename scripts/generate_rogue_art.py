"""
generate_rogue_art.py — Star Raise
Procedural PIL art for the "Rogue AI" faction.

Generates a massive, glowing red mechanical core for the Rogue HQ building:
  assets/buildings/rogue_hq.png   (128×128)

Visual language
---------------
Hard geometry (hex / square panels, inset ring, bolts), cold metallic greys and
blacks, with a violent red optic heart pulsing at the centre.  Read at a glance:
this is a sentient machine, not a biological nest.
"""

import math
import os
import random

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "--break-system-packages", "-q"])
    from PIL import Image, ImageDraw, ImageFilter

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_SCRIPT_DIR)
_BLDG_DIR   = os.path.join(_ROOT, "assets", "buildings")
os.makedirs(_BLDG_DIR, exist_ok=True)

rng = random.Random(0xA1C0DE00)

# ── Palette ───────────────────────────────────────────────────────────────────
_VOID         = (6,   4,   8, 255)
_STEEL_DARK   = (32,  30,  38, 255)
_STEEL_MID    = (62,  60,  72, 255)
_STEEL_LIGHT  = (120, 122, 138, 255)
_STEEL_PLATE  = (90,  90, 104, 255)
_BOLT         = (180, 184, 200, 255)
_RED_DEEP     = (100,  10,  18, 255)
_RED_MID      = (200,  30,  46, 255)
_RED_HOT      = (255,  70,  70, 255)
_RED_WHITE    = (255, 220, 210, 255)
_AMBER        = (255, 170,  60, 255)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _radial_gradient(draw, cx, cy, r_outer, r_inner, col_out, col_in, steps=40):
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(r_inner + (r_outer - r_inner) * t)
        col = _lerp(col_in, col_out, t)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)


def make_rogue_hq():
    """
    128×128 massive glowing red mechanical core.

    Layout (read from outside in):
      1. Dark hex chassis base
      2. Circular armoured ring with 8 bolts
      3. Inner hex trench (cooler gradient)
      4. Glowing red optic lens with radial gradient + crosshair iris
      5. Scanning vanes / chevrons around the lens
      6. Subtle bloom halo
    """
    S = 128
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, S // 2

    # 1 ── Dark hex chassis (rotated square = diamond, then crop with ellipse feel)
    # Use a hexagonal silhouette
    hex_r = 60
    hex_pts = [
        (cx + hex_r * math.cos(math.radians(60 * i - 30)),
         cy + hex_r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    draw.polygon(hex_pts, fill=_STEEL_DARK)

    # Thin chassis edge highlight
    draw.polygon(hex_pts, outline=_STEEL_LIGHT)
    for i in range(6):
        a = hex_pts[i]
        b = hex_pts[(i + 1) % 6]
        draw.line([a, b], fill=_STEEL_LIGHT, width=1)

    # 2 ── Armoured ring (annulus)
    outer_r = 54
    inner_r = 40
    draw.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
                 fill=_STEEL_PLATE)
    draw.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
                 outline=_STEEL_LIGHT, width=2)

    # 8 bolts evenly spaced on the ring (at mid-radius)
    bolt_r    = 3
    ring_mid  = (outer_r + inner_r) / 2
    for i in range(8):
        a = math.radians(i * 45)
        bx = cx + ring_mid * math.cos(a)
        by = cy + ring_mid * math.sin(a)
        draw.ellipse((bx - bolt_r, by - bolt_r, bx + bolt_r, by + bolt_r),
                     fill=_BOLT)
        draw.ellipse((bx - bolt_r + 1, by - bolt_r + 1,
                      bx + bolt_r - 1, by + bolt_r - 1), fill=_STEEL_MID)

    # 3 ── Inner hex trench (cooler, recedes)
    trench_r = 36
    trench_pts = [
        (cx + trench_r * math.cos(math.radians(60 * i - 30)),
         cy + trench_r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    draw.polygon(trench_pts, fill=_VOID)

    # 4 ── Red optic lens — radial gradient at the core
    lens_r = 28
    _radial_gradient(draw, cx, cy, lens_r, 2,
                     col_out=_RED_DEEP, col_in=_RED_WHITE, steps=48)

    # Iris crosshair
    iris_r = 10
    draw.line([(cx - iris_r, cy), (cx + iris_r, cy)], fill=_RED_WHITE, width=1)
    draw.line([(cx, cy - iris_r), (cx, cy + iris_r)], fill=_RED_WHITE, width=1)

    # Iris circle cold outline
    draw.ellipse((cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r),
                 outline=_AMBER, width=1)

    # 5 ── Scanning chevrons — short red tick marks around the lens
    tick_r1 = lens_r + 2
    tick_r2 = lens_r + 6
    for i in range(24):
        a = math.radians(i * 15)
        x1 = cx + tick_r1 * math.cos(a)
        y1 = cy + tick_r1 * math.sin(a)
        x2 = cx + tick_r2 * math.cos(a)
        y2 = cy + tick_r2 * math.sin(a)
        col = _RED_HOT if i % 3 == 0 else _RED_DEEP
        draw.line([(x1, y1), (x2, y2)], fill=col, width=1)

    # 6 ── Subtle bloom halo (outer soft red glow) via a blurred overlay
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(halo)
    hdraw.ellipse((cx - 40, cy - 40, cx + 40, cy + 40),
                  fill=(255, 40, 40, 90))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=10))
    img  = Image.alpha_composite(img, halo)

    # Re-draw a small bright centre over the bloom to restore focus
    over = ImageDraw.Draw(img)
    over.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=_RED_WHITE)

    out_path = os.path.join(_BLDG_DIR, "rogue_hq.png")
    img.save(out_path)
    print(f"[rogue-art] ✅ {out_path}  (128×128)")


if __name__ == "__main__":
    make_rogue_hq()
    print("[rogue-art] done.")
