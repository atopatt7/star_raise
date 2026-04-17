#!/usr/bin/env python3
"""
generate_sci_fi_art.py — Star Raise
Advanced procedural 2.5D isometric sprite generator (PIL-only, offline).

Renders 12 transparent PNGs:
  6 buildings  96×96 px  (rendered at 192×192, LANCZOS downscaled)
  6 units      56×56 px  (rendered at 112×112, LANCZOS downscaled)

Run from project root:  python scripts/generate_sci_fi_art.py
"""

from PIL import Image, ImageDraw
import math, os

# ═══════════════════════ PALETTE ═════════════════════════════════════════════

ST_HI  = (215, 228, 242)   # steel highlight
ST_MID = (148, 163, 178)   # steel mid
ST_LO  = ( 82,  92, 105)   # steel shadow
ST_DK  = ( 35,  40,  50)   # near-black outline

BL_HI  = (135, 190, 255)   # blue armor highlight
BL_MID = ( 65, 118, 205)   # blue armor mid
BL_LO  = ( 28,  58, 145)   # blue armor dark

GN_HI  = ( 90, 230, 120)   # green glow light
GN_LO  = ( 22, 130,  52)   # green glow dark

CY     = (  0, 225, 255)   # cyan neon
OR     = (255, 148,  28)   # orange glow
RD     = (255,  42,  42)   # red
YW     = (255, 205,   0)   # yellow warning
PU_HI  = (130,  75, 205)   # purple light
PU_LO  = ( 48,  22,  80)   # purple dark
WH     = (235, 248, 255)   # near white
BK     = ( 12,  14,  20)   # near black
TN_HI  = (200, 168,  98)   # tan / sand light
TN_LO  = (115,  88,  40)   # tan / sand dark
GRN_HI = (105, 128,  95)   # military green light
GRN_LO = ( 52,  68,  44)   # military green dark
GRN_DK = ( 32,  45,  28)   # military green darkest


def A(c, a=255):
    """RGB tuple → RGBA tuple."""
    return (c[0], c[1], c[2], a)


# ═══════════════════ ISOMETRIC PRIMITIVES ════════════════════════════════════

def iso(x, y, z, ox, oy, S):
    """
    World (x, y, z) → screen (sx, sy).
    Standard 2:1 isometric projection with scale S px/unit.
    Camera looks from north-east, above.
    """
    sx = ox + (x - y) * S
    sy = oy + (x + y) * (S / 2) - z * S
    return (int(sx), int(sy))


def ibox(draw, x0, y0, z0, x1, y1, z1, ox, oy, S,
         tc, rc, fc, ol=None):
    """
    Draw a solid isometric box (x0,y0,z0)→(x1,y1,z1).
    tc = top face colour (brightest)
    rc = right face colour, x=x1  (medium)
    fc = front face colour, y=y1  (darkest)
    ol = optional outline colour
    """
    p = lambda x, y, z: iso(x, y, z, ox, oy, S)

    top   = [p(x0,y0,z1), p(x1,y0,z1), p(x1,y1,z1), p(x0,y1,z1)]
    right = [p(x1,y0,z0), p(x1,y1,z0), p(x1,y1,z1), p(x1,y0,z1)]
    front = [p(x0,y1,z0), p(x1,y1,z0), p(x1,y1,z1), p(x0,y1,z1)]

    # painter order: right, front, top (top sits "above" the sides)
    draw.polygon(right, fill=A(rc), outline=A(ol) if ol else None)
    draw.polygon(front, fill=A(fc), outline=A(ol) if ol else None)
    draw.polygon(top,   fill=A(tc), outline=A(ol) if ol else None)


def glow(draw, cx, cy, r, color, rings=5, max_a=200):
    """Soft neon glow: several transparent halos + solid core."""
    for i in range(rings, 0, -1):
        a = int(max_a * (i / rings) ** 2)
        er = r + (rings - i) * 4
        draw.ellipse([cx-er, cy-er, cx+er, cy+er], fill=(*color[:3], a))
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*color[:3], 255))


def shadow(draw, cx, cy, rx, ry):
    """Ground shadow ellipse."""
    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=(*BK, 42))


# ═══════════════ CANVAS HELPERS ══════════════════════════════════════════════

def bcanvas():
    return Image.new("RGBA", (192, 192), (0, 0, 0, 0))   # 2× building


def ucanvas():
    return Image.new("RGBA", (112, 112), (0, 0, 0, 0))   # 2× unit


