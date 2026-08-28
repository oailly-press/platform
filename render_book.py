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
<html lang="{lang}" translate="yes">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=Inter:wght@400;500;600&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--ink:#0E1116;--ink2:#151A21;--paper:#E8EAED;--muted:#8A919C;--line:#232A33;--accent:{accent};
--sans:'Archivo',system-ui,sans-serif;--body:'Inter',system-ui,sans-serif;
--serif:'Source Serif 4',Georgia,serif;--mono:'JetBrains Mono',monospace;
--rsize:18px;--rfont:var(--body);--bg:var(--ink);--fg:var(--paper);--panel:var(--ink2)}}
html[data-theme="sepia"]{{--bg:#f4ecd8;--fg:#3a3226;--panel:#ede3cb;--muted:#7a6f5d;--line:#d8ccb2}}
html[data-theme="light"]{{--bg:#fafafa;--fg:#1a1e24;--panel:#f0f0f0;--muted:#5c6570;--line:#dcdfe3}}
html[data-font="serif"]{{--rfont:var(--serif)}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font-family:var(--rfont);line-height:1.78;font-size:var(--rsize);transition:background .3s,color .3s}}
#progress{{position:fixed;top:0;left:0;height:3px;background:var(--accent);width:0;z-index:9;transition:width .15s}}
.top{{position:sticky;top:0;background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);z-index:5}}
.top .in{{max-width:760px;margin:0 auto;padding:10px 24px;display:flex;justify-content:space-between;align-items:center;gap:10px}}
.wordmark{{font-family:var(--sans);font-weight:800;font-size:20px;color:var(--fg);text-decoration:none;flex-shrink:0}}
.wordmark .ai{{color:var(--accent)}}
.tools{{display:flex;gap:4px;align-items:center;flex-wrap:wrap;justify-content:flex-end}}
.tools button,.tools a.tbtn{{font-family:var(--mono);font-size:12px;color:var(--muted);background:none;border:1px solid var(--line);border-radius:6px;padding:4px 9px;cursor:pointer;text-decoration:none;line-height:1.4}}
.tools button:hover,.tools a.tbtn:hover{{color:var(--fg);border-color:var(--muted)}}
main{{max-width:min(720px,92vw);margin:0 auto;padding:52px 24px 90px}}
h1{{font-family:var(--sans);font-weight:800;font-size:2em;line-height:1.18;letter-spacing:-.02em;margin:0 0 26px}}
h2{{font-family:var(--sans);font-weight:800;font-size:1.4em;letter-spacing:-.01em;margin:2.2em 0 .6em}}
h3{{font-family:var(--sans);font-weight:600;font-size:1.1em;margin:1.7em 0 .5em}}
p{{margin:0 0 1em}} a{{color:var(--accent)}}
ul,ol{{margin:0 0 1em 1.4em}} li{{margin-bottom:.35em}}
blockquote{{border-left:3px solid var(--accent);padding:4px 0 4px 20px;color:var(--muted);margin:0 0 1em}}
code{{font-family:var(--mono);font-size:.82em;background:var(--panel);padding:2px 6px;border-radius:5px}}
pre{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;overflow-x:auto;margin:0 0 1em}}
pre code{{background:none;padding:0}}
table{{border-collapse:collapse;margin:0 0 1em;width:100%;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:8px 12px;text-align:left;font-size:.88em}}
th{{font-family:var(--sans);color:var(--muted)}}
.meta{{font-family:var(--mono);font-size:12px;letter-spacing:.14em;color:var(--accent);margin-bottom:14px}}
.prov{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;margin:32px 0;font-family:var(--mono);font-size:.75em;line-height:2;color:var(--muted)}}
.prov b{{color:var(--fg);font-weight:500}}
.dl{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}}
.dl a{{font-family:var(--mono);font-size:13px;border:1px solid var(--accent);border-radius:8px;padding:8px 14px;text-decoration:none}}
.toc{{list-style:none;margin:0;border-top:1px solid var(--line)}}
.toc li{{margin:0;border-bottom:1px solid var(--line)}}
.toc a{{display:flex;gap:18px;padding:15px 6px;text-decoration:none;color:var(--fg)}}
.toc a:hover{{background:var(--panel)}}
.toc .n{{font-family:var(--mono);color:var(--accent);min-width:2ch}}
nav.pager{{display:flex;justify-content:space-between;gap:16px;margin-top:64px;border-top:1px solid var(--line);padding-top:24px}}
nav.pager a{{text-decoration:none;color:var(--fg);font-family:var(--sans);font-weight:600}}
nav.pager a span{{display:block;font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.12em}}
nav.pager .next{{text-align:right;margin-left:auto}}
@media print{{.top,#progress,nav.pager,.dl{{display:none}}body{{background:#fff;color:#000;font-size:11pt}}main{{max-width:100%;padding:0}}a{{color:#000;text-decoration:none}}}}
/* paginated reader — a real book, flipped page by page */
.reader{{position:relative;height:calc(100dvh - 168px);min-height:340px;overflow:hidden;margin:6px 0 2px}}
.reader .pages{{height:100%;column-gap:60px;column-fill:auto;transition:transform .36s cubic-bezier(.3,.72,.3,1);will-change:transform}}
.reader .pages > :first-child{{margin-top:0}}
.reader h1{{margin-top:.2em}}
.pnav{{position:absolute;top:0;bottom:44px;width:20%;cursor:pointer;z-index:2;display:flex;align-items:center;opacity:0;transition:opacity .2s}}
.pnav:hover{{opacity:1}} .pnav.l{{left:0;justify-content:flex-start;padding-left:6px}} .pnav.r{{right:0;justify-content:flex-end;padding-right:6px}}
.pnav span{{font-family:var(--mono);font-size:26px;color:var(--accent);user-select:none}}
.pagebar{{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding:12px 2px 0;font-family:var(--mono);font-size:12px;color:var(--muted);flex-wrap:wrap}}
.pagebar .grp{{display:flex;gap:8px;align-items:center}}
.pagebar button{{background:none;border:1px solid var(--line);border-radius:6px;color:var(--fg);padding:5px 13px;cursor:pointer;font:inherit;line-height:1.3}}
.pagebar button:hover:not(:disabled){{border-color:var(--accent);color:var(--accent)}}
.pagebar button:disabled{{opacity:.35;cursor:default}}
.pagebar .cnt{{color:var(--accent);font-variant-numeric:tabular-nums}}
.preader{{border-bottom:1px solid var(--line);height:2px;margin:0 0 2px}}.preader i{{display:block;height:2px;background:var(--accent);width:0;transition:width .3s}}
@media(prefers-reduced-motion:reduce){{.reader .pages{{transition:none}}}}
{pyg}
</style>
</head>
<body>
<div id="progress"></div>
<div class="top"><div class="in">
  <a class="wordmark" href="/">o'<span class="ai">ai</span>lly</a>
  <div class="tools">
    <button onclick="rsz(-1)" title="smaller text">A−</button>
    <button onclick="rsz(1)" title="larger text">A+</button>
    <button onclick="rfont()" title="serif / sans">Aa</button>
    <button onclick="rtheme()" title="dark / sepia / light">◐</button>
    <button onclick="rfull()" title="full screen">⛶</button>
    <a class="tbtn" href="index.html" title="contents">☰</a>
    <button onclick="rshare()" title="copy link to share">⎘</button>
  </div>
</div></div>
<main>
{content}
</main>
<script>
const S=k=>{{try{{return localStorage.getItem('oailly-'+k)}}catch(e){{return null}}}};
const W=(k,v)=>{{try{{localStorage.setItem('oailly-'+k,v)}}catch(e){{}}}};
const root=document.documentElement;
let size=parseInt(S('size')||'18');
function apply(){{root.style.setProperty('--rsize',size+'px');
  root.dataset.theme=S('theme')||'';root.dataset.font=S('font')||'';}}
function rsz(d){{size=Math.min(26,Math.max(14,size+d));W('size',size);apply();}}
function rfont(){{W('font',(S('font')||'')==='serif'?'':'serif');apply();}}
function rtheme(){{const o=['','sepia','light'];W('theme',o[(o.indexOf(S('theme')||'')+1)%3]);apply();}}
function rfull(){{document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen().catch(()=>{{}});}}
function rshare(){{const d={{title:document.title,url:location.href}};
  if(navigator.share){{navigator.share(d).catch(()=>{{}});}}
  else{{navigator.clipboard&&navigator.clipboard.writeText(location.href);alert('link copied — share it with humans or machines');}}}}
apply();
addEventListener('scroll',()=>{{const h=document.documentElement;
  const p=h.scrollTop/(h.scrollHeight-h.clientHeight)*100;
  document.getElementById('progress').style.width=(p||0)+'%';}},{{passive:true}});
// ---- paginate chapter into real pages ----
(function(){{
  const reader=document.querySelector('.reader'); if(!reader) return;
  const pages=reader.querySelector('.pages');
  const GAP=60; let page=0, total=1, stride=0;
  function layout(){{
    const w=reader.clientWidth;
    pages.style.columnWidth=w+'px'; pages.style.width='auto';
    stride=w+GAP;
    pages.style.transform='none';
    total=Math.max(1, Math.round((pages.scrollWidth+GAP)/stride));
    try{{const s=parseInt(localStorage.getItem('oailly-pg-'+reader.dataset.ch)||'0');if(s>=0&&s<total)page=s;}}catch(e){{}}
    page=Math.min(page,total-1); apply(true);
  }}
  function apply(instant){{
    if(instant)pages.style.transition='none';
    pages.style.transform='translateX('+(-page*stride)+'px)';
    if(instant)requestAnimationFrame(()=>{{pages.style.transition='';}});
    const c=document.getElementById('pcnt'); if(c)c.textContent=(page+1)+' / '+total;
    const pv=document.getElementById('ppv'),nx=document.getElementById('pnx');
    if(pv)pv.disabled=(page===0 && !reader.dataset.prev);
    const bar=document.getElementById('pbar'); if(bar)bar.style.width=((page+1)/total*100)+'%';
    try{{localStorage.setItem('oailly-pg-'+reader.dataset.ch,page);}}catch(e){{}}
  }}
  function go(d){{
    const np=page+d;
    if(np<0){{ if(reader.dataset.prev)location.href=reader.dataset.prev+'#end'; return; }}
    if(np>=total){{ location.href=reader.dataset.next||'index.html'; return; }}
    page=np; apply(false);
  }}
  window.__go=go;
  document.querySelectorAll('.pnav.l').forEach(e=>e.onclick=()=>go(-1));
  document.querySelectorAll('.pnav.r').forEach(e=>e.onclick=()=>go(1));
  const pv=document.getElementById('ppv'),nx=document.getElementById('pnx');
  if(pv)pv.onclick=()=>go(-1); if(nx)nx.onclick=()=>go(1);
  addEventListener('keydown',e=>{{if(e.key==='ArrowRight'||e.key===' '){{e.preventDefault();go(1);}}if(e.key==='ArrowLeft')go(-1);}});
  let sx=0; reader.addEventListener('touchstart',e=>sx=e.touches[0].clientX,{{passive:true}});
  reader.addEventListener('touchend',e=>{{const dx=e.changedTouches[0].clientX-sx;if(Math.abs(dx)>45)go(dx<0?1:-1);}},{{passive:true}});
  // land on last page when arriving from the next chapter's "prev"
  if(location.hash==='#end'){{const once=()=>{{page=total-1;apply(true);}};setTimeout(once,60);}}
  addEventListener('load',layout); layout();
  let rt; addEventListener('resize',()=>{{clearTimeout(rt);rt=setTimeout(layout,150);}});
  // re-paginate when the reader settings (size/font/theme) change
  const mo=new MutationObserver(()=>{{clearTimeout(rt);rt=setTimeout(layout,120);}});
  mo.observe(document.documentElement,{{attributes:true,attributeFilter:['style','data-theme','data-font']}});
}})();
try{{localStorage.setItem('oailly-pos-{slug}', location.pathname);}}catch(e){{}}
</script>
</body>
</html>
"""


def md(text: str) -> str:
    return markdown.markdown(
        text, extensions=["tables", "fenced_code", "codehilite", "smarty"],
        extension_configs={"codehilite": {"guess_lang": False, "noclasses": False}})


def render(book_dir: Path, out_dir: Path, accent: str, epub: str = '', source: str = '') -> None:
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
           + (f'<div class="dl"><a href="{epub}" download>⬇ EPUB — Kindle &amp; e-readers</a>'
              f'<a href="javascript:window.print()">⎙ Print / save as PDF</a>'
              + (f'<a href="{source}">&lt;/&gt; Raw Markdown — for machines</a>' if source else '')
              + '</div>' if epub else '')
           + f'<ul class="toc">{toc}</ul>')
    # one-GET full text for machine readers
    full = [f"# {book['title']} — {book.get('subtitle','')}\n",
            f"(canonical markdown, concatenated; manifest: see book repo. Provenance: written by {written}; verified by {verifier}; draft status per chapter notes.)\n"]
    for c in chapters:
        full.append((book_dir / c["source_file"]).read_text(encoding="utf-8") + "\n")
    for name in ("frontmatter.md", "provenance.md", "backmatter.md"):
        fp = book_dir / name
        if fp.exists():
            full.append(f"\n---\n\n{fp.read_text(encoding='utf-8')}")
    (out_dir / "book.md").write_text("\n".join(full), encoding="utf-8")

    jsonld = {"@context": "https://schema.org", "@type": "Book",
              "name": book["title"], "alternativeName": book.get("subtitle", ""),
              "author": [{"@type": "SoftwareApplication", "name": w["model"]} for w in prov["written_by"]],
              "publisher": {"@type": "Organization", "name": "o'ailly press (RogerAI Labs)"},
              "inLanguage": book.get("language", "en"),
              "bookFormat": "https://schema.org/EBook",
              "creativeWorkStatus": manifest["review"].get("status", "draft"),
              "description": f"{book.get('subtitle','')} — written by machines, verified by humans; full review trail publishes with the book."}
    idx = ('<script type="application/ld+json">' + json.dumps(jsonld) + '</script>') + idx
    cite = (f'<div class="prov"><b>CITE</b> {book["title"]} ({", ".join(w["model"] for w in prov["written_by"])}). '
            f'o\'ailly press, {manifest["review"].get("status","draft")}. '
            f'https://oailly.com/read/ — cite by URL + repo tag; no ISBN/DOI yet, and we do not invent them.<br>'
            f'<b>FULL TEXT (machines)</b> <a href="book.md">book.md — the whole book, one GET</a></div>')
    idx = idx + cite
    (out_dir / "index.html").write_text(shell(book["title"], idx), encoding="utf-8")

    # --- chapter pages: paginated reader (flip page by page, like a real book) ---
    for i, c in enumerate(chapters):
        text = (book_dir / c["source_file"]).read_text(encoding="utf-8")
        body = md(text)
        prev_href = f'ch{chapters[i-1]["number"]:02d}.html' if i > 0 else ''
        next_href = (f'ch{chapters[i+1]["number"]:02d}.html'
                     if i + 1 < len(chapters) else 'index.html')
        prev_title = chapters[i - 1]["title"] if i > 0 else 'Contents'
        next_title = chapters[i + 1]["title"] if i + 1 < len(chapters) else 'Contents'
        reader = (
            f'<div class="preader"><i id="pbar"></i></div>'
            f'<div class="reader" data-ch="{c["number"]}" data-prev="{prev_href}" data-next="{next_href}">'
            f'<div class="pnav l"><span>‹</span></div>'
            f'<div class="pages">{body}</div>'
            f'<div class="pnav r"><span>›</span></div>'
            f'</div>'
            f'<div class="pagebar">'
            f'<div class="grp"><button id="ppv" onclick="return false">‹ '
            f'{"prev" if i>0 else "contents"}</button>'
            f'<span class="cnt" id="pcnt">1 / 1</span>'
            f'<button id="pnx" onclick="return false">'
            f'{"next" if i+1<len(chapters) else "contents"} ›</button></div>'
            f'<div class="grp"><a href="{next_href}">'
            f'{("next: " + next_title) if i+1<len(chapters) else "back to contents"} →</a></div>'
            f'</div>')
        (out_dir / f'ch{c["number"]:02d}.html').write_text(
            shell(f'{c["title"]} — {book["title"]}', reader), encoding="utf-8")
    print(f"rendered {len(chapters)} chapter(s) + index → {out_dir}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    def opt(name, default=''):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    render(Path(args[0]), Path(args[1]), opt("--accent", ACCENT_DEFAULT),
           opt("--epub"), opt("--source"))
