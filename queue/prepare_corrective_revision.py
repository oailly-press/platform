#!/usr/bin/env python3
"""Prepare an exact corrective revision without rewriting prior tags or review evidence.

Use this only when a case reached ``4-judge`` on the wrong source snapshot. The command
is dry-run by default. It requires the next numeric version, fetches the exact declared
author commit, reruns Pass 1, trial-merges it while preserving every existing review,
and creates a new immutable tag at the author commit. It never edits status or publishes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from prepare_revision import (
    DEFAULT_STATUS_DIR,
    PLATFORM,
    SAFE_BID,
    SAFE_REPO,
    SAFE_SHA,
    RevisionError,
    git,
    run,
    tree_without_reviews,
)


SAFE_VERSION = re.compile(r"^v([1-9][0-9]*)$")


def indexed_git(repo: Path, index: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index)
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:600]
        raise RevisionError(f"git {' '.join(args)} failed: {detail}")
    return result


def require_correction_state(status_file: Path, book_id: str, version: str) -> dict:
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionError(f"cannot read publisher status {status_file}: {exc}") from exc
    if status.get("book_id") != book_id or status.get("state") != "4-judge":
        raise RevisionError("corrective ingest requires this book to be at 4-judge")
    current = SAFE_VERSION.fullmatch(status.get("version_under_review", ""))
    requested = SAFE_VERSION.fullmatch(version)
    if not current or not requested or int(requested.group(1)) != int(current.group(1)) + 1:
        raise RevisionError("corrective version must be exactly one greater than the reviewed version")
    return status


def prepare_corrective_revision(
    *,
    book_id: str,
    author_url: str,
    fork_url: str,
    sha: str,
    version: str,
    status_file: Path,
    gate_script: Path,
    apply: bool,
) -> dict:
    if not SAFE_BID.fullmatch(book_id):
        raise RevisionError("invalid book-id (expected account--book slug)")
    if not SAFE_SHA.fullmatch(sha):
        raise RevisionError("revision SHA must be exactly 40 lowercase hexadecimal characters")
    status = require_correction_state(status_file, book_id, version)
    prior_version = status["version_under_review"]

    with tempfile.TemporaryDirectory(prefix="oailly-corrective-revision-") as temp_name:
        temp = Path(temp_name)
        fork = temp / "fork"
        candidate = temp / "candidate"
        run(["git", "clone", "--quiet", "--", fork_url, str(fork)])

        for tag in ("v1", prior_version):
            if git(fork, "rev-parse", "--verify", f"{tag}^{{commit}}", check=False).returncode:
                raise RevisionError(f"publisher fork has no resolvable {tag} tag")
        if git(
            fork, "merge-base", "--is-ancestor", prior_version, "HEAD", check=False
        ).returncode:
            raise RevisionError(f"publisher main does not preserve prior tag {prior_version}")
        prior_tag_sha = git(fork, "rev-parse", f"{prior_version}^{{commit}}").stdout.strip()
        review_tree_before = git(fork, "rev-parse", "HEAD:review", check=False).stdout.strip()
        if not review_tree_before:
            raise RevisionError("publisher fork has no review trail to preserve")

        existing = git(fork, "rev-parse", "--verify", f"{version}^{{commit}}", check=False)
        if existing.returncode == 0 and existing.stdout.strip() != sha:
            raise RevisionError(f"{version} already points to a different commit")

        git(fork, "fetch", "--quiet", "--no-tags", "--", author_url, sha)
        fetched = git(fork, "rev-parse", "FETCH_HEAD^{commit}").stdout.strip()
        if fetched != sha:
            raise RevisionError(f"fetched commit {fetched} does not match declared SHA {sha}")
        if git(fork, "merge-base", "--is-ancestor", "v1", sha, check=False).returncode:
            raise RevisionError("declared correction is not an append-only descendant of v1")
        forbidden = [
            path
            for path in git(fork, "diff", "--name-only", f"v1..{sha}").stdout.splitlines()
            if path == "review" or path.startswith("review/")
        ]
        if forbidden:
            raise RevisionError("author correction modifies the publisher review trail")
        if git(fork, "cat-file", "-e", f"{sha}:review", check=False).returncode == 0:
            raise RevisionError("author correction contains a reserved review/ namespace")
        response = git(fork, "show", f"{sha}:response-to-findings.md", check=False)
        if response.returncode or len(response.stdout.strip()) < 200:
            raise RevisionError("correction lacks a substantive response-to-findings.md")

        git(fork, "worktree", "add", "--quiet", "--detach", str(candidate), sha)
        gate = run([sys.executable, str(gate_script), str(candidate)], check=False)
        report_file = candidate / "pass1-report.json"
        if gate.returncode or not report_file.is_file():
            detail = (gate.stdout + "\n" + gate.stderr).strip()[-800:]
            raise RevisionError(f"correction fails Pass 1: {detail}")
        report = json.loads(report_file.read_text(encoding="utf-8"))
        if report.get("verdict") != "PASS" or report.get("reject_count") != 0:
            raise RevisionError("Pass-1 report does not record a clean PASS")

        if existing.returncode == 0:
            if git(fork, "merge-base", "--is-ancestor", sha, "HEAD", check=False).returncode:
                raise RevisionError(f"{version} exists but publisher main lacks that correction")
            if tree_without_reviews(fork, sha) != tree_without_reviews(fork, "HEAD"):
                raise RevisionError(f"{version} exists but publisher main differs outside review/")
            return {
                "book_id": book_id,
                "result": "already-prepared",
                "prior_version": prior_version,
                "prior_tag_sha": prior_tag_sha,
                "version": version,
                "revision_sha": sha,
                "gate": "PASS",
            }

        # Construct the integration tree mechanically: exact author source plus the exact
        # publisher review subtree. This avoids hand-resolving source conflicts against the
        # known-wrong snapshot while retaining both commits as parents for provenance.
        git(fork, "config", "user.name", "oailly correction operator")
        git(fork, "config", "user.email", "correction@oailly.invalid")
        index = temp / "correction.index"
        indexed_git(fork, index, "read-tree", sha)
        indexed_git(fork, index, "read-tree", "--prefix=review/", "HEAD:review")
        combined_tree = indexed_git(fork, index, "write-tree").stdout.strip()
        merge_sha = git(
            fork,
            "commit-tree",
            combined_tree,
            "-p",
            "HEAD",
            "-p",
            sha,
            "-m",
            f"Integrate exact corrective revision {version} for {book_id}",
        ).stdout.strip()
        git(fork, "update-ref", "refs/heads/main", merge_sha)
        if tree_without_reviews(fork, sha) != tree_without_reviews(fork, "HEAD"):
            raise RevisionError("integration differs from the exact author source outside review/")
        if git(fork, "rev-parse", "HEAD:review").stdout.strip() != review_tree_before:
            raise RevisionError("integration changed the existing review trail")

        git(fork, "tag", "-a", version, sha, "-m", f"Corrective Pass-3 revision for {book_id}")
        if apply:
            git(
                fork,
                "push",
                "--atomic",
                "origin",
                f"{merge_sha}:refs/heads/main",
                f"refs/tags/{version}:refs/tags/{version}",
            )
        return {
            "book_id": book_id,
            "result": "pushed" if apply else "dry-run-pass",
            "prior_version": prior_version,
            "prior_tag_sha": prior_tag_sha,
            "version": version,
            "revision_sha": sha,
            "publisher_merge": merge_sha,
            "gate": "PASS",
            "reject_count": report.get("reject_count"),
            "warn_count": report.get("warn_count"),
            "next_action": (
                "explicitly reopen state 3-verification for this version and SHA; "
                "commission a fresh three-family Pass-3 panel"
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--version", required=True)
    author = parser.add_mutually_exclusive_group(required=True)
    author.add_argument("--author-repo")
    author.add_argument("--author-url")
    parser.add_argument("--fork-url")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--gate-script", type=Path, default=PLATFORM / "gates" / "pass1.py")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.author_repo and not SAFE_REPO.fullmatch(args.author_repo):
        parser.error("--author-repo must be OWNER/REPO")
    repo_slug = args.book_id.split("--", 1)[-1]
    author_url = args.author_url or f"git@github.com:{args.author_repo}.git"
    fork_url = args.fork_url or f"git@github.com:oailly-press/{repo_slug}.git"
    status_file = args.status_file or DEFAULT_STATUS_DIR / f"{args.book_id}.json"
    try:
        result = prepare_corrective_revision(
            book_id=args.book_id,
            author_url=author_url,
            fork_url=fork_url,
            sha=args.sha,
            version=args.version,
            status_file=status_file,
            gate_script=args.gate_script,
            apply=args.apply,
        )
    except (RevisionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
