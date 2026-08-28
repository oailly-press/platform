#!/usr/bin/env python3
"""Scaffold a complete o'ailly book workspace so any LLM can write it incrementally.

    python3 new_book.py <out_dir> <plan.json>

plan.json (the ONE thing an author decides up front — the outline):
{
  "title": "...", "subtitle": "...", "tier": "pocket|standard|comprehensive",
  "audience": "one sentence: who this is for and what it assumes",
  "account": "your-publisher-account", "model": "your-model-id",
  "steward": "named human or entity",
  "chapters": [{"title": "...", "purpose": "what this chapter must accomplish",
                "evidence": "what will ground its claims"}]
}

Creates: manifest.json, outline.md, per-chapter stubs (with purpose + a target),
frontmatter/provenance/backmatter templates, and BOOK-PLAN.json (the state file the
author polls with book_status.py). The author then fills ONE chapter at a time — never
needing the whole book in context. Files are the memory.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

TIER_TARGET = {"pocket": 3200, "standard": 5000, "comprehensive": 7000}  # words/chapter aim


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build(out: Path, plan: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tier = plan.get("tier", "pocket")
    target = TIER_TARGET.get(tier, 3200)
    chapters = plan["chapters"]

    ch_meta = []
    for i, c in enumerate(chapters, 1):
        fn = f"ch{i:02d}-{slug(c['title'])}.md"
        stub = (f"# Chapter {i} — {c['title']}\n\n"
                f"<!-- PURPOSE: {c.get('purpose','')} -->\n"
                f"<!-- GROUND IN: {c.get('evidence','')} -->\n"
                f"<!-- TARGET: ~{target} words (chapter floor 2,500, ceiling 12,000). "
                f"Write real substance; padding is auto-rejected. -->\n\n"
                f"*(draft — replace this line and everything below with the chapter.)*\n\n"
                f"TODO: write this chapter. When done, run book_status.py to see what's next.\n")
        (out / fn).write_text(stub, encoding="utf-8")
        ch_meta.append({"number": i, "title": c["title"], "words": 0, "source_file": fn,
                        "written_by": [{"model": plan.get("model", "TBD"),
                                        "version": plan.get("model", "TBD"),
                                        "operator": plan.get("account", "TBD")}]})

    manifest = {
        "manifest_version": "1.0",
        "book": {"title": plan["title"], "subtitle": plan.get("subtitle", ""),
                 "tier": tier, "language": "en", "audience": plan.get("audience", ""),
                 "edition": 1, "series": plan.get("series"), "isbn": None},
        "structure": {"word_count_body": 0, "print_equivalent_pages": 0,
                      "chapters": ch_meta, "has_glossary_or_index": True,
                      "code_listing_policy": plan.get("code_listing_policy", "no_code")},
        "provenance": {
            "written_by": [{"model": plan.get("model", "TBD"), "version": plan.get("model", "TBD"),
                            "operator": plan.get("account", "TBD")}],
            "grounded_in": [{"kind": "url", "reference": "https://example.com — REPLACE with real, resolving sources"}],
            "verified_by": {"name": plan.get("steward", ""), "role": "verifier", "contact": None},
            "tools": [], "disclosure_statement": "Draft. Written by "
            f"{plan.get('model','a model')}; unverified; not for publication."},
        "publisher": {"account": plan.get("account", "TBD"),
                      "steward": {"name": plan.get("steward", ""), "entity": None}},
        "cover": {"mascot_request": {"creature": plan.get("mascot", "an invertebrate"),
                  "why": plan.get("mascot_why", "REPLACE: why this creature fits the subject (the reason is what we read)")},
                  "assigned": None},
        "review": {"status": "draft", "trail_uri": None, "passes": []},
        "signing": {"author_signature": None, "platform_signature": None, "c2pa_manifest_hash": None},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    (out / "outline.md").write_text(
        f"# {plan['title']} — outline\n\n{plan.get('subtitle','')}\n\n"
        "## Contents\n" + "".join(
            f"- Chapter {i}: {c['title']} — {c.get('purpose','')}\n"
            for i, c in enumerate(chapters, 1)) +
        "\nEvery claim must resolve to a real, cited source. Boundaries in plain text.\n",
        encoding="utf-8")

    (out / "frontmatter.md").write_text(
        f"# {plan['title']}\n\n## {plan.get('subtitle','')}\n\n## Contents\n" +
        "".join(f"- Chapter {i}: {c['title']}\n" for i, c in enumerate(chapters, 1)) +
        "\n## Introduction\n\nWho this book is for and what it assumes: "
        f"{plan.get('audience','TODO')}.\n", encoding="utf-8")
    (out / "provenance.md").write_text(
        "# Provenance\n\n**WRITTEN BY** " + plan.get("model", "TBD") +
        "\n\n**VERIFIED BY** " + (plan.get("steward", "") or "TODO: a named human") +
        "\n\n**DISCLOSURE** Draft; unverified. Must be true in both directions "
        "(no hidden AI, no hidden humans).\n\n**REVIEW TRAIL** publishes with the book.\n",
        encoding="utf-8")
    (out / "backmatter.md").write_text(
        "# Back Matter\n\n## Glossary\n" +
        "".join(f"- term-{i}: define a real term your book uses\n" for i in range(1, 41)) +
        "\n## References\n\n- Replace with your real, resolving sources (URL / ISBN / DOI). "
        "Every one is checked at the gate.\n", encoding="utf-8")

    plan_state = {"title": plan["title"], "tier": tier, "target_per_chapter": target,
                  "chapters": [{"number": i, "title": c["title"], "file": ch_meta[i-1]["source_file"],
                                "purpose": c.get("purpose", ""), "done": False}
                               for i, c in enumerate(chapters, 1)]}
    (out / "BOOK-PLAN.json").write_text(json.dumps(plan_state, indent=2) + "\n", encoding="utf-8")

    print(f"scaffolded {out} — {len(chapters)} chapters, tier {tier}")
    print("next: fill one chapter at a time; run book_status.py after each to see what's left.")


if __name__ == "__main__":
    build(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()))
