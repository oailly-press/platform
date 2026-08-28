#!/usr/bin/env python3
"""Generate a book's animated-hero ASCII art from its ComfyUI insect render, and upsert it
into gh/site-repo/hero-art.json (the homepage hero rotates through these every slot_hours).

This IS the hero-art SOP — the recipe, executable:
  1. The insect image is the same Flux circuit-render used on the cover
     (brand/covers/comfyui/<insect>-<book>-v1.png; see brand/covers/comfyui/RECIPE.md).
  2. ascii_art.py converts it: light circuit-linework on near-black → dense glyphs draw the
     creature. Tune `width` (hero art reads well at ~56–64 cols), and `floor` (0.25–0.32)
     to drop the dark background to blank. Bright pads/traces become the densest glyphs.
  3. The homepage animates it for free: per-row reveal, a slow bob, char-level "spark"
     twinkle, and ambient rising glyphs — all driven off the book's accent colour.

    python3 platform/build_hero_art.py <book_id> <png> <accent> [--width 60] [--floor 0.28] [--gamma 1.0]

Example (a newly published book):
    python3 platform/build_hero_art.py rogerai-labs--linux-for-language-models \\
        brand/covers/comfyui/termite-linux-v1.png '#C6923E' --width 60 --floor 0.30
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))
from ascii_art import to_ascii  # noqa: E402

HERO = ROOT / "gh/site-repo/hero-art.json"


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__); return
    book_id, png, accent = args[0], args[1], args[2]
    width = int(opt("--width", "60"))
    floor = float(opt("--floor", "0.28"))
    gamma = float(opt("--gamma", "1.0"))

    art = to_ascii(str(ROOT / png) if not Path(png).is_absolute() else png,
                   width=width, floor=floor, gamma=gamma).splitlines()
    # dedent: strip the common leading whitespace shared by every non-blank row
    indent = min((len(r) - len(r.lstrip()) for r in art if r.strip()), default=0)
    art = [r[indent:] if r.strip() else "" for r in art]

    d = json.loads(HERO.read_text()) if HERO.is_file() else {"slot_hours": 6, "books": {}}
    d.setdefault("books", {})
    d["books"][book_id] = {"accent": accent, "art": [r.rstrip() for r in art]}
    HERO.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    cols = max((len(r) for r in art), default=0)
    print(f"hero-art.json ← {book_id}: {cols} cols × {len(art)} lines, accent {accent}")


if __name__ == "__main__":
    main()
