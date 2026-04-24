# -*- coding: utf-8 -*-
"""
generate_missing_art.py - Star Raise Unit Art Generator (PIL isometric)
Creates 8 unit sprites in isometric style matching the game pixel-art aesthetic.
Run from project root:  python generate_missing_art.py
"""
from PIL import Image, ImageDraw
import math, os, traceback

OUT_DIR = os.path.join("assets", "units")
os.makedirs(OUT_DIR, exist_ok=True)

# --------------------------------------------------------------------------
# Core isometric renderer
# --------------------------------------------------------------------------

def ip(cx, cy, x, y, z, s):
    """Isometric world -> screen pixel.
    x=right, y=depth-into-screen (left on screen), z=up."""
    return (int(cx + (x - y) * s), int(cy + (x + y) * s * 0.5 - z * s))

def iso_box(draw, cx, cy, x0, y0, z0, w, d, h,
            top_c, left_c, right_c, s, edge=None):
    """Filled isometric box, back-to-front draw order."""
    x1, y1, z1 = x0+w, y0+d, z0+h
    r_pts = [ip(cx,cy,x1,y0,z0,s), ip(cx,cy,x1,y1,z0,s),
             ip(cx,cy,x1,y1,z1,s), ip(cx,cy,x1,y0,z1,s)]
    l_pts = [ip(cx,cy,x0,y1,z0,s), ip(cx,cy,x1,y1,z0,s),
             ip(cx,cy,x1,y1,z1,s), ip(cx,cy,x0,y1,z1,s)]
    t_pts = [ip(cx,cy,x0,y0,z1,s), ip(cx,cy,x1,y0,z1,s),
             ip(cx,cy,x1,y1,z1,s), ip(cx,cy,x0,y1,z1,s)]
    if right_c: draw.polygon(r_pts, fill=right_c)
    if left_c:  draw.polygon(l_pts, fill=left_c)
    if top_c:   draw.polygon(t_pts, fill=top_c)
    if edge:
        for face in (r_pts, l_pts, t_pts):
            draw.polygon(face, outline=edge)

def shade(base, f):
    return tuple(min(255, max(0, int(c * f))) for c in base)

def glow_circle(img, cx, cy, r, color, alpha=80):
    """Soft additive glow ring composited on img."""
    if r < 1:
        return
    g = Image.new('RGBA', img.size, (0,0,0,0))
    gd = ImageDraw.Draw(g)
    for i in range(r, 0, -2):
        a = int(alpha * (i / r))
        gd.ellipse([cx-i, cy-i, cx+i, cy+i], fill=(*color[:3], a))
    img.alpha_composite(g)

# ==========================================================================
# SWARM FACTION  -  deep purple chitin, toxic acid-green, bone-white
# ==========================================================================

CHIT_D = (48, 16, 70)
CHIT_M = (85, 32, 112)
CHIT_H = (125, 55, 150)
BONE_D = (162, 145, 115)
BONE_M = (198, 180, 150)
BONE_H = (230, 212, 185)
ACID   = (100, 215, 12)
ACID_H = (185, 255, 42)
ACID_C = (230, 255, 120)

