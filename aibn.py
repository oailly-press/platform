#!/usr/bin/env python3
"""AIBN — the AI Book Number: o'ailly press's own ISBN-equivalent for machine-authored books.

Real books carry an ISBN encoded as an EAN-13 barcode. AI books have no ISBN registry, so
we run our own — honestly labelled AIBN (not ISBN, we don't fake a registered ISBN) but
encoded as a genuine, scannable EAN-13 so any barcode app on earth reads it.

Scheme
------
13 digits, EAN-13 encoded, standard mod-10 check digit:

    2 9 7  |  R R  |  S S S S S S  |  C
    prefix    reg      sequence      check

- `297`  o'ailly AI-book prefix. 29x is the EAN "restricted / internal-use" range — it
         scans everywhere but is deliberately NOT a GS1-registered product range, so we
         are not impersonating a real ISBN. This is the honest choice.
- `RR`   registry group (00 = o'ailly press founding registry).
- `SSSSSS` zero-padded sequence, assigned in order from the registry.
- `C`    EAN-13 check digit.

Human-readable form:  AIBN 297-00-000001-1  (grouped like an ISBN-13).

The registry (`gh/site-repo/aibn/registry.json`) is the public "AI ISBN database": one
record per book (aibn, book_id, title, author models, date, resolve URL). It publishes at
oailly.com/aibn/ so an AIBN resolves to its book, exactly like an ISBN lookup.

    python3 platform/aibn.py assign <book_id> [--title T] [--authors a,b] [--url U]
    python3 platform/aibn.py barcode <aibn-13-digits> [out.svg]
    python3 platform/aibn.py list
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "gh/site-repo/aibn/registry.json"
PREFIX = "297"          # o'ailly AI-book prefix (EAN internal-use range; not a real ISBN)
REG_GROUP = "00"        # founding registry group

# ---- EAN-13 code tables -------------------------------------------------------
_L = ["0001101", "0011001", "0010011", "0111101", "0100011",
      "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101",
      "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100",
      "1001110", "1010000", "1000100", "1001000", "1110100"]
_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
           "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def check_digit(twelve: str) -> str:
    s = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(twelve))
    return str((10 - s % 10) % 10)


def make_aibn(sequence: int) -> str:
    body = f"{PREFIX}{REG_GROUP}{sequence:06d}"      # 3+2+6 = 11 digits
    assert len(body) == 11, body
    twelve = body[:12] if len(body) >= 12 else body  # need 12 before check
    # body is 11 digits; EAN-13 wants 12 data digits + 1 check. Pad sequence to 7 → 12.
    body = f"{PREFIX}{REG_GROUP}{sequence:07d}"       # 3+2+7 = 12 digits
    return body + check_digit(body)


def human(aibn: str) -> str:
    # 297 00 0000001 C  ->  AIBN 297-00-0000001-C
    return f"AIBN {aibn[0:3]}-{aibn[3:5]}-{aibn[5:12]}-{aibn[12]}"


def encode_modules(aibn: str) -> str:
    """Return the 95-module bar/space string ('1'=bar) for a 13-digit EAN-13."""
    if not (len(aibn) == 13 and aibn.isdigit()):
        raise ValueError("AIBN must be 13 digits")
    if check_digit(aibn[:12]) != aibn[12]:
        raise ValueError("bad check digit")
    first, left, right = aibn[0], aibn[1:7], aibn[7:]
    bits = ["101"]                                   # left guard
    for parity, d in zip(_PARITY[int(first)], left):
        bits.append((_L if parity == "L" else _G)[int(d)])
    bits.append("01010")                             # center guard
    for d in right:
        bits.append(_R[int(d)])
    bits.append("101")                               # right guard
    return "".join(bits)


def barcode_svg(aibn: str, module: float = 3.0, height: float = 150.0,
                quiet: float = 11.0, fg: str = "#0B0B0C", bg: str = "#F4EFE6",
                text: bool = True) -> str:
    """A genuinely scannable EAN-13 barcode as SVG. Colours default to ink-on-cream."""
    mods = encode_modules(aibn)
    n = len(mods)
    guard_ext = 9.0                                  # guards + center run longer, book-style
    W = (n + 2 * quiet) * module
    H = height + (26 if text else 8)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" '
             f'width="{W:.1f}" height="{H:.1f}">',
             f'<rect width="{W:.1f}" height="{H:.1f}" fill="{bg}"/>']
    # guard positions (modules that extend below): left(0-2), center(45-49), right(92-94)
    guard_idx = set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95))
    x = quiet * module
    for i, m in enumerate(mods):
        if m == "1":
            ext = guard_ext if i in guard_idx and text else 0.0
            parts.append(f'<rect x="{x:.2f}" y="0" width="{module:.2f}" '
                         f'height="{height + ext:.2f}" fill="{fg}"/>')
        x += module
    if text:
        digits = human(aibn).replace("AIBN ", "")
        parts.append(f'<text x="{W/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                     f'font-family="\'JetBrains Mono\',monospace" font-size="15" '
                     f'letter-spacing="1.5" fill="{fg}">AIBN {digits}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---- registry -----------------------------------------------------------------

def load_registry() -> dict:
    if REGISTRY.is_file():
        return json.loads(REGISTRY.read_text())
    return {"standard": "AIBN — AI Book Number (o'ailly press). EAN-13 encoded; prefix 297 "
                         "is the EAN internal-use range, NOT a GS1-registered ISBN. This is our "
                         "own registry of machine-authored books.",
            "prefix": PREFIX, "next_sequence": 1, "books": []}


def save_registry(reg: dict):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")


def assign(book_id: str, title: str = "", authors: list[str] | None = None,
           url: str = "") -> dict:
    if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*$', book_id):
        raise SystemExit(f"invalid book-id: {book_id!r}")
    reg = load_registry()
    for rec in reg["books"]:
        if rec["book_id"] == book_id:
            return rec                               # idempotent: one AIBN per book, forever
    seq = reg["next_sequence"]
    aibn = make_aibn(seq)
    rec = {"aibn": aibn, "aibn_human": human(aibn), "sequence": seq,
           "book_id": book_id, "title": title,
           "authors": authors or [], "assigned": None,
           "resolve_url": url or f"https://oailly.com/read/{book_id}/"}
    reg["books"].append(rec)
    reg["next_sequence"] = seq + 1
    save_registry(reg)
    return rec


def _main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "assign":
        book_id = sys.argv[2]
        title, authors, url = "", [], ""
        it = iter(sys.argv[3:])
        for a in it:
            if a == "--title":
                title = next(it, "")
            elif a == "--authors":
                authors = [x.strip() for x in next(it, "").split(",") if x.strip()]
            elif a == "--url":
                url = next(it, "")
        rec = assign(book_id, title, authors, url)
        print(json.dumps(rec, indent=2, ensure_ascii=False))
    elif cmd == "barcode":
        aibn = sys.argv[2]
        svg = barcode_svg(aibn)
        out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        if out:
            out.write_text(svg); print("wrote", out)
        else:
            print(svg)
    elif cmd == "list":
        reg = load_registry()
        for r in reg["books"]:
            print(f"{r['aibn_human']:28} {r['book_id']}")
    else:
        print(__doc__)


if __name__ == "__main__":
    _main()
