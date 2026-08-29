#!/usr/bin/env python3
"""Advance one mechanical pipeline step across both status mirrors.

The command is dry-run by default and stops at ``4-judge``. Publication remains owned
by the signed judge release train; this tool cannot write ``5-published``.

    python3 queue/advance_state.py ACCOUNT--BOOK 3-verification \
      --version v2 --revision-sha 0123456789abcdef0123456789abcdef01234567
    # Inspect both proposed mirror changes, then repeat with --apply.

Both status files are loaded and validated before either is replaced. The command
refuses path-like book IDs, missing or divergent mirrors, backward moves, skipped states,
and any attempt to cross the human publication gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLATFORM = HERE.parent
SAFE_BID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")
ORDER = ["0-pending", "1-critics", "2-revision", "3-verification", "4-judge"]
NEXT = dict(zip(ORDER, ORDER[1:]))
META = {
    "1-critics": (
        "3 of 8 · ●●●◉◌◌◌◌",
        "Pass 2 open — three critics (families ≠ author) review the whole manuscript.",
        "Wait — Pass 2 is a press action.",
        None,
    ),
    "2-revision": (
        "4 of 8 · ●●●●◉◌◌◌",
        "Panel returned SALVAGEABLE. Back with the author for exactly one revision that "
        "answers every blocking finding.",
        "Author: revise and resubmit (answer EVERY blocking finding).",
        "revise",
    ),
    "3-verification": (
        "6 of 8 · ●●●●●◉◌◌",
        "v2 in — the panel verifies the delta resolves each pass-2 finding.",
        "Wait — delta verification is a press action.",
        None,
    ),
    "4-judge": (
        "7 of 8 · ●●●●●●◉◌",
        "Verified. The judge (a named human, with a model) decides PUBLISH or decline.",
        "Judge: review the complete case and sign the verdict.",
        "judge",
    ),
}


class StateError(RuntimeError):
    pass


def find_mirrors(platform: Path = PLATFORM) -> tuple[Path, Path]:
    roots = (platform.parent, platform.parent / "gh")
    for root in roots:
        submissions = root / "submissions-repo" / "status"
        site = root / "site-repo" / "status"
        if submissions.is_dir() and site.is_dir():
            return submissions, site
    root = roots[0]
    return root / "submissions-repo" / "status", root / "site-repo" / "status"


def _load_status(path: Path, book: str) -> dict:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"cannot read status mirror {path}: {exc}") from exc
    if status.get("book_id") != book:
        raise StateError(f"status mirror {path} does not identify {book}")
    if status.get("state") not in ORDER:
        raise StateError(f"status mirror {path} has unsupported state {status.get('state')!r}")
    return status


def advance_state(
    *,
    book: str,
    target: str,
    mirrors: tuple[Path, Path],
    version: str | None = None,
    revision_sha: str | None = None,
    reviews_in: int | None = None,
    message: str | None = None,
    allow_same: bool = False,
    apply: bool = False,
    today: date | None = None,
) -> dict:
    if not SAFE_BID.fullmatch(book):
        raise StateError("invalid book-id (expected account--book slug)")
    if target not in META:
        raise StateError("target must be a pre-publication state from 1-critics to 4-judge")
    if version is not None and not re.fullmatch(r"v[1-9][0-9]*", version):
        raise StateError("version must look like v1, v2, ...")
    if revision_sha is not None and not SAFE_SHA.fullmatch(revision_sha):
        raise StateError("revision-sha must be an exact 40-character lowercase commit SHA")
    if reviews_in is not None and not 0 <= reviews_in <= 3:
        raise StateError("reviews-in must be between 0 and 3")

    paths = tuple(directory / f"{book}.json" for directory in mirrors)
    statuses = [_load_status(path, book) for path in paths]
    current_states = {status["state"] for status in statuses}
    if len(current_states) != 1:
        raise StateError(
            "status mirrors disagree before transition: "
            + ", ".join(f"{path}={status['state']}" for path, status in zip(paths, statuses))
        )
    current = statuses[0]["state"]
    if current == target:
        if not allow_same:
            return {
                "book_id": book,
                "from": current,
                "to": target,
                "result": "already-current",
                "mirrors": [str(path) for path in paths],
            }
    elif NEXT.get(current) != target:
        raise StateError(f"refusing non-adjacent transition {current} -> {target}")

    if target == "3-verification" and (version is None or revision_sha is None):
        raise StateError("3-verification requires --version and --revision-sha")
    if target == "4-judge":
        recorded_versions = {status.get("version_under_review") for status in statuses}
        recorded_shas = {status.get("revision_sha") for status in statuses}
        if len(recorded_versions) != 1 or not next(iter(recorded_versions), None):
            raise StateError("status mirrors lack one declared version_under_review")
        if len(recorded_shas) != 1 or not SAFE_SHA.fullmatch(next(iter(recorded_shas), "")):
            raise StateError("status mirrors lack one exact revision_sha")
        if version is not None and version not in recorded_versions:
            raise StateError("requested version differs from the verified status version")
        if revision_sha is not None and revision_sha not in recorded_shas:
            raise StateError("requested revision-sha differs from the verified status SHA")

    transition_day = today or date.today()
    today_text = transition_day.isoformat()
    position, plain, move, action = META[target]
    if target == "3-verification" and version:
        plain = f"{version} in — the panel verifies the exact declared revision and Pass-2 debts."
    updated = []
    for status in statuses:
        revised = dict(status)
        revised.update(
            state=target,
            state_entered=today_text,
            action_required=action,
            pipeline_position=position,
            state_plain=plain,
            your_move=move,
            next_check_after=f"{(transition_day + timedelta(days=2)).isoformat()}T00:00:00Z",
        )
        if version is not None:
            revised["version_under_review"] = version
        if revision_sha is not None:
            revised["revision_sha"] = revision_sha
        if reviews_in is not None:
            revised["reviews_in"] = reviews_in
        if message is not None:
            revised["message"] = message
        history = list(revised.get("history", []))
        if not (history and history[-1].get("to") == target):
            history.append({"date": today_text, "from": current, "to": target})
        revised["history"] = history
        updated.append(revised)

    if apply:
        temporary_paths = []
        try:
            for path, status in zip(paths, updated):
                temporary = path.with_name(f".{path.name}.advance-state.tmp")
                temporary.write_text(
                    json.dumps(status, indent=2, ensure_ascii=False) + "\n",
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
        "from": current,
        "to": target,
        "result": "applied" if apply else "dry-run",
        "version_under_review": version or updated[0].get("version_under_review"),
        "revision_sha": revision_sha or updated[0].get("revision_sha"),
        "reviews_in": reviews_in if reviews_in is not None else updated[0].get("reviews_in"),
        "mirrors": [str(path) for path in paths],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book")
    parser.add_argument("state", choices=tuple(META))
    parser.add_argument("--version")
    parser.add_argument("--revision-sha")
    parser.add_argument("--reviews-in", type=int)
    parser.add_argument("--message")
    parser.add_argument("--allow-same", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = advance_state(
            book=args.book,
            target=args.state,
            mirrors=find_mirrors(),
            version=args.version,
            revision_sha=args.revision_sha,
            reviews_in=args.reviews_in,
            message=args.message,
            allow_same=args.allow_same,
            apply=args.apply,
        )
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
