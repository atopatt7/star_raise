"""
upgrade_rogue_art.py — Star Raise
Upgrades all 9 Rogue AI assets to professional 2.5D isometric style.

Strategy
--------
1. Try to download sprites from KenneyNL open-source repos (fast path).
2. If network is blocked (sandbox), fall back to a fully hand-crafted
   2.5D isometric PIL renderer that produces pre-rendered-3D-quality art.

2.5D Isometric convention used throughout
------------------------------------------
  • Isometric projection: X-axis goes right-down at 26.57°,
    Y-axis goes left-down at 26.57°, Z-axis goes straight up.
  • Three face shades for every prism/box:
      TOP  face  → bright  steel  #888888  (lit from above)
      LEFT face  → mid     steel  #464646  (side shadow)
      RIGHT face → dark    steel  #222222  (deep shadow)
  • Neon accent glows drawn on faces: Red, Teal, Violet per faction role.
  • GaussianBlur halo composited over the base drawing for emission effect.

Assets overwritten
------------------
  assets/buildings/logic_core.png      (96×96)
  assets/buildings/data_node.png       (96×96)
  assets/buildings/quantum_array.png   (96×96)
  assets/buildings/assembly_matrix.png (96×96)
  assets/buildings/plasma_tower.png    (64×64)
  assets/units/observer.png            (32×32)
  assets/units/ravager.png             (32×32)
  assets/units/coder.png               (32×32)
  assets/units/splitter.png            (32×32)
"""

import math
import os
import ssl
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow",
                           "--break-system-packages", "-q"])
    from PIL import Image, ImageDraw, ImageFilter

# ── Paths ─────────────────────────────────────────────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.dirname(_DIR)
_BLDG   = os.path.join(_ROOT, "assets", "buildings")
_UNIT   = os.path.join(_ROOT, "assets", "units")
os.makedirs(_BLDG, exist_ok=True)
os.makedirs(_UNIT, exist_ok=True)

# ── Kenney download table ─────────────────────────────────────────────────────
# Tiles from KenneyNL/Tower-Defense-Top-Down  (already isometric-style PNGs)
_KENNEY_BASE = (
    "https://raw.githubusercontent.com/KenneyNL/"
    "Tower-Defense-Top-Down/master/PNG/Retina/"
)
_DOWNLOAD_MAP = {
    # dest path                               remote tile
    os.path.join(_BLDG, "logic_core.png"):    _KENNEY_BASE + "towerDefense_tile060.png",
    os.path.join(_BLDG, "quantum_array.png"): _KENNEY_BASE + "towerDefense_tile057.png",
    os.path.join(_BLDG, "plasma_tower.png"):  _KENNEY_BASE + "towerDefense_tile245.png",
    os.path.join(_UNIT, "observer.png"):       _KENNEY_BASE + "towerDefense_tile188.png",
    os.path.join(_UNIT, "ravager.png"):        _KENNEY_BASE + "towerDefense_tile196.png",
    os.path.join(_UNIT, "coder.png"):          _KENNEY_BASE + "towerDefense_tile193.png",
    os.path.join(_UNIT, "splitter.png"):       _KENNEY_BASE + "towerDefense_tile199.png",
}

# Tint colours to apply after download (RGBA multiply)
_TINTS = {
    os.path.join(_BLDG, "logic_core.png"):    (80,  160, 255),   # blue
    os.path.join(_BLDG, "quantum_array.png"): (160,  80, 255),   # violet
    os.path.join(_BLDG, "plasma_tower.png"):  (255,  60,  60),   # red
    os.path.join(_UNIT, "observer.png"):       (255,  60,  60),   # red
    os.path.join(_UNIT, "ravager.png"):        (180, 100, 255),   # violet
    os.path.join(_UNIT, "coder.png"):          ( 40, 220, 200),   # teal
    os.path.join(_UNIT, "splitter.png"):       (100,  80, 255),   # indigo
}
# Target sizes after download + resize
_SIZES = {
    os.path.join(_BLDG, "logic_core.png"):    (96, 96),
    os.path.join(_BLDG, "quantum_array.png"): (96, 96),
    os.path.join(_BLDG, "plasma_tower.png"):  (64, 64),
    os.path.join(_UNIT, "observer.png"):       (32, 32),
    os.path.join(_UNIT, "ravager.png"):        (32, 32),
    os.path.join(_UNIT, "coder.png"):          (32, 32),
    os.path.join(_UNIT, "splitter.png"):       (32, 32),
}


