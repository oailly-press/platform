from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PLATFORM = Path(__file__).resolve().parents[2]
CRITICS = PLATFORM / "critics"
sys.path.insert(0, str(CRITICS))

import critique  # noqa: E402
import run_critics  # noqa: E402


def fiction_review(pass_no: int, verdict: str) -> str:
    return f"""# Fiction critic review
CRITIC: test-model + operator
DATE: 2026-08-28
PASS: {pass_no}
READ: {'full manuscript' if pass_no == 2 else 'delta'}

## Verdict summary
The manuscript has been read against the declared standard. **{verdict}**

## Blocking findings
| # | Location | Problem | Evidence | Severity |
|---|---|---|---|---|
| 1 | ch01.md | A concrete debt | A quoted scene-level observation | med |

## Suggestions (non-blocking)
1. Preserve the strongest image while tightening its setup.

## Continuity-and-consistency audit
| Class | Chapters checked | Claimed continuity | Result | Note |
|---|---|---|---|---|
| timeline | 1 | Event order | holds | Checked directly. |

## Craft-axis scores (1–5)
voice: 4 · structure: 4 · stakes: 4 · scene-work: 4 · ending: 4

## Density finding
The central scene earns its length through changed consequence. One transitional
paragraph repeats context and can be compressed without losing voice or causality.

## Pass-3 only: findings ledger
| Finding # | Status | Note |
|---|---|---|
| 1 | resolved | The revised scene supplies the missing consequence. |

## Review detail
{"Specific manuscript evidence and independent craft reasoning. " * 12}
"""


class CriticValidationTests(unittest.TestCase):
    def test_fiction_pass2_complete_review_is_accepted(self):
        text = fiction_review(2, "SALVAGEABLE — findings below")
        critique.validate_review(text, 2, True)
        self.assertEqual("SALVAGEABLE", critique.tally_verdict(text, 2))

    def test_fiction_review_missing_density_section_is_rejected(self):
        text = fiction_review(2, "SALVAGEABLE — findings below").replace(
            "## Density finding", "## Length notes"
        )
        with self.assertRaises(SystemExit):
            critique.validate_review(text, 2, True)

    def test_pass3_requires_delta_ledger_and_pass3_verdict(self):
        text = fiction_review(3, "PUBLISH")
        critique.validate_review(text, 3, True)
        self.assertEqual("PUBLISH", critique.tally_verdict(text, 3))
        with self.assertRaises(SystemExit):
            critique.validate_review(text.replace("## Pass-3 only: findings ledger", "## Ledger"), 3, True)
        with self.assertRaises(SystemExit):
            critique.validate_review(fiction_review(3, "SALVAGEABLE"), 3, True)

    def test_unfilled_verdict_choices_are_rejected(self):
        text = fiction_review(2, "SALVAGEABLE / UNSALVAGEABLE")
        with self.assertRaises(SystemExit):
            critique.validate_review(text, 2, True)

    def test_author_family_mapping_excludes_gpt_models(self):
        self.assertEqual("openai", critique.family_of("gpt-5.6-sol"))


class CriticPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name)
        manifest = {
            "book": {"title": "Test Novel", "shelf": "fiction"},
            "structure": {
                "chapters": [{"number": 1, "title": "Arrival", "source_file": "ch01.md"}]
            },
        }
        (self.book / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.book / "ch01.md").write_text("# Arrival\n\nA changed scene.", encoding="utf-8")
        review_dir = self.book / "review" / "v1"
        review_dir.mkdir(parents=True)
        for seat in "ABC":
            (review_dir / f"critic-{seat}.md").write_text(
                f"critic {seat} prior blocking finding", encoding="utf-8"
            )
        (self.book / "response-to-findings.md").write_text(
            "Every prior finding receives a response.", encoding="utf-8"
        )
        self.delta = self.book / "delta.patch"
        self.delta.write_text("diff --git a/ch01.md b/ch01.md\n+new consequence", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_pass3_packet_includes_complete_case_file(self):
        result = subprocess.run(
            [
                sys.executable,
                str(CRITICS / "assemble_critic_packet.py"),
                str(self.book),
                "3",
                str(self.delta),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS-2 FINDINGS", result.stdout)
        self.assertIn("critic A prior blocking finding", result.stdout)
        self.assertIn("AUTHOR RESPONSE TO FINDINGS", result.stdout)
        self.assertIn("diff --git a/ch01.md", result.stdout)
        self.assertIn("delta verification against Pass-2 findings", result.stdout)

    def test_pass3_packet_fails_closed_without_three_prior_reviews(self):
        (self.book / "review" / "v1" / "critic-C.md").unlink()
        result = subprocess.run(
            [
                sys.executable,
                str(CRITICS / "assemble_critic_packet.py"),
                str(self.book),
                "3",
                str(self.delta),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly three Pass-2 reviews", result.stderr)

    def test_pass3_packet_derives_delta_from_repository_tags(self):
        commands = [
            ["git", "init", "--quiet"],
            ["git", "config", "user.name", "Critic Test"],
            ["git", "config", "user.email", "critic@example.invalid"],
            ["git", "add", "."],
            ["git", "commit", "--quiet", "-m", "v1"],
            ["git", "tag", "v1"],
        ]
        for command in commands:
            subprocess.run(command, cwd=self.book, check=True)
        (self.book / "ch01.md").write_text(
            "# Arrival\n\nA changed scene with a newly paid consequence.", encoding="utf-8"
        )
        subprocess.run(["git", "add", "ch01.md"], cwd=self.book, check=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "v2"], cwd=self.book, check=True
        )
        subprocess.run(["git", "tag", "v2"], cwd=self.book, check=True)

        result = subprocess.run(
            [
                sys.executable,
                str(CRITICS / "assemble_critic_packet.py"),
                str(self.book),
                "3",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("newly paid consequence", result.stdout)
        self.assertIn("diff --git a/ch01.md b/ch01.md", result.stdout)

    def test_chunked_pass3_is_pass_aware_and_fiction_aware(self):
        prompts = []

        def fake_call(endpoint, model, prompt, timeout=900):
            prompts.append(prompt)
            return "Specific chapter-level critic evidence. " * 30

        with (
            mock.patch.object(run_critics, "call_model", side_effect=fake_call),
            mock.patch.object(run_critics, "_pass3_case_file", return_value="PRIOR PANEL CASE"),
            mock.patch.object(run_critics, "_chapter_delta", return_value="EXACT CHAPTER DELTA"),
            mock.patch.object(run_critics, "_nonchapter_delta", return_value="MANIFEST DELTA"),
        ):
            result = run_critics.chunked_review(
                "http://critic.invalid", "test-model", self.book, pass_no=3
            )

        self.assertEqual(3, len(prompts))
        self.assertIn("This is Pass 3", prompts[0])
        self.assertIn("EXACT CHAPTER DELTA", prompts[0])
        self.assertIn("PRIOR PANEL CASE", prompts[0])
        self.assertIn("MANIFEST DELTA", prompts[1])
        self.assertIn("Pass 3", prompts[2])
        self.assertIn("Continuity-and-consistency audit", prompts[2])
        self.assertEqual("Specific chapter-level critic evidence. " * 30, result)


if __name__ == "__main__":
    unittest.main()
