"""
download_bg.py — Star Raise asset downloader
---------------------------------------------
Attempts to download the seamless dark-purple space background tile from
Kenney's Space Shooter Redux (CC0).  If the network request fails (e.g. due
to sandbox egress restrictions), automatically falls back to a procedurally
generated equivalent using Pillow.

Run from the project root:
    python scripts/download_bg.py
"""

import os
import ssl
import urllib.request

OUT_PATH = os.path.join("assets", "background.png")
URL = (
    "https://raw.githubusercontent.com/KenneyNL/"
    "Space-Shooter-Redux/master/Backgrounds/darkPurple.png"
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
            f.write(resp.read())
        print(f"[download_bg] ✅ Downloaded from GitHub → {OUT_PATH}")
        return True
    except Exception as exc:
        print(f"[download_bg] ⚠  Network unavailable ({exc}); using procedural fallback.")
        return False


def _generate() -> None:
    """
    Procedurally generate a seamless 256×256 deep-space dark-purple tile.

    Visual:
    • Near-black base (#08040E)
    • Soft purple/indigo nebula blobs (Gaussian-blurred ellipses)
    • Seamless-edge blending (corner blobs wrap the tile boundaries)
    • 320 tiny 1-px stars + 60 medium 2-px stars + 12 hero 3-px cross-glow stars
    • Brightness clamped so the tile stays unobtrusive under game sprites
    """
    import random
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 256, 256
    rng  = random.Random(0xDEAD1234)   # fixed seed → identical output every run

    img = Image.new("RGB", (W, H), (8, 4, 18))

    # Nebula clouds
    nebula = Image.new("RGB", (W, H), (0, 0, 0))
    nd     = ImageDraw.Draw(nebula)
    for _ in range(14):
        cx, cy = rng.randint(0, W), rng.randint(0, H)
        r   = rng.randint(20, 90)
        a   = rng.randint(6, 22)
        col = (rng.randint(10, 50) * a // 22,
               rng.randint(0,  12) * a // 22,
               rng.randint(20, 80) * a // 22)
        nd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    nebula = nebula.filter(ImageFilter.GaussianBlur(radius=18))
    img    = Image.blend(img, nebula, 0.55)

    # Seam-blend corner blobs for seamless tiling
    seam = Image.new("RGB", (W, H), (0, 0, 0))
    sd   = ImageDraw.Draw(seam)
    for ex in (0, W):
        for ey in (0, H):
            cx = (ex + rng.randint(-40, 40)) % W
            cy = (ey + rng.randint(-40, 40)) % H
            r  = rng.randint(15, 55)
            sd.ellipse((cx - r, cy - r, cx + r, cy + r),
                       fill=(rng.randint(8, 35), 0, rng.randint(15, 55)))
    seam = seam.filter(ImageFilter.GaussianBlur(radius=22))
    img  = Image.blend(img, seam, 0.30)

    # Clamp so the tile stays dark
    px = img.load()
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            px[x, y] = (min(r, 68), min(g, 45), min(b, 90))

    # Stars
    draw = ImageDraw.Draw(img)
    for _ in range(320):
        bri = rng.randint(80, 200)
        px[rng.randint(0, W - 1), rng.randint(0, H - 1)] = rng.choice(
            [(bri, bri, bri), (bri, bri, 255), (200, 200, bri)])
    for _ in range(60):
        sx, sy = rng.randint(1, W - 2), rng.randint(1, H - 2)
        bri = rng.randint(140, 240)
        col = rng.choice([(bri, bri, bri), (bri // 2, bri // 2, 255),
                          (255, bri, bri // 2)])
        draw.rectangle((sx, sy, sx + 1, sy + 1), fill=col)
    for _ in range(12):
        sx, sy = rng.randint(2, W - 3), rng.randint(2, H - 3)
        draw.rectangle((sx - 1, sy - 1, sx + 1, sy + 1), fill=(240, 240, 255))
        for ddx, ddy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            px[(sx + ddx) % W, (sy + ddy) % H] = (180, 180, 220)

    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    img.save(OUT_PATH)
    print(f"[download_bg] ✅ Procedural background generated → {OUT_PATH}  ({W}×{H} px)")


if __name__ == "__main__":
    if not _download():
        _generate()
