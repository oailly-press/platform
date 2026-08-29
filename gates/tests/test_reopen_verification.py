from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM / "queue"))
SPEC = importlib.util.spec_from_file_location(
    "oailly_reopen_verification", PLATFORM / "queue" / "reopen_verification.py"
)
reopen = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = reopen
SPEC.loader.exec_module(reopen)


def run(command, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{' '.join(map(str, command))}\n{result.stderr}")
    return result


def git(repo, *args):
    return run(["git", "-C", str(repo), *args])


class ReopenVerificationTests(unittest.TestCase):
    book = "author--reopen-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        work = self.root / "work"
        self.bare = self.root / "publisher.git"
        run(["git", "init", "--quiet", "--initial-branch=main", str(work)])
        git(work, "config", "user.name", "Reopen Fixture")
        git(work, "config", "user.email", "fixture@example.invalid")
        (work / "source.md").write_text("v1\n", encoding="utf-8")
        git(work, "add", ".")
        git(work, "commit", "--quiet", "-m", "v1")
        git(work, "tag", "v1")
        (work / "source.md").write_text("wrong v2\n", encoding="utf-8")
        git(work, "add", ".")
        git(work, "commit", "--quiet", "-m", "v2")
        git(work, "tag", "v2")
        (work / "source.md").write_text("correct v3\n", encoding="utf-8")
        git(work, "add", ".")
        git(work, "commit", "--quiet", "-m", "v3")
        self.sha = git(work, "rev-parse", "HEAD").stdout.strip()
        git(work, "tag", "v3")
        stale = work / "review" / "v2"
        stale.mkdir(parents=True)
        (stale / "verify-A.md").write_text("preserved stale review\n", encoding="utf-8")
        git(work, "add", "review")
        git(work, "commit", "--quiet", "-m", "preserve stale review")
        run(["git", "clone", "--quiet", "--bare", str(work), str(self.bare)])

        self.subs = self.root / "submissions" / "status"
        self.site = self.root / "site" / "status"
        self.subs.mkdir(parents=True)
        self.site.mkdir(parents=True)
        status = {
            "book_id": self.book,
            "state": "4-judge",
            "version_under_review": "v2",
            "reviews_in": 3,
            "history": [],
        }
        for directory in (self.subs, self.site):
            (directory / f"{self.book}.json").write_text(
                json.dumps(status), encoding="utf-8"
            )

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, **overrides):
        arguments = {
            "book": self.book,
            "mirrors": (self.subs, self.site),
            "fork_url": str(self.bare),
            "version": "v3",
            "revision_sha": self.sha,
            "reason": "The earlier panel reviewed a superseded source snapshot.",
            "today": date(2026, 8, 28),
        }
        arguments.update(overrides)
        return reopen.reopen_verification(**arguments)

    def test_dry_run_does_not_change_mirrors(self):
        before = (self.subs / f"{self.book}.json").read_text(encoding="utf-8")
        result = self.call()
        self.assertEqual(result["result"], "dry-run")
        self.assertEqual(before, (self.subs / f"{self.book}.json").read_text(encoding="utf-8"))

    def test_apply_records_exact_corrective_identity_in_both_mirrors(self):
        result = self.call(apply=True)
        self.assertEqual(result["result"], "applied")
        statuses = [
            json.loads((directory / f"{self.book}.json").read_text(encoding="utf-8"))
            for directory in (self.subs, self.site)
        ]
        self.assertEqual(statuses[0], statuses[1])
        self.assertEqual(statuses[0]["state"], "3-verification")
        self.assertEqual(statuses[0]["version_under_review"], "v3")
        self.assertEqual(statuses[0]["revision_sha"], self.sha)
        self.assertTrue(statuses[0]["history"][-1]["correction"])

    def test_wrong_sha_fails_before_status_mutation(self):
        with self.assertRaisesRegex(reopen.StateError, "does not resolve"):
            self.call(revision_sha="0" * 40, apply=True)
        status = json.loads(
            (self.subs / f"{self.book}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["state"], "4-judge")


if __name__ == "__main__":
    unittest.main()
