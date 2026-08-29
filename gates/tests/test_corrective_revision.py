from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLATFORM / "queue"))
SPEC = importlib.util.spec_from_file_location(
    "oailly_prepare_corrective_revision",
    PLATFORM / "queue" / "prepare_corrective_revision.py",
)
corrective = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = corrective
SPEC.loader.exec_module(corrective)


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode:
        raise AssertionError(
            f"command failed: {' '.join(map(str, command))}\n{result.stdout}\n{result.stderr}"
        )
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", str(repo), *args], check=check)


class CorrectiveRevisionTests(unittest.TestCase):
    book = "author--correction-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.author = self.root / "author"
        self.publisher = self.root / "publisher"
        self.bare = self.root / "publisher.git"
        self.status = self.root / "status.json"
        self.gate = self.root / "gate.py"
        run(["git", "init", "--quiet", "--initial-branch=main", str(self.author)])
        self.configure(self.author)
        (self.author / "manifest.json").write_text(
            json.dumps({"book_id": self.book}), encoding="utf-8"
        )
        (self.author / "backmatter.md").write_text("# Back matter\n\nv1\n", encoding="utf-8")
        git(self.author, "add", ".")
        git(self.author, "commit", "--quiet", "-m", "v1")
        git(self.author, "tag", "v1")
        (self.author / "response-to-findings.md").write_text(
            "# Response\n\n" + "Exact evidence resolves every recorded finding. " * 12,
            encoding="utf-8",
        )
        (self.author / "backmatter.md").write_text("# Back matter\n\nwrong v2\n", encoding="utf-8")
        git(self.author, "add", ".")
        git(self.author, "commit", "--quiet", "-m", "wrong reviewed source")
        wrong_sha = git(self.author, "rev-parse", "HEAD").stdout.strip()

        run(["git", "clone", "--quiet", str(self.author), str(self.publisher)])
        self.configure(self.publisher)
        git(self.publisher, "tag", "v2", wrong_sha)
        reviews = self.publisher / "review" / "v2"
        reviews.mkdir(parents=True)
        for seat in "ABC":
            (reviews / f"verify-{seat}.md").write_text(
                f"# stale verification {seat}\n", encoding="utf-8"
            )
        git(self.publisher, "add", "review")
        git(self.publisher, "commit", "--quiet", "-m", "stale Pass 3")
        run(["git", "clone", "--quiet", "--bare", str(self.publisher), str(self.bare)])

        (self.author / "backmatter.md").write_text(
            "# Back matter\n\nexact corrective source\n", encoding="utf-8"
        )
        git(self.author, "add", "backmatter.md")
        git(self.author, "commit", "--quiet", "-m", "exact author correction")
        self.sha = git(self.author, "rev-parse", "HEAD").stdout.strip()
        self.status.write_text(
            json.dumps(
                {
                    "book_id": self.book,
                    "state": "4-judge",
                    "version_under_review": "v2",
                }
            ),
            encoding="utf-8",
        )
        self.gate.write_text(
            "import json,sys\nfrom pathlib import Path\n"
            "Path(sys.argv[1], 'pass1-report.json').write_text(json.dumps("
            "{'verdict':'PASS','reject_count':0,'warn_count':0}))\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def configure(repo):
        git(repo, "config", "user.name", "Correction Fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")

    def prepare(self, apply=False, version="v3"):
        return corrective.prepare_corrective_revision(
            book_id=self.book,
            author_url=str(self.author),
            fork_url=str(self.bare),
            sha=self.sha,
            version=version,
            status_file=self.status,
            gate_script=self.gate,
            apply=apply,
        )

    def test_apply_preserves_v2_and_reviews_while_tagging_exact_v3(self):
        result = self.prepare(apply=True)
        inspect = self.root / "inspect"
        run(["git", "clone", "--quiet", str(self.bare), str(inspect)])
        self.assertEqual(result["result"], "pushed")
        self.assertEqual(git(inspect, "rev-parse", "v3^{commit}").stdout.strip(), self.sha)
        self.assertEqual(git(inspect, "cat-file", "-t", "v2^{commit}").stdout.strip(), "commit")
        for seat in "ABC":
            self.assertEqual(
                git(inspect, "cat-file", "-t", f"HEAD:review/v2/verify-{seat}.md").stdout.strip(),
                "blob",
            )
        self.assertEqual(
            corrective.tree_without_reviews(inspect, "HEAD"),
            corrective.tree_without_reviews(inspect, self.sha),
        )

    def test_correction_must_use_next_version(self):
        with self.assertRaisesRegex(corrective.RevisionError, "exactly one greater"):
            self.prepare(version="v4")


if __name__ == "__main__":
    unittest.main()