# --- Crusher (68x68) - massive siege beetle ---
def draw_crusher(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 4
    s = 4.4

    glow_circle(img, cx, cy+14, 26, (0,0,0), alpha=55)

    # 3 legs per side (behind body)
    for i in range(3):
        iso_box(d,cx,cy, -4-i, i*0.8-1, 0.2, 1.5,0.6,0.4,
                shade(CHIT_D,0.8), shade(CHIT_D,0.7), None, s)
        iso_box(d,cx,cy, 3, i*0.8-1, 0.2, 1.5,0.6,0.4,
                shade(CHIT_D,0.8), shade(CHIT_D,0.7), None, s)

    # Main body shell
    iso_box(d,cx,cy, -3,-3,0, 6,6,2.0, CHIT_H, CHIT_M, CHIT_D, s, edge=(28,10,42))
    iso_box(d,cx,cy, -2.5,-2.5,2, 5,5,0.6, shade(CHIT_H,1.15), CHIT_H, CHIT_M, s)

    # 5 bone-white armour segments
    for i in range(5):
        sw = 4.5 - i*0.5
        iso_box(d,cx,cy, -sw/2, -2+i*0.9, 2.6+i*0.05, sw,0.8,0.35,
                BONE_H, BONE_M, BONE_D, s)

    # Dorsal ridge nubs
    for i in range(4):
        iso_box(d,cx,cy, -0.4,-1+i*1.1, 2.9, 0.8,0.6,0.7, BONE_H, BONE_M, BONE_D, s)

    # Head
    iso_box(d,cx,cy, -2,-5,0, 4,2,2.8, shade(CHIT_H,1.1), CHIT_M, CHIT_D, s, edge=(28,10,42))

    # Twin siege mandibles
    for sgn in (-1,1):
        ox = sgn*0.5
        iso_box(d,cx,cy, ox,-7,1.6, 0.9,3,0.5, BONE_H, BONE_M, BONE_D, s)
        iso_box(d,cx,cy, ox,-10,1.8, 0.9,1.2,0.4, BONE_H, shade(BONE_H,1.1), BONE_M, s)

    # Compound eyes
    for sgn in (-1,1):
        ep = ip(cx,cy, sgn*0.9,-4.5,2.5, s)
        glow_circle(img, ep[0], ep[1], 4, ACID, alpha=100)
        d.ellipse([ep[0]-3,ep[1]-3,ep[0]+3,ep[1]+3], fill=ACID)
        d.ellipse([ep[0]-1,ep[1]-1,ep[0]+1,ep[1]+1], fill=ACID_C)

    return img


# --- Weaver (56x56) - flying moth with acid sac ---
def draw_weaver(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2
    s = 4.0

    WING_D = (18,55,18)
    WING_M = (30,90,25)
    WING_H = (50,128,44)
    BODY_D = (26,65,22)
    BODY_M = (40,98,34)
    BODY_H = (58,130,50)

    glow_circle(img, cx, cy+8, 18, (0,0,0), alpha=40)

    # Upper wings
    pts_ul = [ip(cx,cy,-1,-1,2,s), ip(cx,cy,-6,-2,2,s),
              ip(cx,cy,-6,2,1,s),  ip(cx,cy,-1,1,2,s)]
    pts_ur = [ip(cx,cy, 1,-1,2,s), ip(cx,cy, 6,-2,2,s),
              ip(cx,cy, 6,1,1,s),  ip(cx,cy, 1,0,2,s)]
    d.polygon(pts_ul, fill=WING_M)
    d.polygon(pts_ul, outline=WING_D)
    d.polygon(pts_ur, fill=WING_M)
    d.polygon(pts_ur, outline=WING_D)

    # Wing veins
    for t in (0.35, 0.65, 0.85):
        for base, tip in ((pts_ul[0],pts_ul[1]),(pts_ur[0],pts_ur[1])):
            vx = int(base[0]+(tip[0]-base[0])*t)
            vy = int(base[1]+(tip[1]-base[1])*t)
            d.line([base,(vx,vy)], fill=WING_H, width=1)

    # Lower wings
    pts_ll = [ip(cx,cy,-1,1,1,s), ip(cx,cy,-5,2,1,s),
              ip(cx,cy,-4,5,0,s), ip(cx,cy,-1,4,0,s)]
    pts_lr = [ip(cx,cy, 1,1,1,s), ip(cx,cy, 5,1,1,s),
              ip(cx,cy, 4,5,0,s), ip(cx,cy, 1,4,0,s)]
    d.polygon(pts_ll, fill=WING_D)
    d.polygon(pts_lr, fill=WING_D)

    # Elongated body
    iso_box(d,cx,cy, -1,-1,0, 2,5,3, BODY_H, BODY_M, BODY_D, s, edge=(16,42,14))

    # Acid sac tail glow
    sp = ip(cx,cy, 0,4.5,0.6, s)
    glow_circle(img, sp[0], sp[1], 11, ACID, alpha=95)
    d.ellipse([sp[0]-6,sp[1]-5,sp[0]+6,sp[1]+5], fill=ACID)
    d.ellipse([sp[0]-3,sp[1]-3,sp[0]+3,sp[1]+3], fill=ACID_H)
    d.ellipse([sp[0]-1,sp[1]-1,sp[0]+1,sp[1]+1], fill=ACID_C)

    # Head + compound eyes
    iso_box(d,cx,cy, -1,-2.5,2.5, 2,1.5,1.5, BODY_H, BODY_M, BODY_D, s)
    for sgn in (-1,1):
        ep = ip(cx,cy, sgn*0.5,-2.8,3.5, s)
        glow_circle(img, ep[0], ep[1], 3, ACID, alpha=80)
        d.ellipse([ep[0]-2,ep[1]-2,ep[0]+2,ep[1]+2], fill=ACID)

    return img


# --- Impaler (50x50) - upright serpent with bone spines ---
def draw_impaler(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 6
    s = 4.2

    BODY_D = (50,20,10)
    BODY_M = (80,38,18)
    BODY_H = (108,55,26)
    SP_D   = (145,16,16)
    SP_M   = (192,35,35)

    glow_circle(img, cx, cy+8, 15, (0,0,0), alpha=50)

    # Coiled tail segments
    for i, (tx,ty) in enumerate([(0.4,1.8), (-0.4,0.2), (0.4,-1.2)]):
        r = 1.1 - i*0.22
        iso_box(d,cx,cy, tx-r/2,ty-r/2,0, r,r,r*1.2, BODY_H, BODY_M, BODY_D, s)

    # Upright torso
    iso_box(d,cx,cy, -1.5,-1.5,1, 3,3,5, BODY_H, BODY_M, BODY_D, s, edge=(36,14,6))

    # Back spines (3 per side)
    spine_sizes = [(2.0,1.2),(1.5,0.9),(1.0,0.6)]
    for i, (reach,sz) in enumerate(spine_sizes):
        zh = 3.5 + i*0.8
        pts_r = [ip(cx,cy,1.5,-0.5,zh,s), ip(cx,cy,1.5+reach,-0.5,zh-sz*0.5,s),
                 ip(cx,cy,1.5+reach,0.5,zh-sz*0.5,s), ip(cx,cy,1.5,0.5,zh,s)]
        d.polygon(pts_r, fill=SP_M)
        d.polygon(pts_r, outline=SP_D)
        bone_tip = ip(cx,cy, 1.5+reach, 0, zh-sz*0.5, s)
        d.ellipse([bone_tip[0]-2,bone_tip[1]-2,bone_tip[0]+2,bone_tip[1]+2], fill=BONE_H)
        # Mirror left side using -y direction
        pts_l = [ip(cx,cy,-1.5,-0.5,zh,s), ip(cx,cy,-1.5,-0.5-reach,zh-sz*0.5,s),
                 ip(cx,cy,-1.5,0.5-reach,zh-sz*0.5,s), ip(cx,cy,-1.5,0.5,zh,s)]
        d.polygon(pts_l, fill=SP_M)
        d.polygon(pts_l, outline=SP_D)

    # Centre top spine
    iso_box(d,cx,cy, -0.4,-0.4,6, 0.8,0.8,1.8, BONE_H, BONE_M, SP_M, s)

    # Head
    iso_box(d,cx,cy, -1.2,-2.5,4.5, 2.4,2,2.2,
            shade(BODY_H,1.15), BODY_M, BODY_D, s, edge=(36,14,6))
    bp1 = ip(cx,cy,-1.2,-2.5,6.7,s)
    bp2 = ip(cx,cy, 1.2,-2.5,6.7,s)
    d.line([bp1,bp2], fill=SP_M, width=2)

    return img


# --- Scourge (32x32) - tiny flying suicide bomb ---
def draw_scourge(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, w//2

    OUTER = (92,14,12)
    INNER = (172,42,16)
    GLOW1 = (248,108,26)
    GLOW2 = (255,186,52)
    CORE  = (255,246,160)
    VEIN  = (222,65,6)
    WING  = (175,220,255,58)

    glow_circle(img, cx, cy, 14, GLOW1, alpha=95)

    # Translucent wings
    wg = Image.new('RGBA', (w,h), (0,0,0,0))
    wd = ImageDraw.Draw(wg)
    for sgn in (-1,1):
        for row in range(2):
            wy  = cy - 3 + row*5
            wx1 = cx + sgn*2
            wx2 = cx + sgn*12
            wd.ellipse([min(wx1,wx2)-1, wy, max(wx1,wx2)+1, wy+4], fill=WING)
    img.alpha_composite(wg)

    # Sac body
    d.ellipse([cx-12,cy-12,cx+12,cy+12], fill=OUTER)
    d.ellipse([cx-10,cy-10,cx+10,cy+10], fill=(122,22,16))
    d.ellipse([cx-8, cy-8, cx+8, cy+8],  fill=INNER)

    # Bioluminescent veins
    for a in range(0,360,40):
        r = math.radians(a)
        x1=int(cx+4*math.cos(r)); y1=int(cy+4*math.sin(r))
        x2=int(cx+9*math.cos(r)); y2=int(cy+9*math.sin(r))
        d.line([(x1,y1),(x2,y2)], fill=VEIN, width=1)

    # Inner core glow
    glow_circle(img, cx, cy, 6, GLOW2, alpha=120)
    d.ellipse([cx-5,cy-5,cx+5,cy+5], fill=GLOW1)
    d.ellipse([cx-3,cy-3,cx+3,cy+3], fill=GLOW2)
    d.ellipse([cx-1,cy-1,cx+1,cy+1], fill=CORE)

    return img


# ==========================================================================
# ROGUE AI FACTION  -  near-black chassis, steel-grey plates, crimson accents
# ==========================================================================

STEEL_D = (20,20,26)
STEEL_M = (40,42,52)
STEEL_H = (66,70,86)
STEEL_E = (92,98,115)
CRIM    = (172,16,28)
CRIM_H  = (225,46,62)
CRIM_C  = (255,132,142)
MUZZLE  = (212,232,255)
PLASMA  = (255,92,102)


# --- Sentinel (52x52) - headless bipedal mech, crimson visor, twin cannons ---
def draw_sentinel(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 4
    s = 4.2

    glow_circle(img, cx, cy+12, 20, (0,0,0), alpha=55)

    # Reverse-joint legs
    for sgn in (-1,1):
        iso_box(d,cx,cy, sgn*1.0, 0, 0, 1.2, 3, 1.5, STEEL_M, STEEL_D, STEEL_D, s)
        kp = ip(cx,cy, sgn*1.6, 3, 1.5, s)
        d.ellipse([kp[0]-4,kp[1]-4,kp[0]+4,kp[1]+4], fill=STEEL_H)
        d.ellipse([kp[0]-2,kp[1]-2,kp[0]+2,kp[1]+2], fill=STEEL_E)
        iso_box(d,cx,cy, sgn*0.5, 3, 0, 1.2, 3, 1.0, STEEL_M, STEEL_D, STEEL_D, s)
        fp = ip(cx,cy, sgn*1.0, 6, 0, s)
        d.ellipse([fp[0]-5,fp[1]-2,fp[0]+5,fp[1]+2], fill=STEEL_H)

    # Hexagonal torso
    iso_box(d,cx,cy, -2.5,-2.5,1.5, 5,5,4.5, STEEL_H, STEEL_M, STEEL_D, s, edge=(14,14,22))

    # Crimson visor stripe on front face
    v1 = ip(cx,cy,-2.5,-2.5,4.0,s)
    v2 = ip(cx,cy, 2.5,-2.5,4.0,s)
    v3 = ip(cx,cy, 2.5,-2.5,3.4,s)
    v4 = ip(cx,cy,-2.5,-2.5,3.4,s)
    d.polygon([v1,v2,v3,v4], fill=CRIM)
    vm1= ip(cx,cy,-2.0,-2.5,3.95,s)
    vm2= ip(cx,cy, 2.0,-2.5,3.95,s)
    vm3= ip(cx,cy, 2.0,-2.5,3.45,s)
    vm4= ip(cx,cy,-2.0,-2.5,3.45,s)
    d.polygon([vm1,vm2,vm3,vm4], fill=CRIM_H)
    vcx = (vm1[0]+vm2[0])//2
    vcy = (vm1[1]+vm3[1])//2
    glow_circle(img, vcx, vcy, 10, CRIM, alpha=65)

    # Sensor plate (top, no face)
    iso_box(d,cx,cy, -1.5,-2.5,6.0, 3,1.2,1.5, STEEL_H, STEEL_M, STEEL_D, s)

    # Shoulder plasma cannons
    for sgn in (-1,1):
        ox = sgn*2.5
        iso_box(d,cx,cy, ox,-2.5,3.5, 1.2,5,2.5, STEEL_M, STEEL_D, STEEL_D, s)
        cs = ip(cx,cy, ox+0.6,-2.5,5.0, s)
        glow_circle(img, cs[0], cs[1], 5, MUZZLE, alpha=100)
        d.ellipse([cs[0]-3,cs[1]-3,cs[0]+3,cs[1]+3], fill=CRIM)
        d.ellipse([cs[0]-2,cs[1]-2,cs[0]+2,cs[1]+2], fill=PLASMA)
        d.ellipse([cs[0]-1,cs[1]-1,cs[0]+1,cs[1]+1], fill=MUZZLE)

    return img


# --- Obliterator (68x68) - anti-grav siege platform, massive railgun ---
def draw_obliterator(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 6
    s = 4.0

    glow_circle(img, cx, cy+16, 28, (0,0,0), alpha=60)

    # Anti-grav emitter rings
    for i in range(3):
        ey = cy + 16 + i*6
        glow_circle(img, cx, ey, max(1, 9-i*2), CRIM, alpha=75)
        d.ellipse([cx-11+i*2, ey-3, cx+11-i*2, ey+3], fill=CRIM)
        d.ellipse([cx-8+i*2,  ey-1, cx+8-i*2,  ey+1], fill=CRIM_H)

    # Main chassis
    iso_box(d,cx,cy, -5.5,-5.5,1, 11,11,2.8, STEEL_H, STEEL_M, STEEL_D, s, edge=(12,12,18))

    # Side detail armour plates
    for sgn in (-1,1):
        iso_box(d,cx,cy, sgn*5.5,-3, 1, 2,6,2.5, STEEL_M, STEEL_D, STEEL_D, s)
        ap1 = ip(cx,cy, sgn*5.5,-3, 2.5, s)
        ap2 = ip(cx,cy, sgn*5.5, 3, 2.5, s)
        d.line([ap1,ap2], fill=CRIM, width=2)

    # Gun mount
    iso_box(d,cx,cy, -1.5,-2,3.8, 3,4,1.2, STEEL_H, STEEL_M, STEEL_D, s)

    # Railgun barrel (extends forward in -y)
    iso_box(d,cx,cy, -1.0,-9,2, 2,12,1.8, STEEL_H, STEEL_M, STEEL_D, s, edge=(12,12,18))

    # Electromagnetic rail channels
    for ox in (-0.25, 0.25):
        rp1 = ip(cx,cy, ox,-9, 3.0, s)
        rp2 = ip(cx,cy, ox,-2, 3.0, s)
        d.line([rp1,rp2], fill=CRIM, width=1)

    # Heat dissipation fins
    for i in range(6):
        fy = -8.5 + i*1.1
        lp1 = ip(cx,cy,-1.2, fy, 3.0, s)
        lp2 = ip(cx,cy,-2.8, fy, 3.0, s)
        rp1 = ip(cx,cy, 1.2, fy, 3.0, s)
        rp2 = ip(cx,cy, 2.8, fy, 3.0, s)
        d.line([lp1,lp2], fill=STEEL_H, width=1)
        d.line([rp1,rp2], fill=STEEL_H, width=1)

    # Muzzle glow
    mp = ip(cx,cy, 0,-9, 3.2, s)
    glow_circle(img, mp[0], mp[1], 11, MUZZLE, alpha=115)
    d.ellipse([mp[0]-5,mp[1]-5,mp[0]+5,mp[1]+5], fill=MUZZLE)
    d.ellipse([mp[0]-3,mp[1]-3,mp[0]+3,mp[1]+3], fill=CRIM_H)
    d.ellipse([mp[0]-1,mp[1]-1,mp[0]+1,mp[1]+1], fill=(255,255,255))

    return img


# --- Tracker (38x38) - lean reverse-joint biped, twin laser guns ---
def draw_tracker(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 3
    s = 3.4

    FR    = (38,44,54)
    FR_M  = (55,62,76)
    FR_H  = (82,90,108)
    JOINT = (65,74,88)
    LASER = (76,198,255)
    LAS_H = (182,236,255)
    SENS_B= (52,172,255)
    SENS_R= (255,55,70)

    glow_circle(img, cx, cy+8, 13, (0,0,0), alpha=45)

    # Upper legs
    for sgn in (-1,1):
        iso_box(d,cx,cy, sgn*0.8, 0, 0, 1,2.8,1.4, FR_M, FR, FR, s)

    # Knee joints
    for sgn in (-1,1):
        kp = ip(cx,cy, sgn*1.3, 2.8, 1.4, s)
        d.ellipse([kp[0]-4,kp[1]-4,kp[0]+4,kp[1]+4], fill=JOINT)
        d.ellipse([kp[0]-2,kp[1]-2,kp[0]+2,kp[1]+2], fill=FR_H)

    # Lower legs (reverse bend)
    for sgn in (-1,1):
        iso_box(d,cx,cy, sgn*0.4, 2.8, 0, 1,3.5,0.9, FR_M, FR, FR, s)
        fp = ip(cx,cy, sgn*0.9, 6.3, 0, s)
        d.ellipse([fp[0]-5,fp[1]-2,fp[0]+5,fp[1]+2], fill=FR_H)

    # Torso
    iso_box(d,cx,cy, -1.4,-1.4,1.4, 2.8,2.8,3, FR_H, FR_M, FR, s, edge=(24,28,38))

    # Sensor head
    iso_box(d,cx,cy, -1.6,-2.2,4.4, 3.2,2,2.4, FR_H, FR_M, FR, s, edge=(24,28,38))

    # Multi-sensor array
    x_offsets = [-1.2,-0.4,0.4,1.2]
    cols = [SENS_B, SENS_R, SENS_B, SENS_R]
    for xo, col in zip(x_offsets, cols):
        ep = ip(cx,cy, xo,-2.2,6.3, s)
        glow_circle(img, ep[0], ep[1], 3, col, alpha=85)
        d.ellipse([ep[0]-2,ep[1]-2,ep[0]+2,ep[1]+2], fill=col)
        d.ellipse([ep[0]-1,ep[1]-1,ep[0]+1,ep[1]+1], fill=LAS_H)

    # Twin laser guns on shoulders
    for sgn, ox in ((-1,-2.4),(1,1.4)):
        iso_box(d,cx,cy, ox,-2.2,4.4, 1,5,1, STEEL_M, STEEL_D, STEEL_D, s)
        mp = ip(cx,cy, ox+0.5,-2.2,5.0, s)
        glow_circle(img, mp[0], mp[1], 4, LASER, alpha=105)
        d.ellipse([mp[0]-2,mp[1]-2,mp[0]+2,mp[1]+2], fill=LASER)
        d.ellipse([mp[0]-1,mp[1]-1,mp[0]+1,mp[1]+1], fill=LAS_H)

    return img


# --- Purifier (60x60) - hexagonal hovering disc, laser matrix, crimson core ---
def draw_purifier(w, h):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    cx, cy = w//2, h//2 + 2
    s = 4.6

    RING_D = (22,44,85)
    RING_C = (65,135,255)
    RING_H = (140,198,255)

    glow_circle(img, cx, cy+10, 28, (0,0,0), alpha=55)

    # Outer energy ring
    outer_pts = [ip(cx,cy, 5.5*math.cos(math.radians(a*30)),
                           5.5*math.sin(math.radians(a*30)), 0.5, s)
                 for a in range(12)]
    d.polygon(outer_pts, fill=RING_D)
    glow_circle(img, cx, cy, 30, RING_C, alpha=55)

    # Ring tick marks
    for a_deg in range(0, 360, 12):
        a = math.radians(a_deg)
        p1 = ip(cx,cy, 4.5*math.cos(a), 4.5*math.sin(a), 0.6, s)
        p2 = ip(cx,cy, 5.5*math.cos(a), 5.5*math.sin(a), 0.6, s)
        col = RING_H if a_deg % 60 == 0 else RING_C
        d.line([p1,p2], fill=col, width=1)

    # Main hexagonal disc
    disc_pts = [ip(cx,cy, 4*math.cos(math.radians(i*60)),
                          4*math.sin(math.radians(i*60)), 0.8, s)
                for i in range(6)]
    d.polygon(disc_pts, fill=STEEL_D)

    inner_pts = [ip(cx,cy, 3.0*math.cos(math.radians(i*60)),
                            3.0*math.sin(math.radians(i*60)), 1.2, s)
                 for i in range(6)]
    d.polygon(inner_pts, fill=STEEL_M)
    d.polygon(inner_pts, outline=STEEL_H)

    # Inner structural ring
    ring2_pts = [ip(cx,cy, 2.0*math.cos(math.radians(i*30)),
                            2.0*math.sin(math.radians(i*30)), 1.4, s)
                 for i in range(12)]
    d.polygon(ring2_pts, outline=STEEL_E)

    # Laser matrix spokes
    for a_deg in range(0, 360, 60):
        a = math.radians(a_deg)
        sp1 = ip(cx,cy, 1.4*math.cos(a), 1.4*math.sin(a), 1.6, s)
        sp2 = ip(cx,cy, 2.8*math.cos(a), 2.8*math.sin(a), 1.6, s)
        d.line([sp1,sp2], fill=MUZZLE, width=1)
        d.ellipse([sp2[0]-2,sp2[1]-2,sp2[0]+2,sp2[1]+2], fill=RING_H)

    # Core crimson weapon mount
    glow_circle(img, cx, cy, 13, CRIM, alpha=80)
    core_pts = [ip(cx,cy, 1.4*math.cos(math.radians(i*60+30)),
                           1.4*math.sin(math.radians(i*60+30)), 2.2, s)
                for i in range(6)]
    d.polygon(core_pts, fill=CRIM)
    d.polygon(core_pts, outline=CRIM_H)

    cp = ip(cx,cy, 0,0, 2.5, s)
    glow_circle(img, cp[0], cp[1], 8, CRIM_C, alpha=105)
    d.ellipse([cp[0]-4,cp[1]-4,cp[0]+4,cp[1]+4], fill=CRIM)
    d.ellipse([cp[0]-2,cp[1]-2,cp[0]+2,cp[1]+2], fill=CRIM_H)
    d.ellipse([cp[0]-1,cp[1]-1,cp[0]+1,cp[1]+1], fill=(255,255,255))

    # Gloss highlight
    hi = Image.new('RGBA', img.size, (0,0,0,0))
    hi_d = ImageDraw.Draw(hi)
    hi_pts = [ip(cx,cy, 1.8*math.cos(math.radians(i*60)),
                         1.8*math.sin(math.radians(i*60)), 1.6, s)
              for i in range(6)]
    hi_d.polygon(hi_pts, fill=(255,255,255,24))
    img.alpha_composite(hi)

    return img


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

UNITS = {
    "crusher":     (68, 68, draw_crusher),
    "weaver":      (56, 56, draw_weaver),
    "impaler":     (50, 50, draw_impaler),
    "scourge":     (32, 32, draw_scourge),
    "sentinel":    (52, 52, draw_sentinel),
    "obliterator": (68, 68, draw_obliterator),
    "tracker":     (38, 38, draw_tracker),
    "purifier":    (60, 60, draw_purifier),
}

for kind, (w, h, fn) in UNITS.items():
    try:
        result = fn(w, h)
        out_path = os.path.join(OUT_DIR, f"{kind}.png")
        result.save(out_path)
        print(f"OK  {kind}.png  ({w}x{h})", flush=True)
    except Exception as e:
        print(f"ERR {kind}: {e}", flush=True)
        traceback.print_exc()

print("Done.", flush=True)
