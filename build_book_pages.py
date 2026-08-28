#!/usr/bin/env python3
"""Aggregate everything known about each book into gh/site-repo/book/<id>.json, which the
detail page (/book/?id=<id>) renders. Every catalog book gets one, at any stage — cover or
placeholder, with its live status, pipeline stage, panel verdicts, judge verdict, review
trail links, and reader reviews. Run after any status/review/publish change.

    python3 platform/build_book_pages.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "gh/site-repo"
SUBS = ROOT / "gh/submissions-repo"
FORKS = ROOT / "platform/critics/.forks"
OUT = SITE / "book"
ORG = "oailly-press"

STATIONS = ["draft", "gates", "pending", "critics", "revision", "verify", "judge", "shelf"]
STATE2ST = {"pre-submission": 1, "0-pending": 2, "1-critics": 3, "2-revision": 4,
            "3-verification": 5, "4-judge": 6, "5-published": 7, "published": 7, "rejected": 6}


def verdict_of(text: str) -> str:
    up = text.upper()
    if "UNSALVAGEABLE" in up:
        return "UNSALVAGEABLE"
    if "DON'T PUBLISH" in up or "DONT PUBLISH" in up:
        return "DON'T PUBLISH"
    if "SALVAGEABLE" in up:
        return "SALVAGEABLE"
    if "PUBLISH" in up:
        return "PUBLISH"
    return "—"


def read_panel(fork: Path):
    """Return (pass_label, [{seat,model,verdict}]) for the most advanced panel present."""
    for vdir, label, prefix in (("v2", "verification (pass 3)", "verify"),
                                ("v1", "critic panel (pass 2)", "critic")):
        d = fork / "review" / vdir
        seats = []
        for seat in ("A", "B", "C"):
            p = d / f"{prefix}-{seat}.md"
            if p.is_file():
                t = p.read_text(encoding="utf-8", errors="replace")
                model = next((l.split(":", 1)[1].strip() for l in t.splitlines()
                              if l.upper().startswith("CRITIC:")), "?")
                seats.append({"seat": seat, "model": model[:80], "verdict": verdict_of(t)})
        if seats:
            return label, seats
    return None, []


def read_judge(fork: Path):
    p = fork / "review" / "judge-verdict.md"
    if not p.is_file():
        return None
    t = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"##\s*Verdict\s*\n+\**([A-Z' ]+?)\**\b", t)
    verdict = (m.group(1).strip() if m else verdict_of(t))
    signed = "SIGNED VERDICT" in t.upper()
    return {"verdict": verdict, "signed": signed}


def read_report(fork: Path):
    for vdir in ("v2", "v1", ""):
        p = fork / "review" / vdir / "REPORT-CARD.md" if vdir else fork / "review" / "REPORT-CARD.md"
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            resolved = len(re.findall(r"\bresolved\b", t, re.I))
            openf = len(re.findall(r"still[- ]open", t, re.I))
            return {"resolved": resolved, "still_open": openf, "has_card": True}
    return {"resolved": 0, "still_open": 0, "has_card": False}


def load_status(book_id: str):
    for base in (SUBS / "status", SITE / "status"):
        p = base / f"{book_id}.json"
        if p.is_file():
            return json.loads(p.read_text())
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((SITE / "catalog.json").read_text())
    reviews = []
    rp = SITE / "reviews/all.json"
    if rp.is_file():
        try:
            reviews = json.loads(rp.read_text())
        except Exception:
            reviews = []

    ids = []
    for b in catalog["books"]:
        bid = b["id"]
        slug = bid.split("--", 1)[1]
        repo = f"https://github.com/{ORG}/{slug}"
        st = load_status(bid) or {}
        state = st.get("state") or ("published" if b.get("status") == "published" else b.get("status"))
        readable = (SITE / "read" / bid / "index.html").is_file()

        fork = FORKS / bid
        panel_label, panel = (None, [])
        judge = report = None
        trail = {"repo": repo}
        if fork.is_dir():
            panel_label, panel = read_panel(fork)
            judge = read_judge(fork)
            report = read_report(fork)
            trail.update(reviews=f"{repo}/tree/main/review",
                         judge_verdict=f"{repo}/blob/main/review/judge-verdict.md" if judge else None)

        data = {
            "id": bid, "title": b.get("title"), "subtitle": b.get("subtitle"),
            "series": b.get("series") or (f"Nº{b['series_no']} · {b.get('shelf','')}" if b.get("series_no") else None),
            "series_no": b.get("series_no"), "shelf": b.get("shelf"), "tier": b.get("tier"),
            "aibn": b.get("aibn"), "accent": (b.get("mascot") or {}).get("accent"),
            "creature": (b.get("mascot") or {}).get("creature"),
            "cover": b.get("cover"), "cover_back": b.get("cover_back"), "cover_spread": b.get("cover_spread"),
            "written_by": [x for x in (b.get("written_by") or []) if x and x.lower() != "tbd"],
            "verified_by": b.get("verified_by"), "keywords": b.get("keywords") or [],
            "progress": b.get("progress"), "catalog_status": b.get("status"),
            "state": state, "stage_index": STATE2ST.get(state, 0), "stations": STATIONS,
            "pipeline_position": st.get("pipeline_position"),
            "message": st.get("message"), "state_plain": st.get("state_plain"),
            "your_move": st.get("your_move"), "action_required": st.get("action_required"),
            "history": st.get("history") or [],
            "readable": readable,
            "read": f"/read/{bid}/" if readable else None,
            "book_md": f"/read/{bid}/book.md" if readable else None,
            "repo": repo, "trail": trail,
            "panel_label": panel_label, "panel": panel, "judge": judge, "findings": report,
            "reader_reviews": [r for r in reviews if r.get("book_id") == bid],
        }
        (OUT / f"{bid}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        ids.append({"id": bid, "title": b.get("title"), "state": state})

    (OUT / "index.json").write_text(json.dumps({"books": ids}, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(ids)} book detail files → {OUT}")


if __name__ == "__main__":
    main()
