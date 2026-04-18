"""
generate_rogue_art_full.py — Star Raise
Procedural PIL art for ALL Rogue AI faction entities.

Visual language: dark metal chassis, neon optic lines, mechanical sci-fi.
Hard geometry (hex / square panels, bolts, circuit traces), cold metallic greys
and blacks, with red/violet/teal accent glows.

Generates:
  assets/buildings/logic_core.png    (96×96)  — dark metal circuit brain
  assets/buildings/quantum_array.png (96×96)  — floating dark obelisk w/ violet energy
  assets/buildings/plasma_tower.png  (64×64)  — mechanical defence turret w/ red laser
  assets/units/observer.png          (32×32)  — small flying drone w/ red eye
  assets/units/ravager.png           (32×32)  — bulky dark metal melee bruiser
  assets/units/coder.png             (32×32)  — sleek teal flying sniper drone
  assets/units/splitter.png          (32×32)  — heavy mechanical siege tank w/ indigo glow
"""

import math
import os
import random

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow",
                           "--break-system-packages", "-q"])
    from PIL import Image, ImageDraw, ImageFilter

# ── Path setup ────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_SCRIPT_DIR)
_BLDG_DIR   = os.path.join(_ROOT, "assets", "buildings")
_UNIT_DIR   = os.path.join(_ROOT, "assets", "units")
os.makedirs(_BLDG_DIR, exist_ok=True)
os.makedirs(_UNIT_DIR, exist_ok=True)

rng = random.Random(0xA1C0DE42)

# ── Shared palette ────────────────────────────────────────────────────────────
_VOID         = (6,    4,   8, 255)
_STEEL_DARK   = (30,  28,  36, 255)
_STEEL_MID    = (60,  58,  70, 255)
_STEEL_LIGHT  = (118, 120, 136, 255)
_STEEL_PLATE  = (88,  88, 102, 255)
_BOLT         = (178, 182, 198, 255)

# Red family
_RED_DEEP     = (100,  10,  18, 255)
_RED_MID      = (200,  30,  46, 255)
_RED_HOT      = (255,  70,  70, 255)
_RED_WHITE    = (255, 220, 210, 255)
_AMBER        = (255, 170,  60, 255)

# Violet / quantum family
_VIOLET_DEEP  = ( 50,  10,  80, 255)
_VIOLET_MID   = (120,  40, 180, 255)
_VIOLET_HOT   = (200,  80, 255, 255)
_VIOLET_WHITE = (230, 200, 255, 255)

# Teal / coder family
_TEAL_DEEP    = (  0,  60,  70, 255)
_TEAL_MID     = ( 20, 160, 160, 255)
_TEAL_HOT     = ( 60, 240, 200, 255)
_TEAL_WHITE   = (200, 255, 240, 255)

# Indigo / splitter family
_INDIGO_DEEP  = ( 30,  20,  80, 255)
_INDIGO_MID   = ( 80,  60, 180, 255)
_INDIGO_HOT   = (130, 100, 255, 255)


# ── Shared helpers ────────────────────────────────────────────────────────────
def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _radial_gradient(draw, cx, cy, r_outer, r_inner, col_out, col_in, steps=32):
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(r_inner + (r_outer - r_inner) * t)
        col = _lerp(col_in, col_out, t)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)


def _hex_pts(cx, cy, r, rot_deg=0):
    return [
        (cx + r * math.cos(math.radians(60 * i + rot_deg)),
         cy + r * math.sin(math.radians(60 * i + rot_deg)))
        for i in range(6)
    ]


def _bloom(img, cx, cy, r, color_rgb, alpha=80, blur=6):
    """Paste a soft glow blob over img."""
    S = img.size
    halo = Image.new("RGBA", S, (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(halo)
    hdraw.ellipse((cx - r, cy - r, cx + r, cy + r),
                  fill=(*color_rgb, alpha))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=blur))
    return Image.alpha_composite(img, halo)


