"""
generate_missing_art.py - Star Raise 2.5D isometric pixel art (60-degree view)
Draw at 4x with pygame (no anti-aliasing), NEAREST-scale to target size.
Coordinate system: x=screen-right, y=screen-depth(left), z=up
"""
import os, math
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from PIL import Image
import traceback

pygame.init()
pygame.display.set_mode((1, 1))

OUT_DIR = os.path.join("assets", "units")
os.makedirs(OUT_DIR, exist_ok=True)

SC = 4   # draw scale: 4x then NEAREST down

# ── Colour palette (sampled from existing sprites) ─────────────────────────
BLK  = (18,  10,  28)

# Swarm purples  (crawl er: #281e32 / #3c1e50 / #78419e / a05ac8)
SP0  = (28,  18,  40)
SP1  = (60,  28,  80)
SP2  = (120, 62, 160)
SP3  = (168,100, 218)
# Swarm green acid  (crawler eye: #39ff14 style)
SA0  = (30, 130,   8)
SA1  = (80, 220,  18)
SA2  = (185,255,  80)
# Swarm red-bone
SR0  = (140, 22,  22)
SR1  = (210, 55,  55)
SB0  = (195,178, 145)
SB1  = (232,215, 185)
# Swarm brown (impaler)
SBR0 = (48,  18,   8)
SBR1 = (88,  40,  16)
SBR2 = (128, 64,  28)
# Rogue AI greys  (ravager/splitter: #1e1e26 / #444452 / #6e6e82 / #aaaabe)
RG0  = (30,  30,  38)
RG1  = (68,  68,  82)
RG2  = (110,112, 132)
RG3  = (168,170, 192)
# Rogue AI crimson  (ravager visor: #b41428)
RC0  = (180, 20,  40)
RC1  = (230, 55,  70)
RC2  = (255,135, 148)
# Rogue AI blue sensor
RB0  = (55, 175, 255)
RB1  = (180,235, 255)

def shade(c, f):
    return tuple(min(255, max(0, int(x*f))) for x in c)

