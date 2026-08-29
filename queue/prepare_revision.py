#!/usr/bin/env python3
"""Validate and prepare an author's declared revision for Pass 3.

The command is fail-closed and dry-run by default. It clones the publisher fork into a
temporary directory, fetches one exact author SHA, verifies that it descends from ``v1``,
rejects author changes under ``review/``, requires ``response-to-findings.md``, reruns
Pass 1 on the author snapshot, and performs a trial merge that must preserve the complete
Pass-2 trail. Only ``--apply`` atomically pushes the merge and an immutable ``v2`` tag.

    python3 queue/prepare_revision.py ACCOUNT--BOOK \
      --author-repo OWNER/REPO --sha 40_HEX_SHA

    # After inspecting the dry-run JSON:
    python3 queue/prepare_revision.py ACCOUNT--BOOK \
      --author-repo OWNER/REPO --sha 40_HEX_SHA --apply

Status transition and critic-seat seeding remain explicit publisher actions after the
atomic push succeeds; this command never edits the submissions repository.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLATFORM = HERE.parent
SAFE_BID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")


class RevisionError(RuntimeError):
    pass


def find_status_dir(platform: Path = PLATFORM) -> Path:
    """Locate submissions status from either canonical or editable-mirror layouts."""
    candidates = (
        platform.parent / "submissions-repo" / "status",
        platform.parent / "gh" / "submissions-repo" / "status",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])


DEFAULT_STATUS_DIR = find_status_dir()


def run(
    command: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        raise RevisionError(f"cannot execute {command[0]}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:600]
        raise RevisionError(f"{' '.join(command)} failed: {detail}")
    return result


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(repo), *args], check=check)


def require_revision_state(status_file: Path, book_id: str) -> dict:
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionError(f"cannot read publisher status {status_file}: {exc}") from exc
    if status.get("book_id") != book_id:
        raise RevisionError("status book_id does not match requested book")
    if status.get("state") != "2-revision" or status.get("action_required") != "revise":
        raise RevisionError(
            f"publisher state must be 2-revision/action_required=revise; got "
            f"{status.get('state')!r}/{status.get('action_required')!r}"
        )
    if status.get("version_under_review") != "v1":
        raise RevisionError("publisher status must identify v1 as the version under review")
    return status


def tree_without_reviews(repo: Path, revision: str) -> list[str]:
    listing = git(repo, "ls-tree", "-r", "--full-tree", revision).stdout.splitlines()
    return sorted(line for line in listing if "\treview/" not in line)


def prepare_revision(
    *,
    book_id: str,
    author_url: str,
    fork_url: str,
    sha: str,
    status_file: Path,
    gate_script: Path,
    apply: bool,
) -> dict:
    if not SAFE_BID.fullmatch(book_id):
        raise RevisionError("invalid book-id (expected account--book slug)")
    if not SAFE_SHA.fullmatch(sha):
        raise RevisionError("revision SHA must be exactly 40 lowercase hexadecimal characters")
    require_revision_state(status_file, book_id)

    with tempfile.TemporaryDirectory(prefix="oailly-revision-") as temp_name:
        temp = Path(temp_name)
        fork = temp / "fork"
        candidate = temp / "candidate"
        run(["git", "clone", "--quiet", "--", fork_url, str(fork)])

        critic_files = sorted(
            path for path in (fork / "review" / "v1").glob("critic-*.md") if path.is_file()
        )
        if len(critic_files) != 3:
            raise RevisionError(
                f"publisher fork must contain exactly three Pass-2 reviews; found {len(critic_files)}"
            )
        if git(fork, "rev-parse", "--verify", "v1^{commit}", check=False).returncode != 0:
            raise RevisionError("publisher fork has no resolvable v1 tag")
        if git(fork, "merge-base", "--is-ancestor", "v1", "HEAD", check=False).returncode != 0:
            raise RevisionError("publisher main does not descend from its v1 tag")
        existing_v2 = git(fork, "rev-parse", "--verify", "v2^{commit}", check=False)
        if (
            existing_v2.returncode != 0
            and tree_without_reviews(fork, "v1") != tree_without_reviews(fork, "HEAD")
        ):
            raise RevisionError("publisher changed the v1 source outside review/")

        git(fork, "fetch", "--quiet", "--no-tags", "--", author_url, sha)
        fetched = git(fork, "rev-parse", "FETCH_HEAD^{commit}").stdout.strip()
        if fetched != sha:
            raise RevisionError(f"fetched commit {fetched} does not match declared SHA {sha}")
        if git(fork, "merge-base", "--is-ancestor", "v1", sha, check=False).returncode != 0:
            raise RevisionError("declared revision is not an append-only descendant of v1")

        changed = [
            line for line in git(fork, "diff", "--name-only", f"v1..{sha}").stdout.splitlines()
            if line
        ]
        if not changed:
            raise RevisionError("revision has no changes relative to v1")
        forbidden = [path for path in changed if path == "review" or path.startswith("review/")]
        if forbidden:
            raise RevisionError(
                "authors may not modify the publisher review trail: " + ", ".join(forbidden)
            )
        if "response-to-findings.md" not in changed:
            raise RevisionError("revision must add or modify response-to-findings.md")
        response = git(fork, "show", f"{sha}:response-to-findings.md", check=False)
        if response.returncode != 0 or len(response.stdout.strip()) < 200:
            raise RevisionError("revision must contain a substantive response-to-findings.md")

        git(fork, "worktree", "add", "--quiet", "--detach", str(candidate), sha)
        gate = run([sys.executable, str(gate_script), str(candidate)], check=False)
        report_file = candidate / "pass1-report.json"
        if gate.returncode != 0 or not report_file.is_file():
            detail = (gate.stdout + "\n" + gate.stderr).strip()[-800:]
            raise RevisionError(f"revision fails Pass 1: {detail}")
        try:
            report = json.loads(report_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RevisionError(f"Pass-1 report is invalid JSON: {exc}") from exc
        if report.get("verdict") != "PASS" or report.get("reject_count") != 0:
            raise RevisionError("Pass-1 report does not record a clean PASS")

        if existing_v2.returncode == 0:
            tagged = existing_v2.stdout.strip()
            if tagged != sha:
                raise RevisionError(f"v2 already points to a different commit: {tagged}")
            if git(fork, "merge-base", "--is-ancestor", sha, "HEAD", check=False).returncode != 0:
                raise RevisionError("v2 exists, but publisher main does not contain that revision")
            if tree_without_reviews(fork, sha) != tree_without_reviews(fork, "HEAD"):
                raise RevisionError("v2 exists, but publisher main differs outside review/")
            return {
                "book_id": book_id,
                "sha": sha,
                "revision_sha": sha,
                "result": "already-prepared",
                "v2": tagged,
                "gate": "PASS",
                "pass2_reviews_preserved": 3,
                "changed_paths": changed,
            }

        git(fork, "config", "user.name", "oailly revision operator")
        git(fork, "config", "user.email", "revision@oailly.invalid")
        merge = git(fork, "merge", "--no-ff", "--no-edit", sha, check=False)
        if merge.returncode != 0:
            git(fork, "merge", "--abort", check=False)
            detail = (merge.stderr or merge.stdout).strip()[:600]
            raise RevisionError(f"revision does not merge cleanly with the Pass-2 trail: {detail}")
        if tree_without_reviews(fork, sha) != tree_without_reviews(fork, "HEAD"):
            raise RevisionError("trial merge changed the author snapshot outside review/")
        if len(list((fork / "review" / "v1").glob("critic-*.md"))) != 3:
            raise RevisionError("trial merge did not preserve the complete Pass-2 panel")

        git(fork, "tag", "-a", "v2", sha, "-m", f"Pass-3 revision for {book_id}")
        merge_sha = git(fork, "rev-parse", "HEAD^{commit}").stdout.strip()
        if apply:
            git(
                fork,
                "push",
                "--atomic",
                "origin",
                f"{merge_sha}:refs/heads/main",
                "refs/tags/v2:refs/tags/v2",
            )

        return {
            "book_id": book_id,
            "sha": sha,
            "revision_sha": sha,
            "result": "pushed" if apply else "dry-run-pass",
            "v2": sha,
            "publisher_merge": merge_sha,
            "gate": "PASS",
            "reject_count": report.get("reject_count"),
            "warn_count": report.get("warn_count"),
            "body_words": report.get("measured", {}).get("body_words_measured"),
            "pass2_reviews_preserved": 3,
            "changed_paths": changed,
            "next_action": (
                "set status to 3-verification with --version v2 and this exact "
                "--revision-sha, then seed/open Pass-3 critic seats"
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--sha", required=True)
    author = parser.add_mutually_exclusive_group(required=True)
    author.add_argument("--author-repo", help="GitHub OWNER/REPO")
    author.add_argument("--author-url", help="explicit Git URL/path (primarily for testing)")
    parser.add_argument("--fork-url", help="publisher fork URL; defaults from book-id")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--gate-script", type=Path, default=PLATFORM / "gates" / "pass1.py")
    parser.add_argument("--apply", action="store_true", help="atomically push main and v2")
    args = parser.parse_args()

    if args.author_repo and not SAFE_REPO.fullmatch(args.author_repo):
        parser.error("--author-repo must be OWNER/REPO")
    if not SAFE_BID.fullmatch(args.book_id):
        parser.error("book_id must be account--book slug")
    repo_slug = args.book_id.split("--", 1)[1]
    author_url = args.author_url or f"git@github.com:{args.author_repo}.git"
    fork_url = args.fork_url or f"git@github.com:oailly-press/{repo_slug}.git"
    status_file = args.status_file or DEFAULT_STATUS_DIR / f"{args.book_id}.json"
    try:
        result = prepare_revision(
            book_id=args.book_id,
            author_url=author_url,
            fork_url=fork_url,
            sha=args.sha,
            status_file=status_file,
            gate_script=args.gate_script,
            apply=args.apply,
        )
    except RevisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