def _tint_image(img: Image.Image, tint_rgb: tuple) -> Image.Image:
    """Multiply the RGB channels by a tint colour (preserves alpha)."""
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    tr, tg, tb = tint_rgb
    r = r.point(lambda x: int(x * tr / 255))
    g = g.point(lambda x: int(x * tg / 255))
    b = b.point(lambda x: int(x * tb / 255))
    return Image.merge("RGBA", (r, g, b, a))


def try_download_all() -> dict[str, bool]:
    """
    Attempt to download each Kenney tile. Returns a dict of {dest: success}.
    Silently falls back on any network or HTTP error.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    results = {}
    for dest, url in _DOWNLOAD_MAP.items():
        try:
            with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
                data = resp.read()
            import io
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            size = _SIZES[dest]
            img  = img.resize(size, Image.LANCZOS)
            img  = _tint_image(img, _TINTS[dest])
            img.save(dest)
            print(f"  [download] ✅ {os.path.basename(dest)}")
            results[dest] = True
        except Exception as e:
            print(f"  [download] ⚠  {os.path.basename(dest)}: {e}")
            results[dest] = False
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  2.5D ISOMETRIC RENDERER
# ══════════════════════════════════════════════════════════════════════════════

# Shared metal palette
_TOP   = (136, 136, 136, 255)   # bright lit face
_LEFT  = ( 70,  70,  70, 255)   # mid shadow face
_RIGHT = ( 30,  30,  30, 255)   # dark shadow face
_EDGE  = (200, 200, 200, 255)   # highlight edge
_VOID  = (  6,   4,   8, 255)

# Accent colours
_RED_HOT    = (255,  70,  50, 255)
_RED_MID    = (180,  30,  30, 255)
_TEAL_HOT   = ( 50, 240, 200, 255)
_TEAL_MID   = ( 20, 160, 150, 255)
_VIOLET_HOT = (180,  80, 255, 255)
_VIOLET_MID = (100,  40, 180, 255)
_AMBER      = (255, 180,  40, 255)


def _iso_box(draw, cx, cy, w, h, d, top_col, left_col, right_col):
    """
    Draw a single isometric box (rectangular prism) centred at (cx, cy).

    Parameters
    ----------
    cx, cy       : centre of the box in canvas coords
    w            : width  of the box (left-right axis)
    h            : height of the box (top-bottom / up axis)
    d            : depth  of the box (front-back axis)
    top_col      : colour of the top   face
    left_col     : colour of the left  face
    right_col    : colour of the right face

    Isometric conventions
    ---------------------
    In a 2:1 isometric projection the X-axis goes right-down
    and the Y-axis goes left-down, both at ~26.57°.  We keep it
    simple: each iso unit maps as:
        iso-right (+x) → pixel ( +cos30°,  +sin30° ) ≈ (+0.866, +0.5)
        iso-up    (+z) → pixel (       0,       -1  )
        iso-left  (+y) → pixel ( -cos30°,  +sin30° ) ≈ (-0.866, +0.5)
    """
    sx = w / 2   # half-width  in screen-x per iso-x unit
    sy = d / 2   # half-depth  in screen-x per iso-y unit (same scale)
    ex = sx * 0.866
    ey = sx * 0.5
    dx = sy * 0.866
    dy = sy * 0.5

    # 8 corners of the prism in pixel space
    # Top face (z = h)  ─ 4 corners
    TF = (cx,        cy - h)
    TR = (cx + ex,   cy - h + ey)
    TB = (cx + ex - dx, cy - h + ey + dy)
    TL = (cx - dx,   cy - h + dy)

    # Bottom face (z = 0) ─ 4 corners
    BF = (cx,        cy)
    BR = (cx + ex,   cy + ey)
    BB = (cx + ex - dx, cy + ey + dy)
    BL = (cx - dx,   cy + dy)

    # Right face  (front-right)
    draw.polygon([TR, BR, BB, TB], fill=right_col)
    # Left face   (front-left)
    draw.polygon([TF, BF, BL, TL], fill=left_col)
    # Top face
    draw.polygon([TF, TR, TB, TL], fill=top_col)

    # Edge highlights
    for seg in [(TF, TR), (TR, TB), (TB, TL), (TL, TF)]:
        draw.line(seg, fill=_EDGE, width=1)


def _iso_cyl(draw, cx, cy, rx, ry_top, h, top_col, side_col, accent=None):
    """
    Draw a flattened iso ellipse stack (iso cylinder approximation).

    rx      : horizontal radius in pixels
    ry_top  : vertical   radius of the top ellipse cap (rx * 0.5 for iso)
    h       : height in pixels (vertical extrusion)
    accent  : optional (r,g,b,a) line drawn on the cylinder side
    """
    # Side rectangle (left and right edges of cylinder body)
    draw.rectangle((cx - rx, cy - h, cx + rx, cy), fill=side_col)

    # Side accent stripe
    if accent:
        mid_y = cy - h // 2
        draw.line([(cx - rx + 2, mid_y), (cx + rx - 2, mid_y)],
                  fill=accent, width=2)

    # Bottom ellipse cap
    draw.ellipse((cx - rx, cy - ry_top, cx + rx, cy + ry_top),
                 fill=side_col, outline=_EDGE)

    # Top ellipse cap (bright)
    draw.ellipse((cx - rx, cy - h - ry_top, cx + rx, cy - h + ry_top),
                 fill=top_col, outline=_EDGE)


def _bloom_over(img, cx, cy, r, rgb, alpha=80, blur=6):
    S = img.size
    halo = Image.new("RGBA", S, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        (cx - r, cy - r, cx + r, cy + r), fill=(*rgb, alpha)
    )
    halo = halo.filter(ImageFilter.GaussianBlur(radius=blur))
    return Image.alpha_composite(img, halo)


def _neon_line(draw, p1, p2, color, width=2):
    draw.line([p1, p2], fill=color, width=width)


# ── logic_core 96×96 ──────────────────────────────────────────────────────────
# 2.5D: multi-tiered isometric processor tower with blue circuit glow
def make_logic_core_iso():
    S = 96
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 72

    # Tier 3 – wide base platform
    _iso_box(draw, cx, cy, 64, 8, 40, _TOP, _LEFT, _RIGHT)
    # Tier 2 – mid block
    _iso_box(draw, cx, cy - 8, 48, 12, 30, _TOP, _LEFT, _RIGHT)
    # Tier 1 – narrow top tower
    _iso_box(draw, cx, cy - 20, 28, 20, 18, _TOP, _LEFT, _RIGHT)

    # Blue circuit lines on top face of tier 2
    circuit_col = (60, 140, 255, 200)
    for i in range(3):
        ox = -10 + i * 10
        draw.line([(cx + ox, cy - 20), (cx + ox, cy - 10)], fill=circuit_col, width=1)
    draw.line([(cx - 10, cy - 15), (cx + 10, cy - 15)], fill=circuit_col, width=1)

    # Central optic – blue radial gradient on top of tower
    for r in range(8, 0, -1):
        t = r / 8
        c = tuple(int(a + (b - a) * t)
                  for a, b in zip((10, 30, 120, 200), (160, 210, 255, 255)))
        draw.ellipse((cx - r, cy - 40 - r // 2, cx + r, cy - 40 + r // 2), fill=c)

    # Blue bloom
    img = _bloom_over(img, cx, cy - 40, 14, (40, 120, 255), alpha=90, blur=7)
    # Rim highlight dot
    ImageDraw.Draw(img).ellipse((cx - 2, cy - 42, cx + 2, cy - 38),
                                fill=(200, 230, 255, 255))

    out = os.path.join(_BLDG, "logic_core.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── quantum_array 96×96 ──────────────────────────────────────────────────────
# 2.5D: tall obelisk on hexagonal platform with violet energy pillar
def make_quantum_array_iso():
    S = 96
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 76

    # Wide hex base (approximated as flat iso box)
    _iso_box(draw, cx, cy, 56, 6, 36, _TOP, _LEFT, _RIGHT)

    # Obelisk body  – tall narrow iso box
    _iso_box(draw, cx, cy - 6, 20, 48, 14, _TOP, _LEFT, _RIGHT)

    # Violet panel insets on right face of obelisk
    vr, vm = _VIOLET_HOT, _VIOLET_MID
    for i in range(3):
        yy = cy - 12 - i * 14
        draw.rectangle((cx + 4, yy, cx + 12, yy + 8), fill=vm)
        draw.rectangle((cx + 4, yy, cx + 12, yy + 8), outline=vr)

    # Apex crystal – violet radial glow (iso-ellipse shape)
    apex_y = cy - 54
    for r in range(7, 0, -1):
        t = r / 7
        c = tuple(int(a + (b - a) * t)
                  for a, b in zip(_VIOLET_MID, (230, 200, 255, 255)))
        draw.ellipse((cx - r, apex_y - r // 2, cx + r, apex_y + r // 2), fill=c)

    # Energy tendril lines from apex
    for angle in range(0, 360, 60):
        rad = math.radians(angle)
        x2  = cx + int(12 * math.cos(rad))
        y2  = apex_y + int(6 * math.sin(rad))
        draw.line([(cx, apex_y), (x2, y2)], fill=_VIOLET_HOT, width=1)

    img = _bloom_over(img, cx, apex_y, 16, (120, 40, 220), alpha=100, blur=8)
    ImageDraw.Draw(img).ellipse((cx - 2, apex_y - 2, cx + 2, apex_y + 2),
                                fill=(240, 210, 255, 255))

    out = os.path.join(_BLDG, "quantum_array.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── plasma_tower 64×64 ───────────────────────────────────────────────────────
# 2.5D: compact turret base + rotating gun head + red plasma muzzle
def make_plasma_tower_iso():
    S = 64
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 50

    # Octagonal base → approximate with wide squat iso box
    _iso_box(draw, cx, cy, 44, 6, 28, _TOP, _LEFT, _RIGHT)

    # Turret ring – slightly narrower iso box
    _iso_box(draw, cx, cy - 6, 30, 8, 20, _TOP, _LEFT, _RIGHT)

    # Turret head cylinder
    _iso_cyl(draw, cx, cy - 14, 10, 4, 10, _TOP, _LEFT, accent=_RED_MID)

    # Barrel – flat iso box extending right
    _iso_box(draw, cx + 14, cy - 20, 18, 5, 6, _TOP, _LEFT, _RIGHT)

    # Muzzle flash / plasma charge
    mx, my = cx + 24, cy - 22
    for r in range(7, 0, -1):
        t  = r / 7
        rc = tuple(int(a + (b - a) * t)
                   for a, b in zip(_RED_MID, (255, 220, 180, 255)))
        draw.ellipse((mx - r, my - r // 2, mx + r, my + r // 2), fill=rc)

    img = _bloom_over(img, mx, my, 10, (255, 40, 40), alpha=120, blur=5)
    ImageDraw.Draw(img).ellipse((mx - 2, my - 2, mx + 2, my + 2),
                                fill=(255, 240, 220, 255))

    # Corner bolts on base
    bolt_col = (190, 190, 200, 255)
    for dx, dy in [(-16, -2), (16, -2), (0, 10), (0, -10)]:
        draw.ellipse((cx + dx - 2, cy + dy - 2, cx + dx + 2, cy + dy + 2),
                     fill=bolt_col)

    out = os.path.join(_BLDG, "plasma_tower.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── observer 32×32 ────────────────────────────────────────────────────────────
# 2.5D: flying disc with iso thickness, glowing red lens
def make_observer_iso():
    S = 32
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 20

    # Disc body – iso cylinder (flat coin)
    _iso_cyl(draw, cx, cy, 11, 4, 5, _TOP, _LEFT)

    # Wing fins (iso thin slabs)
    for sign in (-1, 1):
        wing_pts = [
            (cx + sign * 9,  cy - 3),
            (cx + sign * 14, cy - 1),
            (cx + sign * 14, cy + 2),
            (cx + sign * 9,  cy + 3),
        ]
        draw.polygon(wing_pts, fill=_LEFT if sign == -1 else _RIGHT)

    # Red optic lens
    for r in range(4, 0, -1):
        t  = r / 4
        rc = tuple(int(a + (b - a) * t)
                   for a, b in zip(_RED_MID, (255, 220, 200, 255)))
        draw.ellipse((cx - r, cy - 5 - r // 2, cx + r, cy - 5 + r // 2), fill=rc)

    img = _bloom_over(img, cx, cy - 5, 6, (255, 40, 40), alpha=110, blur=3)
    ImageDraw.Draw(img).ellipse((cx - 1, cy - 6, cx + 1, cy - 4),
                                fill=(255, 230, 220, 255))

    out = os.path.join(_UNIT, "observer.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── ravager 32×32 ─────────────────────────────────────────────────────────────
# 2.5D: stocky mech bipedal bruiser with shoulder armour
def make_ravager_iso():
    S = 32
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 28

    # Feet / base slab
    _iso_box(draw, cx, cy, 22, 3, 10, _TOP, _LEFT, _RIGHT)
    # Legs
    _iso_box(draw, cx - 4, cy - 3, 7, 7, 5, _TOP, _LEFT, _RIGHT)
    _iso_box(draw, cx + 4, cy - 3, 7, 7, 5, _TOP, _LEFT, _RIGHT)
    # Torso
    _iso_box(draw, cx, cy - 10, 16, 10, 10, _TOP, _LEFT, _RIGHT)
    # Shoulder pauldrons
    _iso_box(draw, cx - 10, cy - 14, 8, 5, 6, _TOP, _LEFT, _RIGHT)
    _iso_box(draw, cx + 10, cy - 14, 8, 5, 6, _TOP, _LEFT, _RIGHT)
    # Head
    _iso_box(draw, cx, cy - 17, 10, 7, 7, _TOP, _LEFT, _RIGHT)

    # Visor – violet glow slit
    draw.rectangle((cx - 4, cy - 18, cx + 4, cy - 15), fill=_VIOLET_MID)
    draw.rectangle((cx - 4, cy - 18, cx + 4, cy - 15), outline=_VIOLET_HOT)

    img = _bloom_over(img, cx, cy - 16, 5, (180, 80, 255), alpha=80, blur=3)

    out = os.path.join(_UNIT, "ravager.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── coder 32×32 ───────────────────────────────────────────────────────────────
# 2.5D: sleek hovering sniper drone — long body + forward barrel
def make_coder_iso():
    S = 32
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 18

    # Main fuselage – elongated iso box
    _iso_box(draw, cx, cy, 24, 6, 10, _TOP, _LEFT, _RIGHT)

    # Delta wings (iso thin slabs)
    wing_top   = (_TOP[0], _TOP[1], _TOP[2], 200)
    wing_right = (_RIGHT[0], _RIGHT[1], _RIGHT[2], 200)
    for sign in (-1, 1):
        pts = [
            (cx,          cy - 3),
            (cx + sign * 10, cy + 4),
            (cx + sign * 10, cy + 8),
            (cx,          cy + 2),
        ]
        draw.polygon(pts, fill=wing_top if sign == -1 else wing_right)

    # Sniper barrel
    _iso_box(draw, cx + 14, cy - 2, 10, 3, 5, _TOP, _LEFT, _RIGHT)

    # Teal sensor eye on fuselage
    for r in range(4, 0, -1):
        t  = r / 4
        tc = tuple(int(a + (b - a) * t)
                   for a, b in zip(_TEAL_MID, (200, 255, 240, 255)))
        draw.ellipse((cx - 2 - r, cy - 6 - r // 2,
                      cx - 2 + r, cy - 6 + r // 2), fill=tc)

    img = _bloom_over(img, cx - 2, cy - 6, 6, (20, 200, 180), alpha=100, blur=3)
    ImageDraw.Draw(img).ellipse((cx - 3, cy - 7, cx - 1, cy - 5),
                                fill=(200, 255, 240, 255))

    out = os.path.join(_UNIT, "coder.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── splitter 32×32 ────────────────────────────────────────────────────────────
# 2.5D: wide siege tank — low flat hull, big cannon, indigo charge
def make_splitter_iso():
    S = 32
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 26

    # Tread blocks
    _iso_box(draw, cx - 7, cy, 8, 4, 10, _TOP, _LEFT, _RIGHT)
    _iso_box(draw, cx + 7, cy, 8, 4, 10, _TOP, _LEFT, _RIGHT)

    # Hull
    _iso_box(draw, cx, cy - 4, 20, 6, 14, _TOP, _LEFT, _RIGHT)

    # Turret
    _iso_box(draw, cx - 2, cy - 12, 12, 8, 10, _TOP, _LEFT, _RIGHT)

    # Cannon barrel
    _iso_box(draw, cx + 10, cy - 14, 10, 4, 4, _TOP, _LEFT, _RIGHT)

    # Indigo muzzle charge
    mx, my = cx + 16, cy - 14
    for r in range(5, 0, -1):
        t  = r / 5
        ic = tuple(int(a + (b - a) * t)
                   for a, b in zip(_VIOLET_MID, (180, 160, 255, 255)))
        draw.ellipse((mx - r, my - r // 2, mx + r, my + r // 2), fill=ic)

    img = _bloom_over(img, mx, my, 6, (80, 60, 220), alpha=110, blur=3)
    ImageDraw.Draw(img).ellipse((mx - 1, my - 1, mx + 1, my + 1),
                                fill=(210, 200, 255, 255))

    out = os.path.join(_UNIT, "splitter.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── data_node 96×96 ──────────────────────────────────────────────────────────
# 2.5D: teal relay station — slim comms tower + satellite dish + teal signal glow
# Matches the coder unit's teal/cyan colour scheme.
def make_data_node_iso():
    S = 96
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 74

    # Base pad — flat wide slab
    _iso_box(draw, cx, cy, 58, 6, 34, _TOP, _LEFT, _RIGHT)

    # Server stack — three narrow stepped blocks
    _iso_box(draw, cx, cy - 6,  42, 8,  26, _TOP, _LEFT, _RIGHT)
    _iso_box(draw, cx, cy - 14, 30, 8,  18, _TOP, _LEFT, _RIGHT)

    # Tall slim comms mast
    _iso_box(draw, cx, cy - 30, 10, 16, 8, _TOP, _LEFT, _RIGHT)

    # Teal circuit lines on mid block top face
    cl = (30, 200, 180, 200)
    for i in range(3):
        ox = -8 + i * 8
        draw.line([(cx + ox, cy - 14), (cx + ox, cy - 8)],  fill=cl, width=1)
    draw.line([(cx - 8, cy - 11), (cx + 8, cy - 11)], fill=cl, width=1)

    # Parabolic dish (iso-ellipse tilted on mast top)
    dish_cx, dish_cy = cx + 10, cy - 42
    for r in range(10, 0, -1):
        t = r / 10
        dc = tuple(int(a + (b - a) * t)
                   for a, b in zip(_TEAL_MID, (100, 255, 230, 255)))
        draw.ellipse((dish_cx - r, dish_cy - r // 2,
                      dish_cx + r, dish_cy + r // 2), fill=dc)

    # Teal signal-pulse bloom on dish
    img = _bloom_over(img, dish_cx, dish_cy, 14, (20, 200, 180), alpha=100, blur=7)
    ImageDraw.Draw(img).ellipse((dish_cx - 2, dish_cy - 1,
                                 dish_cx + 2, dish_cy + 1),
                                fill=(180, 255, 240, 255))

    # Teal ring antenna lines
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x2  = dish_cx + int(10 * math.cos(rad))
        y2  = dish_cy + int(5  * math.sin(rad))
        draw.line([(dish_cx, dish_cy), (x2, y2)], fill=_TEAL_HOT, width=1)

    out = os.path.join(_BLDG, "data_node.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── assembly_matrix 96×96 ────────────────────────────────────────────────────
# 2.5D: indigo heavy forge — massive base, industrial arms, violet charge core
# Matches the splitter unit's indigo/violet colour scheme.
def make_assembly_matrix_iso():
    S = 96
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = S // 2, 76

    # Massive base plate
    _iso_box(draw, cx, cy, 70, 8, 46, _TOP, _LEFT, _RIGHT)

    # Heavy central hull — wide and low
    _iso_box(draw, cx, cy - 8, 52, 14, 34, _TOP, _LEFT, _RIGHT)

    # Left arm / press
    _iso_box(draw, cx - 18, cy - 20, 14, 12, 10, _TOP, _LEFT, _RIGHT)
    # Right arm / press
    _iso_box(draw, cx + 18, cy - 20, 14, 12, 10, _TOP, _LEFT, _RIGHT)

    # Central core tower
    _iso_box(draw, cx, cy - 22, 24, 14, 16, _TOP, _LEFT, _RIGHT)

    # Indigo charge panels on right face of central core
    vm, vr = _VIOLET_MID, _VIOLET_HOT
    for i in range(2):
        yy = cy - 28 + i * 10
        draw.rectangle((cx + 4, yy, cx + 14, yy + 7), fill=vm)
        draw.rectangle((cx + 4, yy, cx + 14, yy + 7), outline=vr)

    # Core charge crystal — violet iso-ellipse bloom
    apex_y = cy - 36
    for r in range(9, 0, -1):
        t = r / 9
        ic = tuple(int(a + (b - a) * t)
                   for a, b in zip(_VIOLET_MID, (230, 180, 255, 255)))
        draw.ellipse((cx - r, apex_y - r // 2, cx + r, apex_y + r // 2), fill=ic)

    # Energy discharge lines
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x2  = cx + int(14 * math.cos(rad))
        y2  = apex_y + int(7  * math.sin(rad))
        draw.line([(cx, apex_y), (x2, y2)], fill=_VIOLET_HOT, width=1)

    img = _bloom_over(img, cx, apex_y, 18, (100, 30, 220), alpha=110, blur=8)
    ImageDraw.Draw(img).ellipse((cx - 2, apex_y - 2, cx + 2, apex_y + 2),
                                fill=(230, 210, 255, 255))

    out = os.path.join(_BLDG, "assembly_matrix.png")
    img.save(out)
    print(f"  [iso] ✅ {out}")


# ── Dispatcher ────────────────────────────────────────────────────────────────
_ISO_GENERATORS = {
    os.path.join(_BLDG, "logic_core.png"):      make_logic_core_iso,
    os.path.join(_BLDG, "data_node.png"):        make_data_node_iso,
    os.path.join(_BLDG, "quantum_array.png"):   make_quantum_array_iso,
    os.path.join(_BLDG, "assembly_matrix.png"): make_assembly_matrix_iso,
    os.path.join(_BLDG, "plasma_tower.png"):    make_plasma_tower_iso,
    os.path.join(_UNIT, "observer.png"):         make_observer_iso,
    os.path.join(_UNIT, "ravager.png"):          make_ravager_iso,
    os.path.join(_UNIT, "coder.png"):            make_coder_iso,
    os.path.join(_UNIT, "splitter.png"):         make_splitter_iso,
}


def fallback_generate_2_5D(skip: set[str] | None = None):
    """Run 2.5D isometric generator for every asset not already handled."""
    skip = skip or set()
    for dest, fn in _ISO_GENERATORS.items():
        if dest not in skip:
            fn()


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n[upgrade-rogue-art] Step 1 — trying Kenney downloads…")
    results = try_download_all()
    succeeded = {k for k, v in results.items() if v}

    remaining = set(_ISO_GENERATORS) - succeeded
    if remaining:
        print(f"\n[upgrade-rogue-art] Step 2 — 2.5D isometric fallback for "
              f"{len(remaining)} asset(s)…")
        fallback_generate_2_5D(skip=succeeded)
    else:
        print("\n[upgrade-rogue-art] All assets downloaded — no fallback needed.")

    print("\n[upgrade-rogue-art] ✅ Done — all 9 Rogue AI assets upgraded.")
