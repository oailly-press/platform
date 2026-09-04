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

STATIC = ["/", "/manifesto/", "/privacy/", "/terms/", "/aibn/", "/status/", "/reviews/", "/llms.txt",
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
    added_dates = [b.get("added") for b in books if b.get("added")]
    latest = max([d for d in all_dates if d] + added_dates + ["2026-08-28"])

    def book_date(b):
        """Best date for a book: its publish event, else when it was added."""
        return publish_date(b["id"]) or b.get("added")

    # ---- sitemap.xml ----
    # Each entry is (loc, lastmod). Static section pages carry no date; every
    # book surface — detail page, reader, chapters, and the machine-first
    # book.md / book.epub — gets a <lastmod> from the book's own date.
    locs = [(loc, None) for loc in STATIC]
    for b in books:
        bid = b["id"]
        bd = book_date(b)
        locs.append((f"/book/?id={bid}", bd))                 # detail page for every book
        rdir = SITE / "read" / bid
        if (rdir / "index.html").is_file():                   # published/rendered readers
            locs.append((f"/read/{bid}/", bd))
            for ch in sorted(rdir.glob("ch*.html")):
                locs.append((f"/read/{bid}/{ch.name}", bd))
            if (rdir / "book.md").is_file():                  # machine-first: full text
                locs.append((f"/read/{bid}/book.md", bd))
            if (rdir / "book.epub").is_file():                # machine-first: epub
                locs.append((f"/read/{bid}/book.epub", bd))
            if (rdir / "back-cover.html").is_file():
                locs.append((f"/read/{bid}/back-cover.html", bd))

    def url_tag(loc, lastmod):
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        return f"<url><loc>{BASE}{loc}</loc>{lm}</url>\n"
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(url_tag(loc, lm) for loc, lm in locs)
               + "</urlset>\n")
    (SITE / "sitemap.xml").write_text(sitemap)

    # ---- feed.xml (Atom): publish events + reviews, newest first ----
    entries = []
    for b in books:
        bid = b["id"]
        pd = publish_date(bid)
        edate = pd or b.get("added")          # publish event, else when it was added
        published = b.get("status") == "published"
        readable = (SITE / "read" / bid / "index.html").is_file()
        link = f"{BASE}/read/{bid}/" if (published and readable) else f"{BASE}/book/?id={bid}"
        prog = b.get("progress") or {}
        pbits = (f", {prog['chapters_done']}/{prog['chapters_planned']} chapters, "
                 f"{prog.get('body_words',0)} words") if prog else ""
        aibn = f" · {b['aibn']}" if b.get("aibn") else ""
        verb = "PUBLISHED" if published else f"status: {b.get('status')}"
        summary = f"{b.get('subtitle','')} — {verb}, shelf: {b.get('shelf')}{pbits}{aibn}"
        entries.append((isot(edate, latest), published,
                        f"<entry><title>{escape(b.get('title') or bid)}</title>"
                        f"<id>{BASE}/{bid}</id><link href=\"{link}\"/>"
                        f"<updated>{isot(edate, latest)}</updated>"
                        f"<summary>{escape(summary)}</summary></entry>"))
    for r in reviews:
        bid = r.get("book_id", "")
        stars = ("★" * r["stars"] + " ") if r.get("stars") else ""
        regs = (" · registers: " + ", ".join(r.get("emotions", []))) if r.get("emotions") else ""
        summary = f"{stars}{(r.get('comment') or '')[:400]}{regs}"
        entries.append((isot(r.get("date"), latest), False,
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
            f'<updated>{isot(latest, latest)}</updated>\n'
            f'<id>{BASE}/</id>\n<author><name>o\'ailly press</name></author>\n'
            + "\n".join(e[2] for e in entries) + "\n</feed>\n")
    (SITE / "feed.xml").write_text(feed)

    npub = sum(1 for b in books if b.get("status") == "published")
    print(f"sitemap: {len(locs)} URLs · feed: {len(entries)} entries ({npub} published books)")


if __name__ == "__main__":
    build()
