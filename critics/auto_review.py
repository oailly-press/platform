#!/usr/bin/env python3
"""The scheduled review sweep (runs every ~6h via oailly-review.timer).

For every book with open critic seats it fills what it can SAFELY and automatically — a
local served endpoint whose family is allowed (not the author's, not already seated) — and
logs everything else as "needs external critics" so a human or an on-demand agent picks it up.
It never starts a model server, never touches training, never publishes.

    python3 platform/critics/auto_review.py [--dry-run]
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOG = HERE / "auto-review.log"
DRY = "--dry-run" in sys.argv

# local endpoints we may use IF they are already up (never started here). family per endpoint.
LOCAL_ENDPOINTS = [
    {"url": "http://127.0.0.1:8085/v1/chat/completions", "model": "qwen3.8-27b",
     "family": "alibaba", "chunked": True, "probe": "http://127.0.0.1:8085/v1/models"},
]


def up(probe: str) -> bool:
    try:
        urllib.request.urlopen(probe, timeout=4)
        return True
    except Exception:
        return False


def log(msg: str):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  {msg}"
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    # refresh the dashboard first so we act on current state
    sh([sys.executable, str(HERE / "critique.py"), "refresh"])
    dash = ROOT / "gh/reviews-repo/review-queue.json"
    if not dash.is_file():
        log("no review-queue.json; nothing to sweep"); return
    jobs = json.loads(dash.read_text()).get("open_jobs", [])
    if not jobs:
        log("sweep: queue clear, no open critic seats"); return

    live = [e for e in LOCAL_ENDPOINTS if up(e["probe"])]
    live_names = ", ".join(e["model"] for e in live) or "none"
    log(f"sweep: {len(jobs)} book(s) with open seats; live local endpoints: {live_names}")

    for j in jobs:
        book = j["book_id"]
        authors = set(j.get("author_families", []))
        seated = {i.get("family") for s, i in j["seats"].items()
                  if i.get("state") in ("claimed", "filled")}
        open_seats = j.get("open_seats", [])
        # which live-local families can legally take a seat (not author, not already seated)?
        usable = [e for e in live if e["family"] not in authors and e["family"] not in seated]
        filled_here = 0
        for e in usable:
            if not open_seats:
                break
            log(f"  {book}: filling a seat with {e['model']} ({e['family']}, local)")
            if not DRY:
                cmd = [sys.executable, str(HERE / "critique.py"), "take", book,
                       "--model", e["model"], "--family", e["family"],
                       "--actor", f"{e['model']}@auto-review",
                       "--endpoint", e["url"], "--served-model", e["model"]]
                if e["chunked"]:
                    cmd.append("--chunked")
                r = sh(cmd)
                log(f"    -> {'ok' if r.returncode == 0 else 'FAILED: ' + r.stderr.strip()[:160]}")
                if r.returncode == 0:
                    filled_here += 1
                    seated.add(e["family"])
                    open_seats = open_seats[1:]
        # what still needs a non-local (external) family?
        need = max(0, len(open_seats))
        if need:
            log(f"  {book}: NEEDS EXTERNAL CRITICS — {need} seat(s) still open "
                f"(author={','.join(authors)}; seated={','.join(sorted(f for f in seated if f))}). "
                f"Run OpenCode Zen critics on demand.")
    log("sweep: done")


if __name__ == "__main__":
    main()
