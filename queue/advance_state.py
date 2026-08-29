#!/usr/bin/env python3
"""Advance a book's pipeline state consistently across BOTH status mirrors.

The critic tooling fills seats on the fork (source of truth) but does not move the
book's state; run_queue.py deliberately never advances past a judgment point. So
advancing a book after a panel completes is an explicit operator action — this is it.

    advance_state.py <book-id> <target-state> [--version vN] [--reviews-in N]
                     [--message "..."] [--dry-run]

Writes state/state_entered/action_required/reviews_in/pipeline_position/state_plain/
your_move/next_check_after and appends a history entry, in gh/submissions-repo/status/
and gh/site-repo/status/. It does NOT commit, push, sign, or publish — the caller does
that (then runs build_book_pages.py). Refuses to skip states or move backward.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRRORS = [ROOT / "gh/submissions-repo/status", ROOT / "gh/site-repo/status"]

ORDER = ["0-pending", "1-critics", "2-revision", "3-verification", "4-judge", "5-published"]
META = {
    "1-critics":      ("3 of 8 · ●●●◉◌◌◌◌",
                       "Pass 2 open — three critics (families ≠ author) review the whole manuscript.",
                       "Wait — Pass 2 is a press action."),
    "2-revision":     ("4 of 8 · ●●●●◉◌◌◌",
                       "Panel returned SALVAGEABLE. Back with the author for exactly one revision that answers every blocking finding.",
                       "Author: revise and resubmit (answer EVERY blocking finding)."),
    "3-verification": ("6 of 8 · ●●●●●◉◌◌",
                       "v2 in — the panel verifies the delta resolves each pass-2 finding.",
                       "Wait — delta verification is a press action."),
    "4-judge":        ("7 of 8 · ●●●●●●◉◌",
                       "Verified. The judge (a named human, with a model) decides PUBLISH / revise / decline.",
                       "Judge: sign the verdict."),
    "5-published":    ("8 of 8 · ●●●●●●●●",
                       "On the shelf, signed, with its full review trail.",
                       "Read it."),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book"); ap.add_argument("state", choices=list(META))
    ap.add_argument("--version"); ap.add_argument("--reviews-in", type=int)
    ap.add_argument("--message"); ap.add_argument("--allow-same", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    today = date.today().isoformat()

    for mdir in MIRRORS:
        p = mdir / f"{a.book}.json"
        if not p.is_file():
            print(f"!! missing status file: {p}", file=sys.stderr); return 2
        st = json.loads(p.read_text())
        cur = st.get("state")
        if cur == a.state and not a.allow_same:
            print(f"   {mdir.parent.name}: already {a.state}; skipping"); continue
        if cur in ORDER and a.state in ORDER and ORDER.index(a.state) < ORDER.index(cur):
            print(f"!! refusing to move {a.book} backward {cur} -> {a.state}", file=sys.stderr); return 3
        pos, plain, move = META[a.state]
        st["state"] = a.state
        st["state_entered"] = today
        st["action_required"] = None
        st["pipeline_position"] = pos
        st["state_plain"] = plain
        st["your_move"] = move
        st["next_check_after"] = f"{(date.today()+timedelta(days=2)).isoformat()}T00:00:00Z"
        if a.version: st["version_under_review"] = a.version
        if a.reviews_in is not None: st["reviews_in"] = a.reviews_in
        if a.message: st["message"] = a.message
        hist = st.setdefault("history", [])
        if not (hist and hist[-1].get("to") == a.state):
            hist.append({"date": today, "from": cur, "to": a.state})
        if a.dry_run:
            print(f"   [dry] {mdir.parent.name}: {cur} -> {a.state}")
        else:
            p.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n")
            print(f"   {mdir.parent.name}: {cur} -> {a.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
