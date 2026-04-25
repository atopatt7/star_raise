"""
generate_missing_buildings.py - Star Raise isometric buildings (2.5D 60-deg)
Same technique as generate_missing_art.py: draw at 4x, NEAREST-scale down.
Regenerates ONLY the 12 buildings with poor-quality placeholder art.
"""
import os, math
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from PIL import Image

pygame.init()
pygame.display.set_mode((1, 1))

OUT_DIR = os.path.join("assets", "buildings")
os.makedirs(OUT_DIR, exist_ok=True)

SC = 4

# Palettes
BLK   = (12, 6, 20)
# Swarm
SP0=(28,18,40); SP1=(60,28,80); SP2=(120,62,160); SP3=(168,100,218)
SA0=(30,130,8); SA1=(80,220,18); SA2=(185,255,80)
SR0=(140,22,22); SR1=(210,55,55); SB0=(195,178,145); SB1=(232,215,185)
SBR0=(48,18,8); SBR1=(88,40,16); SBR2=(128,64,28)
# Rogue AI
RG0=(30,30,38); RG1=(68,68,82); RG2=(110,112,132); RG3=(168,170,192)
RC0=(180,20,40); RC1=(230,55,70); RC2=(255,135,148)
RB0=(55,175,255); RB1=(180,235,255)
RT0=(0,140,130); RT1=(0,200,180); RT2=(120,255,240)   # teal data
RP0=(140,30,0); RP1=(220,90,10); RP2=(255,180,60)     # plasma orange
RQ0=(22,44,90); RQ1=(65,135,255); RQ2=(160,210,255)   # quantum blue
RN0=(10,10,14); RN1=(28,18,36); RN2=(55,10,18)        # oblivion near-black

def shade(c, f):
    return tuple(min(255,max(0,int(x*f))) for x in c)

