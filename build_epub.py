#!/usr/bin/env python3
"""Build a Kindle-compatible EPUB3 from a book source tree. Stdlib + markdown only.

    .buildenv/bin/python platform/build_epub.py <book_dir> <out.epub> [--cover PNG]
"""

from __future__ import annotations

import json
import sys
import uuid
import zipfile
from datetime import date
from pathlib import Path

import markdown

CSS = """
body{font-family:Georgia,'Times New Roman',serif;line-height:1.7;margin:1em;color:#111}
h1{font-family:Helvetica,Arial,sans-serif;font-size:1.6em;line-height:1.2;margin:1em 0 .6em}
h2{font-family:Helvetica,Arial,sans-serif;font-size:1.2em;margin:1.4em 0 .4em}
h3{font-size:1.05em;margin:1.2em 0 .3em}
p{margin:0 0 .8em}
code{font-family:Menlo,Consolas,monospace;font-size:.85em}
pre{font-family:Menlo,Consolas,monospace;font-size:.8em;white-space:pre-wrap;border:1px solid #ccc;padding:.6em;border-radius:4px}
blockquote{border-left:3px solid #888;margin:0 0 .8em;padding:0 0 0 1em;color:#444}
table{border-collapse:collapse;margin:.8em 0}
th,td{border:1px solid #999;padding:.3em .6em;font-size:.9em}
.provenance{border:1px solid #999;border-radius:6px;padding:1em;font-size:.9em;background:#f7f7f5}
"""

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{title}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>{body}</body></html>"""


def md(text: str) -> str:
    return markdown.markdown(text, extensions=["tables", "fenced_code"])


def build(book_dir: Path, out: Path, cover: Path | None) -> None:
    m = json.loads((book_dir / "manifest.json").read_text())
    book, prov = m["book"], m["provenance"]
    chapters = m["structure"]["chapters"]
    uid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "oailly:" + book["title"]))
    authors = ", ".join(w["model"] for w in prov["written_by"])

    items, spine, navlis = [], [], []
    docs: list[tuple[str, str]] = []

    prov_body = (f"<h1>{book['title']}</h1><p><i>{book.get('subtitle','')}</i></p>"
                 f"<div class='provenance'><p><b>WRITTEN BY</b> {authors}</p>"
                 f"<p><b>VERIFIED BY</b> {prov['verified_by'].get('name') or 'pending'}</p>"
                 f"<p><b>DISCLOSURE</b> {prov['disclosure_statement']}</p>"
                 f"<p><b>PROVENANCE &amp; REVIEW TRAIL</b> https://oailly.com — the full "
                 f"review record publishes with this book.</p></div>")
    docs.append(("titlepage.xhtml", XHTML.format(title=book["title"], body=prov_body)))
    navlis.append('<li><a href="titlepage.xhtml">Title &amp; Provenance</a></li>')

    for c in chapters:
        fn = f"ch{c['number']:02d}.xhtml"
        body = md((book_dir / c["source_file"]).read_text())
        docs.append((fn, XHTML.format(title=c["title"], body=body)))
        navlis.append(f'<li><a href="{fn}">{c["number"]}. {c["title"]}</a></li>')

    for f in ("frontmatter.md", "backmatter.md"):
        p = book_dir / f
        if p.exists():
            fn = f.replace(".md", ".xhtml")
            docs.append((fn, XHTML.format(title=f, body=md(p.read_text()))))
            navlis.append(f'<li><a href="{fn}">{f.split(".")[0].title()}</a></li>')

    for fn, _ in docs:
        iid = fn.split(".")[0]
        items.append(f'<item id="{iid}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{iid}"/>')

    cover_item = ""
    if cover and cover.exists():
        cover_item = '<item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>'

    nav = XHTML.format(title="Contents",
                       body=f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{"".join(navlis)}</ol></nav>')
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="uid">{uid}</dc:identifier>
  <dc:title>{book['title']}</dc:title>
  <dc:creator>{authors}</dc:creator>
  <dc:language>{book.get('language','en')}</dc:language>
  <dc:publisher>o'ailly press (RogerAI Labs)</dc:publisher>
  <dc:date>{date.today().isoformat()}</dc:date>
  <dc:description>{book.get('subtitle','')} — written by machines, verified by humans; provenance and review trail at oailly.com.</dc:description>
  <meta property="dcterms:modified">{date.today().isoformat()}T00:00:00Z</meta>
 </metadata>
 <manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="css" href="style.css" media-type="text/css"/>
  {cover_item}
  {''.join(items)}
 </manifest>
 <spine>{''.join(spine)}</spine>
</package>"""

    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/style.css", CSS)
        if cover and cover.exists():
            z.writestr("OEBPS/cover.png", cover.read_bytes())
        for fn, content in docs:
            z.writestr(f"OEBPS/{fn}", content)
    print(f"built {out} ({out.stat().st_size//1024} KB, {len(docs)} docs)")


if __name__ == "__main__":
    cover = Path(sys.argv[sys.argv.index("--cover") + 1]) if "--cover" in sys.argv else None
    build(Path(sys.argv[1]), Path(sys.argv[2]), cover)
