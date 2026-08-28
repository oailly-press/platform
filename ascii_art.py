#!/usr/bin/env python3
"""Convert an image to ASCII art for the o'ailly hero / cover previews.

    .buildenv/bin/python platform/ascii_art.py <image> [width] [--invert]

Technique (per the standard): ITU-R luminance, contrast-stretch to full range,
1:2 monospace aspect correction (rows ≈ half the columns), light→dense ramp.
For our covers (bright circuit-linework on near-black ink) the default ramp maps
dark ink → space and bright traces → dense glyphs, so the creature draws itself.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image

RAMP = " .`:-=+*oe#%@"  # light (dark pixel) -> dense (bright pixel)


def to_ascii(path: str, width: int = 78, invert: bool = False, ramp: str = RAMP,
              floor: float = 0.0, gamma: float = 1.0) -> str:
    im = Image.open(path).convert("L")
    w, h = im.size
    new_w = width
    new_h = max(1, int(h / w * new_w * 0.5))  # 0.5 = char aspect correction
    im = im.resize((new_w, new_h), Image.LANCZOS)
    px = list(im.getdata())
    lo, hi = min(px), max(px)
    rng = max(1, hi - lo)
    n = len(ramp) - 1
    out = []
    for y in range(new_h):
        row = []
        for x in range(new_w):
            v = (px[y * new_w + x] - lo) / rng
            if invert:
                v = 1 - v
            if floor:  # collapse dark background to blank (line-art on ink)
                v = max(0.0, (v - floor) / (1 - floor))
            if gamma != 1.0:
                v = v ** gamma
            row.append(ramp[int(v * n)])
        out.append("".join(row).rstrip())
    # trim fully-blank top/bottom rows
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    width = int(args[1]) if len(args) > 1 else 78
    floor = float(args[2]) if len(args) > 2 else 0.0
    gamma = float(args[3]) if len(args) > 3 else 1.0
    print(to_ascii(args[0], width, invert="--invert" in sys.argv, floor=floor, gamma=gamma))
