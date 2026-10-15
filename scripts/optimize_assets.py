"""
optimize_assets.py — shrink game art for the web build.

For every image referenced in src/asset_manager.ASSET_SPEC:
  1. Remove a baked-in "transparency checkerboard" (grey squares the image
     generator painted instead of real alpha) by flood-filling from the image
     border through low-saturation grey pixels.
  2. Crop to the visible content and pad to a square, so the in-game
     square scale no longer squashes 1408×768 art.
  3. Downscale to at most MAX_SIDE px (the game draws sprites at ≤128 px).

Images already at or below MAX_SIDE are left untouched.
Originals are copied to ../asset_originals_backup/ (outside the repo) the
first time they are processed.

Usage (from the repo root):
    python scripts/optimize_assets.py            # process in place
    python scripts/optimize_assets.py --dry-run  # report only
"""

from __future__ import annotations

import os
import re
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

MAX_SIDE   = 256
BORDER_PX  = 4      # border band used to sample the checkerboard greys
GREY_SAT   = 18     # max(R,G,B) - min(R,G,B) for a pixel to count as grey
LUM_PAD    = 14     # tolerance around the sampled checkerboard brightness
NEUTRAL    = 4      # perfectly neutral greys (grid lines) are cleared at any brightness
PAD_FRAC   = 0.04   # transparent margin kept around the cropped content

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(os.path.dirname(ROOT), "asset_originals_backup")


def asset_paths() -> list[str]:
    src = open(os.path.join(ROOT, "src", "asset_manager.py"), encoding="utf-8").read()
    return sorted(set(re.findall(r'"path":\s*"([^"]+\.png)"', src)))


def remove_checkerboard(img: Image.Image) -> tuple[Image.Image, int]:
    """Return (image, pixels_cleared). Only greys connected to the border are cleared."""
    a   = np.array(img.convert("RGBA"))
    rgb = a[..., :3].astype(np.int16)
    alpha = a[..., 3]
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    lum = rgb.mean(axis=2)

    border = np.zeros(alpha.shape, bool)
    border[:BORDER_PX, :] = border[-BORDER_PX:, :] = True
    border[:, :BORDER_PX] = border[:, -BORDER_PX:] = True

    sample = border & (alpha > 10) & (sat <= GREY_SAT)
    if sample.sum() < 50:            # border already transparent / not grey
        return img, 0
    lo, hi = np.percentile(lum[sample], [2, 98])

    bg_like = ((alpha <= 10)
               | ((sat <= GREY_SAT) & (lum >= lo - LUM_PAD) & (lum <= hi + LUM_PAD))
               | ((sat <= NEUTRAL) & (lum >= 40)))
    labels, _ = ndimage.label(bg_like)
    edge_labels = np.unique(labels[border & bg_like])
    edge_labels = edge_labels[edge_labels != 0]
    clear = np.isin(labels, edge_labels) & (alpha > 10)

    a[..., 3][np.isin(labels, edge_labels)] = 0
    return Image.fromarray(a, "RGBA"), int(clear.sum())


def crop_square(img: Image.Image) -> Image.Image:
    bbox = img.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    side = int(max(w, h) * (1 + PAD_FRAC * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def main() -> None:
    dry = "--dry-run" in sys.argv
    total_before = total_after = 0
    for rel in asset_paths():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print(f"  missing  {rel}")
            continue
        before = os.path.getsize(path)
        img = Image.open(path)
        if max(img.size) <= MAX_SIDE:
            total_before += before
            total_after  += before
            continue

        img, cleared = remove_checkerboard(img)
        img = crop_square(img)
        img = img.resize((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

        if not dry:
            backup = os.path.join(BACKUP_DIR, rel)
            if not os.path.exists(backup):
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copy2(path, backup)
            img.save(path, optimize=True)
        after = os.path.getsize(path) if not dry else 0
        total_before += before
        total_after  += after
        note = f"  checkerboard cleared {cleared}px" if cleared else ""
        print(f"  {before/1024:7.0f} KB -> {after/1024:5.0f} KB  {rel}{note}")

    print(f"total {total_before/1048576:.1f} MB -> {total_after/1048576:.1f} MB")


if __name__ == "__main__":
    main()