def ip(cx, cy, x, y, z, t):
    return (int(cx + (x - y) * t), int(cy + (x + y) * t // 2 - z * t))

def ibox(surf, cx, cy, x0, y0, z0, w, d, h, t,
         top, left, right, edge=BLK):
    x1,y1,z1 = x0+w, y0+d, z0+h
    def p(x,y,z): return ip(cx,cy,x,y,z,t)
    rp=[p(x1,y0,z0),p(x1,y1,z0),p(x1,y1,z1),p(x1,y0,z1)]
    lp=[p(x0,y1,z0),p(x1,y1,z0),p(x1,y1,z1),p(x0,y1,z1)]
    tp=[p(x0,y0,z1),p(x1,y0,z1),p(x1,y1,z1),p(x0,y1,z1)]
    if right: pygame.draw.polygon(surf, right, rp)
    if left:  pygame.draw.polygon(surf, left, lp)
    if top:   pygame.draw.polygon(surf, top, tp)
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
    pts = [ip(cx,cy,-rx,0,0,t), ip(cx,cy,0,-ry,0,t),
           ip(cx,cy,rx,0,0,t),  ip(cx,cy,0,ry,0,t)]
    pygame.draw.polygon(surf, (12,8,22,100), pts)

# ============================================================
# SWARM BUILDINGS
# ============================================================

def draw_mutation_pit():
    """Sunken biological reactor: outer bone-ridge walls, dark pit, glowing green column."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*6
    T = 15

    # Outer base slab
    ibox(surf,cx,cy, -4,-4,0, 8,8,0.8, T, shade(SP1,0.5), shade(SP0,0.5), shade(SP0,0.3))

    # Outer wall ring (4 sides, leaving gap at front-left for entrance look)
    ibox(surf,cx,cy, -4,-4,0, 1,8,2.5, T, SP1,SP0,shade(SP0,0.7))   # left wall
    ibox(surf,cx,cy,  3,-4,0, 1,8,2.5, T, SP1,SP0,shade(SP0,0.7))   # right wall
    ibox(surf,cx,cy, -4,-4,0, 8,1,2.5, T, SP1,SP0,shade(SP0,0.7))   # back wall
    # Front wall (short, so pit is visible from viewer angle)
    ibox(surf,cx,cy, -4, 3,0, 8,1,1.0, T, SP1,SP0,shade(SP0,0.7))

    # Bone armour ridges on outer walls
    for i in range(4):
        ibox(surf,cx,cy, -4, -3.5+i*1.8, 2.5, 8,0.5,0.5, T, SB1,SB0,shade(SB0,0.8))

    # Interior pit floor (dark)
    pit_pts = [ip(cx,cy,-3,-3,0.9,T), ip(cx,cy,3,-3,0.9,T),
               ip(cx,cy,3,3,0.9,T),  ip(cx,cy,-3,3,0.9,T)]
    pygame.draw.polygon(surf, (8,4,14), pit_pts)

    # Mutation ooze bubbles in pit (green circles)
    for bx,by in [(-1.5,1),(1.0,-0.5),(0.2,1.8),(-0.8,-1.2)]:
        bp = ip(cx,cy,bx,by,0.9,T)
        pygame.draw.circle(surf, SA0, bp, SC*3)
        pygame.draw.circle(surf, SA1, bp, SC*2)

    # Central mutation column (bio-organic pillar)
    ibox(surf,cx,cy, -1,-1,0.9, 2,2,4, T, SP3,SP2,SP1)
    ibox(surf,cx,cy, -0.6,-0.6,4.9, 1.2,1.2,0.8, T, shade(SA0,0.8),SA0,shade(SA0,0.6))

    # Column glow top
    tp = ip(cx,cy, 0,0,5.9, T)
    pygame.draw.circle(surf, BLK, tp, SC*6)
    pygame.draw.circle(surf, SA0, tp, SC*5)
    pygame.draw.circle(surf, SA1, tp, SC*3)
    pygame.draw.circle(surf, SA2, (tp[0],tp[1]-SC*2), SC*2)

    # Spine nubs on top of walls
    for i in range(6):
        a = i/6 * math.pi * 2
        sx = math.cos(a)*3.2; sy = math.sin(a)*3.2
        ibox(surf,cx,cy, sx-0.3,sy-0.3,2.5, 0.6,0.6,1.2, T, SB1,SB0,shade(SB0,0.8))

    save_png(surf, "mutation_pit", W, H)


def draw_hive_nest():
    """Organic mound hive: stacked bulging tiers, dark entrance tunnel, green glow spots."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2 - SC*2; cy = H*SC//2 + SC*4
    T = 14

    shadow_iso(surf, cx, cy, 4.5, 3.5, T)

    # Base mound (wide, low)
    ibox(surf,cx,cy, -4,-4,0, 8,8,1.2, T, shade(SP1,0.6),shade(SP0,0.6),shade(SP0,0.4))

    # Mound tiers (each smaller, building up the organic dome)
    sizes = [(3.5,3.5,1.5,1.8),(2.8,2.8,3.0,2.0),(2.0,2.0,4.8,1.8),(1.2,1.2,6.5,1.4)]
    for rx,ry,z,h in sizes:
        ibox(surf,cx,cy,-rx,-ry,z, rx*2,ry*2,h, T, SP2,SP1,SP0)

    # Organic surface texture (darker stripe rings on front faces)
    for i in range(4):
        z_s = 1.5 + i*1.7
        ibox(surf,cx,cy, -3+i*0.4, -3+i*0.4, z_s, (3-i*0.4)*2, 0.4, 0.3,
             T, shade(SP0,0.6),shade(SP0,0.4),shade(SP0,0.3))

    # Entrance tunnel (dark recess on front face)
    ent_pts = [ip(cx,cy,-1.2,-3.5,0.5,T), ip(cx,cy,1.2,-3.5,0.5,T),
               ip(cx,cy,1.2,-3.5,2.5,T),  ip(cx,cy,-1.2,-3.5,2.5,T)]
    pygame.draw.polygon(surf, (6,2,10), ent_pts)
    pygame.draw.polygon(surf, BLK, ent_pts, SC*1)

    # Green bioluminescent spots (3-4 glowing holes on surface)
    for sx,sy,sz in [(-2.5,-3.5,2.8),(1.8,-3.0,3.5),(-0.5,-2.8,5.5),(2.0,-2.5,2.2)]:
        sp = ip(cx,cy,sx,sy,sz,T)
        pygame.draw.circle(surf, BLK, sp, SC*3)
        pygame.draw.circle(surf, SA0, sp, SC*2)
        pygame.draw.circle(surf, SA1, sp, SC*1)

    # Crown (organic tip)
    ibox(surf,cx,cy, -0.6,-0.6,8.1, 1.2,1.2,1.2, T, SP3,SP2,SP1)
    tip = ip(cx,cy, 0,0,9.5, T)
    pygame.draw.circle(surf, SA1, tip, SC*2)
    pygame.draw.circle(surf, SA2, (tip[0],tip[1]-SC), SC*1)

    save_png(surf, "hive_nest", W, H)


def draw_spine_ridge():
    """Cluster of bone spines erupting from organic base -- Swarm defensive structure."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*8
    T = 13

    shadow_iso(surf, cx, cy, 4.0, 3.0, T)

    # Organic base mound
    ibox(surf,cx,cy, -3.5,-3.5,0, 7,7,1.5, T, shade(SP1,0.7),shade(SP0,0.7),shade(SP0,0.5))
    ibox(surf,cx,cy, -2.5,-2.5,1.5, 5,5,0.8, T, shade(SP1,0.8),shade(SP0,0.8),shade(SP0,0.6))

    # Flesh tissue strips on base
    for i in range(4):
        ibox(surf,cx,cy, -3,-2.5+i*1.5,0.5, 6,0.5,0.4, T, SBR2,SBR1,SBR0)

    # Large central spine cluster (bone-white + red tips)
    spines = [
        (-0.4,-0.4,2.3, 0.8,0.8,5.5),   # tallest centre
        ( 1.0,-1.0,2.0, 0.7,0.7,4.2),   # right-forward
        (-1.5, 0.5,2.0, 0.7,0.7,4.0),   # left-back
        ( 0.3, 1.5,1.5, 0.6,0.6,3.2),   # back
        (-1.8,-1.5,1.5, 0.6,0.6,3.0),   # left-forward
        ( 2.2, 0.5,1.5, 0.5,0.5,2.5),   # far right
        (-0.5,-2.2,1.5, 0.5,0.5,2.8),   # far forward
    ]
    for x0,y0,z0,w,d,h in spines:
        # Bone shaft (white-grey)
        ibox(surf,cx,cy, x0,y0,z0, w,d,h*0.75, T, SB1,SB0,shade(SB0,0.7))
        # Red-tipped top third
        ibox(surf,cx,cy, x0+0.05,y0+0.05,z0+h*0.72, w-0.1,d-0.1,h*0.28,
             T, SR1,SR0,shade(SR0,0.8))
        # Tip glow
        tx,ty = ip(cx,cy, x0+w/2,y0+d/2,z0+h, T)
        pygame.draw.circle(surf, SR1, (tx,ty), SC*2)

    save_png(surf, "spine_ridge", W, H)


def draw_scourge_nest():
    """Organic egg-sac cluster: large main sac, satellite eggs, orange bioluminescent glow."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2 - SC; cy = H*SC//2 + SC*6
    T = 13

    shadow_iso(surf, cx, cy, 4.5, 3.5, T)

    OR0=(90,14,12); OR1=(165,42,18); OR2=(248,108,28)

    # Organic base puddle
    base_pts = [ip(cx,cy,-4,0,0,T), ip(cx,cy,0,-4,0,T),
                ip(cx,cy,4,0,0,T),  ip(cx,cy,0,4,0,T)]
    pygame.draw.polygon(surf, shade(SP0,0.4), base_pts)

    # Satellite small sacs (draw behind main)
    sacs = [(-2.5,-2.5,0,1.2,1.2,1.6),(2.5,-1.5,0,1.4,1.4,2.0),
            (-1.0, 2.5,0,1.3,1.3,1.8),(3.0, 1.5,0,1.0,1.0,1.4),
            (-3.0, 1.0,0,1.0,1.0,1.3)]
    for x0,y0,z0,w,d,h in sacs:
        # Sac body (stacked decreasing boxes)
        ibox(surf,cx,cy, x0,y0,z0, w,d,h*0.6, T, shade(OR1,0.6),shade(OR0,0.6),shade(OR0,0.4))
        ibox(surf,cx,cy, x0+0.15,y0+0.15,z0+h*0.55, w-0.3,d-0.3,h*0.35,
             T, shade(OR1,0.8),shade(OR0,0.7),shade(OR0,0.5))
        # Membrane vein
        mp = ip(cx,cy, x0+w/2, y0, z0+h*0.7, T)
        pygame.draw.circle(surf, OR1, mp, SC*2)

    # Main large sac (centre, tallest)
    ibox(surf,cx,cy, -2.0,-2.0,0, 4,4,2.5, T, shade(OR1,0.7),shade(OR0,0.7),shade(OR0,0.5))
    ibox(surf,cx,cy, -1.5,-1.5,2.5, 3,3,2.0, T, OR1,shade(OR1,0.8),shade(OR0,0.8))
    ibox(surf,cx,cy, -1.0,-1.0,4.5, 2,2,1.2, T, OR2,OR1,shade(OR1,0.8))

    # Membrane ridges (bone-white skin texture on main sac)
    for i in range(3):
        ibox(surf,cx,cy, -2+i*0.3, -2+i*0.3, 0.8+i*1.4, (4-i*0.6),(4-i*0.6), 0.35,
             T, shade(SB1,0.5),shade(SB0,0.4),shade(SB0,0.3))

    # Central glowing core (orange-red hot)
    cp = ip(cx,cy, 0,0,4.0, T)
    pygame.draw.circle(surf, BLK, cp, SC*5)
    pygame.draw.circle(surf, OR0, cp, SC*4)
    pygame.draw.circle(surf, OR1, cp, SC*3)
    pygame.draw.circle(surf, OR2, cp, SC*2)
    pygame.draw.circle(surf, (255,200,80), (cp[0],cp[1]-SC), SC*1)

    # Sticky tendrils from base
    for a in [30,90,150,210,270,330]:
        r = math.radians(a)
        tx = math.cos(r)*3.5; ty = math.sin(r)*3.5
        p0 = ip(cx,cy,0,0,0.3,T); p1 = ip(cx,cy,tx,ty,0,T)
        pygame.draw.line(surf, shade(SP1,0.8), p0, p1, SC*1)

    save_png(surf, "scourge_nest", W, H)


# ============================================================
# ROGUE AI BUILDINGS
# ============================================================

def draw_logic_core():
    """Hovering processor core: elevated platform, central cube, blue circuit glow."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*4
    T = 14

    shadow_iso(surf, cx, cy, 3.5, 3, T)

    # Support legs (4 thin pillars)
    for lx,ly in [(-2.5,-2.5),(2.5,-2.5),(-2.5,2.5),(2.5,2.5)]:
        ibox(surf,cx,cy, lx-0.3,ly-0.3,0, 0.6,0.6,3.5, T, RG2,RG1,RG0)

    # Platform base
    ibox(surf,cx,cy, -3,-3,3.5, 6,6,0.8, T, RG2,RG1,RG0)

    # Platform circuit grid lines (on top face)
    for d in [-1.0,0,1.0]:
        p0 = ip(cx,cy,-3+0.1,d,4.3,T); p1 = ip(cx,cy,3-0.1,d,4.3,T)
        pygame.draw.line(surf, RB0, p0, p1, SC*1)
        p0 = ip(cx,cy,d,-3+0.1,4.3,T); p1 = ip(cx,cy,d,3-0.1,4.3,T)
        pygame.draw.line(surf, RB0, p0, p1, SC*1)

    # Central processor cube (slightly elevated above platform)
    ibox(surf,cx,cy, -2,-2,4.3, 4,4,3.5, T, RG2,RG1,RG0)
    # Inner bright face strip (circuit block inside)
    ibox(surf,cx,cy, -1.4,-2,5.0, 2.8,0.2,2.0, T, RG3,RB0,shade(RB0,0.7))

    # Circuit lines on cube front face (y=-2)
    for z_off in [0.6,1.2,1.8]:
        p0 = ip(cx,cy,-1.8,-2,4.5+z_off,T); p1 = ip(cx,cy,1.8,-2,4.5+z_off,T)
        pygame.draw.line(surf, RB0, p0, p1, SC*1)

    # Top sensor eye
    ibox(surf,cx,cy, -0.8,-0.8,7.8, 1.6,1.6,1.2, T, RG1,RG0,shade(RG0,0.7))
    ep = ip(cx,cy, 0,0,9.2, T)
    pygame.draw.circle(surf, BLK, ep, SC*4)
    pygame.draw.circle(surf, RQ0, ep, SC*3)
    pygame.draw.circle(surf, RQ1, ep, SC*2)
    pygame.draw.circle(surf, RQ2, (ep[0],ep[1]-SC), SC*1)

    save_png(surf, "logic_core", W, H)


def draw_data_node():
    """Data relay tower: tall narrow shaft, wide dish antenna, teal glow."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*2
    T = 14

    shadow_iso(surf, cx, cy, 2.5, 2, T)

    # Base anchor block
    ibox(surf,cx,cy, -2.5,-2.5,0, 5,5,1.5, T, RG2,RG1,RG0)
    # Reinforcement ridges
    for i in range(3):
        ibox(surf,cx,cy, -2.2,-2.5,0.5+i*0.35, 4.4,0.5,0.2, T, RG3,RG2,RG1)

    # Tower shaft (tall narrow)
    ibox(surf,cx,cy, -1,-1,1.5, 2,2,7.5, T, RG2,RG1,RG0)

    # Mid-section accent ring
    ibox(surf,cx,cy, -1.5,-1.5,5.5, 3,3,0.6, T, RT1,RT0,shade(RT0,0.7))

    # Dish base joint
    ibox(surf,cx,cy, -1.5,-1.5,9.0, 3,3,0.8, T, RG2,RG1,RG0)

    # Wide dish antenna (flat hexagonal shape)
    dish = [ip(cx,cy, 3.5,0,9.8,T), ip(cx,cy,0,-3.5,9.8,T),
            ip(cx,cy,-3.5,0,9.8,T), ip(cx,cy,0,3.5,9.8,T)]
    pygame.draw.polygon(surf, RG1, dish)
    pygame.draw.polygon(surf, BLK, dish, SC*1)
    # Dish inner ring
    dish_in = [ip(cx,cy,2.2,0,9.8,T), ip(cx,cy,0,-2.2,9.8,T),
               ip(cx,cy,-2.2,0,9.8,T), ip(cx,cy,0,2.2,9.8,T)]
    pygame.draw.polygon(surf, RG2, dish_in)
    # Dish sensor nub
    cp = ip(cx,cy, 0,0,10.0, T)
    pygame.draw.circle(surf, BLK, cp, SC*4)
    pygame.draw.circle(surf, RT0, cp, SC*3)
    pygame.draw.circle(surf, RT1, cp, SC*2)
    pygame.draw.circle(surf, RT2, (cp[0],cp[1]-SC*1), SC*1)

    # Signal lines (4 antennas on dish perimeter)
    for ax,ay in [(3.0,0),(0,-3.0),(-3.0,0),(0,3.0)]:
        a0 = ip(cx,cy,ax,ay,9.8,T)
        a1 = ip(cx,cy,ax*1.1,ay*1.1,11.2,T)
        pygame.draw.line(surf, RT1, a0, a1, SC*1)
        pygame.draw.circle(surf, RT2, a1, SC*1)

    save_png(surf, "data_node", W, H)


def draw_quantum_array():
    """Quantum research tower: hex platform, 4 spires of varying height, energy beams."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*4
    T = 13

    QP0=(60,10,100); QP1=(120,30,180); QP2=(180,80,255); QP3=(220,160,255)

    shadow_iso(surf, cx, cy, 4, 3.5, T)

    # Hexagonal base platform
    hex6 = [ip(cx,cy, 4*math.cos(math.radians(i*60)),
                       4*math.sin(math.radians(i*60)), 0, T) for i in range(6)]
    pygame.draw.polygon(surf, shade(QP0,0.6), hex6)
    pygame.draw.polygon(surf, BLK, hex6, SC*1)
    # Platform top
    hex6t = [ip(cx,cy, 3.5*math.cos(math.radians(i*60)),
                        3.5*math.sin(math.radians(i*60)), 0.8, T) for i in range(6)]
    pygame.draw.polygon(surf, QP0, hex6t)
    pygame.draw.polygon(surf, QP1, hex6t, SC*1)

    # 4 quantum spires at platform corners (different heights for visual interest)
    spires = [(-2,-2,0.8,1.0,1.0,6.0),(2,-1.5,0.8,1.0,1.0,8.5),
              (-1.5,2,0.8,1.0,1.0,5.0),(2.0,2.0,0.8,1.0,1.0,7.0)]
    tips = []
    for x0,y0,z0,w,d,h in spires:
        # Base
        ibox(surf,cx,cy, x0,y0,z0, w,d,h*0.6, T, QP1,QP0,shade(QP0,0.7))
        # Upper taper
        ibox(surf,cx,cy, x0+0.1,y0+0.1,z0+h*0.55, w-0.2,d-0.2,h*0.45,
             T, QP2,QP1,shade(QP1,0.7))
        tip = ip(cx,cy, x0+w/2,y0+d/2,z0+h, T)
        tips.append(tip)
        pygame.draw.circle(surf, QP3, tip, SC*3)
        pygame.draw.circle(surf, (255,255,255), (tip[0],tip[1]-SC), SC*1)

    # Energy beams connecting spire tips
    for i in range(len(tips)):
        p0 = tips[i]; p1 = tips[(i+1)%len(tips)]
        pygame.draw.line(surf, QP2, p0, p1, SC*1)

    # Central quantum nexus
    ibox(surf,cx,cy, -0.7,-0.7,0.8, 1.4,1.4,3.5, T, QP1,QP0,shade(QP0,0.7))
    cp = ip(cx,cy,0,0,4.5,T)
    pygame.draw.circle(surf, BLK, cp, SC*5)
    pygame.draw.circle(surf, QP0, cp, SC*4)
    pygame.draw.circle(surf, QP1, cp, SC*3)
    pygame.draw.circle(surf, QP2, cp, SC*2)
    pygame.draw.circle(surf, QP3, (cp[0],cp[1]-SC), SC*1)

    save_png(surf, "quantum_array", W, H)


def draw_assembly_matrix():
    """Splitter forge factory: industrial block, glowing forge bay, mechanical crane arm."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*6
    T = 13

    shadow_iso(surf, cx, cy, 4, 3.5, T)

    IN0=(40,20,70); IN1=(80,42,130)   # indigo

    # Foundation slab
    ibox(surf,cx,cy, -4,-4,0, 8,8,1.0, T, RG1,RG0,shade(RG0,0.7))

    # Main factory building
    ibox(surf,cx,cy, -3.5,-3.5,1.0, 7,7,5.5, T, RG2,RG1,RG0)

    # Front bay opening (dark recess)
    bay_pts = [ip(cx,cy,-1.8,-3.5,1.5,T), ip(cx,cy,1.8,-3.5,1.5,T),
               ip(cx,cy,1.8,-3.5,5.0,T),  ip(cx,cy,-1.8,-3.5,5.0,T)]
    pygame.draw.polygon(surf, (10,5,18), bay_pts)

    # Forge glow inside bay
    fg = ip(cx,cy, 0,-3.5,3.5, T)
    pygame.draw.circle(surf, shade(RC0,0.7), fg, SC*6)
    pygame.draw.circle(surf, RC0, fg, SC*4)
    pygame.draw.circle(surf, RC1, fg, SC*2)

    # Indigo accent panels on building sides
    ibox(surf,cx,cy, -3.5,-3.5,3.5, 0.5,7,1.5, T, IN1,IN0,shade(IN0,0.7))
    ibox(surf,cx,cy,  3.0,-3.5,3.5, 0.5,7,1.5, T, IN1,IN0,shade(IN0,0.7))

    # Roof level
    ibox(surf,cx,cy, -3,-3,6.5, 6,6,0.8, T, RG3,RG2,RG1)

    # Exhaust stacks (2)
    for sx in [-1.5,1.0]:
        ibox(surf,cx,cy, sx,-1.5,7.3, 1,1,2.5, T, RG1,RG0,shade(RG0,0.7))
        ep = ip(cx,cy, sx+0.5,-1,9.8, T)
        pygame.draw.circle(surf, BLK, ep, SC*3)
        pygame.draw.circle(surf, RC0, ep, SC*2)
        pygame.draw.circle(surf, RC1, (ep[0],ep[1]-SC), SC*1)

    # Crane arm extending right (+x)
    ibox(surf,cx,cy, 3.5,-1.5,6.8, 3.0,0.8,0.8, T, RG2,RG1,RG0)
    ibox(surf,cx,cy, 6.0,-1.2,5.2, 0.6,0.6,1.7, T, RG2,RG1,RG0)
    # Claw/hook
    cp = ip(cx,cy, 6.3,-0.9,5.0, T)
    pygame.draw.circle(surf, RG3, cp, SC*2)
    pygame.draw.circle(surf, RC1, cp, SC*1)

    save_png(surf, "assembly_matrix", W, H)


def draw_sensor_array():
    """Wide-area detection array: stepped base, tall sensor mast, multiple dish receivers."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*4
    T = 13

    shadow_iso(surf, cx, cy, 4, 3.5, T)

    # Stepped base (3 layers)
    ibox(surf,cx,cy, -4,-4,0, 8,8,1.0, T, RG2,RG1,RG0)
    ibox(surf,cx,cy, -3,-3,1.0, 6,6,1.0, T, RG2,RG1,RG0)
    ibox(surf,cx,cy, -2,-2,2.0, 4,4,1.0, T, RG3,RG2,RG1)

    # Main mast
    ibox(surf,cx,cy, -0.8,-0.8,3.0, 1.6,1.6,6.5, T, RG2,RG1,RG0)

    # 3 small dish receivers at different heights on the mast
    dishes = [(3.5,4.5,True),(5.5,6.5,False),(7.5,8.2,True)]
    for z0,z1,flip in dishes:
        arm_x = 1.5 if flip else -2.5
        # Arm
        ibox(surf,cx,cy, arm_x if flip else -1.5,-0.5,z0+0.5, abs(arm_x)-0.8,0.5,0.5, T, RG2,RG1,RG0)
        # Dish bowl
        dish_pts = [
            ip(cx,cy, arm_x+0.6 if flip else -2.5, -1.5,z0,T),
            ip(cx,cy, arm_x+0.6 if flip else -2.5,  0.5,z0,T),
            ip(cx,cy, arm_x+2.0 if flip else -4.0,  0.5,z0,T),
            ip(cx,cy, arm_x+2.0 if flip else -4.0, -1.5,z0,T),
        ]
        pygame.draw.polygon(surf, RG1, dish_pts)
        pygame.draw.polygon(surf, BLK, dish_pts, SC*1)
        # Sensor eye in dish
        dc_x = (arm_x+1.3) if flip else -3.25
        dp = ip(cx,cy, dc_x,-0.5,z0+0.1,T)
        pygame.draw.circle(surf, BLK, dp, SC*2)
        pygame.draw.circle(surf, RB0, dp, SC*1)

    # Top beacon
    tp = ip(cx,cy, 0,0,9.8, T)
    pygame.draw.circle(surf, BLK, tp, SC*4)
    pygame.draw.circle(surf, RB0, tp, SC*3)
    pygame.draw.circle(surf, RB1, (tp[0],tp[1]-SC), SC*1)

    save_png(surf, "sensor_array", W, H)


def draw_plasma_forge():
    """Crimson plasma furnace: heavy base, barrel forge chamber, plasma exhaust vents."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*6
    T = 13

    shadow_iso(surf, cx, cy, 4, 3.5, T)

    # Heavy base foundation
    ibox(surf,cx,cy, -4,-4,0, 8,8,1.5, T, RG1,RG0,shade(RG0,0.7))
    # Armoured skirt
    for i in range(3):
        ibox(surf,cx,cy, -4,-4,1.5+i*0.4, 8,0.5,0.3, T, RC0,shade(RC0,0.7),shade(RC0,0.5))
        ibox(surf,cx,cy, -4,-4,1.5+i*0.4, 0.5,8,0.3, T, shade(RC1,0.5),shade(RC0,0.5),shade(RC0,0.3))

    # Main forge chamber (cylindrical - approximated as stacked boxes)
    ibox(surf,cx,cy, -2.5,-2.5,1.5, 5,5,5.0, T, RG2,RG1,RG0)
    ibox(surf,cx,cy, -2.0,-2.0,6.5, 4,4,0.8, T, RG3,RG2,RG1)   # top cap

    # Forge bay window (glowing red)
    bay = [ip(cx,cy,-1.5,-2.5,2.5,T), ip(cx,cy,1.5,-2.5,2.5,T),
           ip(cx,cy,1.5,-2.5,5.5,T),  ip(cx,cy,-1.5,-2.5,5.5,T)]
    pygame.draw.polygon(surf, (8,3,5), bay)
    fg = ip(cx,cy,0,-2.5,4.0,T)
    pygame.draw.circle(surf, shade(RP0,0.5), fg, SC*7)
    pygame.draw.circle(surf, RP0, fg, SC*4)
    pygame.draw.circle(surf, RP1, fg, SC*2)

    # 3 plasma exhaust stacks on roof
    for sx,sy in [(-1.2,-1.2),(0.2,-0.5),(0.8,1.0)]:
        ibox(surf,cx,cy, sx-0.4,sy-0.4,7.3, 0.8,0.8,2.5, T, RG1,RG0,shade(RG0,0.7))
        vp = ip(cx,cy, sx,sy,10.0, T)
        pygame.draw.circle(surf, BLK, vp, SC*3)
        pygame.draw.circle(surf, RP0, vp, SC*2)
        pygame.draw.circle(surf, RP2, (vp[0],vp[1]-SC*2), SC*1)

    save_png(surf, "plasma_forge", W, H)


def draw_quantum_core():
    """Deep-blue quantum power plant: hex platform, tall power column, energy rings."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2; cy = H*SC//2 + SC*4
    T = 13

    shadow_iso(surf, cx, cy, 4, 3.5, T)

    # Hexagonal base
    for dz,scale in [(0,4.0),(0.8,3.6),(1.4,3.0)]:
        h6 = [ip(cx,cy, scale*math.cos(math.radians(i*60)),
                         scale*math.sin(math.radians(i*60)), dz, T) for i in range(6)]
        pygame.draw.polygon(surf, shade(RQ0,0.6+dz*0.1), h6)
        pygame.draw.polygon(surf, BLK, h6, SC*1)

    # Support columns (6 small pillars at hex vertices)
    for i in range(6):
        a = math.radians(i*60)
        px = 2.8*math.cos(a); py = 2.8*math.sin(a)
        ibox(surf,cx,cy, px-0.3,py-0.3,1.4, 0.6,0.6,2.5, T, RQ1,RQ0,shade(RQ0,0.7))

    # Main power column (thick octagonal tower)
    ibox(surf,cx,cy, -1.5,-1.5,1.4, 3,3,7, T, RQ1,RQ0,shade(RQ0,0.7))
    ibox(surf,cx,cy, -0.9,-0.9,8.4, 1.8,1.8,0.8, T, RQ2,RQ1,shade(RQ1,0.7))

    # Energy rings (flat isometric ellipses at 3 heights)
    for rz in [3.5,5.5,7.5]:
        ring6 = [ip(cx,cy, 2.5*math.cos(math.radians(i*60)),
                            2.5*math.sin(math.radians(i*60)), rz, T) for i in range(6)]
        pygame.draw.polygon(surf, shade(RQ0,0.5), ring6)
        pygame.draw.polygon(surf, RQ1, ring6, SC*1)

    # Crown glow
    cp = ip(cx,cy, 0,0,9.4, T)
    pygame.draw.circle(surf, BLK,  cp, SC*5)
    pygame.draw.circle(surf, RQ0,  cp, SC*4)
    pygame.draw.circle(surf, RQ1,  cp, SC*3)
    pygame.draw.circle(surf, RQ2,  cp, SC*2)
    pygame.draw.circle(surf, (255,255,255), (cp[0],cp[1]-SC), SC*1)

    save_png(surf, "quantum_core", W, H)


def draw_oblivion_engine():
    """Near-black superweapon: massive armoured hull, long railgun barrel, dark crimson accents."""
    W, H = 96, 96
    surf = mk(W, H)
    cx = W*SC//2 + SC; cy = H*SC//2 + SC*8
    T = 12

    shadow_iso(surf, cx, cy, 5, 4.5, T)

    # Heavy armoured base (very wide, low)
    ibox(surf,cx,cy, -5,-5,0, 10,10,2.5, T, RN1,RN0,shade(RN0,0.6))

    # Armour ridge plates on base
    for i in range(4):
        ibox(surf,cx,cy, -5,-5+i*2.5,2.5, 10,0.5,0.5, T, RC0,shade(RC0,0.6),shade(RC0,0.4))
        ibox(surf,cx,cy, -5,-5+i*2.5,2.5, 0.5,10,0.5, T, shade(RC0,0.4),shade(RC0,0.3),shade(RC0,0.2))

    # Main hull superstructure
    ibox(surf,cx,cy, -3.5,-4,2.5, 7,8,5.0, T, shade(RN1,1.3),RN1,RN0)

    # Side armour plates (extra thickness)
    ibox(surf,cx,cy, -5,-3.5,1.0, 1.5,7,5.5, T, RN1,RN0,shade(RN0,0.6))
    ibox(surf,cx,cy,  3.5,-3.5,1.0, 1.5,7,5.5, T, RN1,RN0,shade(RN0,0.6))

    # Targeting visor (wide crimson stripe on front face)
    vis = [ip(cx,cy,-3.5,-4,5.0,T), ip(cx,cy,3.5,-4,5.0,T),
           ip(cx,cy,3.5,-4,4.0,T),  ip(cx,cy,-3.5,-4,4.0,T)]
    pygame.draw.polygon(surf, RC0, vis)
    vis2= [ip(cx,cy,-2.5,-4,4.9,T), ip(cx,cy,2.5,-4,4.9,T),
           ip(cx,cy,2.5,-4,4.1,T),  ip(cx,cy,-2.5,-4,4.1,T)]
    pygame.draw.polygon(surf, RC1, vis2)

    # Hull top
    ibox(surf,cx,cy, -3,-3.5,7.5, 6,7,0.8, T, shade(RN1,1.4),RN1,RN0)

    # Railgun barrel mount
    ibox(surf,cx,cy, -1.5,-2,8.3, 3,1.5,1.5, T, RN1,RN0,shade(RN0,0.7))

    # Long barrel extending forward (negative y = toward viewer)
    ibox(surf,cx,cy, -1,-10,7.5, 2,8,2, T, shade(RN1,1.2),RN1,shade(RN0,0.8))

    # EM rail channels on barrel
    for ox in [-0.3,0.3]:
        lp0=ip(cx,cy,ox,-10,9.0,T); lp1=ip(cx,cy,ox,-2,9.0,T)
        pygame.draw.line(surf, RC0, lp0, lp1, SC*1)

    # Muzzle charge glow
    mp = ip(cx,cy, 0,-10,8.5, T)
    pygame.draw.circle(surf, BLK, mp, SC*5)
    pygame.draw.circle(surf, RN2, mp, SC*4)
    pygame.draw.circle(surf, RC0, mp, SC*3)
    pygame.draw.circle(surf, RC1, mp, SC*2)
    pygame.draw.circle(surf, RC2, (mp[0],mp[1]-SC), SC*1)

    save_png(surf, "oblivion_engine", W, H)


# ── Run all ─────────────────────────────────────────────────
import traceback
for fn in [draw_mutation_pit, draw_hive_nest, draw_spine_ridge, draw_scourge_nest,
           draw_logic_core, draw_data_node, draw_quantum_array, draw_assembly_matrix,
           draw_sensor_array, draw_plasma_forge, draw_quantum_core, draw_oblivion_engine]:
    try:
        fn()
    except Exception as e:
        print(f"ERR {fn.__name__}: {e}", flush=True)
        traceback.print_exc()

pygame.quit()
print("Done.", flush=True)
