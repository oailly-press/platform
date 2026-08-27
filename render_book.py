#!/usr/bin/env python3
"""Render a book source tree into the static web reader.

    .buildenv/bin/python platform/render_book.py <book_dir> <out_dir> [--accent HEX]

Output: <out_dir>/index.html (title page: cover, TOC, provenance) plus one page per
chapter with prev/next navigation. Pure static HTML — this IS how readers read books on
oailly.com: no backend, no JS framework; the only client-side nicety is a localStorage
bookmark. Code highlighted at build time (pygments), math left as $…$ (pandoc handles
EPUB/PDF at publication; the web reader keeps v1 simple).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ACCENT_DEFAULT = "#4FD6C3"

SHELL = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--ink:#0E1116;--ink2:#151A21;--paper:#E8EAED;--muted:#8A919C;--line:#232A33;--accent:{accent};
--sans:'Archivo',system-ui,sans-serif;--body:'Inter',system-ui,sans-serif;--mono:'JetBrains Mono',monospace}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--ink);color:var(--paper);font-family:var(--body);line-height:1.75;font-size:18px}}
.top{{position:sticky;top:0;background:color-mix(in srgb,var(--ink) 88%,transparent);backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);z-index:5}}
.top .in{{max-width:760px;margin:0 auto;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}}
.wordmark{{font-family:var(--sans);font-weight:800;font-size:22px;color:var(--paper);text-decoration:none}}
.wordmark .ai{{color:var(--accent)}}
.top .bk{{font-family:var(--mono);font-size:12px;letter-spacing:.12em;color:var(--muted);text-decoration:none;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:55%}}
main{{max-width:760px;margin:0 auto;padding:56px 24px 80px}}
h1{{font-family:var(--sans);font-weight:800;font-size:38px;line-height:1.15;letter-spacing:-.02em;margin:0 0 28px}}
h2{{font-family:var(--sans);font-weight:800;font-size:26px;letter-spacing:-.01em;margin:44px 0 14px}}
h3{{font-family:var(--sans);font-weight:600;font-size:20px;margin:32px 0 10px}}
p{{margin:0 0 18px}} em{{color:var(--paper)}} a{{color:var(--accent)}}
ul,ol{{margin:0 0 18px 1.4em}} li{{margin-bottom:6px}}
blockquote{{border-left:3px solid var(--accent);padding:4px 0 4px 20px;color:var(--muted);margin:0 0 18px}}
code{{font-family:var(--mono);font-size:.85em;background:var(--ink2);padding:2px 6px;border-radius:5px}}
pre{{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:18px;overflow-x:auto;margin:0 0 18px}}
pre code{{background:none;padding:0}}
table{{border-collapse:collapse;margin:0 0 18px;width:100%;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:8px 12px;text-align:left;font-size:16px}}
th{{font-family:var(--sans);color:var(--muted)}}
.meta{{font-family:var(--mono);font-size:13px;letter-spacing:.14em;color:var(--accent);margin-bottom:14px}}
.prov{{background:var(--ink2);border:1px solid var(--line);border-radius:12px;padding:24px;margin:32px 0;
font-family:var(--mono);font-size:14px;line-height:2;color:var(--muted)}}
.prov b{{color:var(--paper);font-weight:500}}
.toc{{list-style:none;margin:0;border-top:1px solid var(--line)}}
.toc li{{margin:0;border-bottom:1px solid var(--line)}}
.toc a{{display:flex;gap:18px;padding:16px 6px;text-decoration:none;color:var(--paper)}}
.toc a:hover{{background:var(--ink2)}}
.toc .n{{font-family:var(--mono);color:var(--accent);min-width:2ch}}
nav.pager{{display:flex;justify-content:space-between;gap:16px;margin-top:64px;border-top:1px solid var(--line);padding-top:24px}}
nav.pager a{{text-decoration:none;color:var(--paper);font-family:var(--sans);font-weight:600}}
nav.pager a span{{display:block;font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.12em}}
nav.pager .next{{text-align:right;margin-left:auto}}
{pyg}
</style>
</head>
<body>
<div class="top"><div class="in">
  <a class="wordmark" href="{home}">o'<span class="ai">ai</span>lly</a>
  <a class="bk" href="index.html">{book_title_upper}</a>
</div></div>
<main>
{content}
</main>
<script>
try{{localStorage.setItem('oailly-pos-{slug}', location.pathname);}}catch(e){{}}
</script>
</body>
</html>
"""


def md(text: str) -> str:
    return markdown.markdown(
        text, extensions=["tables", "fenced_code", "codehilite", "smarty"],
        extension_configs={"codehilite": {"guess_lang": False, "noclasses": False}})


def render(book_dir: Path, out_dir: Path, accent: str) -> None:
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    book, prov = manifest["book"], manifest["provenance"]
    chapters = manifest["structure"]["chapters"]
    slug = re.sub(r"[^a-z0-9-]", "-", book["title"].lower())
    out_dir.mkdir(parents=True, exist_ok=True)
    pyg = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

    def shell(page_title, content):
        return SHELL.format(lang=book.get("language", "en"), page_title=page_title,
                            accent=accent, home="/", slug=slug,
                            book_title_upper=book["title"].upper(), content=content,
                            pyg=pyg)

    # --- title page: cover meta + provenance + TOC
    written = ", ".join(f"{m['model']}" for m in prov["written_by"])
    verifier = prov["verified_by"].get("name") or "—"
    toc = "\n".join(
        f'<li><a href="ch{c["number"]:02d}.html"><span class="n">{c["number"]:02d}</span>'
        f'{c["title"]}</a></li>' for c in chapters)
    idx = (f'<div class="meta">{book.get("series") or "O\'AILLY"} · '
           f'{book["tier"].upper()}</div>'
           f'<h1>{book["title"]}</h1><p>{book.get("subtitle", "")}</p>'
           f'<div class="prov"><b>WRITTEN BY</b> {written}<br>'
           f'<b>VERIFIED BY</b> {verifier}<br>'
           f'<b>DISCLOSURE</b> {prov["disclosure_statement"]}<br>'
           f'<b>REVIEW TRAIL</b> {manifest["review"].get("trail_uri") or "pending publication"}</div>'
           f'<ul class="toc">{toc}</ul>')
    (out_dir / "index.html").write_text(shell(book["title"], idx), encoding="utf-8")

    # --- chapter pages with prev/next
    for i, c in enumerate(chapters):
        text = (book_dir / c["source_file"]).read_text(encoding="utf-8")
        body = md(text)
        pager = ['<nav class="pager">']
        if i > 0:
            p = chapters[i - 1]
            pager.append(f'<a href="ch{p["number"]:02d}.html"><span>PREV</span>← {p["title"]}</a>')
        if i + 1 < len(chapters):
            n = chapters[i + 1]
            pager.append(f'<a class="next" href="ch{n["number"]:02d}.html"><span>NEXT</span>{n["title"]} →</a>')
        else:
            pager.append('<a class="next" href="index.html"><span>END</span>Contents ↑</a>')
        pager.append("</nav>")
        page = body + "\n" + "".join(pager)
        (out_dir / f'ch{c["number"]:02d}.html').write_text(
            shell(f'{c["title"]} — {book["title"]}', page), encoding="utf-8")
    print(f"rendered {len(chapters)} chapter(s) + index → {out_dir}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    accent = ACCENT_DEFAULT
    if "--accent" in sys.argv:
        accent = sys.argv[sys.argv.index("--accent") + 1]
    render(Path(args[0]), Path(args[1]), accent)
