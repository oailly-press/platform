from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "oailly_prepare_judge_case", PLATFORM / "queue" / "prepare_judge_case.py"
)
case_prep = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = case_prep
SPEC.loader.exec_module(case_prep)


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(map(str, command))}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", str(repo), *args], check=check)


def review_text(pass_no: int, seat: str) -> str:
    verdict = "SALVAGEABLE" if pass_no == 2 else "PUBLISH"
    ledger = "" if pass_no == 2 else """
## Pass-3 only: findings ledger
| Finding | Status | Note |
|---|---|---|
| 1 | resolved | Revised paratext matches the body and preserves ambiguity. |
"""
    return f"""# Fiction review {seat}
CRITIC: independent-{seat}
PASS: {pass_no}

## Verdict summary
The complete evidence was checked against the manuscript and its declared scope.
The case is coherent and the response addresses the recorded debt. **{verdict}**

## Blocking findings
| # | Location | Problem | Evidence | Severity |
|---|---|---|---|---|
| 1 | backmatter.md | Earlier cast drift | Current names agree with the scenes | med |

## Suggestions
1. Preserve the exact evidence trail through publication.

## Continuity-and-consistency audit
| Class | Chapters | Claim | Result | Note |
|---|---|---|---|---|
| cast | 1-18 | Identities and roles | holds | Checked against scene evidence. |

## Craft-axis scores
voice: 4 · structure: 4 · stakes: 4 · scene-work: 4 · ending: 4

## Density finding
The revision is bounded, purposeful, and introduces no explanatory or narrative loop.
{ledger}
## Review detail
The critic inspected the full case file, the relevant manuscript passages, and the
declared evidence rather than relying on the author's summary. Timeline, narrator access,
world rules, character identities, and protected ambiguity were sampled independently.
The review records enough location-level reasoning for the judge to audit its conclusion
without trusting a bare vote. This deliberately substantive fixture prevents a filename,
placeholder, or ceremonial verdict from satisfying the report-card boundary.
"""


