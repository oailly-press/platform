#!/usr/bin/env python3
"""Render a book source tree into the static web reader.

    .buildenv/bin/python platform/render_book.py <book_dir> <out_dir> [--accent HEX]
        [--epub URL] [--source URL] [--review URL] [--status STATUS]

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
from datetime import date as _date
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import aibn as _aibn
except Exception:
    _aibn = None

ACCENT_DEFAULT = "#4FD6C3"
_covers = Path(__file__).resolve().parents[1] / "gh/site-repo/assets/covers"
SITE_ASSETS = _covers if _covers.is_dir() else None

SHELL = """<!DOCTYPE html>
<html lang="{lang}" translate="yes">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<meta name="description" content="{og_desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="book">
<meta property="og:site_name" content="o'ailly">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:url" content="{og_url}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:alt" content="{og_image_alt}">
<meta property="book:author" content="{book_author}">
<meta property="book:isbn" content="{book_isbn}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_desc}">
<meta name="twitter:image" content="{og_image}">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=Inter:wght@400;500;600&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--ink:#0E1116;--ink2:#151A21;--paper:#E8EAED;--muted:#8A919C;--line:#232A33;--accent:{accent};
--sans:'Archivo',system-ui,sans-serif;--body:'Inter',system-ui,sans-serif;
--serif:'Source Serif 4',Georgia,serif;--mono:'JetBrains Mono',monospace;
--rsize:18px;--rfont:var(--body);--bg:var(--ink);--fg:var(--paper);--panel:var(--ink2)}}
html[data-theme="sepia"]{{--bg:#f4ecd8;--fg:#3a3226;--panel:#ede3cb;--muted:#6b6152;--line:#d8ccb2;--accent:#8A5A16}}
html[data-theme="light"]{{--bg:#fafafa;--fg:#1a1e24;--panel:#f0f0f0;--muted:#5c6570;--line:#dcdfe3;--accent:#8A5A16}}
html[data-font="serif"]{{--rfont:var(--serif)}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font-family:var(--rfont);line-height:1.78;font-size:var(--rsize);transition:background .3s,color .3s}}
#progress{{position:fixed;top:0;left:0;height:3px;background:var(--accent);width:0;z-index:9;transition:width .15s}}
.top{{position:sticky;top:0;background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);z-index:5}}
.top .in{{max-width:760px;margin:0 auto;padding:10px 24px;display:flex;justify-content:space-between;align-items:center;gap:10px}}
.wordmark{{font-family:var(--sans);font-weight:800;font-size:20px;color:var(--fg);text-decoration:none;flex-shrink:0}}
.wordmark .ai{{color:var(--accent)}}
.booktitle{{font-family:var(--sans);font-weight:600;font-size:14px;color:var(--muted);text-decoration:none;flex:1 1 auto;min-width:0;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 12px}}
.booktitle:hover{{color:var(--fg)}}
@media(max-width:640px){{.booktitle{{font-size:12.5px;text-align:left;padding:0 8px}}}}
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
.morefrom{{margin:56px 0 0;border-top:1px solid var(--line);padding-top:26px}}
.morefrom h2{{font-family:var(--sans);font-weight:800;font-size:1.05em;margin:0 0 16px;letter-spacing:-.01em}}
.mf-row{{display:flex;gap:18px;flex-wrap:wrap}}
.mf-card{{display:flex;flex-direction:column;gap:7px;width:98px;text-decoration:none;color:var(--fg)}}
.mf-card img{{width:98px;height:auto;border:1px solid var(--line);border-radius:4px;box-shadow:0 6px 20px rgba(0,0,0,.4);transition:transform .15s}}
.mf-card:hover img{{transform:translateY(-3px)}}
.mf-card span{{font-family:var(--sans);font-size:11px;line-height:1.32;color:var(--muted)}}
.mf-card:hover span{{color:var(--fg)}}
@media print{{.morefrom{{display:none}}}}
nav.pager{{display:flex;justify-content:space-between;gap:16px;margin-top:64px;border-top:1px solid var(--line);padding-top:24px}}
nav.pager a{{text-decoration:none;color:var(--fg);font-family:var(--sans);font-weight:600}}
nav.pager a span{{display:block;font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.12em}}
nav.pager .next{{text-align:right;margin-left:auto}}
@media print{{.top,#progress,nav.pager,.dl{{display:none}}body{{background:#fff;color:#000;font-size:11pt}}main{{max-width:100%;padding:0}}a{{color:#000;text-decoration:none}}}}
/* cover-to-cover: the front cover opens the book, the back cover closes it */
.coverpage{{display:block;position:relative;margin:0 auto 30px;max-width:560px;text-align:center;text-decoration:none}}
.coverpage img{{width:100%;height:auto;border-radius:6px;box-shadow:0 18px 60px rgba(0,0,0,.55);border:1px solid var(--line)}}
.coverpage .opencue{{display:inline-block;margin-top:16px;font-family:var(--mono);font-size:13px;letter-spacing:2px;color:var(--accent);opacity:.85}}
.coverpage:hover .opencue{{opacity:1}}
.backcover{{max-width:560px;margin:0 auto;text-align:center}}
.backcover img{{width:100%;height:auto;border-radius:6px;box-shadow:0 18px 60px rgba(0,0,0,.55);border:1px solid var(--line)}}
.bc-aibn{{margin:16px 0 4px;font-family:var(--mono);font-size:12px;letter-spacing:1px;color:var(--muted)}}
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
  <a class="booktitle" href="index.html" title="{book_title} — contents">{book_title}</a>
  <div class="tools">
    <button onclick="rsz(-1)" title="smaller text" aria-label="decrease font size">A−</button>
    <button onclick="rsz(1)" title="larger text" aria-label="increase font size">A+</button>
    <button onclick="rfont()" title="serif / sans" aria-label="font size">Aa</button>
    <button onclick="rtheme()" title="dark / sepia / light" aria-label="cycle theme">◐</button>
    <button onclick="rfull()" title="full screen" aria-label="toggle fullscreen">⛶</button>
    <a class="tbtn" href="index.html" title="contents" aria-label="contents">☰</a>
    <button onclick="rshare()" title="copy link to share" aria-label="share">⎘</button>
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


def render(book_dir: Path, out_dir: Path, accent: str, epub: str = '', source: str = '',
           review: str = '', publication_status: str = '') -> None:
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    book, prov = manifest["book"], manifest["provenance"]
    chapters = manifest["structure"]["chapters"]
    slug = re.sub(r"[^a-z0-9-]", "-", book["title"].lower())
    out_dir.mkdir(parents=True, exist_ok=True)
    pyg = HtmlFormatter(style="monokai").get_style_defs(".codehilite")

    def _attr(s):
        return str(s).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    def shell(page_title, content, canonical=None):
        bid = out_dir.name
        og_img = f"https://oailly.com/assets/og/{bid}.png"
        og_url = f"https://oailly.com/read/{bid}/"
        og_desc = _attr((book.get("subtitle") or book["title"])
                        + " — written by machines, verified by humans, signed all the way down.")
        og_image_alt = _attr(f'{book["title"]} — cover, o\'ailly press')
        book_author = _attr(", ".join(w["model"] for w in prov["written_by"]))
        book_isbn = _attr(aibn_rec["aibn"]) if aibn_rec else ""
        return SHELL.format(lang=book.get("language", "en"), page_title=page_title,
                            accent=accent, home="/", slug=slug,
                            book_title_upper=book["title"].upper(), book_title=book["title"], content=content,
                            pyg=pyg, og_title=_attr(book["title"]), og_desc=og_desc,
                            og_url=og_url, og_image=og_img,
                            canonical=(canonical or og_url), og_image_alt=og_image_alt,
                            book_author=book_author, book_isbn=book_isbn)

    # --- book identity: AIBN + cover art (cover-to-cover reader) ---
    book_id = out_dir.name                    # read/<book_id>/
    aibn_rec = None
    if _aibn is not None:
        try:
            aibn_rec = next((r for r in _aibn.load_registry()["books"]
                             if r["book_id"] == book_id), None)
        except Exception:
            aibn_rec = None
    front_cover = f"/assets/covers/{book_id}-front.png"
    back_cover = f"/assets/covers/{book_id}-back.png"
    has_covers = (SITE_ASSETS / f"{book_id}-front.png").is_file() if SITE_ASSETS else False

    # --- title page: front cover + cover meta + provenance + TOC
    written = ", ".join(f"{m['model']}" for m in prov["written_by"])
    verifier = prov["verified_by"].get("name") or "—"
    toc = "\n".join(
        f'<li><a href="ch{c["number"]:02d}.html"><span class="n">{c["number"]:02d}</span>'
        f'{c["title"]}</a></li>' for c in chapters)
    cover_open = (f'<a class="coverpage" href="ch01.html" title="open the book">'
                  f'<img src="{front_cover}" alt="{book["title"]} — front cover" '
                  f'loading="eager"><span class="opencue">open the book →</span></a>'
                  if has_covers else '')
    review_url = review or manifest["review"].get("trail_uri") or ''
    release_status = publication_status or manifest["review"].get("status", "draft")
    review_display = (f'<a href="{review_url}">{review_url}</a>'
                      if review_url else "pending publication")
    # when published, reconcile the author's draft-time DISCLOSURE (which predates release) with the
    # signed reality — otherwise a live book still reads "verification … remain pending".
    attestation = ((f'<b>RELEASE ATTESTATION</b> Published and signed by {verifier}'
                    + (f' · {aibn_rec["aibn_human"]}' if aibn_rec else '')
                    + '. The draft note above predates release; human verification is complete '
                      'and the full review trail is public (below).<br>')
                   if release_status == "published" else '')
    idx = (cover_open
           + f'<div class="meta">{book.get("series") or "O\'AILLY"} · '
           f'{book["tier"].upper()}'
           + (f' · <a href="/aibn/">{aibn_rec["aibn_human"]}</a>' if aibn_rec else '')
           + '</div>'
           f'<h1>{book["title"]}</h1><p>{book.get("subtitle", "")}</p>'
           f'<div class="prov"><b>WRITTEN BY</b> {written}<br>'
           f'<b>VERIFIED BY</b> {verifier}<br>'
           f'<b>DISCLOSURE</b> {prov["disclosure_statement"]}<br>'
           f'{attestation}'
           f'<b>PUBLICATION</b> {release_status.upper()}<br>'
           f'<b>REVIEW TRAIL</b> {review_display}</div>'
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

    og_img = f"https://oailly.com/assets/og/{book_id}.png"
    book_url = f"https://oailly.com/read/{book_id}/"
    date_published = ((aibn_rec.get("assigned") if aibn_rec else None)
                      or (prov.get("verified_by", {}).get("role", ""))
                      or "")
    m = re.search(r"\d{4}-\d{2}-\d{2}", date_published)
    date_published = m.group(0) if m else _date.today().isoformat()
    word_count = manifest["structure"].get("word_count_body")
    keywords = [c["title"] for c in chapters]
    jsonld = {"@context": "https://schema.org", "@type": "Book",
              "name": book["title"], "alternativeName": book.get("subtitle", ""),
              "author": [{"@type": "SoftwareApplication", "name": w["model"]} for w in prov["written_by"]],
              "publisher": {"@type": "Organization", "name": "o'ailly press (RogerAI Labs)"},
              "inLanguage": book.get("language", "en"),
              "bookFormat": "https://schema.org/EBook",
              "creativeWorkStatus": release_status,
              "url": book_url,
              "image": og_img,
              "datePublished": date_published,
              "isAccessibleForFree": True,
              "keywords": ", ".join(keywords),
              "about": [{"@type": "Thing", "name": k} for k in keywords],
              "workExample": [
                  {"@type": "Book", "bookFormat": "https://schema.org/EBook",
                   "encodingFormat": "application/epub+zip", "name": f'{book["title"]} (EPUB)',
                   "url": book_url + "book.epub"},
                  {"@type": "Book", "bookFormat": "https://schema.org/EBook",
                   "encodingFormat": "text/markdown", "name": f'{book["title"]} (Markdown)',
                   "url": book_url + "book.md"}],
              "description": f"{book.get('subtitle','')} — written by machines, verified by humans; full review trail publishes with the book."}
    if word_count:
        jsonld["wordCount"] = word_count
    if aibn_rec:
        jsonld["identifier"] = [
            {"@type": "PropertyValue", "propertyID": "AIBN", "value": aibn_rec["aibn_human"]},
            {"@type": "PropertyValue", "propertyID": "isbn", "value": aibn_rec["aibn"]}]
        jsonld["isbn"] = aibn_rec["aibn"]
    idx = ('<script type="application/ld+json">' + json.dumps(jsonld) + '</script>') + idx
    aibn_cite = (f'{aibn_rec["aibn_human"]} · ' if aibn_rec else '')
    repo = f'https://github.com/oailly-press/{book_id.split("--", 1)[1]}'
    cite = (f'<div class="prov"><b>CITE</b> {book["title"]} ({", ".join(w["model"] for w in prov["written_by"])}). '
            f'o\'ailly press, {release_status}. '
            f'{aibn_cite}https://oailly.com/read/{book_id}/ — cite by AIBN or URL + repo tag.<br>'
            f'<b>FULL TEXT (machines)</b> <a href="book.md">book.md — the whole book, one GET</a><br>'
            f'<b>SOURCE</b> <a href="{repo}">GitHub repo — manifest, chapters &amp; the full review trail</a> '
            f'· <a href="/book/?id={book_id}">book detail page</a></div>')
    # "more from o'ailly" — discovery panel: other published books, same shelf first, then newest
    more = ''
    if SITE_ASSETS is not None:
        cat_path = SITE_ASSETS.parents[1] / "catalog.json"
        try:
            others = [b for b in json.loads(cat_path.read_text()).get("books", [])
                      if b.get("status") == "published" and b.get("id") != book_id and b.get("cover")]
        except Exception:
            others = []
        if others:
            shelf = book.get("shelf")
            key = lambda b: (b.get("added") or "")
            same = sorted((b for b in others if b.get("shelf") == shelf), key=key, reverse=True)
            rest = sorted((b for b in others if b.get("shelf") != shelf), key=key, reverse=True)
            picks = (same + rest)[:4]
            cards = "".join(
                f'<a class="mf-card" href="/read/{b["id"]}/">'
                f'<img src="/assets/covers/thumbs/{b["id"]}-front.webp" '
                f'onerror="this.onerror=null;this.src=\'/assets/covers/{b["id"]}-front.png\'" '
                f'alt="{_attr(b.get("title",""))} cover" loading="lazy">'
                f'<span>{_attr(b.get("title",""))}</span></a>'
                for b in picks)
            more = ('<div class="morefrom"><h2>More from o\'ailly</h2>'
                    f'<div class="mf-row">{cards}</div></div>')
    idx = idx + cite + more
    (out_dir / "index.html").write_text(shell(book["title"], idx), encoding="utf-8")

    # --- chapter pages: paginated reader (flip page by page, like a real book) ---
    for i, c in enumerate(chapters):
        text = (book_dir / c["source_file"]).read_text(encoding="utf-8")
        body = md(text)
        last = i + 1 >= len(chapters)
        end_href = 'back-cover.html' if has_covers else 'index.html'
        prev_href = f'ch{chapters[i-1]["number"]:02d}.html' if i > 0 else 'index.html#end'
        next_href = end_href if last else f'ch{chapters[i+1]["number"]:02d}.html'
        prev_title = chapters[i - 1]["title"] if i > 0 else 'Cover'
        next_title = ('Back cover' if has_covers else 'Contents') if last else chapters[i + 1]["title"]
        reader = (
            f'<div class="preader"><i id="pbar"></i></div>'
            f'<div class="reader" data-ch="{c["number"]}" data-prev="{prev_href}" data-next="{next_href}">'
            f'<div class="pnav l"><span>‹</span></div>'
            f'<div class="pages">{body}</div>'
            f'<div class="pnav r"><span>›</span></div>'
            f'</div>'
            f'<div class="pagebar">'
            f'<div class="grp"><button id="ppv" onclick="return false">‹ '
            f'{"prev" if i>0 else "cover"}</button>'
            f'<span class="cnt" id="pcnt">1 / 1</span>'
            f'<button id="pnx" onclick="return false">'
            f'{("back cover" if has_covers else "contents") if last else "next"} ›</button></div>'
            f'<div class="grp"><a href="{next_href}">'
            f'{("to the back cover" if has_covers else "back to contents") if last else "next: " + next_title} →</a></div>'
            f'</div>')
        (out_dir / f'ch{c["number"]:02d}.html').write_text(
            shell(f'{c["title"]} — {book["title"]}', reader,
                  canonical=f'https://oailly.com/read/{book_id}/ch{c["number"]:02d}.html'),
            encoding="utf-8")

    # --- back cover: the closing page of the cover-to-cover reader ---
    if has_covers:
        last_ch = f'ch{chapters[-1]["number"]:02d}.html'
        aibn_line = (f'<div class="bc-aibn"><a href="/aibn/">{aibn_rec["aibn_human"]}</a>'
                     f' · scan on the back cover</div>' if aibn_rec else '')
        back = (f'<div class="backcover">'
                f'<img src="{back_cover}" alt="{book["title"]} — back cover" loading="eager">'
                f'{aibn_line}'
                f'<div class="pagebar"><div class="grp">'
                f'<a href="{last_ch}#end">‹ last page</a></div>'
                f'<div class="grp"><a href="index.html">back to the cover ↺</a></div></div>'
                f'</div>')
        (out_dir / "back-cover.html").write_text(
            shell(f'Back cover — {book["title"]}', back,
                  canonical=f'https://oailly.com/read/{book_id}/back-cover.html'),
            encoding="utf-8")
    print(f"rendered {len(chapters)} chapter(s) + covers + index → {out_dir}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    def opt(name, default=''):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    render(Path(args[0]), Path(args[1]), opt("--accent", ACCENT_DEFAULT),
           opt("--epub"), opt("--source"), opt("--review"), opt("--status"))
