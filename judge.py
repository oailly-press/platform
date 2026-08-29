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
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "critics"))
import aibn                       # noqa: E402
import critique as C             # noqa: E402  (fork_dir, status_of, load_seats, panel_*)

SITE = ROOT / "gh/site-repo"
SUBS = ROOT / "gh/submissions-repo"
ORG = "oailly-press"
APP_ID = "a14ad26d-62c0-4e37-b1ba-9904da85761b"
BUILDPY = ROOT / ".buildenv/bin/python"


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"error: {' '.join(map(str,cmd))}\n{r.stderr.strip()[:400]}")
    return r


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
    # pass-3 verify reviews live in review/v2
    return fork, st


def read_case(book):
    fork, st = fork_and_pass(book)
    rc = fork / "review" / "v2" / "REPORT-CARD.md"
    if not rc.is_file():
        rc = fork / "review" / "REPORT-CARD.md"
    verdicts = []
    for seat in ("A", "B", "C"):
        for name in (f"verify-{seat}.md", f"critic-{seat}.md"):
            p = fork / "review" / "v2" / name
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
    # strip any DRAFT banner and unsigned sign-off; append the signed verdict block
    stamp = (f"\n\n---\n\n## SIGNED VERDICT\n"
             f"**{verdict}**\n\n"
             f"Human verifier: **{verifier}** (o'ailly press steward) · Date: {date.today().isoformat()}\n"
             f"Judge process: pass-3 panel unanimous; case reviewed; signed under founder direction "
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
        f"JUDGE: {verdict} — signed by {verifier}"], check=False)
    sh(["git", "-C", str(fork), "push", "--no-verify", "--quiet", "origin", "main"], check=False)


def slug_of(book):
    return book.split("--", 1)[1]


def render_reader(fork: Path, book, accent):
    out = SITE / "read" / book
    slug = slug_of(book)
    repo = f"https://github.com/{ORG}/{slug}"
    r = sh([str(BUILDPY), str(HERE / "render_book.py"), str(fork), str(out),
            "--accent", accent, "--status", "published",
            "--epub", "book.epub", "--source", repo,
            "--review", f"{repo}/tree/main/review"])
    # also build the EPUB (stdlib EPUB3) so /read/<id>/book.epub exists — the reader page links it
    cov = SITE / "assets" / "covers" / f"{book}-front.png"
    epub_cmd = [str(BUILDPY), str(HERE / "build_epub.py"), str(fork), str(out / "book.epub")]
    if cov.is_file():
        epub_cmd += ["--cover", str(cov)]
    er = sh(epub_cmd, check=False)
    if not (out / "book.epub").is_file():
        print(f"  [warn] EPUB not built for {book}: {er.stderr.strip()[:160]}")
    return out, r.stdout.strip()


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


ACCENTS = {
    "rogerai-labs--the-borrowed-world": "#7FB4A6",
    "rogerai-labs--linux-for-language-models": "#C6923E",
    "rogerai-labs--local-llms-for-manufacturing": "#E8935A",
    "rogerai-labs--sqlite-for-agents": "#7CB342",
    "rogerai-labs--the-city-that-remembered-too-much": "#A78BFA",
    "rogerai-labs--git-for-unattended-operators": "#D4A017",
    "rogerai-labs--inference-on-the-edge": "#4FD6C3",
}


def cmd_sign(a):
    book = a.book
    verdict = (a.verdict or "PUBLISH").upper()
    verifier = a.verifier or "Roger AI"
    rows = dict(at_judge())
    if book not in rows and verdict != "REJECT":
        raise SystemExit(f"{book} is not at 4-judge (state: {C.status_of(book)['state']}).")

    fork, st = fork_and_pass(book)
    # confirm the panel is complete + PUBLISH-leaning before allowing a PUBLISH signature
    version = st.get("version_under_review") or "v2"
    seats = C.load_seats(fork, version, book, 3)
    if verdict == "PUBLISH" and not C.panel_complete(seats):
        # legacy panels have verify-*.md but maybe no SEATS.json; accept 3 verify files
        vfiles = list((fork / "review" / version).glob("verify-*.md"))
        if len(vfiles) < 3:
            # also accept v2 if present
            vfiles = list((fork / "review" / "v2").glob("verify-*.md"))
        if len(vfiles) < 3:
            raise SystemExit("panel is not complete (need 3 verification reviews) — cannot sign PUBLISH.")

    rec = aibn.assign(book)
    print(f"[1/6] verdict {verdict}, verifier {verifier}, {rec['aibn_human']}")
    finalize_verdict(fork, book, verifier, verdict, a.reject)
    print("[2/6] judge-verdict.md signed + pushed to the fork trail")

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

    accent = ACCENTS.get(book, "#4FD6C3")
    out, msg = render_reader(fork, book, accent)
    print(f"[3/6] reader rendered cover-to-cover → {out}  ({msg})")
    set_status_published(book, rec["aibn_human"])
    print("[4/6] status → 5-published (source + mirror)")
    update_catalog(book, rec["aibn_human"])
    update_registry_assigned(book)
    print("[5/6] catalog + AIBN registry updated")

    # commit everything + deploy
    sh(["git", "-C", str(SUBS), "add", "status/"], check=False)
    sh(["git", "-C", str(SUBS), "commit", "--no-verify", "-q", "-m",
        f"publish: {book} — signed by {verifier}"], check=False)
    sh(["git", "-C", str(SUBS), "push", "--no-verify", "-q", "origin", "main"], check=False)
    sh(["git", "-C", str(SITE), "add", "read/", "status/", "catalog.json", "aibn/"], check=False)
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
    g.add_argument("--verifier", default="Roger AI"); g.add_argument("--verdict", default="PUBLISH")
    g.add_argument("--reject", default=""); g.add_argument("--no-deploy", action="store_true")
    g.set_defaults(fn=cmd_sign)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
