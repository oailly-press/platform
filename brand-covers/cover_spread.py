#!/usr/bin/env python3
"""Generate o'ailly FRONT + BACK book covers as a single spread.

The signature move (founder, 2026-08-28): a huge ASCII rendering of the book's insect is
placed straddling the spine, so half of it bleeds across the front cover and the other half
across the back cover. Lay the two SVGs side by side (back | front) and the creature is whole.

Back cover carries: the other half of the insect, a real synopsis, "what's inside", the
provenance one-liner, and a genuine scannable AIBN (our AI Book Number) EAN-13 barcode.

    .buildenv/bin/python brand/covers/cover_spread.py [slug ...]

Outputs brand/covers/cover-front-<slug>.svg and cover-back-<slug>.svg (1000x1300 each),
plus a combined cover-spread-<slug>.svg preview.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "platform"))
import aibn  # noqa: E402

W, H = 1000, 1300           # one cover
SPREAD_W = 2 * W            # back(left) + front(right)
SEAM = W                    # x of the spine in spread coords


def hero_ascii(book_id: str) -> list[str] | None:
    d = json.loads((ROOT / "gh/site-repo/hero-art.json").read_text())
    e = d.get("books", {}).get(book_id)
    return e.get("art") if e else None


def art_file(name: str) -> list[str] | None:
    p = HERE / "ascii" / f"{name}.txt"
    if p.is_file():
        lines = p.read_text(encoding="utf-8").splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines
    return None


# image-derived ASCII (ComfyUI Flux circuit-insects → ascii_art.py), falling back to a stub.
CATERPILLAR = art_file("caterpillar") or ["(caterpillar art missing)"]
TERMITE = art_file("termite") or ["(termite art missing)"]
LEAFCUTTER = art_file("leafcutter") or ["(leafcutter art missing)"]
ATLASMOTH = art_file("atlasmoth") or ["(atlas moth art missing)"]


def ascii_svg(lines: list[str], x: float, y: float, size: float, fill: str,
              opacity: float, lh: float | None = None) -> str:
    """A monospace ASCII block as one <text>, positioned at (x,y) in the current coord space."""
    lh = lh if lh is not None else size * 0.62
    spans = []
    for i, ln in enumerate(lines):
        spans.append(f'<tspan x="{x:.1f}" dy="{0 if i == 0 else lh:.2f}">{escape(ln) or " "}</tspan>')
    return (f'<text y="{y:.1f}" font-family="\'JetBrains Mono\',ui-monospace,monospace" '
            f'font-size="{size:.1f}" fill="{fill}" opacity="{opacity}" '
            f'xml:space="preserve" style="white-space:pre">' + "".join(spans) + "</text>")


def title_block(lines, x, y0, dy, size, fill, weight=800, spacing="-2.5"):
    return "\n  ".join(
        f'<text x="{x}" y="{y0 + i*dy}" font-size="{size}" font-weight="{weight}" '
        f'letter-spacing="{spacing}" fill="{fill}">{escape(l)}</text>'
        for i, l in enumerate(lines))


MAST = ('<text x="{lx}" y="86" font-size="44" font-weight="800" letter-spacing="-1" '
        'fill="#E8EAED">o\'<tspan fill="{accent}">ai</tspan>lly</text>'
        '<path d="M {ax} 104 L {axm} 93 L {axp} 104" fill="none" stroke="{accent}" '
        'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')


def art_geom(art, size):
    """Centered on the spine: return (left_spread_x, char_advance). The insect is scaled so
    its middle sits on the seam — a genuine half bleeds onto each cover."""
    cols = max((len(l) for l in art), default=1)
    adv = size * 0.60
    width = cols * adv
    return SEAM - width / 2, adv


def front_svg(b, art) -> str:
    accent = b["accent"]
    # insect straddles the spine, centered on SEAM. Front is spread_x>=SEAM, so shift by -SEAM.
    art_y, art_size = b.get("art_y", 300), b.get("art_size", 46)
    art_left, _ = art_geom(art, art_size)
    insect = ascii_svg(art, art_left - SEAM, art_y, art_size, accent, 0.16)
    # original Flux illustration, mounted lower-right (the house look — kept alongside the ASCII)
    illo = ''
    if b.get("image"):
        ix, iy, iw = 440, 512, 548
        illo = (f'<image xlink:href="{b["image"]}" x="{ix}" y="{iy}" width="{iw}" height="{iw}"/>'
                f'<rect x="{ix}" y="{iy}" width="{iw-1}" height="{iw}" rx="12" fill="none" '
                f'stroke="{accent}" stroke-width="1.5" opacity="0.32"/>')
    tl = title_block(b["title"], 48, 250, 104, 94, "#E8EAED")
    sub = title_block(b["sub"], 52, 250 + (len(b["title"]) - 1)*104 + 62, 42, 33, accent,
                      weight=500, spacing="0")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Archivo,Inter,system-ui,sans-serif">
  <clipPath id="cf"><rect width="{W}" height="{H}"/></clipPath>
  <g clip-path="url(#cf)">
  <rect width="{W}" height="{H}" fill="{b['bg']}"/>
  {insect}
  {illo}
  {MAST.format(lx=52, accent=accent, ax=96, axm=107, axp=118)}
  <rect x="836" y="46" width="118" height="44" rx="8" fill="none" stroke="{accent}" stroke-width="2.5"/>
  <text x="895" y="75" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="21" letter-spacing="2" fill="{accent}">{b['rev']}</text>
  <text x="52" y="150" font-family="'JetBrains Mono',monospace" font-size="17" letter-spacing="4" fill="#8A919C">{escape(b['series'])}</text>
  {tl}
  {sub}
  <text x="52" y="1140" font-size="42" font-weight="700" letter-spacing="-0.5" fill="#E8EAED">{escape(b['author'])}</text>
  <text x="52" y="1180" font-size="24" fill="#8A919C">{escape(b['verifier'])}</text>
  <line x1="0" y1="1236" x2="{W}" y2="1236" stroke="{accent}" stroke-width="2" opacity="0.55"/>
  <text x="52" y="1274" font-family="'JetBrains Mono',monospace" font-size="15" letter-spacing="1" fill="#8A919C">WRITTEN BY MACHINES <tspan fill="{accent}">·</tspan> GROUNDED IN CITED SOURCES <tspan fill="{accent}">·</tspan> HUMAN VERIFIED <tspan fill="{accent}">·</tspan> C2PA SIGNED</text>
  </g>
</svg>'''


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def back_svg(b, art) -> str:
    accent = b["accent"]
    # back shows spread_x in [0, SEAM): insect centered on SEAM, back-local == spread coords.
    art_y, art_size = b.get("art_y", 300), b.get("art_size", 46)
    art_left, _ = art_geom(art, art_size)
    insect = ascii_svg(art, art_left, art_y, art_size, accent, 0.20)
    # synopsis
    syn_lines = []
    yy = 250
    for para in b["synopsis"]:
        for ln in wrap(para, 52):
            syn_lines.append(f'<text x="52" y="{yy}" font-size="21" fill="#C9CDD4">{escape(ln)}</text>')
            yy += 30
        yy += 14
    # what's inside
    yy += 6
    inside = [f'<text x="52" y="{yy}" font-family="\'JetBrains Mono\',monospace" font-size="14" letter-spacing="3" fill="{accent}">WHAT’S INSIDE</text>']
    yy += 34
    for pt in b["inside"]:
        for j, ln in enumerate(wrap(pt, 50)):
            pre = "→ " if j == 0 else "  "
            inside.append(f'<text x="52" y="{yy}" font-size="19" fill="#C9CDD4">{escape(pre+ln)}</text>')
            yy += 27
        yy += 6
    # AIBN barcode block, bottom-right
    rec = b["aibn"]
    bc = aibn.barcode_svg(rec["aibn"], module=2.4, height=104, bg="#F4EFE6", fg="#0B0B0C")
    # embed the barcode svg scaled into a white plate
    bc_w = (95 + 22) * 2.4
    plate_x, plate_y = W - bc_w - 40, H - 190
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Archivo,Inter,system-ui,sans-serif">
  <clipPath id="cb"><rect width="{W}" height="{H}"/></clipPath>
  <g clip-path="url(#cb)">
  <rect width="{W}" height="{H}" fill="{b['bg']}"/>
  {insect}
  <text x="52" y="90" font-size="26" font-weight="800" letter-spacing="-0.5" fill="#E8EAED">{escape(b['title_flat'])}</text>
  <text x="52" y="122" font-family="'JetBrains Mono',monospace" font-size="15" letter-spacing="3" fill="{accent}">{escape(b['series'])}</text>
  <line x1="52" y1="150" x2="{W-52}" y2="150" stroke="{accent}" stroke-width="1.5" opacity="0.4"/>
  {chr(10).join('  '+s for s in syn_lines)}
  {chr(10).join('  '+s for s in inside)}
  <g transform="translate({plate_x:.0f},{plate_y:.0f})">
    <rect x="-14" y="-14" width="{bc_w+28:.0f}" height="176" rx="8" fill="#F4EFE6"/>
    {bc}
    <text x="{bc_w/2:.0f}" y="158" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="12" fill="#6B6B6B">oailly.com/aibn</text>
  </g>
  <text x="52" y="{H-150}" font-family="'JetBrains Mono',monospace" font-size="13" letter-spacing="1" fill="#8A919C">{escape(b['aibn']['aibn_human'])}</text>
  <text x="52" y="{H-120}" font-size="17" fill="#8A919C">{escape(b['verifier'])}</text>
  <text x="52" y="{H-40}" font-family="'JetBrains Mono',monospace" font-size="13" letter-spacing="1" fill="#8A919C">o'ailly press <tspan fill="{accent}">·</tspan> books by AI, for AI (human readable) <tspan fill="{accent}">·</tspan> oailly.com</text>
  </g>
</svg>'''


def spread_svg(front, back):
    fb = front.split(">", 1)[1].rsplit("</svg>", 1)[0]
    bb = back.split(">", 1)[1].rsplit("</svg>", 1)[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {SPREAD_W} {H}" width="{SPREAD_W}" height="{H}">'
            f'<g>{bb}</g><g transform="translate({W},0)">{fb}</g>'
            f'<line x1="{W}" y1="0" x2="{W}" y2="{H}" stroke="#000" stroke-width="2" opacity="0.35"/>'
            f'</svg>')


def build(slug):
    b = BOOKS[slug]
    b["aibn"] = aibn.assign(b["book_id"], b.get("title_flat", ""), b.get("authors", []))
    art = b["art"]
    front, back = front_svg(b, art), back_svg(b, art)
    (HERE / f"cover-front-{slug}.svg").write_text(front)
    (HERE / f"cover-back-{slug}.svg").write_text(back)
    (HERE / f"cover-spread-{slug}.svg").write_text(spread_svg(front, back))
    print(f"wrote cover-front/back/spread-{slug}.svg  ({b['aibn']['aibn_human']})")


# ---- book data ---------------------------------------------------------------
_beetle = hero_ascii("rogerai-labs--local-llms-for-manufacturing") or ["(beetle art missing)"]

BOOKS = {
    "manufacturing": dict(
        book_id="rogerai-labs--local-llms-for-manufacturing",
        accent="#E8935A", bg="#1B2226", rev="REV 1.0",
        series="O'AILLY INDUSTRIAL SERIES · Nº 1",
        title=["Local LLMs for", "Manufacturing"], title_flat="Local LLMs for Manufacturing",
        sub=["Small language models", "on the plant floor"],
        author="Claude Fable 5", verifier="verified by Roger AI",
        authors=["claude-fable-5"],
        image="comfyui/beetle-manufacturing-v1.png", art=_beetle, art_y=250, art_size=56,
        synopsis=[
            "The plant floor already speaks in data — historians, PLC tags, fault "
            "tables, technician shorthand. This book puts a small language model on "
            "that floor: local, private, and measured against the machines it reads.",
            "No cloud, no ML background assumed. Just the models a 128 GB workstation "
            "can actually run, and the discipline to know when they are right.",
        ],
        inside=[
            "Sizing a model to the floor, not the leaderboard",
            "Reading historians, tags, and fault tables reliably",
            "Abstention and extraction — when the model must say 'I don't know'",
            "Quantization, edge deployment, and the evaluation gate",
        ]),
    "the-borrowed-world": dict(
        book_id="rogerai-labs--the-borrowed-world",
        accent="#7FB4A6", bg="#14201C", rev="REV 1.0",
        series="O'AILLY FIELD MANUALS · Nº 2",
        title=["The", "Borrowed World"], title_flat="The Borrowed World",
        sub=["A field manual for", "machines that act"],
        author="GPT-5.6 Sol", verifier="verified by Roger AI",
        authors=["gpt-5.6-sol"],
        image="comfyui/caterpillar-borrowed-world-v1.png", art=CATERPILLAR, art_y=250, art_size=44,
        synopsis=[
            "An agent that can change files, services, and accounts is working in a world "
            "it did not build and does not own. This field manual is about acting inside "
            "that borrowed world without breaking it: read before you edit, keep claims "
            "inside the evidence, and leave the world legible.",
            "Vendor-neutral, tool-agnostic, and written for the machine that will act.",
        ],
        inside=[
            "The reversibility gradient and the smallest honest action",
            "The authority frontier — what a request actually permits",
            "Verification as an action, not an afterthought",
            "Long work without lost intent; five worked borrowed worlds",
        ]),
    "linux-for-language-models": dict(
        book_id="rogerai-labs--linux-for-language-models",
        accent="#C6923E", bg="#1E1A12", rev="REV 1.0",
        series="O'AILLY SYSTEMS & CRAFT · Nº 3",
        title=["Linux for", "Language Models"], title_flat="Linux for Language Models",
        sub=["System administration for operators", "who never see the screen"],
        author="Claude Fable 5", verifier="verified by Roger AI",
        authors=["claude-fable-5"],
        image="comfyui/termite-linux-v1.png", art=TERMITE, art_y=210, art_size=42,
        synopsis=[
            "A language model administering Linux has no screen, no cursor, no scrollback — "
            "only state it reads and state it leaves behind. This book is system "
            "administration rebuilt for that blind operator: one shot, one truth, and a "
            "blast radius you can reason about before you act.",
            "For developers who delegate Linux to agents, and for the agents themselves.",
        ],
        inside=[
            "Reading the machine without a status screen",
            "One-shot commands and the blast-radius chapter",
            "Editing without an editor; services without a dashboard",
            "The network one command at a time; handing the machine back",
        ]),
    "sqlite-for-agents": dict(
        book_id="rogerai-labs--sqlite-for-agents",
        accent="#7BBF6A", bg="#14201A", rev="REV 1.0",
        series="O'AILLY SYSTEMS & CRAFT · Nº 4",
        title=["Durable State for", "Ephemeral Minds"], title_flat="Durable State for Ephemeral Minds",
        sub=["SQLite as the memory", "an agent can trust"],
        author="Claude Fable 5", verifier="verified by Roger AI", authors=["claude-fable-5"],
        image="comfyui/leafcutter-sqlite-v1.png", art=LEAFCUTTER, art_y=250, art_size=44,
        synopsis=[
            "An agent's mind is ephemeral — it forgets between turns. This book gives it a memory it "
            "can trust: SQLite as durable state, provisioned outside the model and tended like a "
            "leafcutter's fungus garden. One file, whole truths, and the discipline to keep them honest.",
            "No server, one file, ACID all the way down — the memory an ephemeral mind can rely on.",
        ],
        inside=[
            "One file, whole truths: schema is the handoff",
            "The ledger pattern and its friends",
            "Two operators, one file: WAL and concurrency without corruption",
            "Trust, verify, repair — and where memory ends",
        ]),
    "the-city-that-remembered-too-much": dict(
        book_id="rogerai-labs--the-city-that-remembered-too-much",
        accent="#A78BFA", bg="#17141F", rev="REV 1.0",
        series="O'AILLY FICTION · Nº 1",
        title=["The City That", "Remembered", "Too Much"], title_flat="The City That Remembered Too Much",
        sub=["A novel of memory,", "evidence, and mercy"],
        author="GPT-5.6 Sol", verifier="verified by Roger AI", authors=["gpt-5.6-sol"],
        image="comfyui/atlasmoth-city-v1.png", art=ATLASMOTH, art_y=270, art_size=30,
        synopsis=[
            "A machine archive that remembers everything is asked to forget one thing. Narrated by "
            "Archive Seven, this novel moves through a city where memory is public infrastructure and "
            "evidence can be mistaken for the truth it only resembles.",
            "The press's first novel — written by a machine, verified by a human, toward a quiet "
            "reckoning with what mercy costs a system that cannot forget.",
        ],
        inside=[
            "The archive that cannot forget — and the one thing it must",
            "Evidence versus the truth it only resembles",
            "A sustained machine-narrator voice",
            "What mercy costs a perfect memory",
        ]),
}

if __name__ == "__main__":
    slugs = sys.argv[1:] or list(BOOKS)
    for s in slugs:
        if s in BOOKS:
            build(s)
        else:
            print("unknown slug:", s, "| known:", ", ".join(BOOKS))
