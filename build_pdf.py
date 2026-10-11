#!/usr/bin/env python3
"""Build a print-style PDF from a book source tree (same inputs as build_epub.py).

    .buildenv/bin/python platform/build_pdf.py <book_dir> <out.pdf> [--cover PNG]

Order: cover, title/provenance page, contents, frontmatter, chapters, backmatter.
Needs fpdf2 + Markdown (both in .buildenv) and the DejaVu fonts (full Unicode).
"""

from __future__ import annotations

import html as htmllib
import json
import re
import sys
from pathlib import Path

import markdown
from fpdf import FPDF
from fpdf.fonts import FontFace

FONTS = Path("/usr/share/fonts/dejavu")
KNOWN_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "em", "strong", "i", "b",
              "code", "pre", "blockquote", "table", "thead", "tbody", "tr", "th", "td", "br", "a",
              "hr", "u", "sub", "sup", "img", "font", "dl", "dt", "dd", "center", "section"}


def md(text: str) -> str:
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    # fpdf2's HTML renderer has no <hr> support in blockquotes etc.; keep it simple
    html = html.replace("<hr />", "<p>* * *</p>")
    # Literal placeholders such as <published-sha256> survive Markdown as raw tags and
    # would vanish in the PDF: escape every tag the renderer doesn't know.
    html = re.sub(r"<(/?)([A-Za-z][\w-]*)([^>]*)>",
                  lambda m: m.group(0) if m.group(2).lower() in KNOWN_TAGS
                  else f"&lt;{m.group(1)}{m.group(2)}{m.group(3)}&gt;", html)
    # fpdf2 table cells hold plain text only: flatten inline markup inside cells
    html = re.sub(r"<(td|th)([^>]*)>(.*?)</\1>",
                  lambda m: f"<{m.group(1)}{m.group(2)}>{re.sub(r'</?(?:em|strong|code|b|i|a)[^>]*>', '', m.group(3))}</{m.group(1)}>",
                  html, flags=re.S)
    return html


class Book(FPDF):
    def __init__(self, title: str):
        super().__init__(format=(152.4, 228.6))  # 6x9 in trade size
        self.book_title = title
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(True, margin=20)
        for style, f in (("", "DejaVuSerif.ttf"), ("B", "DejaVuSerif-Bold.ttf"),
                         ("I", "DejaVuSerif-Italic.ttf"), ("BI", "DejaVuSerif-BoldItalic.ttf")):
            self.add_font("body", style, str(FONTS / f))
        for style, f in (("", "DejaVuSansMono.ttf"), ("B", "DejaVuSansMono-Bold.ttf"),
                         ("I", "DejaVuSansMono-Oblique.ttf"), ("BI", "DejaVuSansMono-BoldOblique.ttf")):
            self.add_font("mono", style, str(FONTS / f))
        for style, f in (("", "DejaVuSans.ttf"), ("B", "DejaVuSans-Bold.ttf")):
            self.add_font("sans", style, str(FONTS / f))
        self.set_font("body", size=10)
        self.running = True

    def header(self):
        if self.page_no() <= 2 or not self.running:
            return
        self.set_y(9)
        self.set_font("sans", size=7)
        self.set_text_color(120)
        self.cell(0, 6, self.book_title.upper(), align="C")
        self.set_text_color(0)
        self.set_y(20)

    def footer(self):
        if self.page_no() <= 2 or not self.running:
            return
        self.set_y(-14)
        self.set_font("sans", size=8)
        self.set_text_color(120)
        self.cell(0, 6, str(self.page_no()), align="C")
        self.set_text_color(0)

    def html(self, html: str):
        self.set_font("body", size=10)
        self.write_html(
            html,
            font_family="body",
            tag_styles={
                "h1": FontFace(family="sans", emphasis="B", size_pt=18, color=0),
                "h2": FontFace(family="sans", emphasis="B", size_pt=13, color=0),
                "h3": FontFace(family="sans", emphasis="B", size_pt=11, color=0),
                "h4": FontFace(family="sans", emphasis="B", size_pt=10, color=0),
                "code": FontFace(family="mono", size_pt=8.5),
                "pre": FontFace(family="mono", size_pt=8.5),
                "blockquote": FontFace(color=(70, 70, 70)),
            },
        )


