#!/usr/bin/env python3
"""Validate and submit one independent judge-model draft; dry-run by default.

The draft is read from ``--file`` or stdin. The command clones the publisher fork,
binds the case to the version and exact revision SHA in status, runs the complete judge
preflight, and refuses to overwrite an existing draft. It never signs or publishes.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLATFORM = HERE.parent
sys.path.insert(0, str(PLATFORM))
sys.path.insert(0, str(PLATFORM / "critics"))
sys.path.insert(0, str(HERE))

import judge  # noqa: E402
from prepare_revision import DEFAULT_STATUS_DIR, SAFE_BID, RevisionError, git, run  # noqa: E402


def normalize_transport_wrapper(draft: str) -> str:
    """Remove one model-added outer Markdown fence, preserving the document verbatim."""
    lines = draft.strip().splitlines()
    if lines and lines[0].strip().lower() in ("```", "```markdown", "```md"):
        if lines[-1].strip() != "```":
            raise RevisionError("judge draft starts an outer Markdown fence but does not close it")
        lines = lines[1:-1]
    return "\n".join(lines).strip() + "\n"


def submit_judge_draft(
    *,
    book_id: str,
    fork_url: str,
    status_file: Path,
    draft: str,
    apply: bool,
) -> dict:
    if not SAFE_BID.fullmatch(book_id):
        raise RevisionError("invalid book-id (expected account--book slug)")
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionError(f"cannot read publisher status {status_file}: {exc}") from exc
    if status.get("book_id") != book_id or status.get("state") != "4-judge":
        raise RevisionError("judge draft requires this book to be at 4-judge")
    version = status.get("version_under_review", "")
    revision_sha = status.get("revision_sha", "")
    draft = normalize_transport_wrapper(draft)
    if len(draft.strip()) < 300:
        raise RevisionError("judge draft is incomplete (<300 characters)")

    with tempfile.TemporaryDirectory(prefix="oailly-judge-draft-") as temp_name:
        fork = Path(temp_name) / "fork"
        run(["git", "clone", "--quiet", "--", fork_url, str(fork)])
        path = fork / "review" / "judge-verdict.md"
        if path.exists():
            raise RevisionError("judge-verdict.md already exists; refusing to overwrite it")
        path.write_text(draft.strip() + "\n", encoding="utf-8")
        seats = judge.C.load_seats(fork, version, book_id, 3)
        declared = judge._declared_judge_verdict(draft)
        if declared == "PUBLISH WITH CONDITIONS":
            raise RevisionError("conditional publication is not implemented")
        verdict = "PUBLISH" if declared == "PUBLISH" else "REJECT"
        try:
            judge.validate_judge_case(
                fork, book_id, seats, verdict, version, revision_sha
            )
        except SystemExit as exc:
            raise RevisionError(str(exc)) from exc

        git(fork, "config", "user.name", "oailly judge-case operator")
        git(fork, "config", "user.email", "judge-case@oailly.invalid")
        relative = str(path.relative_to(fork))
        git(fork, "add", relative)
        git(fork, "commit", "--quiet", "-m", f"Add independent judge draft for {book_id}")
        commit = git(fork, "rev-parse", "HEAD^{commit}").stdout.strip()
        if git(fork, "diff", "--name-only", "HEAD^").stdout.splitlines() != [relative]:
            raise RevisionError("judge-draft commit contains changes beyond judge-verdict.md")
        if apply:
            git(fork, "push", "--quiet", "origin", f"{commit}:refs/heads/main")
        return {
            "book_id": book_id,
            "result": "pushed" if apply else "dry-run-pass",
            "version_under_review": version,
            "revision_sha": revision_sha,
            "judge_verdict": verdict,
            "publisher_commit": commit,
            "next_action": "named human reviews the complete case and signs or rejects",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--fork-url")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    draft = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
    repo_slug = args.book_id.split("--", 1)[-1]
    fork_url = args.fork_url or f"git@github.com:oailly-press/{repo_slug}.git"
    status_file = args.status_file or DEFAULT_STATUS_DIR / f"{args.book_id}.json"
    try:
        result = submit_judge_draft(
            book_id=args.book_id,
            fork_url=fork_url,
            status_file=status_file,
            draft=draft,
            apply=args.apply,
        )
    except (RevisionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