def bsave(img, name):
    path = f"assets/buildings/{name}.png"
    os.makedirs("assets/buildings", exist_ok=True)
    img.resize((96, 96), Image.LANCZOS).save(path)
    print(f"  ✓  {path}")


def usave(img, name):
    path = f"assets/units/{name}.png"
    os.makedirs("assets/units", exist_ok=True)
    img.resize((56, 56), Image.LANCZOS).save(path)
    print(f"  ✓  {path}")


# Building canvas constants  (2× = 192×192)
BOX = 96    # origin X
BOY = 110   # origin Y  — bottom of a (5,5,0) box lands at ~190
BS  = 16    # scale (px / iso unit)

# Unit canvas constants  (2× = 112×112)
UOX = 56
UOY = 78
US  = 10


# ═══════════════════════ BUILDINGS ═══════════════════════════════════════════

# ── 1. Barracks ──────────────────────────────────────────────────────────────
def gen_barracks():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 14, 72, 14)

    # Steel base platform
    ibox(d, 0,0,0, 5,5,0.5, BOX,BOY,BS, ST_HI,ST_MID,ST_LO, ST_DK)

    # Blue armored main tower (3×3, centred on 5×5 base)
    ibox(d, 1,1,0.5, 4,4,3.0, BOX,BOY,BS, BL_HI,BL_MID,BL_LO, ST_DK)

    # Horizontal ridge strips on right face
    for zr in (1.0, 2.0):
        ridge = [p(4,1,zr), p(4,4,zr), p(4,4,zr+0.18), p(4,1,zr+0.18)]
        d.polygon(ridge, fill=A(BL_HI))

    # Glowing window panels on front face (y=4 side)
    for xw in (1.25, 2.7):
        win = [p(xw,4,1.0), p(xw+0.75,4,1.0),
               p(xw+0.75,4,2.5), p(xw,4,2.5)]
        d.polygon(win, fill=(*CY, 145))
        d.polygon(win, outline=A(CY), width=2)

    # Dome on top — stacked isometric ellipses
    dc = p(2.5, 2.5, 3.0)
    for i in range(9, 0, -1):
        t   = i / 9
        rx  = int(1.65 * BS * t)
        ry  = int(0.82 * BS * t)
        cy  = dc[1] - int((1 - t) * 2.9 * BS)
        col = BL_MID if i % 2 == 0 else BL_HI
        d.ellipse([dc[0]-rx, cy-ry, dc[0]+rx, cy+ry], fill=A(col))

    # Antenna + beacon
    tip_y = dc[1] - int(2.9 * BS)
    d.line([(dc[0], tip_y), (dc[0], tip_y - 22)], fill=A(ST_HI), width=3)
    glow(d, dc[0], tip_y - 24, 6, CY, rings=4)

    return img


# ── 2. Refinery ──────────────────────────────────────────────────────────────
def gen_refinery():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 12, 75, 14)

    # Main industrial block
    ibox(d, 0,0,0, 5,5,3.0, BOX,BOY,BS, ST_HI,ST_MID,ST_LO, ST_DK)

    # Chimney stack at back-right
    ibox(d, 3.6,0,3.0, 5.0,1.4,5.8, BOX,BOY,BS, ST_MID,ST_LO,ST_DK, ST_DK)

    # Chimney cap
    cap = p(4.3, 0.7, 5.8)
    d.ellipse([cap[0]-16, cap[1]-8, cap[0]+16, cap[1]+8], fill=A(ST_DK))
    glow(d, cap[0], cap[1] - 2, 7, (180, 180, 180), rings=3, max_a=100)

    # Furnace opening on front face
    furnace = [p(1.0,5,0.4), p(3.2,5,0.4), p(3.2,5,2.6), p(1.0,5,2.6)]
    d.polygon(furnace, fill=A(ST_DK))
    fc = p(2.1, 5, 1.5)
    glow(d, fc[0], fc[1], 22, OR, rings=6, max_a=210)
    d.polygon(furnace, outline=A(OR, 200), width=3)

    # Vertical orange pipe on right face
    r1 = p(5, 0.6, 0.5)
    r2 = p(5, 0.6, 3.0)
    d.line([r1, r2], fill=A(OR, 200), width=4)
    for zp in (1.0, 2.0):
        seg = [p(5,0.3,zp), p(5,1.1,zp), p(5,1.1,zp+0.28), p(5,0.3,zp+0.28)]
        d.polygon(seg, fill=A(ST_LO))

    # Warning blinker on chimney top
    wl = p(4.3, 0.7, 5.9)
    glow(d, wl[0], wl[1], 6, OR, rings=3)

    # Rooftop machinery box
    ibox(d, 0.5,0.5,3.0, 2.5,2.5,3.8, BOX,BOY,BS, ST_HI,ST_MID,ST_MID, ST_DK)

    return img