class JudgeCasePreparationTests(unittest.TestCase):
    book = "author--case-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "publisher-work"
        self.bare = self.root / "publisher.git"
        self.status = self.root / "status.json"
        run(["git", "init", "--quiet", "--initial-branch=main", str(self.work)])
        git(self.work, "config", "user.name", "Case Fixture")
        git(self.work, "config", "user.email", "fixture@example.invalid")
        manifest = {
            "book": {"title": "Case Fixture", "shelf": "fiction"},
            "provenance": {"written_by": [{"model": "gpt-5"}]},
        }
        (self.work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.work / "pass1-report.json").write_text(
            json.dumps({"verdict": "PASS", "reject_count": 0, "warn_count": 0}),
            encoding="utf-8",
        )
        (self.work / "backmatter.md").write_text("# Back matter\n\nOld cast.\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "--quiet", "-m", "v1 source")
        git(self.work, "tag", "v1")

        git(self.work, "switch", "--quiet", "-c", "author-v2")
        (self.work / "backmatter.md").write_text(
            "# Back matter\n\nCorrected cast.\n", encoding="utf-8"
        )
        (self.work / "response-to-findings.md").write_text(
            "# Response to findings\n\n" + "Resolved with exact scene evidence. " * 20,
            encoding="utf-8",
        )
        git(self.work, "add", ".")
        git(self.work, "commit", "--quiet", "-m", "v2 author revision")
        git(self.work, "tag", "v2")
        git(self.work, "switch", "--quiet", "main")

        pass2_dir = self.work / "review" / "v1"
        pass2_dir.mkdir(parents=True)
        pass2_seats = self.seats(2, "v1", "SALVAGEABLE")
        (pass2_dir / "SEATS.json").write_text(json.dumps(pass2_seats), encoding="utf-8")
        for seat in case_prep.C.SEATS:
            (pass2_dir / f"critic-{seat}.md").write_text(
                review_text(2, seat), encoding="utf-8"
            )
        git(self.work, "add", "review")
        git(self.work, "commit", "--quiet", "-m", "Pass 2 panel")
        git(self.work, "merge", "--quiet", "--no-ff", "v2", "-m", "merge v2")

        pass3_dir = self.work / "review" / "v2"
        pass3_dir.mkdir(parents=True)
        pass3_seats = self.seats(3, "v2", "PUBLISH")
        (pass3_dir / "SEATS.json").write_text(json.dumps(pass3_seats), encoding="utf-8")
        for seat in case_prep.C.SEATS:
            (pass3_dir / f"verify-{seat}.md").write_text(
                review_text(3, seat), encoding="utf-8"
            )
        git(self.work, "add", "review/v2")
        git(self.work, "commit", "--quiet", "-m", "Pass 3 panel")
        run(["git", "clone", "--quiet", "--bare", str(self.work), str(self.bare)])

        self.status.write_text(
            json.dumps(
                {
                    "book_id": self.book,
                    "version_under_review": "v2",
                    "state": "3-verification",
                    "action_required": None,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def seats(self, pass_no, version, verdict):
        families = {"A": "anthropic", "B": "muse", "C": "tencent"}
        return {
            "book_id": self.book,
            "pass": pass_no,
            "version": version,
            "author_families": ["openai"],
            "seats": {
                seat: {"state": "filled", "family": family, "verdict": verdict}
                for seat, family in families.items()
            },
        }

    def prepare(self, apply=False):
        return case_prep.prepare_judge_case(
            book_id=self.book,
            fork_url=str(self.bare),
            status_file=self.status,
            apply=apply,
        )

    def test_dry_run_builds_card_without_mutating_remote(self):
        before = git(self.bare, "rev-parse", "refs/heads/main").stdout.strip()
        result = self.prepare()
        self.assertEqual(result["result"], "dry-run-pass")
        self.assertEqual(result["pass3_reviews"], 3)
        self.assertEqual(before, git(self.bare, "rev-parse", "refs/heads/main").stdout.strip())
        self.assertNotEqual(
            git(
                self.bare,
                "cat-file",
                "-e",
                "main:review/v2/REPORT-CARD.md",
                check=False,
            ).returncode,
            0,
        )

    def test_apply_pushes_a_fingerprinted_complete_report_card(self):
        result = self.prepare(apply=True)
        card = git(self.bare, "show", "main:review/v2/REPORT-CARD.md").stdout
        self.assertEqual(result["result"], "pushed")
        self.assertIn("## Evidence fingerprints", card)
        self.assertIn("## Seat A", card)
        self.assertIn("### Findings ledger", card)
        self.assertIn("### Score evidence (Pass 2 → Pass 3)", card)
        self.assertIn("Pass 2:", card)
        self.assertIn("Pass 3:", card)
        self.assertIn("Mechanical tally", card)
        self.assertEqual(result["report_card_sha256"], case_prep._digest(card))
        repeated = self.prepare(apply=True)
        self.assertEqual(repeated["result"], "already-prepared")

    def test_duplicate_family_panel_is_rejected(self):
        seats_path = self.work / "review" / "v2" / "SEATS.json"
        seats = json.loads(seats_path.read_text(encoding="utf-8"))
        seats["seats"]["C"]["family"] = "muse"
        seats_path.write_text(json.dumps(seats), encoding="utf-8")
        git(self.work, "add", str(seats_path.relative_to(self.work)))
        git(self.work, "commit", "--quiet", "-m", "invalid duplicate family")
        git(self.work, "push", "--quiet", str(self.bare), "HEAD:refs/heads/main")
        with self.assertRaisesRegex(case_prep.RevisionError, "three distinct families"):
            self.prepare()

    def test_legacy_pass2_files_are_reconstructed_without_weakening_checks(self):
        seats_path = self.work / "review" / "v1" / "SEATS.json"
        seats_path.unlink()
        git(self.work, "add", str(seats_path.relative_to(self.work)))
        git(self.work, "commit", "--quiet", "-m", "legacy Pass 2 without seats file")
        git(self.work, "push", "--quiet", str(self.bare), "HEAD:refs/heads/main")
        result = self.prepare()
        self.assertEqual(result["result"], "dry-run-pass")

    def test_existing_different_report_card_is_never_overwritten(self):
        card = self.work / "review" / "v2" / "REPORT-CARD.md"
        card.write_text("# Hand-edited card\n", encoding="utf-8")
        git(self.work, "add", str(card.relative_to(self.work)))
        git(self.work, "commit", "--quiet", "-m", "conflicting card")
        git(self.work, "push", "--quiet", str(self.bare), "HEAD:refs/heads/main")
        with self.assertRaisesRegex(case_prep.RevisionError, "refusing to overwrite"):
            self.prepare(apply=True)


if __name__ == "__main__":
    unittest.main()
