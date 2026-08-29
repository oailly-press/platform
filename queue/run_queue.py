#!/usr/bin/env python3
"""O'AILLY daily queue runner — the mechanical half of the review SOP.

    python3 platform/queue/run_queue.py [--dry-run]

Run daily (cron/timer). It does everything that needs no judgment, and writes a
WORKLIST of everything that does. Humans+critic models act on the worklist; the runner
never advances a book past a judgment point by itself.

Per state, the runner:
  (intake)        new submission issues in oailly-press/submissions labeled
                  '0-pending' with no status file -> scaffolds status.json, notes
                  fork-at-intake as an operator action (fork needs org auth decisions)
  pre-submission  re-runs Pass-1 gates on the local book tree if present; updates the
                  status message with the current gate verdict
  0-pending       verifies gates on the fork; worklist: assign 3 critics
  1-critics       counts critic reviews present in the fork's review/ dir;
                  when 3 -> worklist: panel verdict decision
  2-revision      checks deadline vs today; worklist reminder
  3-verification  counts verify files; when 3 -> worklist: judge packet
  4-judge         worklist: verdict due (judge = human+model, never the runner)
  PUBLISH duties  (after a judge PUBLISH verdict is recorded) worklist: mascot
                  assignment, ComfyUI cover per brand/covers/comfyui/RECIPE.md,
                  render_book.py, pandoc artifacts, release, catalog update

Always: syncs submissions status/ -> site repo mirror, re-aggregates reviews/all.json,
mirrors reviews repo -> site, updates catalog progress numbers from local manifests,
commits+pushes site if changed, and appends the daily digest to
platform/queue/digest.log (operator-readable; newest last).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # ~/ai/books-by-ai
SITE = ROOT / "gh/site-repo"
SUBS = ROOT / "gh/submissions-repo"
REVS = ROOT / "gh/reviews-repo"
BOOKS = ROOT / "books"
DIGEST = Path(__file__).parent / "digest.log"
DRY = "--dry-run" in sys.argv

worklist: list[str] = []
actions: list[str] = []

# book-id must be exactly <account-slug>--<title-slug>; it is used as a FILE PATH, so
# validate hard before any filesystem use (untrusted issue text reaches this).
SAFE_BID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*$')


def sh(cmd: str, cwd: Path | None = None, check: bool = True) -> str:
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd}: {r.stderr.strip()[:300]}")
    return r.stdout


def pull_repos() -> None:
    for repo in (SUBS, REVS, SITE):
        sh("git pull --ff-only --quiet", cwd=repo, check=False)


def detect_new_submissions() -> None:
    """Open submission issues with no status file -> scaffold status + worklist."""
    try:
        out = sh('gh issue list -R oailly-press/submissions --label submission '
                 '--state open --json number,title,body --limit 50')
        issues = json.loads(out or "[]")
    except Exception as e:
        worklist.append(f"intake check failed (gh): {str(e)[:120]}")
        return
    for iss in issues:
        m = re.search(r"\[submission\]\s*(\S+)", iss.get("title", ""))
        bid = m.group(1).strip() if m else None
        if not bid or not SAFE_BID.match(bid):
            bm = re.search(r"book-id\s*\n+\s*([a-z0-9-]+--[a-z0-9-]+)", iss.get("body", ""))
            bid = bm.group(1) if bm else None
        if not bid or not SAFE_BID.match(bid):
            worklist.append(f"submissions issue #{iss['number']}: unsafe/unparseable book-id — triage manually")
            continue
        sf = (SUBS / "status" / f"{bid}.json").resolve()
        if sf.parent != (SUBS / "status").resolve():
            worklist.append(f"issue #{iss['number']}: book-id escapes status/ — refused")
            continue
        if sf.exists():
            continue
        status = {"book_id": bid, "version_under_review": None, "state": "0-pending",
                  "state_entered": date.today().isoformat(), "next_check_after": None,
                  "action_required": None, "action_deadline": None, "feedback": [],
                  "message": f"submission received (issue #{iss['number']}); operator: "
                             "fork at declared SHA, run CI gates, then assign critics",
                  "history": [{"date": date.today().isoformat(), "from": None, "to": "0-pending"}]}
        if not DRY:
            sf.write_text(json.dumps(status, indent=2) + "\n")
        actions.append(f"{bid}: status scaffolded from issue #{iss['number']}")
        worklist.append(f"{bid}: NEW SUBMISSION (issue #{iss['number']}) — fork at declared "
                        "SHA into org, dispatch pass1-gate CI, verify SHA matches")


def gate_local_books() -> None:
    """pre-submission books that live locally: refresh gate verdict into status."""
    for status_file in (SUBS / "status").glob("*.json"):
        st = json.loads(status_file.read_text())
        if st.get("state") != "pre-submission":
            continue
        if not SAFE_BID.match(st.get("book_id", "")):
            worklist.append(f"{status_file.name}: book-id fails safety pattern — skipped")
            continue
        slug = st["book_id"].split("--", 1)[-1]
        tree = BOOKS / slug
        if not tree.is_dir():
            worklist.append(f"{st['book_id']}: pre-submission but no local tree at books/{slug}")
            continue
        r = subprocess.run([sys.executable, str(ROOT / "platform/gates/pass1.py"),
                            str(tree), "--offline"], capture_output=True, text=True)
        verdict = "PASS" if r.returncode == 0 else "REJECT"
        rep = json.loads((tree / "pass1-report.json").read_text())
        msg = (f"gates {verdict} ({rep['reject_count']} reject / {rep['warn_count']} warn), "
               f"{rep['measured'].get('body_words_measured', '?')} words — {date.today().isoformat()}")
        if msg.split(" — ")[0] not in (st.get("message") or ""):
            st["message"] = msg + ". " + (st.get("message") or "").split(". ", 1)[-1][:400]
            if not DRY:
                status_file.write_text(json.dumps(st, indent=2) + "\n")
            actions.append(f"{st['book_id']}: status gate line refreshed ({verdict})")
        if verdict == "PASS":
            worklist.append(f"{st['book_id']}: gate PASS — awaiting interview/verification, then intake")


def count_reviews_in_fork(book_id: str, version: str, kind: str) -> int:
    # critique.py keeps its local fork clones under platform/critics/.forks (not gh/forks).
    # Prefer the authoritative dashboard critique.py rebuilds from FRESH forks; fall back to
    # counting files in the local clone if the dashboard is unavailable.
    dash = ROOT / "gh/reviews-repo/review-queue.json"
    if dash.is_file():
        try:
            d = json.loads(dash.read_text())
            want = "verify" if kind == "verify" else "critic"  # kinds map 1:1 to pass
            for j in d.get("open_jobs", []) + d.get("awaiting_judge", []):
                if j["book_id"] == book_id and j.get("version") == version:
                    return sum(1 for s in j.get("seats", {}).values() if s.get("state") == "filled")
        except Exception:
            pass
    fork = ROOT / "platform/critics/.forks" / book_id
    if not fork.is_dir():
        return -1
    return len(list((fork / "review" / version).glob(f"{kind}-*.md"))) if (fork / "review" / version).is_dir() else 0


def walk_states() -> None:
    for status_file in sorted((SUBS / "status").glob("*.json")):
        st = json.loads(status_file.read_text())
        bid, state = st["book_id"], st.get("state")
        v = st.get("version_under_review") or "v1"
        if state == "0-pending":
            worklist.append(f"{bid}: assign 3 critics (families ≠ author), then -> 1-critics")
        elif state == "1-critics":
            n = count_reviews_in_fork(bid, v, "critic")
            worklist.append(f"{bid}: critics {max(n,0)}/3 filed" + (" — PANEL VERDICT DUE" if n >= 3 else ""))
        elif state == "2-revision":
            dl = st.get("action_deadline") or "?"
            worklist.append(f"{bid}: revision out with author, deadline {dl}")
        elif state == "3-verification":
            n = count_reviews_in_fork(bid, v, "verify")
            worklist.append(f"{bid}: verification {max(n,0)}/3" + (" — ASSEMBLE JUDGE PACKET" if n >= 3 else ""))
        elif state == "4-judge":
            worklist.append(f"{bid}: JUDGE VERDICT DUE (founder + judge model). On PUBLISH: "
                            "mascot->registry, ComfyUI cover per RECIPE, render_book, pandoc, release, catalog")


def push_submissions() -> None:
    changed = sh("git status --porcelain", cwd=SUBS).strip()
    if changed and not DRY:
        sh('git add -A && git commit -q -m "queue-runner: status refresh" --no-verify', cwd=SUBS)
        sh("git push --no-verify -q origin main", cwd=SUBS, check=False)
        actions.append("submissions status pushed")


def sync_site() -> None:
    sh(f"cp {SUBS}/status/*.json {SITE}/status/", check=False)
    sh(f"mkdir -p {SITE}/reviews && cp -r {REVS}/reviews/* {SITE}/reviews/", check=False)
    sh(f"cd {SITE} && python3 scripts-sync-reviews.py", check=False)
    changed = sh("git status --porcelain", cwd=SITE).strip()
    if changed and not DRY:
        sh('git add -A && git commit -q -m "queue-runner: daily sync (status/reviews mirrors)" --no-verify', cwd=SITE)
        sh("git push --no-verify -q origin main", cwd=SITE, check=False)
        sh("doctl apps create-deployment a14ad26d-62c0-4e37-b1ba-9904da85761b >/dev/null 2>&1", check=False)
        actions.append("site mirrors synced + deployed")
    elif changed:
        actions.append(f"site changes pending (dry-run): {len(changed.splitlines())} files")


def main() -> None:
    pull_repos()
    detect_new_submissions()
    gate_local_books()
    push_submissions()
    walk_states()
    sync_site()
    stamp = date.today().isoformat()
    lines = [f"== {stamp} {'(dry-run)' if DRY else ''} =="]
    lines += [f"  did: {a}" for a in actions] or ["  did: nothing needed"]
    lines += [f"  WORKLIST: {w}" for w in worklist] or ["  WORKLIST: empty"]
    report = "\n".join(lines)
    print(report)
    if not DRY:
        with DIGEST.open("a") as f:
            f.write(report + "\n")


if __name__ == "__main__":
    main()
