from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PLATFORM = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("oailly_judge", PLATFORM / "judge.py")
judge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = judge
SPEC.loader.exec_module(judge)


def run(command, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(map(str, command))}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def git(repo, *args):
    return run(["git", "-C", str(repo), *args])


def verification_review(seat: str) -> str:
    return f"""# Verification review {seat}
CRITIC: independent-{seat}
PASS: 3

## Verdict summary
Every prior debt has been tested against the exact revision. **PUBLISH**

## Blocking findings
| # | Location | Problem | Evidence | Severity |
|---|---|---|---|---|
| 1 | backmatter.md | Earlier cast drift | Revised names match the body | med |

## Suggestions
1. Preserve the revised paratext.

## Continuity-and-consistency audit
| Class | Chapters | Claim | Result | Note |
|---|---|---|---|---|
| cast | 1-18 | Names and roles | holds | Checked against scenes. |

## Craft-axis scores
voice: 4 · structure: 4 · stakes: 4 · scene-work: 4 · ending: 4

## Density finding
The revision changes only accountable paratext and introduces no repetitive narrative.

## Pass-3 only: findings ledger
| Finding | Status | Note |
|---|---|---|
| 1 | resolved | The reader-facing record now agrees with the manuscript. |

## Review detail
The critic inspected the declared v1-to-v2 delta, the complete prior panel, the author
response, and the affected passages. The evidence is internally consistent and no prior
blocking finding remains unanswered. Regression sampling found no changed story rule,
narrator boundary, chronology, character identity, or protected ambiguity. This detail
is intentionally complete enough to prove that a filename or one-line verdict cannot
cross the judge boundary without a real verification record.
"""


