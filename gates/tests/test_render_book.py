from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from html import escape as html_escape
from pathlib import Path
from unittest import mock


PLATFORM = Path(__file__).resolve().parents[2]

sys.modules.setdefault(
    "markdown",
    types.SimpleNamespace(markdown=lambda text, **_: f"<p>{html_escape(text)}</p>"),
)
pygments = types.ModuleType("pygments")
formatters = types.ModuleType("pygments.formatters")


class HtmlFormatter:
    def __init__(self, **_):
        pass

    def get_style_defs(self, _selector):
        return ""


formatters.HtmlFormatter = HtmlFormatter
pygments.formatters = formatters
sys.modules.setdefault("pygments", pygments)
sys.modules.setdefault("pygments.formatters", formatters)

spec = importlib.util.spec_from_file_location("oailly_render_book", PLATFORM / "render_book.py")
render_book = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render_book)


class WebRenderTests(unittest.TestCase):
    def test_cover_path_uses_sibling_site_checkout(self):
        self.assertEqual(
            render_book._covers,
            PLATFORM.parent / "site-repo" / "assets" / "covers",
        )

    def test_cover_locator_supports_nested_and_standalone_checkouts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested_platform = root / "site" / ".platform"
            nested_covers = root / "site" / "assets" / "covers"
            nested_platform.mkdir(parents=True)
            nested_covers.mkdir(parents=True)
            self.assertEqual(render_book.locate_cover_dir(nested_platform), nested_covers)

            standalone_platform = root / "workspace" / "platform"
            standalone_covers = root / "workspace" / "gh" / "site-repo" / "assets" / "covers"
            standalone_platform.mkdir(parents=True)
            standalone_covers.mkdir(parents=True)
            self.assertEqual(
                render_book.locate_cover_dir(standalone_platform), standalone_covers
            )

    def test_canonical_sections_are_rendered_in_cover_to_cover_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / "book"
            output = root / "read" / "publisher--book"
            book.mkdir()
            manifest = {
                "book": {
                    "title": "The Test Book",
                    "subtitle": "A Complete Rendering",
                    "language": "en",
                    "series": "FICTION",
                    "tier": "standard",
                },
                "structure": {"chapters": [
                    {"number": 1, "title": "First", "source_file": "ch01.md"},
                    {"number": 2, "title": "Second", "source_file": "ch02.md"},
                ]},
                "provenance": {
                    "written_by": [{"model": "test-model"}],
                    "verified_by": {"name": "Test Human"},
                    "disclosure_statement": "Test disclosure.",
                },
                "review": {"status": "draft", "trail_uri": None},
            }
            (book / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            for name, marker in (
                ("provenance.md", "PROVENANCE_MARKER"),
                ("frontmatter.md", "FRONT_MARKER"),
                ("ch01.md", "CHAPTER_ONE_MARKER"),
                ("ch02.md", "CHAPTER_TWO_MARKER"),
                ("backmatter.md", "BACK_MARKER"),
            ):
                (book / name).write_text(marker, encoding="utf-8")

            render_book.render(
                book,
                output,
                "#123456",
                review="https://example.invalid/review",
                publication_status="published",
                version="v3",
                revision_sha="a" * 40,
            )

            expected = {
                "index.html", "provenance.html", "frontmatter.html", "ch01.html",
                "ch02.html", "backmatter.html", "book.md",
            }
            self.assertEqual(expected, {path.name for path in output.iterdir()})
            full = (output / "book.md").read_text(encoding="utf-8")
            positions = [full.index(marker) for marker in (
                "PROVENANCE_MARKER", "FRONT_MARKER", "CHAPTER_ONE_MARKER",
                "CHAPTER_TWO_MARKER", "BACK_MARKER",
            )]
            self.assertEqual(sorted(positions), positions)

            index = (output / "index.html").read_text(encoding="utf-8")
            links = [index.index(name) for name in (
                "provenance.html", "frontmatter.html", "ch01.html", "ch02.html",
                "backmatter.html",
            )]
            self.assertEqual(sorted(links), links)
            self.assertIn('data-prev="index.html#end" data-next="frontmatter.html"',
                          (output / "provenance.html").read_text(encoding="utf-8"))
            self.assertIn('data-prev="provenance.html" data-next="ch01.html"',
                          (output / "frontmatter.html").read_text(encoding="utf-8"))
            self.assertIn('data-prev="frontmatter.html" data-next="ch02.html"',
                          (output / "ch01.html").read_text(encoding="utf-8"))
            self.assertIn('data-prev="ch01.html" data-next="backmatter.html"',
                          (output / "ch02.html").read_text(encoding="utf-8"))
            self.assertIn('data-prev="ch02.html" data-next="index.html"',
                          (output / "backmatter.html").read_text(encoding="utf-8"))
            self.assertIn(
                "Release Attestation",
                (output / "provenance.html").read_text(encoding="utf-8"),
            )
            self.assertIn("exact source commit " + "a" * 40, full)
            self.assertIn("PUBLICATION</b> PUBLISHED", index)
            self.assertIn('<div class="prov release"><b>RELEASE ATTESTATION</b>', index)
            self.assertNotIn('<b>RELEASE ATTESTATION</b> <h2>', index)

    def test_front_and_back_covers_are_both_required_for_cover_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / "book"
            output = root / "read" / "publisher--book"
            covers = root / "covers"
            book.mkdir()
            covers.mkdir()
            manifest = {
                "book": {"title": "Covered", "language": "en", "tier": "standard"},
                "structure": {"chapters": [
                    {"number": 1, "title": "One", "source_file": "ch01.md"}
                ]},
                "provenance": {
                    "written_by": [{"model": "test-model"}],
                    "verified_by": {"name": "Test Human"},
                    "disclosure_statement": "Test disclosure.",
                },
                "review": {"status": "published", "trail_uri": None},
            }
            (book / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (book / "ch01.md").write_text("chapter", encoding="utf-8")
            (covers / "publisher--book-front.png").write_bytes(b"front")
            (covers / "publisher--book-back.png").write_bytes(b"back")
            with mock.patch.object(render_book, "SITE_ASSETS", covers):
                render_book.render(book, output, "#123456")
            self.assertTrue((output / "back-cover.html").is_file())
            self.assertIn("publisher--book-front.png", (output / "index.html").read_text())
            self.assertIn(
                'data-next="back-cover.html"',
                (output / "ch01.html").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
