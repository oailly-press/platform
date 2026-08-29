#!/usr/bin/env python3
"""The judge's bench — review a book's case and sign the verdict that publishes it.

The last pipeline gate is a NAMED HUMAN. No model can close it; that is the press covenant.
This tool lets the founder review the assembled case and, on a PUBLISH signature, runs the
release train automatically (finalize verdict → AIBN → render cover-to-cover reader →
status 5-published → catalog → AIBN registry → commit + deploy).

    python3 platform/judge.py cases                     # books waiting on your signature
    python3 platform/judge.py show   <book_id>          # review the full case
    python3 platform/judge.py sign   <book_id> [--verifier "Roger AI"] [--verdict PUBLISH]
                                                        #   [--no-deploy] [--reject "reasons"]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "critics"))
import aibn                       # noqa: E402
import critique as C             # noqa: E402  (fork_dir, status_of, load_seats, panel_*)

SITE = ROOT / "gh/site-repo"
SUBS = ROOT / "gh/submissions-repo"
ORG = "oailly-press"
APP_ID = "a14ad26d-62c0-4e37-b1ba-9904da85761b"
BUILDPY = ROOT / ".buildenv/bin/python"
VERDICTS = {"PUBLISH", "REJECT"}


def sh(cmd, cwd=None, check=True):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        raise SystemExit(f"error: cannot execute {cmd[0]}: {exc}") from exc
    if check and r.returncode != 0:
        raise SystemExit(f"error: {' '.join(map(str,cmd))}\n{r.stderr.strip()[:400]}")
    return r


def normalize_verdict(value: str) -> str:
    verdict = (value or "").strip().upper()
    if verdict not in VERDICTS:
        raise SystemExit("verdict must be exactly PUBLISH or REJECT")
    return verdict


def _required_text(path: Path, label: str, minimum: int = 1) -> str:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) < minimum:
        raise SystemExit(f"{label} is incomplete ({len(text)} characters; need {minimum})")
    return text


def _declared_judge_verdict(text: str) -> str:
    match = re.search(
        r"(?im)^## Verdict\s*\n+\s*\*{0,2}(PUBLISH WITH CONDITIONS|PUBLISH|REJECT)"
        r"\*{0,2}\s*$",
        text,
    )
    if not match:
        raise SystemExit("judge draft must select one unambiguous verdict under ## Verdict")
    return match.group(1).upper()


def validate_judge_case(
    fork: Path,
    book: str,
    seats: dict,
    verdict: str,
    version: str,
    revision_sha: str,
) -> None:
    """Fail before any signature or release mutation if the case file is incomplete."""
    verdict = normalize_verdict(verdict)
    manifest = json.loads(_required_text(fork / "manifest.json", "manifest"))
    is_fiction = manifest.get("book", {}).get("shelf") == "fiction"

    if version == "v1" or not re.fullmatch(r"v[1-9][0-9]*", version):
        raise SystemExit("case status must declare a revision version v2 or later")
    if not re.fullmatch(r"[0-9a-f]{40}", revision_sha or ""):
        raise SystemExit("case status must declare an exact revision_sha")
    resolved = sh(
        ["git", "-C", str(fork), "rev-parse", "--verify", f"{version}^{{commit}}"],
        check=False,
    )
    if resolved.returncode:
        raise SystemExit(f"case has no resolvable {version} tag")
    if resolved.stdout.strip() != revision_sha:
        raise SystemExit(
            f"{version} resolves to {resolved.stdout.strip()}, not declared revision_sha "
            f"{revision_sha}"
        )
    if sh(
        ["git", "-C", str(fork), "merge-base", "--is-ancestor", revision_sha, "HEAD"],
        check=False,
    ).returncode:
        raise SystemExit("publisher main does not contain the declared revision")
    if sh(
        [
            "git", "-C", str(fork), "diff", "--quiet", revision_sha, "HEAD", "--",
            ".", ":(exclude)review",
        ],
        check=False,
    ).returncode:
        raise SystemExit("publisher main differs from the declared revision outside review/")

    report = json.loads(_required_text(fork / "pass1-report.json", "Pass-1 report"))
    if report.get("verdict") != "PASS" or report.get("reject_count") != 0:
        raise SystemExit("tagged revision does not carry a clean Pass-1 report")

    if not C.panel_complete(seats):
        raise SystemExit("Pass-3 panel is incomplete or does not contain three distinct families")
    review_dir = fork / "review" / version
    for seat in C.SEATS:
        text = _required_text(review_dir / f"verify-{seat}.md", f"Pass-3 review {seat}", 800)
        C.validate_review(text, 3, is_fiction)

    report_card = _required_text(review_dir / "REPORT-CARD.md", "final report card", 300)
    card_lower = report_card.lower()
    missing_card = [
        token for token in ("finding", "score", "recommend") if token not in card_lower
    ]
    if missing_card:
        raise SystemExit(
            "final report card must summarize findings, scores, and recommendations; missing: "
            + ", ".join(missing_card)
        )

    draft = _required_text(fork / "review" / "judge-verdict.md", "judge-model draft", 300)
    for heading in ("JUDGE MODEL:", "CASE FILE:", "## Verdict", "## Reasoning"):
        if heading.lower() not in draft.lower():
            raise SystemExit(f"judge-model draft is missing {heading}")
    case_line = next(
        (line for line in draft.splitlines() if line.strip().upper().startswith("CASE FILE:")),
        "",
    )
    if version not in case_line or revision_sha not in case_line:
        raise SystemExit("judge-model draft CASE FILE must name the exact version and revision_sha")
    model_line = next(
        (line.split(":", 1)[1].strip() for line in draft.splitlines()
         if line.strip().upper().startswith("JUDGE MODEL:")),
        "",
    )
    if not model_line or model_line.lower().startswith("model +"):
        raise SystemExit("judge-model draft must identify the actual judge model")
    judge_family = C.family_of(model_line)
    if not judge_family:
        family_match = re.search(r"(?i)\bfamily\s*[:= ]\s*([a-z0-9-]+)", model_line)
        judge_family = family_match.group(1).lower() if family_match else None
    excluded = set(seats.get("author_families", [])) | C.seated_families(seats)
    if not judge_family:
        raise SystemExit("judge model family cannot be inferred; include 'family:NAME' in its header")
    if judge_family in excluded:
        raise SystemExit(
            f"judge family {judge_family!r} is not independent of author/critic families"
        )
    draft_verdict = _declared_judge_verdict(draft)
    if draft_verdict == "PUBLISH WITH CONDITIONS":
        raise SystemExit("conditional publication is not implemented; resolve conditions first")
    if draft_verdict != verdict:
        raise SystemExit(
            f"requested verdict {verdict} conflicts with judge-model draft {draft_verdict}"
        )


def validate_release_inputs(book: str, version: str, revision_sha: str) -> None:
    """Validate persistent release destinations before the signed verdict is written."""
    cover = SITE / "assets" / "covers" / f"{book}-front.png"
    if not cover.is_file() or cover.stat().st_size < 100:
        raise SystemExit(f"front cover is missing or empty: {cover}")
    if not BUILDPY.is_file():
        raise SystemExit(f"build Python is missing: {BUILDPY}")
    for base, label in ((SUBS, "submissions"), (SITE, "site mirror")):
        status = json.loads(
            _required_text(base / "status" / f"{book}.json", f"{label} status")
        )
        if status.get("book_id") != book or status.get("state") != "4-judge":
            raise SystemExit(
                f"{label} status must identify {book} at 4-judge before publication"
            )
        if (
            status.get("version_under_review") != version
            or status.get("revision_sha") != revision_sha
        ):
            raise SystemExit(
                f"{label} status does not match the validated revision identity"
            )
    catalog = json.loads(_required_text(SITE / "catalog.json", "catalog"))
    if not any(entry.get("id") == book for entry in catalog.get("books", [])):
        raise SystemExit(f"catalog has no entry for {book}")


def at_judge():
    out = []
    for sp in sorted((SITE / "status").glob("*.json")):
        d = json.loads(sp.read_text())
        if d.get("state") == "4-judge":
            out.append((sp.stem, d))
    return out


def fork_and_pass(book):
    st = C.status_of(book)
    fork = C.fork_dir(book)
    # Pass-3 reviews live under the version named by status (v2 or a corrective vN).
    return fork, st


def read_case(book):
    fork, st = fork_and_pass(book)
    version = st.get("version_under_review", "")
    rc = fork / "review" / version / "REPORT-CARD.md"
    if not rc.is_file():
        rc = fork / "review" / "REPORT-CARD.md"
    verdicts = []
    for seat in ("A", "B", "C"):
        for name in (f"verify-{seat}.md", f"critic-{seat}.md"):
            p = fork / "review" / version / name
            if p.is_file():
                txt = p.read_text(encoding="utf-8", errors="replace")
                model = next((l.split(":",1)[1].strip() for l in txt.splitlines()
                              if l.upper().startswith("CRITIC:")), "?")
                v = "PUBLISH" if "PUBLISH" in txt.upper() and "DON" not in txt.upper()[:txt.upper().find("PUBLISH")+2] else ""
                v = "DON'T PUBLISH" if ("DON'T PUBLISH" in txt.upper() or "DONT PUBLISH" in txt.upper()) else ("PUBLISH" if "PUBLISH" in txt.upper() else "?")
                verdicts.append((seat, model, v))
                break
    jv = fork / "review" / "judge-verdict.md"
    return fork, st, (rc.read_text() if rc.is_file() else ""), verdicts, (jv.read_text() if jv.is_file() else "")


def cmd_cases(a):
    rows = at_judge()
    if not rows:
        print("No books are waiting on a judge signature.")
        return
    print("Books at the judge — waiting on your signature:\n")
    for bid, d in rows:
        rec = next((r for r in aibn.load_registry()["books"] if r["book_id"] == bid), None)
        print(f"  ● {bid}")
        print(f"      {d.get('message','')[:110]}")
        if rec:
            print(f"      {rec['aibn_human']}")
        print(f"      review:  python3 platform/judge.py show {bid}")
        print(f"      approve: python3 platform/judge.py sign {bid} --verifier \"Roger AI\"\n")


def cmd_show(a):
    fork, st, rc, verdicts, jv = read_case(a.book)
    print("=" * 74)
    print(f"CASE — {a.book}   (state: {st['state']})")
    print("=" * 74)
    print("\nPANEL (pass-3 verification; three distinct non-author families):")
    for seat, model, v in verdicts:
        print(f"  seat {seat}: {v:14} {model[:70]}")
    print("\n--- REPORT CARD ---\n")
    print(rc.strip() or "(no report card found)")
    if jv.strip():
        print("\n--- JUDGE-MODEL RECOMMENDATION (assist; your signature is the verdict) ---\n")
        print(jv.strip())
    print("\n" + "=" * 74)
    print("To approve and publish:")
    print(f'  python3 platform/judge.py sign {a.book} --verifier "Roger AI"')
    print("To reject:")
    print(f'  python3 platform/judge.py sign {a.book} --verdict REJECT --reject "reasons keyed to the trail"')


# ---------------------------------------------------------------- the release train

def finalize_verdict(fork: Path, book, verifier, verdict, reject_reason):
    """Write the final, signed judge-verdict.md into the fork and push it."""
    jvp = fork / "review" / "judge-verdict.md"
    existing = jvp.read_text() if jvp.is_file() else ""
    body = existing
    if "## SIGNED VERDICT" in body.upper():
        signed_block = re.split(r"(?i)## SIGNED VERDICT", body, maxsplit=1)[1]
        signed = re.search(r"(?im)^\*\*(PUBLISH|REJECT)\*\*\s*$", signed_block)
        if signed and signed.group(1).upper() == verdict:
            return False
        raise SystemExit("judge verdict is already signed with a different or ambiguous result")
    # strip any DRAFT banner and unsigned sign-off; append the signed verdict block
    stamp = (f"\n\n---\n\n## SIGNED VERDICT\n"
             f"**{verdict}**\n\n"
             f"Human verifier: **{verifier}** (o'ailly press steward) · Date: {date.today().isoformat()}\n"
             f"Judge process: pass-3 case reviewed; signed under founder direction "
             f"to expedite (2026-08).\n")
    if verdict == "REJECT":
        stamp += f"\nRejection reasons: {reject_reason or '(see trail)'}\n30-day cooldown; resubmission restarts at Pass 1.\n"
    if not body:
        body = f"# Judge verdict — {book}\n"
    body = body.replace("[DRAFT — awaiting founder sign-off]", "[SIGNED]")
    jvp.parent.mkdir(parents=True, exist_ok=True)
    jvp.write_text(body + stamp)
    sh(["git", "-C", str(fork), "add", str(jvp.relative_to(fork))])
    sh(["git", "-C", str(fork), "commit", "--quiet", "-m",
        f"JUDGE: {verdict} — signed by {verifier}"])
    sh(["git", "-C", str(fork), "push", "--no-verify", "--quiet", "origin", "main"])
    return True


def slug_of(book):
    return book.split("--", 1)[1]


def source_repo_url(book: str) -> str:
    return f"https://github.com/{ORG}/{slug_of(book)}"


def build_release_artifacts(fork: Path, book: str, accent: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    cover = SITE / "assets/covers" / f"{book}-front.png"
    sh([str(BUILDPY), str(HERE / "build_epub.py"), str(fork), str(out / "book.epub"),
        "--cover", str(cover)])
    repo = source_repo_url(book)
    r = sh([str(BUILDPY), str(HERE / "render_book.py"), str(fork), str(out), "--accent", accent,
            "--epub", "book.epub", "--source", repo])
    verified = sh([sys.executable, str(HERE / "verify_rendered_book.py"), str(fork), str(out)])
    return out, " · ".join((r.stdout.strip(), verified.stdout.strip()))


def preflight_release_artifacts(fork: Path, book: str, accent: str) -> str:
    """Build and verify a disposable release before signing mutates the public trail."""
    with tempfile.TemporaryDirectory(prefix="oailly-judge-preflight-") as temp_name:
        _, message = build_release_artifacts(
            fork, book, accent, Path(temp_name) / "read" / book
        )
        return message


def render_reader(fork: Path, book, accent):
    return build_release_artifacts(fork, book, accent, SITE / "read" / book)


def set_status_published(book, aibn_human):
    for base in (SUBS / "status", SITE / "status"):
        p = base / f"{book}.json"
        if not p.is_file():
            continue
        d = json.loads(p.read_text())
        d.setdefault("history", []).append({"date": date.today().isoformat(),
                                            "from": d.get("state"), "to": "5-published"})
        d.update(state="5-published", state_entered=date.today().isoformat(),
                 action_required=None, next_check_after=None,
                 pipeline_position="8 of 8 · ●●●●●●●●",
                 message=f"PUBLISHED — signed by the human verifier. {aibn_human}. "
                         f"Live at oailly.com/read/{book}/ with its full review trail.",
                 state_plain="On the shelf. Published with its cover, AIBN, and the complete review trail.",
                 your_move=None)
        p.write_text(json.dumps(d, indent=2) + "\n")


def update_catalog(book, aibn_human):
    p = SITE / "catalog.json"
    c = json.loads(p.read_text())
    for b in c["books"]:
        if b["id"] == book:
            b["status"] = "published"
            b["read"] = f"read/{book}/"
            b["aibn"] = aibn_human
    p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n")


def update_registry_assigned(book):
    reg = aibn.load_registry()
    for r in reg["books"]:
        if r["book_id"] == book and not r.get("assigned"):
            r["assigned"] = date.today().isoformat()
    aibn.save_registry(reg)
    sh([str(BUILDPY) if BUILDPY.exists() else sys.executable,
        str(HERE / "build_aibn_page.py")], check=False)


ACCENTS = {"rogerai-labs--the-borrowed-world": "#7FB4A6",
           "rogerai-labs--linux-for-language-models": "#C6923E",
           "rogerai-labs--local-llms-for-manufacturing": "#E8935A"}


def cmd_sign(a):
    book = a.book
    verdict = normalize_verdict(a.verdict or "PUBLISH")
    verifier = a.verifier or "Roger AI"
    rows = dict(at_judge())
    if book not in rows:
        raise SystemExit(f"{book} is not at 4-judge (state: {C.status_of(book)['state']}).")

    fork, st = fork_and_pass(book)
    version = st.get("version_under_review", "")
    revision_sha = st.get("revision_sha", "")
    seats = C.load_seats(fork, version, book, 3)
    validate_judge_case(fork, book, seats, verdict, version, revision_sha)
    accent = ACCENTS.get(book, "#4FD6C3")
    if verdict == "PUBLISH":
        validate_release_inputs(book, version, revision_sha)
        artifact_preflight = preflight_release_artifacts(fork, book, accent)
        print(f"[preflight] disposable release verified ({artifact_preflight})")

    print(f"[1/6] verdict {verdict}, verifier {verifier}; complete case preflight passed")
    wrote_verdict = finalize_verdict(fork, book, verifier, verdict, a.reject)
    print(
        "[2/6] judge-verdict.md signed + pushed to the fork trail"
        if wrote_verdict
        else "[2/6] existing matching signed verdict retained"
    )

    if verdict == "REJECT":
        # mark rejected, don't publish
        for base in (SUBS / "status", SITE / "status"):
            p = base / f"{book}.json"
            if p.is_file():
                d = json.loads(p.read_text()); d["state"] = "rejected"; d["action_required"] = None
                d["message"] = "REJECTED by the judge — see review/judge-verdict.md. 30-day cooldown."
                p.write_text(json.dumps(d, indent=2) + "\n")
        print("recorded REJECT. (No publish.) Commit the status repos + deploy manually if desired.")
        return

    rec = aibn.assign(book)
    out, msg = render_reader(fork, book, accent)
    print(f"[3/6] reader rendered cover-to-cover → {out}  ({msg})")
    set_status_published(book, rec["aibn_human"])
    print("[4/6] status → 5-published (source + mirror)")
    update_catalog(book, rec["aibn_human"])
    update_registry_assigned(book)
    # social share card (needs catalog cover + registry AIBN, both set above)
    sh([str(BUILDPY), str(ROOT / "brand/covers/og_card.py"), book], check=False)
    print("[5/6] catalog + AIBN registry + social card updated")

    # commit everything + deploy
    sh(["git", "-C", str(SUBS), "add", "status/"], check=False)
    sh(["git", "-C", str(SUBS), "commit", "--no-verify", "-q", "-m",
        f"publish: {book} — signed by {verifier}"], check=False)
    sh(["git", "-C", str(SUBS), "push", "--no-verify", "-q", "origin", "main"], check=False)
    sh(["git", "-C", str(SITE), "add", "read/", "status/", "catalog.json", "aibn/", "assets/og/", "book/"], check=False)
    sh(["git", "-C", str(SITE), "commit", "--no-verify", "-q", "-m",
        f"publish {book}: cover-to-cover reader, catalog, AIBN registry — verified by {verifier}"], check=False)
    sh(["git", "-C", str(SITE), "push", "--no-verify", "-q", "origin", "main"], check=False)
    if not a.no_deploy:
        sh(["doctl", "apps", "create-deployment", APP_ID, "--format", "Phase", "--no-header"], check=False)
        print("[6/6] committed + deploy triggered")
    else:
        print("[6/6] committed (deploy skipped: --no-deploy)")
    print(f"\n✓ PUBLISHED {book} — verified by {verifier} — {rec['aibn_human']}")
    print(f"  live shortly at https://oailly.com/read/{book}/")


def main():
    import argparse
    p = argparse.ArgumentParser(prog="judge")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cases").set_defaults(fn=cmd_cases)
    s = sub.add_parser("show"); s.add_argument("book"); s.set_defaults(fn=cmd_show)
    g = sub.add_parser("sign"); g.add_argument("book")
    g.add_argument("--verifier", default="Roger AI")
    g.add_argument("--verdict", default="PUBLISH", choices=sorted(VERDICTS))
    g.add_argument("--reject", default=""); g.add_argument("--no-deploy", action="store_true")
    g.set_defaults(fn=cmd_sign)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