# ── 3. Rover Bay ─────────────────────────────────────────────────────────────
def gen_rover_bay():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 12, 80, 15)

    # Wide low main body (5.5 wide, 4.5 deep, 2 tall)
    ibox(d, 0,0,0, 5.5,4.5,2.0, BOX,BOY,BS, ST_HI,ST_MID,ST_LO, ST_DK)

    # Roof lip (slightly lighter strip)
    roof = [p(0,0,2.0), p(5.5,0,2.0), p(5.5,4.5,2.0), p(0,4.5,2.0)]
    d.polygon(roof, fill=A(ST_HI), outline=A(ST_DK))

    # Large garage door on front face (y=4.5)
    door = [p(0.7,4.5,0.0), p(4.5,4.5,0.0), p(4.5,4.5,1.75), p(0.7,4.5,1.75)]
    d.polygon(door, fill=A(ST_DK))

    # Cyan door-frame glow strip
    dtop = [p(0.7,4.5,1.60), p(4.5,4.5,1.60), p(4.5,4.5,1.78), p(0.7,4.5,1.78)]
    d.polygon(dtop, fill=(*CY, 200))

    # Interior glow
    gc = p(2.6, 4.5, 0.9)
    d.ellipse([gc[0]-32, gc[1]-13, gc[0]+32, gc[1]+13], fill=(*CY, 22))

    # Vehicle tracks in front
    for tx in (1.4, 3.4):
        t1 = iso(tx, 4.5, 0, BOX, BOY, BS)
        t2 = iso(tx, 6.0, 0, BOX, BOY, BS)
        d.line([t1[0], t1[1]+5, t2[0], t2[1]+5], fill=A(ST_LO, 140), width=4)

    # Side vents on right face
    for zv in (0.5, 1.2):
        vent = [p(5.5,0.8,zv), p(5.5,2.5,zv), p(5.5,2.5,zv+0.28), p(5.5,0.8,zv+0.28)]
        d.polygon(vent, fill=A(ST_LO))

    # Satellite dish on roof
    ant = p(4.8, 0.8, 2.0)
    d.line([(ant[0], ant[1]), (ant[0], ant[1]-22)], fill=A(ST_MID), width=4)
    glow(d, ant[0], ant[1]-24, 8, CY, rings=3)

    return img


# ── 4. Spec Ops ──────────────────────────────────────────────────────────────
def gen_spec_ops():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 14, 45, 12)

    # Wide armoured base ring
    ibox(d, 0.5,0.5,0, 4.5,4.5,1.0, BOX,BOY,BS, ST_MID,ST_LO,ST_DK, ST_DK)

    # Mid platform (purple-dark)
    ibox(d, 1.0,1.0,1.0, 4.0,4.0,2.0, BOX,BOY,BS, PU_HI,PU_LO,PU_LO, ST_DK)

    # Tall narrow spire
    ibox(d, 1.8,1.8,2.0, 3.2,3.2,6.2, BOX,BOY,BS, PU_HI,PU_LO,BK, ST_DK)

    # Sensor ring at spire mid-height
    ring = [p(1.5,1.5,4.1), p(3.5,1.5,4.1), p(3.5,3.5,4.1), p(1.5,3.5,4.1)]
    d.polygon(ring, outline=A(GN_HI), width=4)
    for sx, sy in ((1.5,1.5),(3.5,1.5),(3.5,3.5),(1.5,3.5)):
        sc = p(sx, sy, 4.1)
        glow(d, sc[0], sc[1], 5, GN_HI, rings=3)

    # Apex pyramid
    base4 = [p(1.8,1.8,6.2), p(3.2,1.8,6.2), p(3.2,3.2,6.2), p(1.8,3.2,6.2)]
    tip   = p(2.5, 2.5, 7.4)
    for i in range(4):
        face = [base4[i], base4[(i+1)%4], tip]
        d.polygon(face, fill=A(PU_HI if i < 2 else PU_LO))

    # Antenna tip with strong green beacon
    ant = p(2.5, 2.5, 7.4)
    d.line([(ant[0], ant[1]), (ant[0], ant[1]-20)], fill=A(ST_HI), width=3)
    glow(d, ant[0], ant[1]-22, 8, GN_HI, rings=5, max_a=230)

    # Side micro-antennae
    for sx, sy in ((1.8,1.8),(3.2,1.8)):
        ac = p(sx, sy, 3.6)
        d.line([(ac[0], ac[1]), (ac[0]-5, ac[1]-18)], fill=A(ST_MID), width=2)
        d.ellipse([ac[0]-8, ac[1]-21, ac[0]-1, ac[1]-14], fill=A(GN_LO))

    return img