class JudgePreflightTests(unittest.TestCase):
    book = "author--judge-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fork = self.root / "fork"
        run(["git", "init", "--quiet", "--initial-branch=main", str(self.fork)])
        git(self.fork, "config", "user.name", "Judge Fixture")
        git(self.fork, "config", "user.email", "fixture@example.invalid")
        manifest = {
            "book": {"title": "Judge Fixture", "shelf": "fiction"},
            "provenance": {"written_by": [{"model": "gpt-5"}]},
        }
        (self.fork / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.fork / "pass1-report.json").write_text(
            json.dumps({"verdict": "PASS", "reject_count": 0, "warn_count": 0}),
            encoding="utf-8",
        )
        (self.fork / "ch01.md").write_text("# Chapter 1\n\nStory.\n", encoding="utf-8")
        git(self.fork, "add", ".")
        git(self.fork, "commit", "--quiet", "-m", "v1")
        git(self.fork, "tag", "v1")
        (self.fork / "response-to-findings.md").write_text(
            "# Response\n\n" + "Resolved with exact evidence. " * 20,
            encoding="utf-8",
        )
        git(self.fork, "add", ".")
        git(self.fork, "commit", "--quiet", "-m", "v2")
        git(self.fork, "tag", "v2")
        self.revision_sha = git(self.fork, "rev-parse", "v2^{commit}").stdout.strip()

        review_dir = self.fork / "review" / "v2"
        review_dir.mkdir(parents=True)
        for seat in judge.C.SEATS:
            (review_dir / f"verify-{seat}.md").write_text(
                verification_review(seat), encoding="utf-8"
            )
        (review_dir / "REPORT-CARD.md").write_text(
            "# Final report card\n\n"
            "## Findings ledger\nAll prior findings are resolved with cited evidence.\n\n"
            "## Score deltas\nVoice, structure, stakes, scene-work, and ending remain 4/5.\n\n"
            "## Panel recommendations\nAll seats recommend publication after checking the delta.\n\n"
            + "The card preserves a concise, inspectable account of the final case. " * 5,
            encoding="utf-8",
        )
        (self.fork / "review" / "judge-verdict.md").write_text(
            "# Judge verdict\n\n"
            "JUDGE MODEL: gemini-3-pro + operator\n"
            f"CASE FILE: v2; revision_sha {self.revision_sha}; review/v1 and review/v2; final report card\n\n"
            "## Verdict\n**PUBLISH**\n\n"
            "## Reasoning\n"
            + "The complete case demonstrates that every blocking debt was resolved. " * 7,
            encoding="utf-8",
        )
        git(self.fork, "add", "review")
        git(self.fork, "commit", "--quiet", "-m", "Pass 3 and judge draft")

        self.seats = {
            "book_id": self.book,
            "pass": 3,
            "version": "v2",
            "author_families": ["openai"],
            "seats": {
                "A": {"state": "filled", "family": "anthropic", "verdict": "PUBLISH"},
                "B": {"state": "filled", "family": "muse", "verdict": "PUBLISH"},
                "C": {"state": "filled", "family": "tencent", "verdict": "PUBLISH"},
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, verdict="PUBLISH"):
        return judge.validate_judge_case(
            self.fork,
            self.book,
            self.seats,
            verdict,
            "v2",
            self.revision_sha,
        )

    def test_complete_independent_case_passes_preflight(self):
        self.validate()

    def test_workspace_paths_resolve_without_duplicate_gh_segment(self):
        self.assertEqual(judge.SITE, PLATFORM.parent / "site-repo")
        self.assertEqual(judge.SUBS, PLATFORM.parent / "submissions-repo")

    def test_arbitrary_verdict_cannot_reach_release_train(self):
        with self.assertRaisesRegex(SystemExit, "exactly PUBLISH or REJECT"):
            judge.normalize_verdict("publish-ish")

    def test_missing_verification_file_fails_closed(self):
        (self.fork / "review" / "v2" / "verify-C.md").unlink()
        with self.assertRaisesRegex(SystemExit, "Pass-3 review C is missing"):
            self.validate()

    def test_judge_family_must_differ_from_authors_and_critics(self):
        draft = self.fork / "review" / "judge-verdict.md"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace("gemini-3-pro", "claude-opus-5"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SystemExit, "not independent"):
            self.validate()

    def test_requested_verdict_must_match_judge_model_draft(self):
        with self.assertRaisesRegex(SystemExit, "conflicts with judge-model draft"):
            self.validate("REJECT")

    def test_release_inputs_fail_before_signature_when_cover_is_missing(self):
        site = self.root / "site"
        subs = self.root / "submissions"
        buildpy = self.root / "build-python"
        (site / "status").mkdir(parents=True)
        (subs / "status").mkdir(parents=True)
        (site / "assets" / "covers").mkdir(parents=True)
        buildpy.write_text("executable fixture\n", encoding="utf-8")
        status = json.dumps(
            {
                "book_id": self.book,
                "state": "4-judge",
                "version_under_review": "v2",
                "revision_sha": self.revision_sha,
            }
        )
        (site / "status" / f"{self.book}.json").write_text(status, encoding="utf-8")
        (subs / "status" / f"{self.book}.json").write_text(status, encoding="utf-8")
        (site / "catalog.json").write_text(
            json.dumps({"books": [{"id": self.book}]}), encoding="utf-8"
        )

        with (
            mock.patch.object(judge, "SITE", site),
            mock.patch.object(judge, "SUBS", subs),
            mock.patch.object(judge, "BUILDPY", buildpy),
        ):
            with self.assertRaisesRegex(SystemExit, "front cover is missing"):
                judge.validate_release_inputs(self.book, "v2", self.revision_sha)
            (site / "assets" / "covers" / f"{self.book}-front.png").write_bytes(b"x" * 101)
            (site / "assets" / "covers" / f"{self.book}-back.png").write_bytes(b"x" * 101)
            judge.validate_release_inputs(self.book, "v2", self.revision_sha)
            (subs / "status" / f"{self.book}.json").write_text(
                json.dumps({"book_id": self.book, "state": "3-verification"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "must identify.*at 4-judge"):
                judge.validate_release_inputs(self.book, "v2", self.revision_sha)

    def test_selected_tag_must_match_declared_sha(self):
        with self.assertRaisesRegex(SystemExit, "not declared revision_sha"):
            judge.validate_judge_case(
                self.fork, self.book, self.seats, "PUBLISH", "v2", "0" * 40
            )

    def test_disposable_release_runs_build_render_and_verifier(self):
        calls = []

        def fake_sh(command, cwd=None, check=True):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "verified", "")

        with mock.patch.object(judge, "sh", side_effect=fake_sh):
            message = judge.preflight_release_artifacts(self.fork, self.book, "#123456")

        self.assertEqual(3, len(calls))
        self.assertIn("--cover", calls[0])
        self.assertIn(judge.source_repo_url(self.book), calls[1])
        self.assertIn("verify_rendered_book.py", calls[2][1])
        self.assertIn("verified", message)

    def test_source_repository_url_uses_press_organization(self):
        self.assertEqual(
            judge.source_repo_url(self.book),
            "https://github.com/oailly-press/judge-fixture",
        )


if __name__ == "__main__":
    unittest.main()