# ── Isometric rendering core ────────────────────────────────────────────────
def ip(cx, cy, x, y, z, t):
    """World (x,y,z) -> screen px at 4x.  t = tile size in 4x-pixels."""
    return (int(cx + (x - y) * t), int(cy + (x + y) * t // 2 - z * t))

def ibox(surf, cx, cy, x0, y0, z0, w, d, h, t,
         top, left, right, edge=BLK):
    """Draw one isometric box back-to-front (painter's algorithm).
       top/left/right = None skips that face."""
    x1, y1, z1 = x0+w, y0+d, z0+h
    def p(x, y, z): return ip(cx, cy, x, y, z, t)
    rp = [p(x1,y0,z0), p(x1,y1,z0), p(x1,y1,z1), p(x1,y0,z1)]
    lp = [p(x0,y1,z0), p(x1,y1,z0), p(x1,y1,z1), p(x0,y1,z1)]
    tp = [p(x0,y0,z1), p(x1,y0,z1), p(x1,y1,z1), p(x0,y1,z1)]
    if right: pygame.draw.polygon(surf, right, rp)
    if left:  pygame.draw.polygon(surf, left,  lp)
    if top:   pygame.draw.polygon(surf, top,   tp)
    if edge:
        for fp in (rp, lp, tp):
            pygame.draw.polygon(surf, edge, fp, 1)

def mk(w, h):
    return pygame.Surface((w*SC, h*SC), pygame.SRCALPHA)

def save_png(surf, name, w, h):
    raw = pygame.image.tostring(surf, "RGBA")
    pil = Image.frombytes("RGBA", (w*SC, h*SC), raw)
    pil = pil.resize((w, h), Image.NEAREST)
    pil.save(os.path.join(OUT_DIR, f"{name}.png"))
    print(f"OK  {name}.png", flush=True)

def shadow_iso(surf, cx, cy, rx, ry, t):
    """Draw elliptical ground shadow in isometric plane."""
    # 4 corners of iso ellipse at z=0
    pts = [ip(cx,cy, -rx, 0, 0, t), ip(cx,cy, 0, -ry, 0, t),
           ip(cx,cy,  rx, 0, 0, t), ip(cx,cy, 0,  ry, 0, t)]
    pygame.draw.polygon(surf, (12, 8, 22, 100), pts)

# ══════════════════════════════════════════════════════════════════════════════
# SWARM UNITS  ── organic + isometric blend
# ══════════════════════════════════════════════════════════════════════════════

def draw_crusher():
    """Heavy siege beetle -- domed carapace, 6 legs, bone-white armour strips, forward mandibles."""
    W, H = 68, 68
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*3
    T = 10

    shadow_iso(surf, cx, cy, 3.0, 2.5, T)

    # -- 3 legs per side, fan out wide (draw before body)
    for i in range(3):
        body_y = -0.3 + i * 0.9
        for sgn in (-1, 1):
            p0 = ip(cx, cy, sgn * 2.5, body_y, 0.6, T)
            p1 = ip(cx, cy, sgn * 5.2, body_y + 0.4, 0.0, T)
            pygame.draw.line(surf, BLK, p0, p1, SC*2)
            pygame.draw.line(surf, SP1, p0, p1, SC*1)

    # -- Lower body slab (wide flat base)
    ibox(surf, cx, cy, -2.5, -1.5, 0,   5.0, 3.5, 1.2, T, SP1, SP0, shade(SP0, 0.7))

    # -- Main carapace dome (narrower at base, built up in 3 tiers)
    ibox(surf, cx, cy, -2.2, -1.2, 1.2,  4.4, 3.0, 1.8, T, SP2, SP1, SP0)
    ibox(surf, cx, cy, -1.8, -0.9, 3.0,  3.6, 2.5, 1.6, T, SP3, SP2, SP1)
    ibox(surf, cx, cy, -1.3, -0.6, 4.6,  2.6, 1.8, 1.0, T, shade(SP3,1.1), SP3, SP2)

    # -- Bone armour ridge strips (5 across carapace top)
    for i in range(5):
        bw = 3.2 - i * 0.3
        ibox(surf, cx, cy, -bw/2, -0.8 + i*0.56, 3.0,
             bw, 0.4, 0.28, T, SB1, SB0, shade(SB0, 0.8))

    # -- Dorsal spines (3 nubs on centre ridge)
    for i in range(3):
        ibox(surf, cx, cy, -0.35, -0.4 + i*0.9, 5.4,
             0.7, 0.5, 0.7, T, SB1, SB0, shade(SB0, 0.8))

    # -- Head (projects forward, negative-y = toward viewer/right-of-body)
    ibox(surf, cx, cy, -1.6, -2.5, 0.5,   3.2, 1.2, 2.8, T, SP2, SP1, SP0)

    # -- Twin mandibles
    for sgn in (-1, 1):
        ox = sgn * 0.5
        ibox(surf, cx, cy, ox, -3.5, 1.0,  0.8, 1.2, 0.5, T, SB1, SB0, shade(SB0,0.8))
        ibox(surf, cx, cy, ox, -4.5, 1.2,  0.8, 0.7, 0.35, T, SB1, SB1, SB0)

    # -- Compound eyes
    for sgn in (-1, 1):
        ep = ip(cx, cy, sgn * 0.8, -2.5, 2.5, T)
        pygame.draw.circle(surf, BLK, ep, SC*2)
        pygame.draw.circle(surf, SA1,  ep, SC*1)

    save_png(surf, "crusher", W, H)


def draw_weaver():
    """Flying ink-moth -- vertical body, two pairs of wings, glowing acid sac."""
    W, H = 56, 56
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*3
    T = 9   # compact so wings fit

    GD0 = (18, 55, 18);  GD1 = (38, 100, 30);  GD2 = (62, 140, 50)

    shadow_iso(surf, cx, cy, 2.5, 2.0, T)

    # ── Acid sac / abdomen (tail, drawn first = behind) ──
    sp = ip(cx, cy, 0, 1.5, 0.6, T)
    pygame.draw.circle(surf, BLK, sp, SC*5)
    pygame.draw.circle(surf, SA0, sp, SC*4)
    pygame.draw.circle(surf, SA1, sp, SC*3)
    pygame.draw.circle(surf, SA2, (sp[0], sp[1]-SC), SC*1)

    # ── Lower wings (swept backward, draw behind body) ──
    ibox(surf, cx, cy, -4.5, 0.5, 1.0,  3.5, 1.8, 0.35, T, GD0, shade(GD0,0.7), shade(GD0,0.5))
    ibox(surf, cx, cy,  1.0, 0.5, 1.0,  3.5, 1.8, 0.35, T, GD0, shade(GD0,0.7), shade(GD0,0.5))

    # ── Body (elongated thorax) ──
    ibox(surf, cx, cy, -0.9, -0.5, 0,  1.8, 2.8, 4.0, T, GD2, GD1, GD0)

    # ── Upper wings (spread wide from shoulder at z=3) ──
    ibox(surf, cx, cy, -5.0, -0.5, 2.8,  4.2, 1.4, 0.4, T, GD1, GD0, shade(GD0,0.7))
    ibox(surf, cx, cy,  0.8, -0.5, 2.8,  4.2, 1.4, 0.4, T, GD1, GD0, shade(GD0,0.7))
    # Wing vein -- a highlight line running along each upper wing
    for sgn in (-1, 1):
        root_x = sgn * 0.9
        tip_x  = sgn * 4.8
        p0 = ip(cx, cy, root_x, -0.5, 3.1, T)
        p1 = ip(cx, cy, tip_x,   0.6, 2.9, T)
        pygame.draw.line(surf, SA1, p0, p1, SC*1)

    # ── Head ──
    ibox(surf, cx, cy, -0.7, -1.6, 3.8,  1.4, 1.2, 1.6, T, GD2, GD1, GD0)

    # ── Compound eyes ──
    for sgn in (-1, 1):
        ep = ip(cx, cy, sgn * 0.5, -1.6, 4.8, T)
        pygame.draw.circle(surf, BLK, ep, SC*2)
        pygame.draw.circle(surf, SA1, ep, SC*1)

    save_png(surf, "weaver", W, H)


def draw_impaler():
    """Rearing serpent -- coiled base, upright scaly torso, lateral bone spines, fanged head."""
    W, H = 50, 50
    surf = mk(W, H)
    cx = W*SC//2 - SC;  cy = H*SC//2 + SC*4
    T = 9

    shadow_iso(surf, cx, cy, 2.0, 1.8, T)

    # -- Coiled tail base (3 overlapping boxes at z=0)
    for tx, ty, r in [(0.4, 1.0, 1.0), (-0.3, 0.2, 0.75), (0.2, -0.6, 0.55)]:
        ibox(surf, cx, cy, tx-r, ty-r, 0,  r*2, r*2, r*1.1, T, SBR2, SBR1, SBR0)

    # -- Lower torso (rising from coil)
    ibox(surf, cx, cy, -1.0, -0.5, 1.0,  2.0, 2.0, 3.0, T, SBR2, SBR1, SBR0)

    # -- Scale ridges on torso (horizontal stripes)
    for i in range(4):
        sz = 1.7 - i * 0.1
        ibox(surf, cx, cy, -sz/2, -0.5, 1.5 + i * 0.7,
             sz, 0.3, 0.25, T, SB0, shade(SBR1, 1.1), SBR1)

    # -- Lateral bone spines (fan out from torso sides)
    for i, (reach, zh) in enumerate([(2.2, 2.8), (1.7, 3.8), (1.1, 4.6)]):
        ibox(surf, cx, cy, 1.0, -0.2, zh,  reach, 0.8, 0.6, T, SB1, SR1, SR0)
        tp_r = ip(cx, cy, 1.0 + reach, 0.2, zh + 0.6, T)
        pygame.draw.circle(surf, SB1, tp_r, SC*2)
        ibox(surf, cx, cy, -1.0 - reach, -0.2, zh,  reach, 0.8, 0.6, T, SB1, SR1, SR0)
        tp_l = ip(cx, cy, -1.0 - reach, 0.2, zh + 0.6, T)
        pygame.draw.circle(surf, SB1, tp_l, SC*2)

    # -- Upper torso (narrower, connecting to head)
    ibox(surf, cx, cy, -0.8, -0.5, 4.0,  1.6, 1.8, 2.0, T, SBR2, SBR1, SBR0)

    # -- Centre dorsal spine
    ibox(surf, cx, cy, -0.3, -0.3, 5.8,  0.6, 0.6, 1.6, T, SB1, SB0, SR1)

    # -- Head (flared, slightly wider than upper torso)
    ibox(surf, cx, cy, -1.2, -1.6, 5.5,  2.4, 1.6, 2.0, T, SBR2, SBR1, SBR0)

    # -- Eyes
    for sgn in (-1, 1):
        ep = ip(cx, cy, sgn * 0.8, -1.6, 6.8, T)
        pygame.draw.circle(surf, BLK, ep, SC*2)
        pygame.draw.circle(surf, SR1,  ep, SC*1)

    # -- Brow crest
    bp0 = ip(cx, cy, -1.2, -1.6, 7.5, T)
    bp1 = ip(cx, cy,  1.2, -1.6, 7.5, T)
    pygame.draw.line(surf, SR1, bp0, bp1, SC*1)

    save_png(surf, "impaler", W, H)


def draw_scourge():
    """Kamikaze flying spore -- compact winged insect body with bioluminescent acid core."""
    W, H = 32, 32
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*1
    T = 6

    OR0=(90,14,12); OR1=(165,42,18); OR2=(248,108,28); OR3=(255,200,80); CORE=(255,248,165)
    SC_G = (40, 160, 20)   # dark green chitin

    shadow_iso(surf, cx, cy, 1.5, 1.2, T)

    # -- Lower wings (behind body, swept back)
    ibox(surf, cx, cy, -3.5, 0.5, 0.4,  2.5, 1.5, 0.3, T, shade(SC_G,0.6), shade(SC_G,0.4), shade(SC_G,0.3))
    ibox(surf, cx, cy,  1.0, 0.5, 0.4,  2.5, 1.5, 0.3, T, shade(SC_G,0.6), shade(SC_G,0.4), shade(SC_G,0.3))

    # -- Upper wings (wider, at mid height)
    ibox(surf, cx, cy, -4.0, -0.3, 1.2,  3.2, 1.2, 0.3, T, shade(SC_G,0.8), shade(SC_G,0.6), shade(SC_G,0.5))
    ibox(surf, cx, cy,  0.8, -0.3, 1.2,  3.2, 1.2, 0.3, T, shade(SC_G,0.8), shade(SC_G,0.6), shade(SC_G,0.5))

    # -- Body (thorax block)
    ibox(surf, cx, cy, -0.8, -0.5, 0,  1.6, 2.0, 2.4, T, shade(SC_G,0.9), shade(SC_G,0.7), shade(SC_G,0.5))

    # -- Abdomen / acid bomb (glowing orange-red sphere)
    sp = ip(cx, cy, 0, 1.2, 0.8, T)
    pygame.draw.circle(surf, BLK, sp, SC*5)
    pygame.draw.circle(surf, OR0, sp, SC*4)
    pygame.draw.circle(surf, OR1, sp, SC*3)
    pygame.draw.circle(surf, OR2, sp, SC*2)
    pygame.draw.circle(surf, OR3, (sp[0], sp[1]-SC), SC*1)

    # -- Head (small front block)
    ibox(surf, cx, cy, -0.6, -1.5, 1.5,  1.2, 1.0, 1.0, T, shade(SC_G,0.9), shade(SC_G,0.7), shade(SC_G,0.5))

    # -- Eyes (orange glow)
    for sgn in (-1, 1):
        ep = ip(cx, cy, sgn * 0.35, -1.5, 2.2, T)
        pygame.draw.circle(surf, OR2, ep, SC*1)

    save_png(surf, "scourge", W, H)


# ══════════════════════════════════════════════════════════════════════════════
# ROGUE AI UNITS  ── pure isometric voxel/block style
# ══════════════════════════════════════════════════════════════════════════════

def draw_sentinel():
    W, H = 52, 52
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*6
    T = 11

    shadow_iso(surf, cx, cy, 2.5, 2, T)

    # ── Feet ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*1,-0.5,0, 1.5,2,0.8, T, RG2,RG1,RG0)

    # ── Lower legs ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*1,0,0.8, 1.2,1.5,2.5, T, RG2,RG1,RG0)

    # ── Knee joints ──
    for sgn in (-1,1):
        kp = ip(cx,cy, sgn*1.6, 0.75, 3.3, T)
        pygame.draw.circle(surf, BLK, kp, SC*3)
        pygame.draw.circle(surf, RG3, kp, SC*2)

    # ── Upper legs ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*1,-0.5,3.3, 1.2,2,2.5, T, RG2,RG1,RG0)

    # ── Torso (hexagonal — approximated as box) ──
    ibox(surf,cx,cy, -2.5,-2.5,5.8, 5,5,5, T, RG2,RG1,RG0)
    # Inner chest detail
    ibox(surf,cx,cy, -1.8,-2.5,6.5, 3.6,0.5,2.5, T, RG3,RG2,RG1)

    # ── Crimson visor stripe on front face (y = -2.5) ──
    v_pts = [ip(cx,cy,-2.5,-2.5,8.8,T), ip(cx,cy,2.5,-2.5,8.8,T),
             ip(cx,cy,2.5,-2.5,7.6,T),  ip(cx,cy,-2.5,-2.5,7.6,T)]
    pygame.draw.polygon(surf, RC0, v_pts)
    vi_pts= [ip(cx,cy,-2.0,-2.5,8.7,T), ip(cx,cy,2.0,-2.5,8.7,T),
             ip(cx,cy,2.0,-2.5,7.7,T),  ip(cx,cy,-2.0,-2.5,7.7,T)]
    pygame.draw.polygon(surf, RC1, vi_pts)
    vc_pts= [ip(cx,cy,-1.0,-2.5,8.5,T), ip(cx,cy,1.0,-2.5,8.5,T),
             ip(cx,cy,1.0,-2.5,8.0,T),  ip(cx,cy,-1.0,-2.5,8.0,T)]
    pygame.draw.polygon(surf, RC2, vc_pts)

    # ── Sensor plate on top (no head) ──
    ibox(surf,cx,cy, -1.5,-2.5,10.8, 3,1.5,2, T, RG2,RG1,RG0)

    # ── Shoulder plasma cannons ──
    for sgn in (-1,1):
        ox = sgn*2.5
        ibox(surf,cx,cy, ox,-2.5,8.5, 1.5,5,2.5, T, RG1,RG0,shade(RG0,0.7))
        # Plasma charge slot
        slp=[ip(cx,cy,ox,-2.5,10,T),ip(cx,cy,ox+1.5,-2.5,10,T),
             ip(cx,cy,ox+1.5,-2.5,9.2,T),ip(cx,cy,ox,-2.5,9.2,T)]
        pygame.draw.polygon(surf, RC0, slp)
        pygame.draw.polygon(surf, RC1, slp, 1)
        # Muzzle glow
        mp = ip(cx,cy, ox+0.75,-2.5,11, T)
        pygame.draw.circle(surf, BLK, mp, SC*3)
        pygame.draw.circle(surf, RC1, mp, SC*2)
        pygame.draw.circle(surf, RC2, (mp[0],mp[1]-SC), SC*1)

    save_png(surf, "sentinel", W, H)


def draw_obliterator():
    W, H = 68, 68
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*8
    T = 13

    # ── Anti-grav emitter rings under hull ──
    for i in range(3):
        cy_r = cy + (i+1)*SC*5
        rx = (5 - i*0.8) * T
        ry = rx // 2
        pygame.draw.ellipse(surf, (*RC0, 160),
            pygame.Rect(cx-rx, cy_r-ry//2, rx*2, ry), SC*2)
        pygame.draw.ellipse(surf, (*RC1, 200),
            pygame.Rect(cx-rx+SC*2, cy_r-ry//4, (rx-SC*2)*2, ry//2), SC*1)

    # ── Main hover chassis ──
    ibox(surf,cx,cy, -5.5,-4.5,0, 11,9,2.5, T, RG1,RG0,shade(RG0,0.7))
    ibox(surf,cx,cy, -4.5,-3.5,2.5, 9,7,1, T, RG2,RG1,RG0)  # top plate

    # ── Side detail armour ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*5.5,-3,0.5, 2,6,2, T, RG1,RG0,shade(RG0,0.6))
        # Crimson accent strip
        sp=[ip(cx,cy,sgn*5.5,-3,1.5,T), ip(cx,cy,sgn*7.5,-3,1.5,T),
            ip(cx,cy,sgn*7.5,-3,1.0,T), ip(cx,cy,sgn*5.5,-3,1.0,T)]
        pygame.draw.polygon(surf, RC0, sp)

    # ── Gun mount block ──
    ibox(surf,cx,cy, -1.5,-2,3.5, 3,4,1.5, T, RG2,RG1,RG0)

    # ── Railgun barrel (extends forward in -y direction) ──
    ibox(surf,cx,cy, -1,-9.5,2.5, 2,12,2, T, RG2,RG1,RG0)
    # EM rail channels
    for ox in (-0.3,0.3):
        lp0 = ip(cx,cy, ox,-9.5,4.5,T)
        lp1 = ip(cx,cy, ox,-2,4.5,T)
        pygame.draw.line(surf, RC0, lp0, lp1, SC*1)

    # ── Heat fins on barrel ──
    for i in range(6):
        fy = -9 + i*1.1
        for ox_sign in (-1,1):
            lp0=ip(cx,cy,ox_sign*1.2,fy,4.0,T)
            lp1=ip(cx,cy,ox_sign*2.8,fy,4.0,T)
            pygame.draw.line(surf, RG2, lp0, lp1, SC*1)

    # ── Muzzle overheated glow ──
    mp = ip(cx,cy, 0,-9.5,4.5,T)
    pygame.draw.circle(surf, BLK,  mp, SC*5)
    pygame.draw.circle(surf, RG3,  mp, SC*4)
    pygame.draw.circle(surf, RC1,  mp, SC*3)
    pygame.draw.circle(surf, RC2,  mp, SC*2)
    pygame.draw.circle(surf, (255,255,255), mp, SC*1)

    save_png(surf, "obliterator", W, H)


def draw_tracker():
    W, H = 38, 38
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*4
    T = 9

    shadow_iso(surf, cx, cy, 1.8, 1.5, T)

    # ── Feet ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*0.5,-0.5,0, 1.2,1.5,0.6, T, RG2,RG1,RG0)

    # ── Lower legs (reverse bend) ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*0.5,0.5,0.6, 1,2,2, T, RG2,RG1,RG0)

    # ── Knee joints ──
    for sgn in (-1,1):
        kp = ip(cx,cy, sgn*1.0, 0.5, 2.6, T)
        pygame.draw.circle(surf, BLK, kp, SC*2)
        pygame.draw.circle(surf, RG3, kp, SC*1)

    # ── Upper legs ──
    for sgn in (-1,1):
        ibox(surf,cx,cy, sgn*0.5,-0.5,2.6, 1,2,2, T, RG2,RG1,RG0)

    # ── Torso ──
    ibox(surf,cx,cy, -1.5,-1.5,4.6, 3,3,3, T, RG2,RG1,RG0)

    # ── Head (boxy sensor block) ──
    ibox(surf,cx,cy, -1.8,-2,7.6, 3.6,2,2.5, T, RG2,RG1,RG0)

    # ── Multi-sensor array (4 coloured dots on front face) ──
    dot_cols = [RB0, RC0, RB0, RC0]
    for i,(xo,col) in enumerate(zip([-1.2,-0.4,0.4,1.2], dot_cols)):
        ep = ip(cx,cy, xo,-2,9.5, T)
        pygame.draw.circle(surf, BLK, ep, SC*2)
        pygame.draw.circle(surf, col, ep, SC*1)

    # ── Twin laser guns on shoulders ──
    for sgn,ox in ((-1,-2.5),(1,1.5)):
        ibox(surf,cx,cy, ox,-2,7.5, 1,4,1, T, RG1,RG0,shade(RG0,0.7))
        mp = ip(cx,cy, ox+0.5,-2,8.5, T)
        pygame.draw.circle(surf, BLK,  mp, SC*3)
        pygame.draw.circle(surf, RB0,  mp, SC*2)
        pygame.draw.circle(surf, RB1,  (mp[0],mp[1]-SC), SC*1)

    save_png(surf, "tracker", W, H)


def draw_purifier():
    W, H = 60, 60
    surf = mk(W, H)
    cx = W*SC//2;  cy = H*SC//2 + SC*2
    T = 13

    shadow_iso(surf, cx, cy, 5, 4, T)

    RN0=(22,44,90); RN1=(65,135,255); RN2=(140,198,255)

    # ── Outer energy ring (isometric ellipse at z=0) ──
    ring_pts = [ip(cx,cy, 5.5*math.cos(math.radians(a*20)),
                           5.5*math.sin(math.radians(a*20)), 0.3, T)
                for a in range(18)]
    pygame.draw.polygon(surf, RN0, ring_pts)
    # Ring highlight ticks
    for a_d in range(0,360,20):
        a=math.radians(a_d)
        p1=ip(cx,cy,4.5*math.cos(a),4.5*math.sin(a),0.4,T)
        p2=ip(cx,cy,5.5*math.cos(a),5.5*math.sin(a),0.4,T)
        col=RN2 if a_d%60==0 else RN1
        pygame.draw.line(surf, col, p1, p2, SC*1)

    # ── Main disc (3 stacked thin hex boxes for thickness) ──
    for dz,col_t,col_l,col_r in [(0,RG1,RG0,shade(RG0,0.7)),
                                   (0.5,RG2,RG1,RG0),
                                   (1.0,RG1,RG0,shade(RG0,0.7))]:
        hex6 = [ip(cx,cy, 4*math.cos(math.radians(i*60)),
                           4*math.sin(math.radians(i*60)), dz, T)
                for i in range(6)]
        pygame.draw.polygon(surf, col_t, hex6)
    # Inner hex outline
    hex4 = [ip(cx,cy, 3*math.cos(math.radians(i*60)),
                       3*math.sin(math.radians(i*60)), 1.2, T)
            for i in range(6)]
    pygame.draw.polygon(surf, RG2, hex4)
    pygame.draw.polygon(surf, RG3, hex4, SC*1)

    # ── Laser matrix spokes ──
    for a_d in range(0,360,60):
        a=math.radians(a_d)
        sp1=ip(cx,cy,1.5*math.cos(a),1.5*math.sin(a),1.5,T)
        sp2=ip(cx,cy,2.8*math.cos(a),2.8*math.sin(a),1.5,T)
        pygame.draw.line(surf, RN2, sp1, sp2, SC*1)
        pygame.draw.circle(surf, RN2, sp2, SC*1)

    # ── Crimson core weapon ──
    cp = ip(cx,cy, 0,0,2, T)
    pygame.draw.circle(surf, BLK, cp, SC*5)
    pygame.draw.circle(surf, RC0, cp, SC*4)
    pygame.draw.circle(surf, RC1, cp, SC*3)
    pygame.draw.circle(surf, RC2, cp, SC*2)
    pygame.draw.circle(surf, (255,255,255), cp, SC*1)

    save_png(surf, "purifier", W, H)


# ── Run all ─────────────────────────────────────────────────────────────────
for fn in [draw_crusher, draw_weaver, draw_impaler, draw_scourge,
           draw_sentinel, draw_obliterator, draw_tracker, draw_purifier]:
    try:
        fn()
    except Exception as e:
        print(f"ERR {fn.__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()

pygame.quit()
print("Done.", flush=True)