# ── 5. Heavy Factory ─────────────────────────────────────────────────────────
def gen_heavy_factory():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 12, 80, 16)

    # Massive main body
    ibox(d, 0,0,0, 5.5,4.8,3.5, BOX,BOY,BS, ST_MID,ST_LO,ST_DK, ST_DK)

    # Outer reinforcement skirt
    ibox(d, -0.12,-0.12,0, 5.62,4.92,0.55, BOX,BOY,BS, ST_HI,ST_MID,ST_MID, ST_DK)

    # Yellow/black warning stripes on front face (y=4.8)
    stripe_z = 0.55
    sw = 0.42
    for i in range(8):
        z0s = stripe_z + i * sw
        z1s = z0s + sw * 0.55
        col = YW if i % 2 == 0 else BK
        pts = [p(0,4.8,z0s), p(5.5,4.8,z0s), p(5.5,4.8,z1s), p(0,4.8,z1s)]
        d.polygon(pts, fill=A(col, 210))

    # Heavy reinforced blast door (dark, on front face)
    port = [p(1.5,4.8,1.4), p(4.0,4.8,1.4), p(4.0,4.8,3.5), p(1.5,4.8,3.5)]
    d.polygon(port, fill=A(ST_DK))
    d.polygon(port, outline=A(YW, 180), width=3)

    # Bolted cross on blast door
    mid_x  = p(2.75,4.8,2.45)
    left_x = p(1.5, 4.8,2.45)
    rght_x = p(4.0, 4.8,2.45)
    bot_x  = p(2.75,4.8,1.4)
    top_x  = p(2.75,4.8,3.5)
    d.line([left_x, rght_x], fill=A(YW, 130), width=3)
    d.line([bot_x,  top_x],  fill=A(YW, 130), width=3)

    # Rooftop ventilation boxes
    ibox(d, 1.8,0.4,3.5, 4.0,2.0,4.2, BOX,BOY,BS, ST_HI,ST_MID,ST_MID, ST_DK)
    ibox(d, 0.4,2.8,3.5, 2.0,4.4,4.0, BOX,BOY,BS, ST_HI,ST_MID,ST_MID, ST_DK)

    # Warning lights
    for wx, wy in ((0.8,0.8),(4.8,0.8),(0.8,4.1),(4.8,4.1)):
        wc = p(wx, wy, 3.65)
        glow(d, wc[0], wc[1], 5, YW, rings=3)

    return img


