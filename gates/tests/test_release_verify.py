from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "oailly_verify_rendered_book", PLATFORM / "verify_rendered_book.py"
)
release_verify = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(release_verify)


XHTML = ('<?xml version="1.0" encoding="utf-8"?>'
         '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title></head>'
         '<body><p>x</p></body></html>')


class ReleaseVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "source"
        self.rendered = root / "rendered"
        self.source.mkdir()
        self.rendered.mkdir()
        manifest = {
            "structure": {"chapters": [{
                "number": 1,
                "title": "One",
                "source_file": "ch01.md",
            }]},
        }
        (self.source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.sections = [
            ("provenance.html", "provenance.md", "PROVENANCE"),
            ("frontmatter.html", "frontmatter.md", "FRONT"),
            ("ch01.html", "ch01.md", "CHAPTER"),
            ("backmatter.html", "backmatter.md", "BACK"),
        ]
        for _, source_name, marker in self.sections:
            (self.source / source_name).write_text(marker, encoding="utf-8")
        names = [name for name, _, _ in self.sections]
        (self.rendered / "index.html").write_text(
            "".join(f'<a href="{name}">{name}</a>' for name in names)
            + '<a href="book.md">full</a><a href="book.epub">epub</a>',
            encoding="utf-8",
        )
        for index, (name, _, marker) in enumerate(self.sections):
            previous = names[index - 1] if index else "index.html#end"
            following = names[index + 1] if index + 1 < len(names) else "index.html"
            (self.rendered / name).write_text(
                f'<div class="reader" data-prev="{previous}" data-next="{following}">'
                f'{marker}</div><a href="{following}">next</a>',
                encoding="utf-8",
            )
        (self.rendered / "book.md").write_text(
            "\n".join(marker for _, _, marker in self.sections), encoding="utf-8"
        )
        self.write_epub(["titlepage", "provenance", "frontmatter", "ch01", "backmatter"])

    def tearDown(self):
        self.temp.cleanup()

    def write_epub(self, spine):
        items = ["titlepage", "provenance", "frontmatter", "ch01", "backmatter"]
        manifest_items = ''.join(
            f'<item id="{item}" href="{item}.xhtml" media-type="application/xhtml+xml"/>'
            for item in items
        )
        opf = ('<?xml version="1.0" encoding="utf-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
               '<manifest><item id="nav" href="nav.xhtml" '
               'media-type="application/xhtml+xml" properties="nav"/>'
               '<item id="css" href="style.css" media-type="text/css"/>'
               f'{manifest_items}</manifest><spine>'
               + ''.join(f'<itemref idref="{item}"/>' for item in spine)
               + '</spine></package>')
        nav = ('<?xml version="1.0" encoding="utf-8"?>'
               '<html xmlns="http://www.w3.org/1999/xhtml"><body><nav><ol>'
               + ''.join(f'<li><a href="{item}.xhtml">{item}</a></li>' for item in items)
               + '</ol></nav></body></html>')
        container = ('<?xml version="1.0"?><container version="1.0" '
                     'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                     '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                     'media-type="application/oebps-package+xml"/></rootfiles></container>')
        with zipfile.ZipFile(self.rendered / "book.epub", "w") as archive:
            archive.writestr("mimetype", "application/epub+zip",
                             compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", nav)
            archive.writestr("OEBPS/style.css", "body{}")
            for item in items:
                archive.writestr(f"OEBPS/{item}.xhtml", XHTML)

    def test_complete_release_passes(self):
        self.assertEqual([], release_verify.verify(self.source, self.rendered))

    def test_missing_web_target_fails(self):
        page = self.rendered / "ch01.html"
        page.write_text(page.read_text().replace('href="backmatter.html"',
                                                  'href="missing.html"'))
        problems = release_verify.verify(self.source, self.rendered)
        self.assertTrue(any("links to missing" in problem for problem in problems), problems)

    def test_wrong_epub_spine_fails(self):
        self.write_epub(["titlepage", "ch01"])
        problems = release_verify.verify(self.source, self.rendered)
        self.assertTrue(any("epub: spine" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
