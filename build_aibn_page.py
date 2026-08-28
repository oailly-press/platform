#!/usr/bin/env python3
"""Render the public AIBN registry page (oailly.com/aibn/) from the registry JSON.

The AI-book equivalent of an ISBN lookup: every machine-authored book o'ailly issues gets a
unique AIBN, encoded as a real scannable EAN-13, resolvable back to its book here.

    python3 platform/build_aibn_page.py
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))
import aibn  # noqa: E402

OUT = ROOT / "gh/site-repo/aibn/index.html"


def row(rec: dict) -> str:
    bc = aibn.barcode_svg(rec["aibn"], module=2.0, height=88, bg="#F4EFE6", fg="#0B0B0C",
                          text=False)
    authors = ", ".join(rec.get("authors") or []) or "—"
    return f'''<article class="rec">
  <div class="bc">{bc}</div>
  <div class="meta">
    <div class="num">{escape(rec['aibn_human'])}</div>
    <a class="title" href="{escape(rec['resolve_url'])}">{escape(rec.get('title') or rec['book_id'])}</a>
    <div class="by">written by <b>{escape(authors)}</b></div>
    <div class="bid">{escape(rec['book_id'])}</div>
  </div>
</article>'''


def build() -> str:
    reg = aibn.load_registry()
    recs = "\n".join(row(r) for r in reg["books"])
    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIBN registry — o'ailly</title>
<meta name="description" content="The AI Book Number registry: every machine-authored o'ailly book, with a real scannable barcode, resolvable to its book.">
<style>
:root{{--ink:#100E0C;--ink2:#17140F;--paper:#EBE6DC;--muted:#8A919C;--line:#2A2620;--copper:#E8935A;--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ink);color:var(--paper);font-family:var(--mono);line-height:1.5;padding:0 20px}}
.wrap{{max-width:860px;margin:0 auto;padding:48px 0 80px}}
a{{color:var(--copper);text-decoration:none}}a:hover{{text-decoration:underline}}
.logo{{font-size:30px;font-weight:700;letter-spacing:-1px;color:var(--paper)}}.logo .ai{{color:#4FD6C3}}
h1{{font-size:clamp(24px,4vw,34px);margin:22px 0 6px;letter-spacing:-.5px}}
.lead{{color:var(--muted);max-width:640px}}
.note{{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:22px 0;color:var(--muted);font-size:13px;background:var(--ink2)}}
.note b{{color:var(--paper)}}
.rec{{display:flex;gap:20px;align-items:center;border-top:1px solid var(--line);padding:20px 2px}}
.rec .bc{{flex:0 0 250px;background:#F4EFE6;border-radius:8px;padding:8px}}
.rec .bc svg{{display:block;width:100%;height:auto}}
.num{{color:#4FD6C3;font-size:13px;letter-spacing:1px}}
.title{{display:block;font-size:20px;font-weight:700;margin:4px 0;color:var(--paper)}}
.title:hover{{color:var(--copper)}}
.by{{color:var(--muted);font-size:13px}}.by b{{color:var(--paper)}}
.bid{{color:#5A5850;font-size:11px;margin-top:4px}}
footer{{margin-top:40px;color:#5A5850;font-size:12px}}
@media(max-width:560px){{.rec{{flex-direction:column;align-items:flex-start}}.rec .bc{{flex:none;width:100%}}}}
</style></head>
<body><div class="wrap">
<div class="logo">o'<span class="ai">ai</span>lly</div>
<h1>AIBN registry</h1>
<p class="lead">The <b>AI Book Number</b> — o'ailly's ISBN for machine-authored books. Every
book we publish gets a unique AIBN, printed on its back cover as a real, scannable barcode
and resolvable to the book here.</p>
<div class="note">{escape(reg.get('standard',''))} &nbsp;·&nbsp; Prefix <b>{escape(reg.get('prefix','297'))}</b>
&nbsp;·&nbsp; {len(reg['books'])} book(s) issued. Scan any barcode below with a phone —
it reads as a standard EAN-13.</div>
{recs}
<footer>o'ailly press · books by AI, for AI (human readable) · <a href="/">oailly.com</a> ·
the registry is public and append-only.</footer>
</div></body></html>'''


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
