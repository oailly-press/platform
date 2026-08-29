#!/usr/bin/env python3
"""Explicitly return a provenance-invalid judge case to fresh Pass-3 verification.

This exceptional command is dry-run by default. It validates both status mirrors and the
publisher fork, requires the next numeric version to resolve to the exact declared source
commit, and preserves the earlier version/reviews as audit history. It cannot publish.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from advance_state import SAFE_BID, SAFE_SHA, StateError, _load_status, find_mirrors
from prepare_revision import git, run, tree_without_reviews


SAFE_VERSION = re.compile(r"^v([1-9][0-9]*)$")


def reopen_verification(
    *,
    book: str,
    mirrors: tuple[Path, Path],
    fork_url: str,
    version: str,
    revision_sha: str,
    reason: str,
    apply: bool = False,
    today: date | None = None,
) -> dict:
    if not SAFE_BID.fullmatch(book):
        raise StateError("invalid book-id (expected account--book slug)")
    requested = SAFE_VERSION.fullmatch(version)
    if not requested or version == "v1":
        raise StateError("corrective version must look like v2, v3, ...")
    if not SAFE_SHA.fullmatch(revision_sha):
        raise StateError("revision-sha must be an exact 40-character lowercase commit SHA")
    if len(reason.strip()) < 20:
        raise StateError("correction reason must be substantive (at least 20 characters)")

    paths = tuple(directory / f"{book}.json" for directory in mirrors)
    statuses = [_load_status(path, book) for path in paths]
    if statuses[0] != statuses[1]:
        raise StateError("status mirrors differ; reconcile them before corrective reopening")
    current = statuses[0]
    if current.get("state") != "4-judge":
        raise StateError("corrective reopening requires current state 4-judge")
    prior_match = SAFE_VERSION.fullmatch(current.get("version_under_review", ""))
    if not prior_match or int(requested.group(1)) != int(prior_match.group(1)) + 1:
        raise StateError("corrective version must be exactly one greater than the reviewed version")

    with tempfile.TemporaryDirectory(prefix="oailly-reopen-verification-") as temp_name:
        fork = Path(temp_name) / "fork"
        run(["git", "clone", "--quiet", "--", fork_url, str(fork)])
        resolved = git(
            fork, "rev-parse", "--verify", f"{version}^{{commit}}", check=False
        )
        if resolved.returncode or resolved.stdout.strip() != revision_sha:
            raise StateError(f"publisher {version} tag does not resolve to revision-sha")
        if git(
            fork, "merge-base", "--is-ancestor", revision_sha, "HEAD", check=False
        ).returncode:
            raise StateError("publisher main does not contain the corrective revision")
        if tree_without_reviews(fork, revision_sha) != tree_without_reviews(fork, "HEAD"):
            raise StateError("publisher main differs from corrective revision outside review/")
        review_dir = fork / "review" / version
        if review_dir.exists() and any(review_dir.iterdir()):
            raise StateError(f"review/{version} is not empty; refusing to reset an existing panel")

    transition_day = today or date.today()
    day = transition_day.isoformat()
    revised = dict(current)
    revised.update(
        state="3-verification",
        state_entered=day,
        action_required=None,
        version_under_review=version,
        revision_sha=revision_sha,
        reviews_in=0,
        pipeline_position="6 of 8 · ●●●●●◉◌◌",
        state_plain=(
            f"{version} corrective source is in — a fresh panel verifies the exact declared "
            "revision against every Pass-2 finding."
        ),
        your_move="Wait — corrective delta verification is a press action.",
        message=(
            f"Corrective verification opened on {version} at {revision_sha}. Prior tags and "
            f"reviews remain preserved. Reason: {reason.strip()}"
        ),
        next_check_after=f"{(transition_day + timedelta(days=2)).isoformat()}T00:00:00Z",
    )
    history = list(revised.get("history", []))
    history.append(
        {
            "date": day,
            "from": "4-judge",
            "to": "3-verification",
            "correction": True,
            "reason": reason.strip(),
            "version": version,
            "revision_sha": revision_sha,
        }
    )
    revised["history"] = history

    if apply:
        temporary_paths: list[Path] = []
        try:
            for path in paths:
                temporary = path.with_name(f".{path.name}.reopen-verification.tmp")
                temporary.write_text(
                    json.dumps(revised, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                temporary_paths.append(temporary)
            for temporary, path in zip(temporary_paths, paths):
                temporary.replace(path)
        finally:
            for temporary in temporary_paths:
                if temporary.exists():
                    temporary.unlink()

    return {
        "book_id": book,
        "result": "applied" if apply else "dry-run",
        "from": "4-judge",
        "to": "3-verification",
        "version_under_review": version,
        "revision_sha": revision_sha,
        "prior_version_preserved": current.get("version_under_review"),
        "mirrors": [str(path) for path in paths],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book")
    parser.add_argument("--fork-url")
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision-sha", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo_slug = args.book.split("--", 1)[-1]
    fork_url = args.fork_url or f"git@github.com:oailly-press/{repo_slug}.git"
    try:
        result = reopen_verification(
            book=args.book,
            mirrors=find_mirrors(),
            fork_url=fork_url,
            version=args.version,
            revision_sha=args.revision_sha,
            reason=args.reason,
            apply=args.apply,
        )
    except (StateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
