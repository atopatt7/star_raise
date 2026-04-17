"""
generate_swarm_art.py — Star Raise
Procedural PIL art for "The Swarm" alien faction.
Generates organic, fleshy assets with deep purples, neon greens, and fleshy pinks.

Assets generated
----------------
  assets/buildings/swarm_hq.png       (128×128)
  assets/buildings/acid_pool.png      (96×96)
  assets/buildings/toxin_chamber.png  (96×96)
  assets/units/crawler.png            (32×32)
  assets/units/spitter.png            (32×32)
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
_UNIT_DIR   = os.path.join(_ROOT, "assets", "units")

os.makedirs(_BLDG_DIR, exist_ok=True)
os.makedirs(_UNIT_DIR, exist_ok=True)

rng = random.Random(0xDEAD1234)   # deterministic


# ── Colour palette ────────────────────────────────────────────────────────────
# Deep purples / neon greens / fleshy pinks — no metallic tones
_VOID_BLACK   = (4,   2,  12, 255)
_DEEP_PURPLE  = (55,  10, 80, 255)
_MID_PURPLE   = (100, 20, 150, 255)
_BRIGHT_PURPLE= (160, 50, 220, 255)
_NEON_GREEN   = (57, 255, 20, 255)
_ACID_GREEN   = (110, 200, 30, 255)
_SLIME_GREEN  = (40,  140, 10, 255)
_FLESH_PINK   = (210, 90, 120, 255)
_FLESH_PALE   = (230, 150, 160, 255)
_VEIN_RED     = (170, 30,  60, 255)
_CHITIN_DARK  = (30,  15,  40, 255)
_CHITIN_MID   = (60,  30,  80, 255)
_CHITIN_SHEEN = (120, 70, 160, 255)


def _lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _radial_gradient(draw, cx, cy, r_outer, r_inner, col_out, col_in, steps=32):
    """Paint a radial gradient circle from col_out (edge) to col_in (centre)."""
    for i in range(steps, 0, -1):
        t   = i / steps
        r   = int(r_inner + (r_outer - r_inner) * t)
        col = _lerp_color(col_in, col_out, t)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)


def _wobbly_circle(draw, cx, cy, r, amplitude, col, n_verts=48):
    """Draw a blob polygon approximating a circle with radial noise."""
    pts = []
    for i in range(n_verts):
        angle = 2 * math.pi * i / n_verts
        dr    = rng.uniform(-amplitude, amplitude)
        rx    = (r + dr) * math.cos(angle)
        ry    = (r + dr) * math.sin(angle)
        pts.append((cx + rx, cy + ry))
    draw.polygon(pts, fill=col)


# ── Asset 1: swarm_hq.png (128×128) ──────────────────────────────────────────
def make_swarm_hq(path: str, size: int = 128) -> None:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Outer biomass blob — multiple overlapping wobbly circles
    for _ in range(6):
        ox = rng.randint(-8, 8)
        oy = rng.randint(-8, 8)
        r  = rng.randint(38, 46)
        _wobbly_circle(draw, cx + ox, cy + oy, r, 6, _DEEP_PURPLE)

    # Mid-layer flesh mound
    _wobbly_circle(draw, cx, cy, 34, 5, _MID_PURPLE)
    _wobbly_circle(draw, cx, cy, 26, 4, _FLESH_PINK)

    # Pulsing core — radial gradient
    _radial_gradient(draw, cx, cy, 22, 4, _BRIGHT_PURPLE, _NEON_GREEN, 40)

    # Veins radiating outward
    for angle_deg in range(0, 360, 30):
        angle = math.radians(angle_deg + rng.uniform(-10, 10))
        for seg in range(5):
            t0  = 0.3 + seg * 0.14
            t1  = t0 + 0.13
            x0  = int(cx + t0 * 48 * math.cos(angle))
            y0  = int(cy + t0 * 48 * math.sin(angle))
            x1  = int(cx + t1 * 48 * math.cos(angle))
            y1  = int(cy + t1 * 48 * math.sin(angle))
            draw.line([(x0, y0), (x1, y1)], fill=_VEIN_RED, width=2)

    # Small acid pustules on surface
    for _ in range(9):
        angle = rng.uniform(0, 2 * math.pi)
        dist  = rng.uniform(18, 34)
        px = int(cx + dist * math.cos(angle))
        py = int(cy + dist * math.sin(angle))
        r2 = rng.randint(3, 6)
        _wobbly_circle(draw, px, py, r2, 1, _ACID_GREEN)
        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=_NEON_GREEN)

    # Glow pass
    glow  = img.filter(ImageFilter.GaussianBlur(radius=3))
    final = Image.alpha_composite(glow, img)
    final.save(path)
    print(f"[SwarmArt] ✅ {path}")


# ── Asset 2: acid_pool.png (96×96) ───────────────────────────────────────────
def make_acid_pool(path: str, size: int = 96) -> None:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Fleshy outer ring of the spawning pool
    _wobbly_circle(draw, cx, cy, 40, 7, _FLESH_PINK)
    _wobbly_circle(draw, cx, cy, 34, 5, _MID_PURPLE)

    # Inner acid pool — glowing green puddle
    _wobbly_circle(draw, cx, cy, 26, 5, _SLIME_GREEN)
    _radial_gradient(draw, cx, cy, 24, 4, _ACID_GREEN, _NEON_GREEN, 36)

    # Bubbles / boiling acid surface
    for _ in range(10):
        bx = int(cx + rng.uniform(-18, 18))
        by = int(cy + rng.uniform(-18, 18))
        br = rng.randint(2, 5)
        draw.ellipse((bx - br, by - br, bx + br, by + br),
                     fill=_NEON_GREEN, outline=(200, 255, 100, 200))

    # Fleshy tendrils around the rim
    for i in range(8):
        angle = 2 * math.pi * i / 8 + rng.uniform(-0.1, 0.1)
        for step in range(4):
            t0 = 0.55 + step * 0.1
            t1 = t0 + 0.09
            x0 = int(cx + t0 * size * 0.45 * math.cos(angle))
            y0 = int(cy + t0 * size * 0.45 * math.sin(angle))
            x1 = int(cx + t1 * size * 0.45 * math.cos(angle + rng.uniform(-0.15, 0.15)))
            y1 = int(cy + t1 * size * 0.45 * math.sin(angle + rng.uniform(-0.15, 0.15)))
            draw.line([(x0, y0), (x1, y1)], fill=_VEIN_RED, width=3)

    glow  = img.filter(ImageFilter.GaussianBlur(radius=2))
    final = Image.alpha_composite(glow, img)
    final.save(path)
    print(f"[SwarmArt] ✅ {path}")


# ── Asset 2b: toxin_chamber.png (96×96) ──────────────────────────────────────
def make_toxin_chamber(path: str, size: int = 96) -> None:
    """
    Tall fleshy alien spire with glowing green toxin nodes.

    Silhouette: a tapered pustule-studded pillar (≈ 70 px tall) rising
    from a wide biomass base.  Four glowing green nodes climb the spine,
    framed by drooping tendrils.  Reads very differently from the
    puddle-shaped acid_pool so players can identify each building at
    a glance.
    """
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = size // 2

    # ── Wide biomass base (anchors the spire to the ground) ───────────
    base_cy = size - 16
    _wobbly_circle(draw, cx, base_cy, 30, 5, _DEEP_PURPLE)
    _wobbly_circle(draw, cx, base_cy, 24, 4, _MID_PURPLE)
    _wobbly_circle(draw, cx, base_cy, 18, 3, _FLESH_PINK)

    # ── Central fleshy spire — tapered from wide base to narrow tip ───
    # Drawn as a stack of overlapping wobbly circles of decreasing radius
    # so the column looks biological rather than polygon-straight.
    tip_y = 10
    n_segs = 10
    for i in range(n_segs):
        t   = i / (n_segs - 1)
        sy  = int(base_cy - 6 - t * (base_cy - tip_y))
        rad = int(16 - t * 11)
        ox  = rng.randint(-2, 2)
        _wobbly_circle(draw, cx + ox, sy, rad, 2, _MID_PURPLE)
        _wobbly_circle(draw, cx + ox, sy, max(2, rad - 4), 1, _FLESH_PINK)

    # ── Four glowing toxin nodes climbing the spine ────────────────────
    node_ys = [base_cy - 10, base_cy - 26, base_cy - 44, base_cy - 60]
    for ny in node_ys:
        side = rng.choice((-1, 1))
        nx   = cx + side * rng.randint(2, 4)
        draw.ellipse((nx - 6, ny - 6, nx + 6, ny + 6), fill=_SLIME_GREEN)
        _radial_gradient(draw, nx, ny, 6, 1, _ACID_GREEN, _NEON_GREEN, 14)
        draw.ellipse((nx - 2, ny - 2, nx + 2, ny + 2),
                     fill=(210, 255, 170, 255))

    # ── Crown of acid droplets at the tip ─────────────────────────────
    for ang_deg in (-50, -20, 20, 50):
        ang = math.radians(ang_deg - 90)
        dx  = int(8 * math.cos(ang))
        dy  = int(8 * math.sin(ang))
        draw.ellipse((cx + dx - 2, tip_y + dy - 2,
                      cx + dx + 2, tip_y + dy + 2),
                     fill=_NEON_GREEN)

    # ── Drooping fleshy tendrils around the base ──────────────────────
    for i in range(6):
        ang = math.radians(210 + i * 24 + rng.uniform(-6, 6))
        x0  = int(cx + 18 * math.cos(ang))
        y0  = int(base_cy + 4 * math.sin(ang))
        x1  = int(cx + 32 * math.cos(ang))
        y1  = int(base_cy + 12 * math.sin(ang) + 6)
        draw.line([(x0, y0), (x1, y1)], fill=_VEIN_RED, width=3)

    # ── Veins running up the spine ────────────────────────────────────
    for side in (-1, 1):
        pts = []
        for j in range(9):
            t   = j / 8
            vy  = int(base_cy - 4 - t * (base_cy - tip_y - 6))
            vx  = cx + side * int(3 + 2 * math.sin(j * 1.3))
            pts.append((vx, vy))
        draw.line(pts, fill=_VEIN_RED, width=1)

    # ── Glow pass ─────────────────────────────────────────────────────
    glow  = img.filter(ImageFilter.GaussianBlur(radius=2))
    final = Image.alpha_composite(glow, img)
    final.save(path)
    print(f"[SwarmArt] ✅ {path}")


# ── Asset 3: crawler.png (32×32) ─────────────────────────────────────────────
def make_crawler(path: str, size: int = 32) -> None:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Chitin body — compact, low-profile ellipse
    draw.ellipse((cx - 9, cy - 7, cx + 9, cy + 7), fill=_CHITIN_DARK)
    draw.ellipse((cx - 7, cy - 5, cx + 7, cy + 5), fill=_CHITIN_MID)

    # Sheen highlight
    draw.ellipse((cx - 4, cy - 3, cx + 2, cy),     fill=_CHITIN_SHEEN)

    # 6 jagged legs (3 per side)
    for i, angle_deg in enumerate([-50, 0, 50]):
        for side, xmul in [(-1, -1), (1, 1)]:
            angle   = math.radians(angle_deg + 90)
            leg_len = rng.randint(7, 9)
            seg_x   = int(cx + xmul * 8)
            seg_y   = int(cy + (i - 1) * 4)
            ex      = int(seg_x + xmul * leg_len * math.cos(angle))
            ey      = int(seg_y + leg_len * math.sin(angle))
            draw.line([(seg_x, seg_y), (ex, ey)], fill=_CHITIN_SHEEN, width=1)

    # Glowing green eyes
    draw.ellipse((cx + 4, cy - 4, cx + 7, cy - 1), fill=_NEON_GREEN)
    draw.ellipse((cx + 5, cy - 3, cx + 6, cy - 2), fill=(200, 255, 150, 255))

    img.save(path)
    print(f"[SwarmArt] ✅ {path}")


# ── Asset 4: spitter.png (32×32) ─────────────────────────────────────────────
def make_spitter(path: str, size: int = 32) -> None:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # Bulbous body — fatter than crawler
    _wobbly_circle(draw, cx, cy, 11, 2, _MID_PURPLE)
    _wobbly_circle(draw, cx, cy, 8,  1, _FLESH_PINK)

    # Acid sac — glowing green belly
    draw.ellipse((cx - 5, cy + 1, cx + 5, cy + 9), fill=_SLIME_GREEN)
    _radial_gradient(draw, cx, cy + 5, 5, 1, _ACID_GREEN, _NEON_GREEN, 12)

    # Stubby legs (4 total)
    for side, xmul in [(-1, -1), (1, 1)]:
        for yoff in [-2, 4]:
            sx0 = cx + xmul * 8
            sy0 = cy + yoff
            sx1 = cx + xmul * 13
            sy1 = cy + yoff + 3
            draw.line([(sx0, sy0), (sx1, sy1)], fill=_CHITIN_DARK, width=2)

    # Forward acid nozzle (mouth) — protruding right
    draw.rectangle((cx + 9, cy - 1, cx + 14, cy + 1), fill=_NEON_GREEN)
    draw.ellipse((cx + 12, cy - 2, cx + 15, cy + 2), fill=_ACID_GREEN)

    # Glowing eyes
    draw.ellipse((cx + 3, cy - 5, cx + 6, cy - 2), fill=_NEON_GREEN)
    draw.ellipse((cx + 4, cy - 4, cx + 5, cy - 3), fill=(220, 255, 180, 255))

    glow  = img.filter(ImageFilter.GaussianBlur(radius=1))
    final = Image.alpha_composite(glow, img)
    final.save(path)
    print(f"[SwarmArt] ✅ {path}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    make_swarm_hq     (os.path.join(_BLDG_DIR, "swarm_hq.png"))
    make_acid_pool    (os.path.join(_BLDG_DIR, "acid_pool.png"))
    make_toxin_chamber(os.path.join(_BLDG_DIR, "toxin_chamber.png"))
    make_crawler      (os.path.join(_UNIT_DIR,  "crawler.png"))
    make_spitter      (os.path.join(_UNIT_DIR,  "spitter.png"))
    print("[SwarmArt] All 5 assets written.")