def _circuit_lines(draw, S, color, count=6, seed=0):
    """Overlay a sparse grid of right-angle circuit traces."""
    r = random.Random(seed)
    for _ in range(count):
        x1 = r.randint(4, S - 4)
        y1 = r.randint(4, S - 4)
        x2 = r.randint(4, S - 4)
        y2 = r.randint(4, S - 4)
        # Manhattan-style: go horizontal first, then vertical
        mid = (x2, y1)
        draw.line([(x1, y1), mid], fill=color, width=1)
        draw.line([mid, (x2, y2)], fill=color, width=1)
        # Small dot at corners
        draw.ellipse((mid[0] - 1, mid[1] - 1, mid[0] + 1, mid[1] + 1), fill=color)


# ─────────────────────────────────────────────────────────────────────────────
# BUILDING: logic_core.png  96×96
# Dark metal hex chassis with blue circuit lines and a glowing blue processor eye
# ─────────────────────────────────────────────────────────────────────────────
def make_logic_core():
    S = 96
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer hex chassis
    hex_pts = _hex_pts(cx, cy, 44, rot_deg=-30)
    draw.polygon(hex_pts, fill=_STEEL_DARK)
    draw.polygon(hex_pts, outline=_STEEL_LIGHT)

    # Panel rivets along hex edges
    bolt_r = 2
    for i, pt in enumerate(hex_pts):
        nxt = hex_pts[(i + 1) % 6]
        mid = ((pt[0] + nxt[0]) / 2, (pt[1] + nxt[1]) / 2)
        draw.ellipse((mid[0]-bolt_r, mid[1]-bolt_r,
                      mid[0]+bolt_r, mid[1]+bolt_r), fill=_BOLT)

    # Inner armoured ring
    draw.ellipse((cx-34, cy-34, cx+34, cy+34), fill=_STEEL_PLATE)
    draw.ellipse((cx-34, cy-34, cx+34, cy+34), outline=_STEEL_MID, width=2)

    # Blue circuit trace web
    _circuit_lines(draw, S, (30, 80, 180, 180), count=10, seed=42)

    # Central processor core — blue radial gradient
    _radial_gradient(draw, cx, cy, 22, 2,
                     col_out=(10, 20, 80, 255), col_in=(180, 220, 255, 255), steps=36)

    # Cross-hair iris
    iris_r = 8
    draw.line([(cx - iris_r, cy), (cx + iris_r, cy)], fill=(160, 210, 255, 255), width=1)
    draw.line([(cx, cy - iris_r), (cx, cy + iris_r)], fill=(160, 210, 255, 255), width=1)
    draw.ellipse((cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r),
                 outline=(80, 140, 240, 220), width=1)

    # Tick ring
    for i in range(16):
        a = math.radians(i * 22.5)
        r1, r2 = 24, 28
        draw.line([(cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                   (cx + r2 * math.cos(a), cy + r2 * math.sin(a))],
                  fill=(80, 140, 240, 200), width=1)

    # Blue bloom glow
    img = _bloom(img, cx, cy, 30, (40, 120, 255), alpha=70, blur=8)

    # Restore bright centre dot
    ImageDraw.Draw(img).ellipse((cx-2, cy-2, cx+2, cy+2), fill=(220, 240, 255, 255))

    out = os.path.join(_BLDG_DIR, "logic_core.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (96×96)")


# ─────────────────────────────────────────────────────────────────────────────
# BUILDING: quantum_array.png  96×96
# Floating dark metal obelisk with violet energy tendrils
# ─────────────────────────────────────────────────────────────────────────────
def make_quantum_array():
    S = 96
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Base platform — dark hexagon
    base_pts = _hex_pts(cx, cy + 18, 24, rot_deg=0)
    draw.polygon(base_pts, fill=_STEEL_DARK)
    draw.polygon(base_pts, outline=_STEEL_MID)

    # Obelisk body — tall narrow rectangle with chamfered top
    ob_w, ob_h = 20, 52
    ob_x = cx - ob_w // 2
    ob_y = cy - 42
    # Body
    draw.rectangle((ob_x, ob_y + 6, ob_x + ob_w, ob_y + ob_h), fill=_STEEL_PLATE)
    # Chamfered top (triangle)
    draw.polygon([
        (ob_x, ob_y + 6),
        (ob_x + ob_w, ob_y + 6),
        (cx, ob_y),
    ], fill=_STEEL_MID)

    # Panel seams on obelisk
    for i in range(1, 4):
        y = ob_y + 6 + i * 12
        draw.line([(ob_x + 2, y), (ob_x + ob_w - 2, y)],
                  fill=_STEEL_MID, width=1)

    # Violet energy core pulsing along obelisk centre
    for j in range(8, 0, -1):
        t = j / 8
        col = _lerp(_VIOLET_DEEP, _VIOLET_WHITE, 1 - t)
        r = int(2 + 5 * (1 - t))
        ey = ob_y + 6 + ob_h // 3 + j * 3
        if ey < ob_y + ob_h:
            draw.ellipse((cx - r, ey - r, cx + r, ey + r), fill=col)

    # Apex crystal
    _radial_gradient(draw, cx, ob_y + 3, 6, 1,
                     col_out=_VIOLET_DEEP, col_in=_VIOLET_WHITE, steps=16)

    # Violet energy tendrils (arcing lines outward)
    tendril_r = random.Random(99)
    for i in range(6):
        a = math.radians(i * 60 + 10)
        length = tendril_r.randint(10, 22)
        x1, y1 = cx, ob_y + 6 + ob_h // 4
        x2 = x1 + length * math.cos(a)
        y2 = y1 + length * math.sin(a)
        draw.line([(x1, y1), (x2, y2)], fill=_VIOLET_HOT, width=1)
        draw.ellipse((x2 - 1, y2 - 1, x2 + 1, y2 + 1), fill=_VIOLET_WHITE)

    # Violet bloom
    img = _bloom(img, cx, ob_y + 6, 20, (120, 40, 200), alpha=90, blur=8)

    out = os.path.join(_BLDG_DIR, "quantum_array.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (96×96)")


# ─────────────────────────────────────────────────────────────────────────────
# BUILDING: plasma_tower.png  64×64
# Mechanical defence turret with a glowing red laser barrel
# ─────────────────────────────────────────────────────────────────────────────
def make_plasma_tower():
    S = 64
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Base pad — octagonal dark steel
    oct_r = 28
    oct_pts = [
        (cx + oct_r * math.cos(math.radians(45 * i + 22.5)),
         cy + oct_r * math.sin(math.radians(45 * i + 22.5)))
        for i in range(8)
    ]
    draw.polygon(oct_pts, fill=_STEEL_DARK)
    draw.polygon(oct_pts, outline=_STEEL_LIGHT)

    # Ring detail on base
    draw.ellipse((cx-18, cy-18, cx+18, cy+18), fill=_STEEL_MID)
    draw.ellipse((cx-18, cy-18, cx+18, cy+18), outline=_STEEL_PLATE, width=2)

    # Turret pivot — small circle
    draw.ellipse((cx-8, cy-8, cx+8, cy+8), fill=_STEEL_DARK)
    draw.ellipse((cx-8, cy-8, cx+8, cy+8), outline=_STEEL_LIGHT, width=1)

    # Gun barrel — pointing right (east), angled slightly upward
    barrel_len = 20
    barrel_w   = 4
    bx1, by1   = cx + 4, cy - 2
    bx2, by2   = cx + 4 + barrel_len, cy - 2
    # Main barrel rectangle
    draw.rectangle((bx1, by1 - barrel_w // 2, bx2, by1 + barrel_w // 2),
                   fill=_STEEL_PLATE)
    draw.rectangle((bx1, by1 - barrel_w // 2, bx2, by1 + barrel_w // 2),
                   outline=_STEEL_LIGHT, width=1)

    # Cooling vents on barrel
    for i in range(3):
        vx = bx1 + 5 + i * 5
        draw.line([(vx, by1 - barrel_w//2 + 1), (vx, by1 + barrel_w//2 - 1)],
                  fill=_STEEL_DARK, width=1)

    # Muzzle glow — red plasma charge at barrel tip
    mx, my = bx2, by1
    _radial_gradient(draw, mx, my, 6, 1,
                     col_out=_RED_DEEP, col_in=_RED_WHITE, steps=12)

    # Laser emitter glow bloom
    img = _bloom(img, mx, my, 8, (255, 40, 40), alpha=100, blur=5)

    # Re-draw bright muzzle dot over bloom
    ImageDraw.Draw(img).ellipse((mx-2, my-2, mx+2, my+2), fill=_RED_WHITE)

    # Corner bolts on base
    for i in range(4):
        a = math.radians(45 + 90 * i)
        bx = cx + 22 * math.cos(a)
        by = cy + 22 * math.sin(a)
        draw.ellipse((bx-2, by-2, bx+2, by+2), fill=_BOLT)

    out = os.path.join(_BLDG_DIR, "plasma_tower.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (64×64)")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: observer.png  32×32
# Small flying drone — circular disc body with a glowing red central eye
# ─────────────────────────────────────────────────────────────────────────────
def make_observer():
    S = 32
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Disc body
    draw.ellipse((cx-12, cy-7, cx+12, cy+7), fill=_STEEL_DARK)
    draw.ellipse((cx-12, cy-7, cx+12, cy+7), outline=_STEEL_LIGHT, width=1)

    # Wing fins (left + right)
    for sign in (-1, 1):
        wing_pts = [
            (cx + sign * 10, cy),
            (cx + sign * 15, cy - 4),
            (cx + sign * 15, cy + 4),
        ]
        draw.polygon(wing_pts, fill=_STEEL_MID)

    # Central red optic eye
    _radial_gradient(draw, cx, cy, 5, 1,
                     col_out=_RED_DEEP, col_in=_RED_WHITE, steps=10)

    # Bloom
    img = _bloom(img, cx, cy, 7, (255, 40, 40), alpha=90, blur=3)

    # Bright centre dot
    ImageDraw.Draw(img).ellipse((cx-1, cy-1, cx+1, cy+1), fill=_RED_WHITE)

    out = os.path.join(_UNIT_DIR, "observer.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (32×32)")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: ravager.png  32×32
# Bulky dark metal melee bruiser — wide shoulders, heavy armour plates
# ─────────────────────────────────────────────────────────────────────────────
def make_ravager():
    S = 32
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Torso — wide trapezoid
    torso_pts = [
        (cx - 10, cy - 6),
        (cx + 10, cy - 6),
        (cx + 12, cy + 8),
        (cx - 12, cy + 8),
    ]
    draw.polygon(torso_pts, fill=_STEEL_DARK)
    draw.polygon(torso_pts, outline=_STEEL_LIGHT)

    # Shoulder pauldrons
    for sign in (-1, 1):
        x0 = min(cx + sign*8, cx + sign*14)
        x1 = max(cx + sign*8, cx + sign*14)
        draw.rectangle((x0, cy-10, x1, cy-1), fill=_STEEL_PLATE)
        draw.rectangle((x0, cy-10, x1, cy-1), outline=_STEEL_MID)

    # Head — small rectangle
    draw.rectangle((cx-5, cy-14, cx+5, cy-6), fill=_STEEL_MID)
    draw.rectangle((cx-5, cy-14, cx+5, cy-6), outline=_STEEL_LIGHT)

    # Visor — red slit
    draw.rectangle((cx-4, cy-12, cx+4, cy-9), fill=_RED_MID)

    # Legs — two rectangles
    for sign in (-1, 1):
        lx0 = min(cx + sign*4, cx + sign*9)
        lx1 = max(cx + sign*4, cx + sign*9)
        draw.rectangle((lx0, cy+8, lx1, cy+14), fill=_STEEL_PLATE)

    # Red accent glowing lines on torso
    for i in range(3):
        gy = cy - 2 + i * 3
        draw.line([(cx-8, gy), (cx+8, gy)], fill=_RED_DEEP, width=1)

    out = os.path.join(_UNIT_DIR, "ravager.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (32×32)")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: coder.png  32×32
# Sleek teal flying sniper drone — elongated, thin wings, glowing teal eye
# ─────────────────────────────────────────────────────────────────────────────
def make_coder():
    S = 32
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fuselage — narrow elongated diamond
    body_pts = [
        (cx - 13, cy),
        (cx,      cy - 4),
        (cx + 13, cy),
        (cx,      cy + 4),
    ]
    draw.polygon(body_pts, fill=_STEEL_DARK)
    draw.polygon(body_pts, outline=_TEAL_MID)

    # Swept-back delta wings
    for sign in (-1, 1):
        wing_pts = [
            (cx,      cy + sign * 1),
            (cx - 6,  cy + sign * 8),
            (cx + 6,  cy + sign * 6),
        ]
        draw.polygon(wing_pts, fill=_STEEL_PLATE)
        draw.polygon(wing_pts, outline=_TEAL_DEEP)

    # Sniper barrel — thin line extending forward
    draw.line([(cx + 9, cy), (cx + 15, cy)], fill=_STEEL_LIGHT, width=2)
    draw.rectangle((cx + 14, cy - 1, cx + 16, cy + 1), fill=_TEAL_HOT)

    # Central teal optic sensor
    _radial_gradient(draw, cx - 2, cy, 4, 1,
                     col_out=_TEAL_DEEP, col_in=_TEAL_WHITE, steps=10)

    # Teal bloom
    img = _bloom(img, cx - 2, cy, 6, (20, 200, 180), alpha=90, blur=3)

    ImageDraw.Draw(img).ellipse((cx-3, cy-1, cx-1, cy+1), fill=_TEAL_WHITE)

    out = os.path.join(_UNIT_DIR, "coder.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (32×32)")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT: splitter.png  32×32
# Heavy mechanical siege tank — wide, squat, indigo glow from the siege cannon
# ─────────────────────────────────────────────────────────────────────────────
def make_splitter():
    S = 32
    cx, cy = S // 2, S // 2
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Tank hull — wide low rectangle
    draw.rectangle((cx-13, cy-4, cx+13, cy+10), fill=_STEEL_DARK)
    draw.rectangle((cx-13, cy-4, cx+13, cy+10), outline=_STEEL_LIGHT)

    # Turret — squarish box on top
    draw.rectangle((cx-6, cy-10, cx+6, cy-4), fill=_STEEL_PLATE)
    draw.rectangle((cx-6, cy-10, cx+6, cy-4), outline=_STEEL_MID)

    # Siege cannon — thick, long barrel
    draw.rectangle((cx+6, cy-8, cx+16, cy-6), fill=_STEEL_PLATE)
    draw.rectangle((cx+6, cy-8, cx+16, cy-6), outline=_STEEL_LIGHT)

    # Cannon muzzle — indigo glow charge
    mx, my = cx + 16, cy - 7
    _radial_gradient(draw, mx, my, 4, 1,
                     col_out=_INDIGO_DEEP, col_in=_INDIGO_HOT, steps=8)

    # Treads — two rectangles below hull
    for sign in (-1, 1):
        tx0 = min(cx + sign * 3, cx + sign * 13)
        tx1 = max(cx + sign * 3, cx + sign * 13)
        draw.rectangle((tx0, cy + 10, tx1, cy + 14), fill=_STEEL_MID)
        # Tread segments
        for i in range(3):
            tx = cx + sign * (4 + i * 3)
            draw.line([(tx, cy + 10), (tx, cy + 14)], fill=_STEEL_DARK, width=1)

    # Indigo bloom at muzzle
    img = _bloom(img, mx, my, 5, (80, 60, 200), alpha=100, blur=3)

    ImageDraw.Draw(img).ellipse((mx-1, my-1, mx+1, my+1), fill=_INDIGO_HOT)

    out = os.path.join(_UNIT_DIR, "splitter.png")
    img.save(out)
    print(f"[rogue-art] ✅ {out}  (32×32)")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[rogue-art-full] Generating all Rogue AI sprites…\n")
    make_logic_core()
    make_quantum_array()
    make_plasma_tower()
    make_observer()
    make_ravager()
    make_coder()
    make_splitter()
    print("\n[rogue-art-full] ✅ All 7 assets generated.")