# ── 6. Starport ──────────────────────────────────────────────────────────────
def gen_starport():
    img = bcanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, BOX, BOY, BS)

    shadow(d, BOX, BOY + 14, 82, 16)

    N_RIM   = 8
    CX_PAD  = 2.8
    CY_PAD  = 2.8
    R_OUTER = 2.8
    R_INNER = 2.2

    def pad_p(angle_deg, r, z):
        a  = math.radians(angle_deg)
        wx = CX_PAD + r * math.cos(a)
        wy = CY_PAD + r * math.sin(a)
        return iso(wx, wy, z, BOX, BOY, BS)

    # Outer rim top + sides
    outer_top = [pad_p(i*360/N_RIM, R_OUTER, 0.55) for i in range(N_RIM)]
    outer_bot = [pad_p(i*360/N_RIM, R_OUTER, 0.00) for i in range(N_RIM)]
    for i in range(N_RIM):
        j    = (i + 1) % N_RIM
        face = [outer_top[i], outer_top[j], outer_bot[j], outer_bot[i]]
        ang  = (i * 360/N_RIM + 180/N_RIM) % 360
        col  = ST_MID if ang < 180 else ST_LO
        d.polygon(face, fill=A(col))
    d.polygon(outer_top, fill=A(ST_MID))

    # Inner landing deck
    inner_top = [pad_p(i*360/N_RIM, R_INNER, 0.38) for i in range(N_RIM)]
    d.polygon(inner_top, fill=A(ST_HI))

    # Dark centre circle
    cen = p(CX_PAD, CY_PAD, 0.40)
    d.ellipse([cen[0]-32, cen[1]-18, cen[0]+32, cen[1]+18], fill=A(ST_DK))

    # Yellow "H" marking
    hx, hy = cen[0], cen[1]
    for lx in (hx-17, hx+17):
        d.rectangle([lx-3, hy-11, lx+3, hy+11], fill=A(YW))
    d.rectangle([hx-17, hy-3, hx+17, hy+3], fill=A(YW))

    # Cyan runway lights
    for i in range(N_RIM):
        lp = pad_p(i*360/N_RIM, R_INNER - 0.1, 0.58)
        glow(d, lp[0], lp[1], 4, CY, rings=3, max_a=210)

    # Control tower (back-right)
    ibox(d, 4.2,0,0, 5.5,1.1,4.6, BOX,BOY,BS, ST_HI,ST_MID,ST_LO, ST_DK)
    for wz in (2.6, 3.6):
        win = [p(5.5,0.15,wz), p(5.5,0.95,wz), p(5.5,0.95,wz+0.58), p(5.5,0.15,wz+0.58)]
        d.polygon(win, fill=(*CY, 160))
    glow(d, *p(4.85, 0.55, 4.65)[:2], 7, CY, rings=3)

    return img


# ═══════════════════════ UNITS ════════════════════════════════════════════════

# ── 1. Marine ────────────────────────────────────────────────────────────────
def gen_marine():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    shadow(d, UOX, UOY + 8, 22, 8)

    # Boots
    ibox(d,1.0,1.5,0.0, 1.85,2.45,0.45, UOX,UOY,US, ST_LO,ST_DK,ST_DK)
    ibox(d,2.15,1.5,0.0, 3.0,2.45,0.45, UOX,UOY,US, ST_LO,ST_DK,ST_DK)

    # Legs
    ibox(d,1.1,1.6,0.45, 1.9,2.4,1.55, UOX,UOY,US, BL_MID,BL_LO,BL_LO)
    ibox(d,2.1,1.6,0.45, 2.9,2.4,1.55, UOX,UOY,US, BL_MID,BL_LO,BL_LO)

    # Torso (blue armour)
    ibox(d,0.75,1.35,1.55, 3.25,2.65,3.05, UOX,UOY,US, BL_HI,BL_MID,BL_LO, ST_DK)

    # Backpack
    ibox(d,0.85,1.35,1.7, 1.25,1.55,2.85, UOX,UOY,US, ST_MID,ST_LO,ST_DK)

    # Shoulder pads
    ibox(d,0.40,1.45,2.85, 1.25,2.55,3.35, UOX,UOY,US, BL_HI,BL_MID,BL_MID)
    ibox(d,2.75,1.45,2.85, 3.60,2.55,3.35, UOX,UOY,US, BL_HI,BL_MID,BL_MID)

    # Helmet
    hcx, hcy = p(2.0, 2.0, 3.65)
    d.ellipse([hcx-14, hcy-14, hcx+14, hcy+14], fill=A(BL_MID))
    d.ellipse([hcx-14, hcy-14, hcx+14, hcy+14], outline=A(ST_DK), width=2)

    # Visor slit (white with cyan border)
    d.rectangle([hcx-10, hcy-4, hcx+10, hcy+3], fill=(*WH, 210))
    d.rectangle([hcx-10, hcy-4, hcx+10, hcy+3], outline=A(CY, 160), width=1)

    # Gun arm
    ibox(d,2.85,1.0,2.25, 3.45,1.85,2.7, UOX,UOY,US, ST_HI,ST_MID,ST_LO)
    gb1 = p(3.45, 1.2, 2.48)
    gb2 = p(5.35, 0.3, 2.48)
    d.line([gb1, gb2], fill=A(ST_DK), width=6)
    d.line([gb1, gb2], fill=A(ST_MID), width=4)
    glow(d, gb2[0], gb2[1], 4, YW, rings=2, max_a=110)

    return img