esc = htmllib.escape


def build(book_dir: Path, out: Path, cover: Path | None) -> None:
    m = json.loads((book_dir / "manifest.json").read_text())
    book, prov = m["book"], m["provenance"]
    chapters = m["structure"]["chapters"]
    authors = ", ".join(w["model"] for w in prov["written_by"])

    pdf = Book(book["title"])
    pdf.set_title(book["title"])
    pdf.set_author(authors)
    pdf.set_creator("o'ailly press (RogerAI Labs) - platform/build_pdf.py")
    pdf.set_subject(book.get("subtitle", ""))
    pdf.set_lang(book.get("language", "en"))

    # cover (full bleed) or typeset title page
    pdf.add_page()
    if cover and cover.exists():
        pdf.image(str(cover), x=0, y=0, w=pdf.w, h=pdf.h)
    else:
        pdf.set_y(70)
        pdf.set_font("sans", "B", 24)
        pdf.multi_cell(0, 11, book["title"], align="C")
        pdf.ln(4)
        pdf.set_font("body", "I", 12)
        pdf.multi_cell(0, 7, book.get("subtitle", ""), align="C")
        pdf.set_y(-50)
        pdf.set_font("sans", size=9)
        pdf.cell(0, 6, "Written by " + authors, align="C")

    # title + provenance page
    pdf.add_page()
    verified = prov["verified_by"].get("name") or "pending"
    pdf.html(
        f"<h1>{esc(book['title'])}</h1><p><i>{esc(book.get('subtitle', ''))}</i></p><br>"
        f"<p><b>WRITTEN BY</b> {esc(authors)}</p>"
        f"<p><b>VERIFIED BY</b> {esc(verified)}</p>"
        f"<p><b>DISCLOSURE</b> {esc(prov['disclosure_statement'])}</p>"
        f"<p><b>PROVENANCE &amp; REVIEW TRAIL</b> https://oailly.com - the full review "
        f"record publishes with this book.</p>"
    )

    # contents (page numbers via outline links)
    pdf.add_page()
    toc_entries: list[tuple[str, str]] = []
    pdf.html("<h1>Contents</h1>")
    toc_y = pdf.get_y()

    sections: list[tuple[str, str, str]] = []  # (label, title, html)
    fm = book_dir / "frontmatter.md"
    if fm.exists():
        sections.append(("", "Front Matter", md(fm.read_text())))
    for c in chapters:
        sections.append((f"{c['number']}.", c["title"], md((book_dir / c["source_file"]).read_text())))
    bm = book_dir / "backmatter.md"
    if bm.exists():
        sections.append(("", "Back Matter", md(bm.read_text())))

    # first pass renders into a scratch doc to learn page numbers for the TOC
    def render(doc: Book, pages: dict[int, int] | None):
        for i, (label, title, html) in enumerate(sections):
            doc.add_page()
            if pages is not None:
                pages[i] = doc.page_no()
            doc.start_section(f"{label} {title}".strip())
            doc.html(html)

    scratch = Book(book["title"])
    scratch.add_page(); scratch.add_page(); scratch.add_page()
    pages: dict[int, int] = {}
    toc_pages = 1
    render(scratch, pages)
    # contents may spill past one page: reserve extra pages if needed
    per_page = 32
    toc_pages = max(1, -(-len(sections) // per_page))
    shift = toc_pages - 1

    pdf.set_font("body", size=10)
    pdf.set_y(toc_y)
    for n, (label, title, _) in enumerate(sections):
        if n and n % per_page == 0:
            pdf.add_page()
        pg = pages[n] + shift
        txt = f"{label} {title}".strip()
        pdf.cell(pdf.epw - 14, 6, txt, border=0)
        pdf.cell(14, 6, str(pg), align="R", new_x="LMARGIN", new_y="NEXT")

    render(pdf, None)
    pdf.output(str(out))
    print(f"built {out} ({out.stat().st_size // 1024} KB, {pdf.page_no()} pages)")


if __name__ == "__main__":
    cover = Path(sys.argv[sys.argv.index("--cover") + 1]) if "--cover" in sys.argv else None
    build(Path(sys.argv[1]), Path(sys.argv[2]), cover)
