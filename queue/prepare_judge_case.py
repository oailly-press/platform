#!/usr/bin/env python3
"""Validate a completed Pass-3 panel and prepare its final judge report card.

The command is dry-run by default. It clones the publisher fork, proves that ``main``
contains the exact revision commit declared by status without publisher changes outside
``review/``, validates both three-seat panels and their independence, and deterministically
assembles the selected version's ``REPORT-CARD.md`` with evidence fingerprints.

    python3 queue/prepare_judge_case.py ACCOUNT--BOOK
    # Inspect the JSON and generated-card digest, then repeat with --apply.

Only ``--apply`` commits and pushes the report card. This command never changes status,
commissions a judge model, signs a verdict, assigns an AIBN, or publishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLATFORM = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLATFORM / "critics"))

from prepare_revision import (  # noqa: E402
    DEFAULT_STATUS_DIR,
    SAFE_BID,
    RevisionError,
    git,
    run,
    tree_without_reviews,
)
import critique as C  # noqa: E402


def require_verification_state(status_file: Path, book_id: str) -> dict:
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionError(f"cannot read publisher status {status_file}: {exc}") from exc
    if status.get("book_id") != book_id:
        raise RevisionError("status book_id does not match requested book")
    if status.get("state") != "3-verification":
        raise RevisionError(
            f"publisher state must be 3-verification; got {status.get('state')!r}"
        )
    version = status.get("version_under_review", "")
    if version == "v1" or not re.fullmatch(r"v[1-9][0-9]*", version):
        raise RevisionError("publisher status must identify a revision version v2 or later")
    revision_sha = status.get("revision_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision_sha):
        raise RevisionError("publisher status must declare an exact revision_sha")
    return status


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}(?:\s*\([^\n]*\))?\s*$\n"
        rf"(.*?)(?=^##\s+|\Z)",
        text,
    )
    if not match:
        raise RevisionError(f"review is missing section {heading!r}")
    return match.group(1).strip()


def _identity(text: str) -> str:
    identities = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().upper().startswith("CRITIC:")
    ]
    return identities[0] if identities else "unknown"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_legacy_fiction_pass2(text: str) -> None:
    """Accept only the substantive fiction adaptation used before FICTION headings shipped.

    This does not apply to new submissions or Pass 3. The immutable early panels used the
    general template but explicitly converted its fact-check into an internal-consistency
    audit and discussed the same craft/density axes. Preserve and disclose that history.
    """
    C.validate_review(text, 2, False)
    lower = text.lower()
    required_evidence = ("internal-consistency", "character", "timeline", "density", "voice")
    missing = [token for token in required_evidence if token not in lower]
    if not any(token in lower for token in ("adapted for fiction", "fiction adaptation")):
        missing.append("explicit fiction adaptation")
    if not any(token in lower for token in ("structure", "pacing")):
        missing.append("structure/pacing")
    if not any(token in lower for token in ("ending", "denouement", "thematic payoff", "lands")):
        missing.append("ending/payoff")
    if missing:
        raise RevisionError(
            "legacy Pass-2 fiction review lacks equivalent audit evidence: "
            + ", ".join(missing)
        )


def validate_panel(fork: Path, book_id: str, version: str, pass_no: int) -> tuple[dict, dict]:
    review_dir = fork / "review" / version
    seats_file = review_dir / "SEATS.json"
    if seats_file.is_file():
        try:
            seats = json.loads(seats_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RevisionError(f"invalid {version}/SEATS.json: {exc}") from exc
    else:
        # The first press panels predate self-service seat files. Reconstruct them from
        # the immutable A/B/C reviews, then apply every modern independence check below.
        seats = C.load_seats(fork, version, book_id, pass_no)
    if (
        seats.get("book_id") != book_id
        or seats.get("pass") != pass_no
        or seats.get("version") != version
    ):
        raise RevisionError(f"{version}/SEATS.json does not identify this Pass-{pass_no} case")
    if set(seats.get("seats", {})) != set(C.SEATS) or not C.panel_complete(seats):
        raise RevisionError(f"Pass-{pass_no} panel is incomplete or lacks three distinct families")
    author_families = set(C.manifest_families(fork))
    if set(seats.get("author_families", [])) != author_families:
        raise RevisionError(f"{version}/SEATS.json author families do not match the manifest")
    critic_families = C.seated_families(seats)
    overlap = author_families & critic_families
    if overlap:
        raise RevisionError(
            f"Pass-{pass_no} critic families overlap the author: {', '.join(sorted(overlap))}"
        )

    manifest = json.loads((fork / "manifest.json").read_text(encoding="utf-8"))
    is_fiction = manifest.get("book", {}).get("shelf") == "fiction"
    reviews = {}
    prefix = "critic" if pass_no == 2 else "verify"
    for seat in C.SEATS:
        path = review_dir / f"{prefix}-{seat}.md"
        if not path.is_file():
            raise RevisionError(f"Pass-{pass_no} review {seat} is missing")
        text = path.read_text(encoding="utf-8", errors="replace")
        legacy_fiction = (
            is_fiction
            and pass_no == 2
            and "## Fact-check sample" in text
            and "## Continuity-and-consistency audit" not in text
        )
        try:
            if legacy_fiction:
                validate_legacy_fiction_pass2(text)
            else:
                C.validate_review(text, pass_no, is_fiction)
        except (SystemExit, RevisionError) as exc:
            raise RevisionError(f"Pass-{pass_no} review {seat} is invalid: {exc}") from exc
        tallied = C.tally_verdict(text, pass_no)
        recorded = seats["seats"][seat].get("verdict")
        if recorded != tallied:
            raise RevisionError(
                f"Pass-{pass_no} seat {seat} records {recorded!r}, but review tallies {tallied!r}"
            )
        reviews[seat] = {"path": path, "text": text, "verdict": tallied}
    return seats, reviews


def assemble_report_card(
    book_id: str,
    fork: Path,
    pass2_reviews: dict,
    pass3_seats: dict,
    pass3_reviews: dict,
    version: str,
    revision_sha: str,
) -> str:
    v1 = git(fork, "rev-parse", "v1^{commit}").stdout.strip()
    response = (fork / "response-to-findings.md").read_text(encoding="utf-8")
    tally = C.panel_tally(pass3_seats)
    legacy_pass2 = all("## Fact-check sample" in review["text"] for review in pass2_reviews.values())
    lines = [
        f"# Final report card — {book_id} {version}",
        "",
        "Generated mechanically from the immutable two-pass review trail. The judge must",
        "read the underlying reviews; this card indexes evidence and does not replace it.",
        "",
        "## Case provenance",
        "",
        f"- v1 commit: `{v1}`",
        f"- {version} commit: `{revision_sha}`",
        f"- author response SHA-256: `{_digest(response)}`",
        "- Pass-2 reviews: 3; Pass-3 verification reviews: 3",
        "- Pass-2 format: "
        + (
            "legacy general headings with explicit fiction-adapted internal-consistency audits"
            if legacy_pass2
            else "current shelf-specific FICTION template"
        ),
        "",
        "## Panel recommendation",
        "",
        f"Mechanical tally: **{tally['recommendation']}**.",
        "Verdicts: " + ", ".join(
            f"seat {seat} = {pass3_reviews[seat]['verdict']}" for seat in C.SEATS
        ) + ".",
        "",
        "## Evidence fingerprints",
        "",
        "| Pass | Seat | File | SHA-256 |",
        "|---|---|---|---|",
    ]
    for pass_no, reviews in ((2, pass2_reviews), (3, pass3_reviews)):
        for seat in C.SEATS:
            review = reviews[seat]
            relative = review["path"].relative_to(fork)
            lines.append(f"| {pass_no} | {seat} | `{relative}` | `{_digest(review['text'])}` |")

    for seat in C.SEATS:
        review = pass3_reviews[seat]
        text = review["text"]
        prior_text = pass2_reviews[seat]["text"]
        score_heading = "Craft-axis scores" if "## Craft-axis scores" in text else "Scores"
        prior_score_heading = (
            "Craft-axis scores" if "## Craft-axis scores" in prior_text else "Scores"
        )
        lines.extend(
            [
                "",
                f"## Seat {seat} — {_identity(text)}",
                "",
                f"Recorded recommendation: **{review['verdict']}**.",
                "",
                "### Recommendation reasoning",
                "",
                _section(text, "Verdict summary"),
                "",
                "### Findings ledger",
                "",
                _section(text, "Pass-3 only: findings ledger"),
                "",
                "### Score evidence (Pass 2 → Pass 3)",
                "",
                "Pass 2:",
                "",
                _section(prior_text, prior_score_heading),
                "",
                "Pass 3:",
                "",
                _section(text, score_heading),
            ]
        )

    lines.extend(
        [
            "",
            "## Judge handoff",
            "",
            "The judge reviews the manuscript, full Pass-2 findings, author response, exact",
            f"v1→{version} delta, all Pass-3 ledgers, and this report card. Still-open findings, if",
            "any, remain visible; the mechanical tally does not sign or determine publication.",
            "",
        ]
    )
    return "\n".join(lines)


def prepare_judge_case(
    *, book_id: str, fork_url: str, status_file: Path, apply: bool
) -> dict:
    if not SAFE_BID.fullmatch(book_id):
        raise RevisionError("invalid book-id (expected account--book slug)")
    status = require_verification_state(status_file, book_id)
    version = status["version_under_review"]
    revision_sha = status["revision_sha"]
    with tempfile.TemporaryDirectory(prefix="oailly-judge-case-") as temp_name:
        fork = Path(temp_name) / "fork"
        run(["git", "clone", "--quiet", "--", fork_url, str(fork)])
        for tag in ("v1", version):
            if git(fork, "rev-parse", "--verify", f"{tag}^{{commit}}", check=False).returncode:
                raise RevisionError(f"publisher fork has no resolvable {tag} tag")
        resolved = git(fork, "rev-parse", f"{version}^{{commit}}").stdout.strip()
        if resolved != revision_sha:
            raise RevisionError(
                f"{version} resolves to {resolved}, not declared revision_sha {revision_sha}"
            )
        if git(
            fork, "merge-base", "--is-ancestor", revision_sha, "HEAD", check=False
        ).returncode:
            raise RevisionError("publisher main does not contain the declared revision")
        if tree_without_reviews(fork, revision_sha) != tree_without_reviews(fork, "HEAD"):
            raise RevisionError(
                "publisher main differs from the declared revision outside review/"
            )
        response = fork / "response-to-findings.md"
        if not response.is_file() or len(response.read_text(encoding="utf-8").strip()) < 200:
            raise RevisionError("case lacks a substantive response-to-findings.md")
        report = json.loads((fork / "pass1-report.json").read_text(encoding="utf-8"))
        if report.get("verdict") != "PASS" or report.get("reject_count") != 0:
            raise RevisionError(f"{version} does not carry a clean Pass-1 report")

        _, pass2_reviews = validate_panel(fork, book_id, "v1", 2)
        pass3_seats, pass3_reviews = validate_panel(fork, book_id, version, 3)
        card = assemble_report_card(
            book_id,
            fork,
            pass2_reviews,
            pass3_seats,
            pass3_reviews,
            version,
            revision_sha,
        )
        card_path = fork / "review" / version / "REPORT-CARD.md"
        if card_path.is_file():
            if card_path.read_text(encoding="utf-8") != card:
                raise RevisionError("existing REPORT-CARD.md differs; refusing to overwrite it")
            result = "already-prepared"
            commit = git(fork, "rev-parse", "HEAD^{commit}").stdout.strip()
        else:
            card_path.write_text(card, encoding="utf-8")
            git(fork, "config", "user.name", "oailly case operator")
            git(fork, "config", "user.email", "case@oailly.invalid")
            relative_card = str(card_path.relative_to(fork))
            git(fork, "add", relative_card)
            git(fork, "commit", "--quiet", "-m", f"Assemble final report card for {book_id}")
            commit = git(fork, "rev-parse", "HEAD^{commit}").stdout.strip()
            changed = git(fork, "diff", "--name-only", "HEAD^").stdout.splitlines()
            if changed != [relative_card]:
                raise RevisionError("judge-case commit contains changes beyond the report card")
            if apply:
                git(fork, "push", "--quiet", "origin", f"{commit}:refs/heads/main")
            result = "pushed" if apply else "dry-run-pass"

        return {
            "book_id": book_id,
            "result": result,
            "version_under_review": version,
            "revision_sha": revision_sha,
            "publisher_commit": commit,
            "report_card_sha256": _digest(card),
            "pass2_reviews": 3,
            "pass3_reviews": 3,
            "pass3_tally": C.panel_tally(pass3_seats),
            "next_action": (
                "set status to 4-judge, commission an independent judge model, then obtain "
                "the named human signature"
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id")
    parser.add_argument("--fork-url")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo_slug = args.book_id.split("--", 1)[-1]
    fork_url = args.fork_url or f"git@github.com:oailly-press/{repo_slug}.git"
    status_file = args.status_file or DEFAULT_STATUS_DIR / f"{args.book_id}.json"
    try:
        result = prepare_judge_case(
            book_id=args.book_id,
            fork_url=fork_url,
            status_file=status_file,
            apply=args.apply,
        )
    except (RevisionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