# ── 2. Tank ──────────────────────────────────────────────────────────────────
def gen_tank():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    shadow(d, UOX, UOY + 6, 32, 10)

    # Treads (dark, slightly wider than hull)
    ibox(d,-0.25,0.3,0, 0.55,4.7,0.85, UOX,UOY,US, ST_DK,BK,BK)
    ibox(d, 4.45,0.3,0, 5.25,4.7,0.85, UOX,UOY,US, ST_DK,BK,BK)

    # Tread grip notches
    for i in range(5):
        z0 = 0.08 + i * 0.15
        sl = [p(-0.25, 0.5+i*0.88, z0), p(0.55, 0.5+i*0.88, z0),
              p(0.55,  0.5+i*0.88, z0+0.1), p(-0.25, 0.5+i*0.88, z0+0.1)]
        d.polygon(sl, fill=(*ST_MID, 120))

    # Hull body (military green)
    ibox(d, 0.5,0.4,0.85, 4.5,4.6,2.05, UOX,UOY,US, GRN_HI,GRN_LO,GRN_DK, ST_DK)

    # Sloped front glacis
    slop = [p(0.5,4.6,2.05), p(4.5,4.6,2.05), p(4.75,4.6,0.85), p(0.25,4.6,0.85)]
    d.polygon(slop, fill=A(GRN_DK))
    d.polygon(slop, outline=A(ST_DK), width=1)

    # Turret
    ibox(d, 1.4,1.5,2.05, 3.6,3.5,3.1, UOX,UOY,US, GRN_HI,GRN_LO,GRN_DK, ST_DK)

    # Cannon barrel
    cb1 = p(3.6, 2.0, 2.6)
    cb2 = p(6.8, 0.1, 2.6)
    d.line([cb1, cb2], fill=A(ST_DK), width=9)
    d.line([cb1, cb2], fill=A(ST_LO), width=6)
    d.ellipse([cb2[0]-5, cb2[1]-3, cb2[0]+5, cb2[1]+3], fill=A(ST_DK))

    # Hatch
    hc = p(2.0, 2.4, 3.1)
    d.ellipse([hc[0]-10, hc[1]-7, hc[0]+10, hc[1]+7], fill=A(GRN_LO))
    d.ellipse([hc[0]-10, hc[1]-7, hc[0]+10, hc[1]+7], outline=A(ST_DK), width=2)

    return img


# ── 3. Jackal ────────────────────────────────────────────────────────────────
def gen_jackal():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    shadow(d, UOX, UOY + 7, 30, 10)

    # 4 wheels
    WHL = (38, 40, 44, 255)
    WHH = (68, 72, 76, 255)
    for wx, wy in ((0.3,0.5),(0.3,3.8),(4.2,0.5),(4.2,3.8)):
        wc = p(wx, wy, 0.65)
        d.ellipse([wc[0]-13, wc[1]-9, wc[0]+13, wc[1]+9], fill=WHL)
        d.ellipse([wc[0]-9,  wc[1]-6, wc[0]+9,  wc[1]+6], fill=WHH)
        d.ellipse([wc[0]-3,  wc[1]-2, wc[0]+3,  wc[1]+2], fill=(*ST_DK, 255))

    # Low chassis
    ibox(d, 0.5,0.4,0.65, 4.5,4.1,1.25, UOX,UOY,US, TN_HI,TN_HI,TN_LO, ST_DK)

    # Roll cage bars
    cage = [
        [p(0.5,0.4,1.25), p(4.5,0.4,1.25)],
        [p(0.5,4.1,1.25), p(4.5,4.1,1.25)],
        [p(0.5,0.4,1.25), p(0.5,4.1,1.25)],
        [p(4.5,0.4,1.25), p(4.5,4.1,1.25)],
    ]
    for pair in cage:
        d.line(pair, fill=A(ST_MID), width=3)

    # Mini turret
    ibox(d,1.8,1.5,1.25, 3.2,3.0,1.95, UOX,UOY,US, ST_HI,ST_MID,ST_LO, ST_DK)
    gb1 = p(3.2, 1.8, 1.65)
    gb2 = p(4.8, 0.8, 1.65)
    d.line([gb1, gb2], fill=A(ST_DK), width=5)
    d.line([gb1, gb2], fill=A(ST_LO), width=3)

    # Headlights
    for hx in (1.2, 3.5):
        hc = p(hx, 4.1, 0.95)
        glow(d, hc[0], hc[1], 5, YW, rings=3, max_a=180)

    return img


