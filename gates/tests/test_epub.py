from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
import zipfile
from html import escape as html_escape
from pathlib import Path
from xml.etree import ElementTree


PLATFORM = Path(__file__).resolve().parents[2]

# Gate CI is stdlib-only. The builder's ordering and package tests do not need Markdown
# semantics, so provide a minimal module while importing it here.
sys.modules.setdefault(
    "markdown",
    types.SimpleNamespace(markdown=lambda text, **_: f"<p>{html_escape(text)}</p>"),
)
spec = importlib.util.spec_from_file_location("oailly_build_epub", PLATFORM / "build_epub.py")
build_epub = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_epub)


class EpubBuildTests(unittest.TestCase):
    def test_canonical_front_and_back_matter_have_correct_spine_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "book": {
                    "title": "Memory & Mercy",
                    "subtitle": "A Test <Novel>",
                    "language": "en",
                },
                "structure": {
                    "chapters": [{
                        "number": 1,
                        "title": "Cause & Consequence",
                        "source_file": "ch01.md",
                    }],
                },
                "provenance": {
                    "written_by": [{"model": "model&a"}],
                    "verified_by": {"name": "Human & Steward"},
                    "disclosure_statement": "AI & human roles are declared.",
                },
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "provenance.md").write_text("# Provenance", encoding="utf-8")
            (root / "frontmatter.md").write_text("# Introduction", encoding="utf-8")
            (root / "ch01.md").write_text("# Cause & Consequence", encoding="utf-8")
            (root / "backmatter.md").write_text("# Back Matter", encoding="utf-8")
            output = root / "book.epub"
            second_output = root / "book-again.epub"

            build_epub.build(
                root,
                output,
                None,
                "published",
                "https://example.invalid/review",
                "v3",
                "a" * 40,
            )
            build_epub.build(
                root,
                second_output,
                None,
                "published",
                "https://example.invalid/review",
                "v3",
                "a" * 40,
            )
            self.assertEqual(output.read_bytes(), second_output.read_bytes())

            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual("mimetype", archive.namelist()[0])
                self.assertEqual(zipfile.ZIP_STORED,
                                 archive.getinfo("mimetype").compress_type)
                opf = archive.read("OEBPS/content.opf")
                package = ElementTree.fromstring(opf)
                ns = {"opf": "http://www.idpf.org/2007/opf"}
                spine = [item.attrib["idref"] for item in package.findall(
                    "opf:spine/opf:itemref", ns
                )]
                self.assertEqual(
                    ["titlepage", "provenance", "frontmatter", "ch01", "backmatter"],
                    spine,
                )
                self.assertIn(
                    b"Release Attestation",
                    archive.read("OEBPS/provenance.xhtml"),
                )
                self.assertIn(
                    ("exact source commit " + "a" * 40).encode(),
                    archive.read("OEBPS/titlepage.xhtml"),
                )
                for name in archive.namelist():
                    if name.endswith((".xhtml", ".opf", ".xml")):
                        ElementTree.fromstring(archive.read(name))


if __name__ == "__main__":
    unittest.main()
