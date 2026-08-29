from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
GATES = PLATFORM / "gates"
sys.path.insert(0, str(GATES))

from checks_padding import check_padding  # noqa: E402
from checks_shelves import check_shelf  # noqa: E402
from checks_structure import check_structure  # noqa: E402


class FictionShelfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name)
        self.chapters = []
        for number in range(1, 9):
            source = f"ch{number:02d}.md"
            (self.book / source).write_text(
                f"# Chapter {number}\n\n" + "story " * 7_500,
                encoding="utf-8",
            )
            self.chapters.append({
                "number": number,
                "title": f"Chapter {number}",
                "source_file": source,
                "words": 7_500,
            })
        self.manifest = {
            "book": {
                "shelf": "fiction",
                "fiction_form": "novel",
                "tier": "standard",
            },
            "structure": {"chapters": self.chapters},
        }
        (self.book / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        self.write_audit()

    def tearDown(self):
        self.temp.cleanup()

    def write_audit(self, *, missing_chapter=None, thread_status="resolved"):
        timeline = [
            {
                "id": f"event-{number}",
                "chapter": number,
                "sequence": number,
                "description": f"Event in chapter {number}",
                "depends_on": [] if number == 1 else [f"event-{number - 1}"],
            }
            for number in range(1, 9)
            if number != missing_chapter
        ]
        audit = {
            "version": "1.0",
            "form": "novel",
            "narrator": {
                "mode": "first person",
                "access_rules": ["observes public acts", "cannot read private thought"],
                "uncertainty_policy": "Unknowns remain labeled as unknown.",
            },
            "characters": [
                {
                    "id": f"character-{number}",
                    "name": f"Character {number}",
                    "role": "test character",
                    "first_chapter": 1,
                    "last_chapter": 8,
                }
                for number in range(1, 4)
            ],
            "timeline": timeline,
            "world_rules": [
                {
                    "id": f"rule-{number}",
                    "rule": f"World rule {number}",
                    "introduced_chapter": 1,
                    "tested_chapters": [number + 1],
                }
                for number in range(1, 4)
            ],
            "threads": [{
                "id": "main-thread",
                "status": thread_status,
                "introduced_chapter": 1,
                "resolution_chapter": 8,
                "note": "The central problem reaches its declared ending.",
            }],
            "refrains": [{
                "text": "The gap remained.",
                "purpose": "Changes from anomaly to accepted limit.",
            }],
        }
        (self.book / "fiction-audit.json").write_text(
            json.dumps(audit), encoding="utf-8"
        )

    def test_complete_novel_and_audit_pass(self):
        findings, metrics = check_shelf(self.manifest, self.book)
        self.assertEqual([], findings)
        self.assertEqual(60_000, metrics["measured_words"])
        self.assertEqual("PASS", metrics["continuity_audit"])
        self.assertEqual(8, metrics["chapters_covered"])

    def test_manifest_schema_matches_flexible_sizing_and_fiction_floor(self):
        schema = json.loads((PLATFORM / "book-manifest.schema.json").read_text())
        structure = schema["properties"]["structure"]["properties"]
        self.assertEqual(20_000, structure["word_count_body"]["minimum"])
        self.assertEqual(5, structure["chapters"]["minItems"])
        chapter_words = structure["chapters"]["items"]["properties"]["words"]
        self.assertEqual(800, chapter_words["minimum"])
        self.assertNotIn("maximum", chapter_words)

    def test_novel_below_sixty_thousand_rejects(self):
        (self.book / "ch08.md").write_text(
            "# Chapter 8\n\n" + "story " * 7_000, encoding="utf-8"
        )
        findings, _ = check_shelf(self.manifest, self.book)
        self.assertIn("FICTION_NOVEL_TOO_SHORT", {item["code"] for item in findings})

    def test_missing_audit_rejects(self):
        (self.book / "fiction-audit.json").unlink()
        findings, _ = check_shelf(self.manifest, self.book)
        self.assertIn("FICTION_AUDIT_MISSING", {item["code"] for item in findings})

    def test_timeline_must_cover_every_chapter(self):
        self.write_audit(missing_chapter=5)
        findings, _ = check_shelf(self.manifest, self.book)
        self.assertIn(
            "FICTION_TIMELINE_COVERAGE_INCOMPLETE",
            {item["code"] for item in findings},
        )

    def test_timeline_dependency_cannot_point_forward(self):
        path = self.book / "fiction-audit.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        audit["timeline"][0]["depends_on"] = ["event-2"]
        path.write_text(json.dumps(audit), encoding="utf-8")
        findings, _ = check_shelf(self.manifest, self.book)
        self.assertIn(
            "FICTION_TIMELINE_DEPENDENCY_FORWARD",
            {item["code"] for item in findings},
        )

    def test_ordinary_unresolved_thread_rejects(self):
        self.write_audit(thread_status="unresolved")
        findings, _ = check_shelf(self.manifest, self.book)
        self.assertIn("FICTION_THREAD_UNRESOLVED", {item["code"] for item in findings})

    def test_fiction_uses_shorter_chapter_floor(self):
        for number in range(1, 9):
            (self.book / f"ch{number:02d}.md").write_text(
                f"# Chapter {number}\n\n" + "story " * 900,
                encoding="utf-8",
            )
        fiction_findings, _ = check_structure(self.manifest, self.book)
        self.assertNotIn(
            "CHAPTER_TOO_SHORT",
            {item["code"] for item in fiction_findings},
        )
        nonfiction = json.loads(json.dumps(self.manifest))
        nonfiction["book"]["shelf"] = "industrial"
        nonfiction_findings, _ = check_structure(nonfiction, self.book)
        self.assertIn(
            "CHAPTER_TOO_SHORT",
            {item["code"] for item in nonfiction_findings},
        )

    def test_narrative_fiction_does_not_receive_index_warning(self):
        (self.book / "frontmatter.md").write_text("# Front Matter", encoding="utf-8")
        (self.book / "provenance.md").write_text(
            "WRITTEN BY test\n\nVERIFIED BY human", encoding="utf-8"
        )
        (self.book / "backmatter.md").write_text(
            "# Back Matter\n\n## References\n\nNone.", encoding="utf-8"
        )
        fiction_findings, _ = check_structure(self.manifest, self.book)
        self.assertNotIn("INDEX_THIN", {item["code"] for item in fiction_findings})
        nonfiction = json.loads(json.dumps(self.manifest))
        nonfiction["book"]["shelf"] = "industrial"
        nonfiction_findings, _ = check_structure(nonfiction, self.book)
        self.assertIn("INDEX_THIN", {item["code"] for item in nonfiction_findings})

    def test_twenty_thousand_word_novella_passes_form_floor(self):
        self.manifest["book"]["fiction_form"] = "novella"
        for number in range(1, 9):
            (self.book / f"ch{number:02d}.md").write_text(
                f"# Chapter {number}\n\n" + "story " * 2_500,
                encoding="utf-8",
            )
        path = self.book / "fiction-audit.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        audit["form"] = "novella"
        path.write_text(json.dumps(audit), encoding="utf-8")
        findings, metrics = check_shelf(self.manifest, self.book)
        self.assertEqual([], findings)
        self.assertEqual(20_000, metrics["measured_words"])

    def test_fiction_disables_nonfiction_scaffold_detector(self):
        text = "\n\n".join(
            f"In this chapter we will follow scene {number}." for number in range(20)
        )
        (self.book / "ch01.md").write_text(text, encoding="utf-8")
        one = {"structure": {"chapters": [{"source_file": "ch01.md"}]}}
        nonfiction_findings, _ = check_padding(one, self.book)
        fiction = json.loads(json.dumps(one))
        fiction["book"] = {"shelf": "fiction"}
        fiction_findings, metrics = check_padding(fiction, self.book)
        self.assertIn(
            "SUMMARY_SHADOW", {item["code"] for item in nonfiction_findings}
        )
        self.assertNotIn(
            "SUMMARY_SHADOW", {item["code"] for item in fiction_findings}
        )
        self.assertEqual("fiction-v1", metrics["profile"])

    def test_fiction_profile_still_rejects_repetitive_loop(self):
        paragraph = (
            "The same scene repeats without changed consequence, character choice, "
            "setting, image, tension, implication, discovery, reversal, or cost."
        )
        (self.book / "ch01.md").write_text(
            "\n\n".join([paragraph] * 250), encoding="utf-8"
        )
        fiction = {
            "book": {"shelf": "fiction"},
            "structure": {"chapters": [{"source_file": "ch01.md"}]},
        }
        findings, _ = check_padding(fiction, self.book)
        codes = {item["code"] for item in findings}
        self.assertIn("COMPRESSES_TOO_WELL", codes)
        self.assertIn("BOILERPLATE_LOOP", codes)

    def test_malformed_audit_rejects_without_crashing(self):
        path = self.book / "fiction-audit.json"
        audit = json.loads(path.read_text(encoding="utf-8"))
        audit["characters"][0]["name"] = None
        audit["timeline"][0]["description"] = []
        audit["world_rules"][0]["rule"] = False
        audit["threads"][0]["note"] = None
        path.write_text(json.dumps(audit), encoding="utf-8")
        findings, _ = check_shelf(self.manifest, self.book)
        codes = {item["code"] for item in findings}
        self.assertIn("FICTION_CHARACTER_TEXT_INVALID", codes)
        self.assertIn("FICTION_TIMELINE_DESCRIPTION_INVALID", codes)
        self.assertIn("FICTION_WORLD_RULE_TEXT_INVALID", codes)
        self.assertIn("FICTION_THREAD_NOTE_INVALID", codes)

    def test_critic_packet_uses_fiction_template(self):
        result = subprocess.run(
            [
                sys.executable,
                str(PLATFORM / "critics" / "assemble_critic_packet.py"),
                str(self.book),
                "2",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        packet = result.stdout
        self.assertIn("Continuity-and-consistency audit", packet)
        self.assertIn("voice: · structure: · stakes:", packet)
        self.assertIn("Only reviewer-directed content counts", packet)
        self.assertNotIn("Fact-check sample", packet)


if __name__ == "__main__":
    unittest.main()
