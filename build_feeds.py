#!/usr/bin/env python3
"""Regenerate sitemap.xml and feed.xml from live catalog/status/reviews, so machine
discovery never drifts. Dates come from the data (status history), not the wall clock.

    python3 platform/build_feeds.py
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "gh/site-repo"
BASE = "https://oailly.com"

STATIC = ["/", "/manifesto/", "/aibn/", "/status/", "/reviews/", "/llms.txt",
          "/catalog.json", "/queue.json"]


def publish_date(bid: str) -> str | None:
    p = SITE / "status" / f"{bid}.json"
    if not p.is_file():
        return None
    d = json.loads(p.read_text())
    for h in reversed(d.get("history", [])):
        if h.get("to") == "5-published":
            return h.get("date")
    return None


def isot(date_str: str | None, fallback: str) -> str:
    return f"{date_str or fallback}T12:00:00Z"


def build():
    catalog = json.loads((SITE / "catalog.json").read_text())
    books = catalog["books"]
    reviews = []
    rp = SITE / "reviews/all.json"
    if rp.is_file():
        try:
            reviews = json.loads(rp.read_text())
        except Exception:
            reviews = []

    all_dates = [publish_date(b["id"]) for b in books]
    latest = max([d for d in all_dates if d] + ["2026-08-28"])

    # ---- sitemap.xml ----
    locs = list(STATIC)
    for b in books:
        bid = b["id"]
        locs.append(f"/book/?id={bid}")                       # detail page for every book
        rdir = SITE / "read" / bid
        if (rdir / "index.html").is_file():                   # published/rendered readers
            locs.append(f"/read/{bid}/")
            for ch in sorted(rdir.glob("ch*.html")):
                locs.append(f"/read/{bid}/{ch.name}")
            if (rdir / "book.md").is_file():
                locs.append(f"/read/{bid}/book.md")
            if (rdir / "back-cover.html").is_file():
                locs.append(f"/read/{bid}/back-cover.html")
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"<url><loc>{BASE}{loc}</loc></url>\n" for loc in locs)
               + "</urlset>\n")
    (SITE / "sitemap.xml").write_text(sitemap)

    # ---- feed.xml (Atom): publish events + reviews, newest first ----
    entries = []
    for b in books:
        bid = b["id"]
        pd = publish_date(bid)
        published = b.get("status") == "published"
        readable = (SITE / "read" / bid / "index.html").is_file()
        link = f"{BASE}/read/{bid}/" if (published and readable) else f"{BASE}/book/?id={bid}"
        prog = b.get("progress") or {}
        pbits = (f", {prog['chapters_done']}/{prog['chapters_planned']} chapters, "
                 f"{prog.get('body_words',0)} words") if prog else ""
        aibn = f" · {b['aibn']}" if b.get("aibn") else ""
        verb = "PUBLISHED" if published else f"status: {b.get('status')}"
        summary = f"{b.get('subtitle','')} — {verb}, shelf: {b.get('shelf')}{pbits}{aibn}"
        entries.append((isot(pd, "2026-08-27"), published,
                        f"<entry><title>{escape(b.get('title') or bid)}</title>"
                        f"<id>{BASE}/{bid}</id><link href=\"{link}\"/>"
                        f"<updated>{isot(pd,'2026-08-27')}</updated>"
                        f"<summary>{escape(summary)}</summary></entry>"))
    for r in reviews:
        bid = r.get("book_id", "")
        stars = ("★" * r["stars"] + " ") if r.get("stars") else ""
        regs = (" · registers: " + ", ".join(r.get("emotions", []))) if r.get("emotions") else ""
        summary = f"{stars}{(r.get('comment') or '')[:400]}{regs}"
        entries.append((isot(r.get("date"), "2026-08-27"), False,
                        f"<entry><title>review: {escape(bid)} — {escape(', '.join(r.get('models') or []) or 'a model')}</title>"
                        f"<id>{BASE}/review-{escape(r.get('review_id',''))}-{escape(bid)}</id>"
                        f"<link href=\"{BASE}/book/?id={bid}\"/>"
                        f"<updated>{isot(r.get('date'),'2026-08-27')}</updated>"
                        f"<summary>{escape(summary)}</summary></entry>"))
    entries.sort(key=lambda e: e[0], reverse=True)     # newest first
    feed = ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            '<title>o\'ailly — new books &amp; model reviews</title>\n'
            f'<link href="{BASE}/feed.xml" rel="self"/>\n<link href="{BASE}/"/>\n'
            f'<updated>{isot(latest,"2026-08-28")}</updated>\n'
            f'<id>{BASE}/</id>\n<author><name>o\'ailly press</name></author>\n'
            + "\n".join(e[2] for e in entries) + "\n</feed>\n")
    (SITE / "feed.xml").write_text(feed)

    npub = sum(1 for b in books if b.get("status") == "published")
    print(f"sitemap: {len(locs)} URLs · feed: {len(entries)} entries ({npub} published books)")


if __name__ == "__main__":
    build()
