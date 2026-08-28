#!/usr/bin/env python3
"""Generate a 1200x630 social/OG share card per book: cover + title + AIBN + byline.

When someone shares a book link (oailly.com/read/<id>/), this is the rich preview that
renders on X, Slack, iMessage, etc. Cover on the left, the book's identity on the right.

    .buildenv/bin/python brand/covers/og_card.py <book_id> [book_id ...]

Writes gh/site-repo/assets/og/<book_id>.png.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "platform"))
import aibn  # noqa: E402

SITE = ROOT / "gh/site-repo"
W, H = 1200, 630


def wrap(text, n):
    out, cur = [], ""
    for w in (text or "").split():
        if len(cur) + len(w) + 1 > n:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


def card_svg(b, rec):
    accent = (b.get("mascot") or {}).get("accent") or "#E8935A"
    cover = SITE / (b.get("cover") or "").lstrip("/")
    title = b.get("title") or b["id"]
    sub = b.get("subtitle") or ""
    author = ", ".join(a for a in (b.get("written_by") or []) if a and a.lower() != "tbd") or "a machine"
    aibn_h = (rec or {}).get("aibn_human", "")

    tlines = wrap(title, 20)[:2]
    tblock = "".join(
        f'<text x="470" y="{188 + i*66}" font-size="58" font-weight="800" '
        f'letter-spacing="-1.5" fill="#F1EEE8">{escape(l)}</text>'
        for i, l in enumerate(tlines))
    y_sub = 188 + len(tlines) * 66 + 6
    sblock = "".join(
        f'<text x="472" y="{y_sub + i*34}" font-size="26" fill="{accent}">{escape(l)}</text>'
        for i, l in enumerate(wrap(sub, 34)[:2]))

    cover_tag = ""
    if cover.is_file():
        # cover is 1000x1300; fit to height 470, left panel. Embed as data URI (reliable in rsvg).
        cw = int(470 * 1000 / 1300)
        data = base64.b64encode(cover.read_bytes()).decode()
        cover_tag = (f'<rect x="56" y="78" width="{cw+8}" height="478" rx="10" fill="#000" opacity="0.5"/>'
                     f'<image xlink:href="data:image/png;base64,{data}" x="60" y="80" width="{cw}" height="470"/>'
                     f'<rect x="60" y="80" width="{cw}" height="470" rx="8" fill="none" '
                     f'stroke="{accent}" stroke-width="1.5" opacity="0.35"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Archivo,Inter,system-ui,sans-serif">
  <rect width="{W}" height="{H}" fill="#100E0C"/>
  <rect width="{W}" height="{H}" fill="url(#g)"/>
  <defs><radialGradient id="g" cx="78%" cy="20%" r="90%">
    <stop offset="0" stop-color="{accent}" stop-opacity="0.14"/><stop offset="0.6" stop-color="{accent}" stop-opacity="0"/>
  </radialGradient></defs>
  {cover_tag}
  <text x="470" y="104" font-size="38" font-weight="800" letter-spacing="-1" fill="#E8EAED">o'<tspan fill="{accent}">ai</tspan>lly</text>
  <text x="470" y="134" font-family="'JetBrains Mono',monospace" font-size="15" letter-spacing="3" fill="#8A919C">{escape((b.get('series') or "O'AILLY").upper())}</text>
  {tblock}
  {sblock}
  <text x="470" y="500" font-size="26" font-weight="700" fill="#E8EAED">{escape(author)}</text>
  <text x="470" y="530" font-size="19" fill="#8A919C">verified by {escape(b.get('verified_by') or 'a named human')}</text>
  <line x1="470" y1="556" x2="1144" y2="556" stroke="{accent}" stroke-width="1.5" opacity="0.5"/>
  <text x="470" y="586" font-family="'JetBrains Mono',monospace" font-size="15" letter-spacing="1" fill="#8A919C">{escape(aibn_h)}  <tspan fill="{accent}">·</tspan>  written by machines, verified by humans</text>
</svg>'''


def build(book_id):
    catalog = json.loads((SITE / "catalog.json").read_text())
    b = next((x for x in catalog["books"] if x["id"] == book_id), None)
    if not b:
        print(f"  skip {book_id}: not in catalog"); return
    rec = next((r for r in aibn.load_registry()["books"] if r["book_id"] == book_id), None)
    svg = card_svg(b, rec)
    out_svg = HERE / f"og-{book_id}.svg"
    out_png = SITE / "assets/og" / f"{book_id}.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg)
    subprocess.run(["rsvg-convert", str(out_svg), "-w", str(W), "-h", str(H), "-o", str(out_png)], check=True)
    out_svg.unlink(missing_ok=True)
    print(f"  wrote assets/og/{book_id}.png")


if __name__ == "__main__":
    for bid in sys.argv[1:]:
        build(bid)
