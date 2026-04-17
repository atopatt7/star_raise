"""
download_bg.py — Star Raise asset downloader
---------------------------------------------
Attempts to download the seamless riveted iron plate floor texture from
Kenney's Isometric Sci-Fi pack (CC0).  If the network request fails (e.g.
due to sandbox egress restrictions), automatically falls back to a
procedurally generated metal floor tile using Pillow.

Run from the project root:
    python scripts/download_bg.py
"""

import os
import ssl
import urllib.request

OUT_PATH = os.path.join("assets", "background.png")
URL = (
    "https://raw.githubusercontent.com/KenneyNL/"
    "Isometric-Sci-Fi/master/PNG/Floor/floor_01.png"
)

os.makedirs("assets", exist_ok=True)


def _download() -> bool:
    """Try to fetch the PNG from GitHub.  Returns True on success."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp, \
                open(OUT_PATH, "wb") as f:
            data = resp.read()
            f.write(data)
        print(f"[download_bg] ✅ Downloaded from GitHub → {OUT_PATH}")
        return True
    except Exception as exc:
        print(f"[download_bg] ⚠  Network unavailable ({exc}); using procedural fallback.")
        return False


def _generate() -> None:
    """
    Procedurally generate a seamless 256×256 riveted iron plate floor tile.

    Visual layers (bottom to top)
    ------------------------------
    1. Dark steel base  (#2a2e35)
    2. Subtle panel grid (slightly darker seam lines every 64 px)
    3. Per-panel specular gradient (top-left lighter, bottom-right darker)
    4. Surface noise / micro-scratches (random single-pixel brightness jitter)
    5. Rivet grid: one rivet per 64×64 panel, near each corner
       Each rivet: dark outer ring → mid steel → bright highlight dot
    6. Very slight overall desaturated vignette at seam lines
    """
    import random
    from PIL import Image, ImageDraw, ImageFilter

    W, H   = 256, 256
    rng    = random.Random(0xFE1C0AD5)   # fixed seed → identical output every run

    # ── 1. Steel base ─────────────────────────────────────────────────────────
    img = Image.new("RGB", (W, H), (42, 46, 53))   # #2a2e35

    # ── 2. Panel seam grid (every 64 px) ──────────────────────────────────────
    draw = ImageDraw.Draw(img)
    GRID = 64
    SEAM = (28, 31, 36)           # darker seam line
    for x in range(0, W, GRID):
        draw.line([(x, 0), (x, H - 1)], fill=SEAM, width=2)
    for y in range(0, H, GRID):
        draw.line([(0, y), (W - 1, y)], fill=SEAM, width=2)

    # ── 3. Per-panel specular gradient ────────────────────────────────────────
    spec = Image.new("RGB", (W, H), (0, 0, 0))
    sp   = spec.load()
    for py in range(H):
        for px_x in range(W):
            # local position within the 64×64 panel
            lx = px_x % GRID
            ly = py  % GRID
            # gradient: top-left brightest (+14), bottom-right darkest (-6)
            bright = int(14 * (1 - lx / GRID) * (1 - ly / GRID))
            dark   = int( 6 * (lx / GRID)     * (ly / GRID))
            v = max(0, min(255, bright - dark))
            sp[px_x, py] = (v, v, v)
    img = Image.blend(img, Image.blend(img, spec, 0), 0)   # manual additive
    # True additive: clamp channel-wise add
    base_px = img.load()
    spec_px = spec.load()
    for y in range(H):
        for x in range(W):
            br, bg, bb = base_px[x, y]
            sv = spec_px[x, y][0]
            base_px[x, y] = (min(255, br + sv), min(255, bg + sv), min(255, bb + sv))

    # ── 4. Surface noise / micro-scratches ────────────────────────────────────
    px = img.load()
    for _ in range(1800):
        nx = rng.randint(0, W - 1)
        ny = rng.randint(0, H - 1)
        delta = rng.randint(-12, 18)
        r, g, b = px[nx, ny]
        px[nx, ny] = (
            max(0, min(255, r + delta)),
            max(0, min(255, g + delta)),
            max(0, min(255, b + delta)),
        )
    # occasional horizontal scratch lines
    for _ in range(6):
        sy = rng.randint(4, H - 4)
        sx = rng.randint(0, W // 2)
        sw = rng.randint(20, 80)
        bri = rng.randint(55, 75)
        draw.line([(sx, sy), (sx + sw, sy)], fill=(bri, bri + 2, bri + 4), width=1)

    # ── 5. Rivets — one per 64×64 panel, positioned near each quadrant corner ─
    RIVET_OFFSET = 10    # px from the panel seam
    for panel_col in range(W // GRID):
        for panel_row in range(H // GRID):
            # Rivet centre slightly inset from the top-left corner of each panel
            rx = panel_col * GRID + RIVET_OFFSET
            ry = panel_row * GRID + RIVET_OFFSET
            # Dark shadow ring (r=5)
            draw.ellipse((rx - 5, ry - 5, rx + 5, ry + 5), fill=(20, 22, 26))
            # Main rivet body (r=4) — slightly lighter than base plate
            draw.ellipse((rx - 4, ry - 4, rx + 4, ry + 4), fill=(55, 60, 68))
            # Mid-tone inner dome (r=2)
            draw.ellipse((rx - 2, ry - 2, rx + 2, ry + 2), fill=(70, 76, 85))
            # Specular highlight dot (1px, top-left of dome)
            draw.point((rx - 1, ry - 1), fill=(160, 168, 180))

    # ── 6. Very slight final soften (removes aliasing from drawn elements) ─────
    img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

    img.save(OUT_PATH)
    print(f"[download_bg] ✅ Procedural metal floor tile generated → {OUT_PATH}  (256×256)")


if __name__ == "__main__":
    if not _download():
        _generate()
