#!/usr/bin/env python3
"""Verify a rendered web reader and EPUB before publication state is mutated.

    python3 verify_rendered_book.py <book_source_dir> <rendered_dir>

Stdlib only. Exit 0 means the release artifact is internally complete; exit 1 prints
every detected problem. This complements the post-deploy HTTP health check.
"""

from __future__ import annotations

import json
import posixpath
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []
        self.reader_nav: list[tuple[str | None, str | None]] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        classes = set(values.get("class", "").split())
        if "reader" in classes:
            self.reader_nav.append((values.get("data-prev"), values.get("data-next")))


def canonical_sections(manifest: dict, source: Path) -> list[tuple[str, Path, str]]:
    sections: list[tuple[str, Path, str]] = []
    for source_name, output_name in (
        ("provenance.md", "provenance.html"),
        ("frontmatter.md", "frontmatter.html"),
    ):
        path = source / source_name
        if path.is_file():
            sections.append((output_name, path, output_name.removesuffix(".html")))
    for chapter in manifest.get("structure", {}).get("chapters", []):
        number = chapter.get("number")
        chapter_path = source / chapter.get("source_file", "")
        sections.append((f"ch{number:02d}.html", chapter_path, f"ch{number:02d}"))
    backmatter = source / "backmatter.md"
    if backmatter.is_file():
        sections.append(("backmatter.html", backmatter, "backmatter"))
    return sections


def _local_target(rendered: Path, page: Path, href: str) -> Path | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("/", "#", "javascript:", "mailto:")):
        return None
    relative = unquote(parsed.path)
    if not relative:
        return None
    return page.parent / relative


def verify_web(source: Path, rendered: Path, sections) -> list[str]:
    problems: list[str] = []
    required = {"index.html", "book.md", "book.epub"} | {name for name, _, _ in sections}
    missing = sorted(name for name in required if not (rendered / name).is_file())
    if missing:
        problems.append(f"web: missing required artifacts {missing}")

    html_pages = sorted(rendered.glob("*.html"))
    for page in html_pages:
        parser = PageLinks()
        try:
            parser.feed(page.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"web: cannot read {page.name}: {error}")
            continue
        for href in parser.hrefs:
            target = _local_target(rendered, page, href)
            if target is not None and not target.is_file():
                problems.append(f"web: {page.name} links to missing {href!r}")

    names = [name for name, _, _ in sections]
    has_back_cover = (rendered / "back-cover.html").is_file()
    for index, name in enumerate(names):
        page = rendered / name
        if not page.is_file():
            continue
        parser = PageLinks()
        parser.feed(page.read_text(encoding="utf-8"))
        expected_prev = names[index - 1] if index else "index.html#end"
        expected_next = (names[index + 1] if index + 1 < len(names)
                         else ("back-cover.html" if has_back_cover else "index.html"))
        if parser.reader_nav != [(expected_prev, expected_next)]:
            problems.append(
                f"web: {name} navigation {parser.reader_nav!r} != "
                f"{[(expected_prev, expected_next)]!r}"
            )

    index_path = rendered / "index.html"
    if index_path.is_file():
        index_html = index_path.read_text(encoding="utf-8")
        cursor = 0
        for name in names:
            position = index_html.find(f'href="{name}"', cursor)
            if position < 0:
                problems.append(f"web: index TOC lacks ordered link to {name}")
                break
            cursor = position + 1

    full_path = rendered / "book.md"
    if full_path.is_file():
        full = full_path.read_text(encoding="utf-8")
        cursor = 0
        for name, source_path, _ in sections:
            if not source_path.is_file():
                problems.append(f"source: missing canonical file for {name}: {source_path}")
                continue
            source_text = source_path.read_text(encoding="utf-8")
            position = full.find(source_text, cursor)
            if position < 0:
                problems.append(f"web: book.md omits or misorders {source_path.name}")
                break
            cursor = position + len(source_text)
    return problems


def verify_epub(rendered: Path, expected_ids: list[str]) -> list[str]:
    problems: list[str] = []
    path = rendered / "book.epub"
    if not path.is_file():
        return ["epub: book.epub is missing"]
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not names or names[0] != "mimetype":
                problems.append("epub: mimetype must be the first ZIP entry")
            elif archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                problems.append("epub: mimetype must be stored without compression")
            elif archive.read("mimetype") != b"application/epub+zip":
                problems.append("epub: mimetype content is invalid")
            corrupt = archive.testzip()
            if corrupt:
                problems.append(f"epub: corrupt ZIP member {corrupt}")

            for name in names:
                if name.endswith((".xhtml", ".opf", ".xml")):
                    try:
                        ElementTree.fromstring(archive.read(name))
                    except ElementTree.ParseError as error:
                        problems.append(f"epub: invalid XML in {name}: {error}")

            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            )
            if rootfile is None or not rootfile.get("full-path"):
                return problems + ["epub: container lacks a rootfile"]
            opf_name = rootfile.get("full-path")
            package = ElementTree.fromstring(archive.read(opf_name))
            ns = {"opf": "http://www.idpf.org/2007/opf"}
            manifest = {
                item.get("id"): item.get("href")
                for item in package.findall("opf:manifest/opf:item", ns)
            }
            opf_dir = posixpath.dirname(opf_name)
            for item_id, href in manifest.items():
                member = posixpath.normpath(posixpath.join(opf_dir, href or ""))
                if member not in names:
                    problems.append(f"epub: manifest item {item_id!r} targets missing {member}")
            spine = [item.get("idref") for item in package.findall("opf:spine/opf:itemref", ns)]
            if spine != expected_ids:
                problems.append(f"epub: spine {spine!r} != expected {expected_ids!r}")
            unknown = [item_id for item_id in spine if item_id not in manifest]
            if unknown:
                problems.append(f"epub: spine references unknown manifest ids {unknown}")

            nav_href = manifest.get("nav")
            if nav_href:
                nav_name = posixpath.normpath(posixpath.join(opf_dir, nav_href))
                nav = ElementTree.fromstring(archive.read(nav_name))
                xhtml = {"x": "http://www.w3.org/1999/xhtml"}
                for anchor in nav.findall(".//x:a", xhtml):
                    href = anchor.get("href", "")
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(nav_name), href))
                    if target not in names:
                        problems.append(f"epub: nav targets missing {target}")
    except (OSError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        problems.append(f"epub: cannot validate package: {error}")
    return problems


def verify(source: Path, rendered: Path) -> list[str]:
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"source: cannot load manifest.json: {error}"]
    sections = canonical_sections(manifest, source)
    expected_ids = ["titlepage"] + [section_id for _, _, section_id in sections]
    return verify_web(source, rendered, sections) + verify_epub(rendered, expected_ids)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_rendered_book.py <book_source_dir> <rendered_dir>", file=sys.stderr)
        return 2
    problems = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    if problems:
        print(f"RELEASE VERIFY — FAIL ({len(problems)} problem(s))")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("RELEASE VERIFY — PASS (web + EPUB internally complete)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
