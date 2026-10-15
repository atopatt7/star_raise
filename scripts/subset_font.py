"""
subset_font.py — shrink NotoSansTC.ttf to the glyphs the game actually uses.

All on-screen text is hard-coded in the Python sources and data/*.json, so the
character set is collected from those files plus printable ASCII.  Run by the
deploy workflow on the CI copy only; the full font stays in the repo.

Usage (from the repo root):
    python scripts/subset_font.py [output_path]   # default: overwrite in place
"""

from __future__ import annotations

import glob
import os
import sys

from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "assets", "fonts", "NotoSansTC.ttf")


def used_text() -> str:
    files = [os.path.join(ROOT, "main.py")]
    files += glob.glob(os.path.join(ROOT, "src", "*.py"))
    files += glob.glob(os.path.join(ROOT, "data", "*.json"))
    chars = {chr(c) for c in range(0x20, 0x7F)}
    for path in files:
        with open(path, encoding="utf-8") as f:
            chars.update(ch for ch in f.read() if ord(ch) >= 0x80)
    return "".join(sorted(chars))


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else FONT
    before = os.path.getsize(FONT)
    text = used_text()
    subset.main([FONT, f"--text={text}", f"--output-file={out}",
                 "--layout-features=*", "--no-hinting"])
    print(f"{len(text)} glyphs  {before/1024:.0f} KB -> {os.path.getsize(out)/1024:.0f} KB")


if __name__ == "__main__":
    main()
