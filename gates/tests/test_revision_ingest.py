import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_revision", ROOT / "queue" / "prepare_revision.py"
)
prepare_revision = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = prepare_revision
SPEC.loader.exec_module(prepare_revision)


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(map(str, command))}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", str(repo), *args], check=check)


class RevisionPreparationTests(unittest.TestCase):
    book_id = "author--revision-fixture"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.author = self.root / "author"
        self.publisher_work = self.root / "publisher-work"
        self.publisher_bare = self.root / "publisher.git"
        self.status_file = self.root / "status.json"
        self.gate_script = self.root / "fake_gate.py"

        run(["git", "init", "--quiet", "--initial-branch=main", str(self.author)])
        self.configure_git(self.author)
        (self.author / "manifest.json").write_text(
            json.dumps({"book_id": self.book_id}) + "\n", encoding="utf-8"
        )
        (self.author / "backmatter.md").write_text(
            "# Back matter\n\nOriginal edition.\n", encoding="utf-8"
        )
        git(self.author, "add", ".")
        git(self.author, "commit", "--quiet", "-m", "submission v1")
        git(self.author, "tag", "-a", "v1", "-m", "submission v1")

        run(["git", "clone", "--quiet", str(self.author), str(self.publisher_work)])
        self.configure_git(self.publisher_work)
        reviews = self.publisher_work / "review" / "v1"
        reviews.mkdir(parents=True)
        for seat in "ABC":
            (reviews / f"critic-{seat}.md").write_text(
                f"# Independent critic {seat}\n\nVerdict: SALVAGEABLE\n",
                encoding="utf-8",
            )
        git(self.publisher_work, "add", "review")
        git(self.publisher_work, "commit", "--quiet", "-m", "record Pass-2 panel")
        run(["git", "clone", "--quiet", "--bare", str(self.publisher_work), str(self.publisher_bare)])

        (self.author / "backmatter.md").write_text(
            "# Back matter\n\nReconciled revision.\n", encoding="utf-8"
        )
        response = (
            "# Response to findings\n\n"
            "The revision addresses every panel finding with an exact chapter-level "
            "account of the changed evidence, while retaining disputed passages when "
            "the criticism depended on a mistaken speaker attribution. This fixture "
            "is deliberately substantive so the ingestion boundary cannot be crossed "
            "with an empty acknowledgment or a ceremonial filename.\n"
        )
        (self.author / "response-to-findings.md").write_text(response, encoding="utf-8")
        git(self.author, "add", ".")
        git(self.author, "commit", "--quiet", "-m", "author revision")
        self.revision_sha = git(self.author, "rev-parse", "HEAD").stdout.strip()

        self.status_file.write_text(
            json.dumps(
                {
                    "book_id": self.book_id,
                    "version_under_review": "v1",
                    "state": "2-revision",
                    "action_required": "revise",
                }
            ),
            encoding="utf-8",
        )
        self.gate_script.write_text(
            """import json
import sys
from pathlib import Path

report = {
    "verdict": "PASS",
    "reject_count": 0,
    "warn_count": 0,
    "measured": {"body_words_measured": 60263},
}
Path(sys.argv[1], "pass1-report.json").write_text(json.dumps(report), encoding="utf-8")
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def configure_git(repo):
        git(repo, "config", "user.name", "Revision Fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")

    def prepare(self, *, apply=False, sha=None):
        return prepare_revision.prepare_revision(
            book_id=self.book_id,
            author_url=str(self.author),
            fork_url=str(self.publisher_bare),
            sha=sha or self.revision_sha,
            status_file=self.status_file,
            gate_script=self.gate_script,
            apply=apply,
        )

    def test_dry_run_validates_without_mutating_publisher_remote(self):
        before = git(self.publisher_bare, "rev-parse", "refs/heads/main").stdout.strip()

        result = self.prepare()

        self.assertEqual(result["result"], "dry-run-pass")
        self.assertEqual(result["v2"], self.revision_sha)
        self.assertEqual(result["pass2_reviews_preserved"], 3)
        self.assertEqual(
            git(self.publisher_bare, "rev-parse", "refs/heads/main").stdout.strip(), before
        )
        self.assertNotEqual(
            git(self.publisher_bare, "rev-parse", "--verify", "refs/tags/v2", check=False).returncode,
            0,
        )

    def test_apply_pushes_author_snapshot_as_v2_and_preserves_review_trail(self):
        result = self.prepare(apply=True)
        inspect = self.root / "inspect"
        run(["git", "clone", "--quiet", str(self.publisher_bare), str(inspect)])

        self.assertEqual(result["result"], "pushed")
        self.assertEqual(git(inspect, "rev-parse", "v2^{commit}").stdout.strip(), self.revision_sha)
        self.assertEqual(
            git(inspect, "show", "HEAD:backmatter.md").stdout,
            git(self.author, "show", f"{self.revision_sha}:backmatter.md").stdout,
        )
        for seat in "ABC":
            self.assertEqual(
                git(inspect, "cat-file", "-t", f"HEAD:review/v1/critic-{seat}.md").stdout.strip(),
                "blob",
            )
        changed_to_v2 = git(inspect, "diff", "--name-only", "v1..v2").stdout.splitlines()
        self.assertFalse(any(path.startswith("review/") for path in changed_to_v2))
        self.assertEqual(
            prepare_revision.tree_without_reviews(inspect, "HEAD"),
            prepare_revision.tree_without_reviews(inspect, self.revision_sha),
        )

        repeated = self.prepare(apply=True)
        self.assertEqual(repeated["result"], "already-prepared")
        self.assertEqual(repeated["pass2_reviews_preserved"], 3)

    def test_status_locator_supports_canonical_and_mirror_layouts(self):
        canonical_platform = self.root / "canonical" / "platform"
        canonical_platform.mkdir(parents=True)
        canonical_status = self.root / "canonical" / "gh" / "submissions-repo" / "status"
        canonical_status.mkdir(parents=True)
        self.assertEqual(
            prepare_revision.find_status_dir(canonical_platform), canonical_status
        )

        mirror_platform = self.root / "mirror" / "platform-repo"
        mirror_platform.mkdir(parents=True)
        mirror_status = self.root / "mirror" / "submissions-repo" / "status"
        mirror_status.mkdir(parents=True)
        self.assertEqual(prepare_revision.find_status_dir(mirror_platform), mirror_status)

    def test_rejects_author_attempt_to_modify_publisher_review_namespace(self):
        forbidden = self.author / "review" / "v1"
        forbidden.mkdir(parents=True)
        (forbidden / "critic-A.md").write_text("replacement\n", encoding="utf-8")
        git(self.author, "add", "review")
        git(self.author, "commit", "--quiet", "-m", "tamper with review")
        tampered_sha = git(self.author, "rev-parse", "HEAD").stdout.strip()

        with self.assertRaisesRegex(prepare_revision.RevisionError, "may not modify"):
            self.prepare(sha=tampered_sha)

    def test_rejects_any_status_outside_declared_revision_state(self):
        self.status_file.write_text(
            json.dumps(
                {
                    "book_id": self.book_id,
                    "version_under_review": "v1",
                    "state": "3-verification",
                    "action_required": "verify",
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(prepare_revision.RevisionError, "must be 2-revision"):
            self.prepare()

    def test_rejects_publisher_source_drift_during_panel_review(self):
        (self.publisher_work / "manifest.json").write_text(
            json.dumps({"book_id": self.book_id, "publisher_edit": True}) + "\n",
            encoding="utf-8",
        )
        git(self.publisher_work, "add", "manifest.json")
        git(self.publisher_work, "commit", "--quiet", "-m", "improper publisher edit")
        git(
            self.publisher_work,
            "push",
            "--quiet",
            str(self.publisher_bare),
            "HEAD:refs/heads/main",
        )

        with self.assertRaisesRegex(prepare_revision.RevisionError, "changed the v1 source"):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