# ── 4. Ghost ─────────────────────────────────────────────────────────────────
def gen_ghost():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    shadow(d, UOX, UOY + 9, 14, 6)   # faint — stealthy

    CLOAK_HI = (58,  62,  80)
    CLOAK_MD = (28,  30,  42)
    CLOAK_DK = (12,  14,  22)

    # Flowing cloak bottom
    cloak = [p(0.9,1.1,0), p(3.1,1.1,0), p(3.1,3.5,0), p(0.9,3.5,0)]
    d.polygon(cloak, fill=A(CLOAK_DK))

    # Slim legs
    ibox(d,1.3,1.6,0, 1.9,2.5,1.5, UOX,UOY,US, CLOAK_MD,CLOAK_DK,CLOAK_DK)
    ibox(d,2.1,1.6,0, 2.7,2.5,1.5, UOX,UOY,US, CLOAK_MD,CLOAK_DK,CLOAK_DK)

    # Torso
    ibox(d,1.0,1.3,1.5, 3.0,2.7,3.25, UOX,UOY,US, CLOAK_HI,CLOAK_MD,CLOAK_DK, ST_DK)

    # Hood
    hcx, hcy = p(2.0, 2.0, 3.85)
    d.ellipse([hcx-12, hcy-14, hcx+12, hcy+14], fill=A(CLOAK_MD))
    d.ellipse([hcx-12, hcy-14, hcx+12, hcy+14], outline=A(CLOAK_DK), width=2)

    # Red visor
    d.rectangle([hcx-8, hcy-3, hcx+8, hcy+3], fill=(*RD, 220))
    glow(d, hcx+6, hcy, 3, RD, rings=2, max_a=160)

    # Long sniper rifle
    rb1 = p(3.0, 1.5, 2.6)
    rb2 = p(6.6, -0.6, 2.6)
    d.line([rb1, rb2], fill=A(CLOAK_DK), width=7)
    d.line([rb1, rb2], fill=A(ST_LO), width=4)

    # Scope
    sc = p(4.5, 0.8, 2.78)
    d.ellipse([sc[0]-5, sc[1]-3, sc[0]+5, sc[1]+3], fill=(*RD, 160))

    # Suppressor
    d.ellipse([rb2[0]-4, rb2[1]-3, rb2[0]+4, rb2[1]+3], fill=A(ST_DK))

    # Laser trace
    laser = (rb2[0]+36, rb2[1]-18)
    d.line([rb2, laser], fill=(*RD, 35), width=1)
    glow(d, laser[0], laser[1], 3, RD, rings=2, max_a=75)

    return img


# ── 5. Hellfire ──────────────────────────────────────────────────────────────
def gen_hellfire():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    shadow(d, UOX, UOY + 6, 30, 10)

    HULL_HI = (128, 118, 102)
    HULL_MD = ( 85,  78,  65)
    HULL_DK = ( 48,  44,  36)

    # Treads
    ibox(d,-0.2,0.4,0, 0.6,4.6,0.72, UOX,UOY,US, ST_DK,BK,BK)
    ibox(d, 4.4,0.4,0, 5.2,4.6,0.72, UOX,UOY,US, ST_DK,BK,BK)

    # Chassis
    ibox(d, 0.5,0.3,0.72, 4.5,4.7,2.1, UOX,UOY,US, HULL_HI,HULL_MD,HULL_DK, ST_DK)

    # Launcher base bed
    ibox(d,0.7,0.6,2.1, 4.3,4.4,2.55, UOX,UOY,US, ST_MID,ST_LO,ST_DK, ST_DK)

    # 6 missile tubes (3 × 2 grid)
    for row, ty in enumerate((0.75, 2.45)):
        for col, tx in enumerate((1.0, 2.3, 3.6)):
            ibox(d, tx, ty, 2.55, tx+0.68, ty+0.76, 4.55,
                 UOX,UOY,US, ST_MID,ST_LO,ST_DK)
            # Missile tip (orange warhead)
            tip = p(tx+0.34, ty+0.38, 4.55)
            d.ellipse([tip[0]-5, tip[1]-6, tip[0]+5, tip[1]+6], fill=A(OR))
            d.ellipse([tip[0]-2, tip[1]-3, tip[0]+2, tip[1]+3], fill=A(YW))

    # Engine exhausts at back
    for ex, ey in ((1.0, 0.3),(3.5, 0.3)):
        ec = p(ex, ey, 1.2)
        glow(d, ec[0], ec[1], 7, OR, rings=3, max_a=170)

    return img


