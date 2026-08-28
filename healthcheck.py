#!/usr/bin/env python3
"""Live health check: every published book's artifacts + the key pages must resolve 200.
Uses a browser User-Agent (Cloudflare 403s the default python-urllib UA).

    python3 platform/healthcheck.py            # exits non-zero if anything fails
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path

BASE = "https://oailly.com/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
SITE = Path(__file__).resolve().parent.parent / "gh/site-repo"


def code(p):
    try:
        return urllib.request.urlopen(urllib.request.Request(BASE + p, headers=UA), timeout=12).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"ERR {str(e)[:24]}"


def main():
    catalog = json.loads((SITE / "catalog.json").read_text())
    published = [b["id"] for b in catalog["books"] if b.get("status") == "published"]
    checks = ["", "manifesto/", "aibn/", "feed.xml", "sitemap.xml", "catalog.json",
              "llms.txt", "queue.json", "status/"]
    for bid in published:
        checks += [f"read/{bid}/", f"read/{bid}/book.md", f"read/{bid}/book.epub",
                   f"assets/og/{bid}.png", f"book/{bid}.json", f"book/?id={bid}"]
    fails = [(p, c) for p in checks if (c := code(p)) != 200]
    ok = len(checks) - len(fails)
    print(f"o'ailly healthcheck: {ok}/{len(checks)} OK ({len(published)} published books)")
    for p, c in fails:
        print(f"  ✗ /{p}  {c}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