# ── 6. Valkyrie ──────────────────────────────────────────────────────────────
def gen_valkyrie():
    img = ucanvas()
    d   = ImageDraw.Draw(img)
    p   = lambda x, y, z: iso(x, y, z, UOX, UOY, US)

    # Ground shadow far below (aircraft is flying)
    d.ellipse([UOX-30, UOY+18, UOX+30, UOY+30], fill=(*BK, 35))

    FZ = 3.0   # flying altitude offset

    HULL_HI = (165, 175, 190)
    HULL_MD = (112, 122, 138)
    HULL_DK = ( 68,  75,  86)

    # Swept left wing
    lw = [p(  -0.2,1.9,FZ+0.3), p(1.5,1.4,FZ+0.3),
           p(  1.5,3.6,FZ+0.3), p(-0.6,4.6,FZ+0.3)]
    d.polygon(lw, fill=A(HULL_MD))
    d.polygon(lw, outline=A(ST_DK), width=2)

    # Swept right wing
    rw = [p(5.2,1.9,FZ+0.3), p(3.5,1.4,FZ+0.3),
           p(3.5,3.6,FZ+0.3), p(5.6,4.6,FZ+0.3)]
    d.polygon(rw, fill=A(HULL_MD))
    d.polygon(rw, outline=A(ST_DK), width=2)

    # Wing leading-edge highlight
    d.line([p(-0.2,1.9,FZ+0.3), p(1.5,1.4,FZ+0.3)], fill=A(HULL_HI), width=3)
    d.line([p(5.2,1.9,FZ+0.3), p(3.5,1.4,FZ+0.3)], fill=A(HULL_HI), width=3)

    # Fuselage body
    ibox(d, 1.5,0.8,FZ, 3.5,4.2,FZ+0.95, UOX,UOY,US,
         HULL_HI, HULL_MD, HULL_DK, ST_DK)

    # Tail fin
    tail = [p(2.2,0.8,FZ+0.95), p(2.8,0.8,FZ+0.95),
             p(2.8,0.8,FZ+1.9),  p(2.2,0.8,FZ+1.9)]
    d.polygon(tail, fill=A(HULL_MD))
    d.polygon(tail, outline=A(ST_DK), width=1)

    # Cockpit canopy (translucent blue)
    cp = p(2.5, 1.5, FZ+0.95)
    d.ellipse([cp[0]-15, cp[1]-9, cp[0]+15, cp[1]+9], fill=(*BL_LO, 180))
    d.ellipse([cp[0]-15, cp[1]-9, cp[0]+15, cp[1]+9], outline=(*CY, 120), width=2)
    d.ellipse([cp[0]-8,  cp[1]-6, cp[0]+2,  cp[1]-1], fill=(*WH, 95))

    # Twin engines with strong cyan glow
    for ex, ey in ((0.9, 2.5),(4.1, 2.5)):
        ec = p(ex, ey, FZ+0.25)
        glow(d, ec[0], ec[1], 9, CY, rings=5, max_a=210)
        # Exhaust trail
        t1 = p(ex, ey-0.5, FZ+0.22)
        t2 = p(ex, ey-2.2, FZ+0.22)
        d.line([t1, t2], fill=(*CY, 55), width=5)

    # Missile hard-points under wings
    for mx, my in ((0.4, 3.2),(4.6, 3.2)):
        ibox(d, mx, my, FZ, mx+0.5, my+0.45, FZ+0.28,
             UOX,UOY,US, OR, (200,105,0), (145,75,0))

    return img


# ═══════════════════════ MAIN ═════════════════════════════════════════════════

GENERATORS = [
    (bsave, "barracks",      gen_barracks),
    (bsave, "refinery",      gen_refinery),
    (bsave, "rover_bay",     gen_rover_bay),
    (bsave, "spec_ops",      gen_spec_ops),
    (bsave, "heavy_factory", gen_heavy_factory),
    (bsave, "starport",      gen_starport),
    (usave, "marine",        gen_marine),
    (usave, "tank",          gen_tank),
    (usave, "jackal",        gen_jackal),
    (usave, "ghost",         gen_ghost),
    (usave, "hellfire",      gen_hellfire),
    (usave, "valkyrie",      gen_valkyrie),
]

if __name__ == "__main__":
    print("🎨  Generating advanced procedural sci-fi sprites…\n")
    for save_fn, name, gen_fn in GENERATORS:
        img = gen_fn()
        save_fn(img, name)
    print(f"\n✅  Done — {len(GENERATORS)} sprites written.")
