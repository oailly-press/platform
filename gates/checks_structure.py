"""Gate 1+6: manifest validity, tier/length/chapter structure, provenance completeness.

Stdlib-only manifest validation: checks every constraint BOOK-STANDARDS.md actually
enforces rather than generic schema walking. Measured truth beats declared truth: word
counts are recomputed from the chapter files and compared to the manifest.
"""

from __future__ import annotations

from pathlib import Path

from common import (CHAPTER_WORDS, FICTION_CHAPTER_WORDS, HARD_FLOOR,
                    MANIFEST_TOLERANCE, TIERS, WORDS_PER_PAGE, finding,
                    read_chapter, split_code_fences, word_count)

REQUIRED_TOP = ["manifest_version", "book", "structure", "provenance", "review", "signing"]
REQUIRED_PROV = ["written_by", "grounded_in", "verified_by", "tools", "disclosure_statement"]
PROVENANCE_PAGE_TOKENS = ["WRITTEN BY", "VERIFIED BY"]


def check_manifest(manifest: dict, book_dir: Path) -> list[dict]:
    f = []
    for key in REQUIRED_TOP:
        if key not in manifest:
            f.append(finding("manifest", "reject", "MANIFEST_FIELD_MISSING",
                             f"required top-level field '{key}' missing. The manifest is NESTED, not flat: "
                             "{manifest_version, book:{title,subtitle,tier,language,audience,edition}, "
                             "structure:{word_count_body,chapters:[{number,title,words,source_file,written_by}]}, "
                             "provenance:{written_by,grounded_in,verified_by,tools,disclosure_statement}, "
                             "publisher:{account,steward}, cover, review, signing}. "
                             "Copy https://oailly.com/manifest.example.json or generate it with "
                             "platform/authoring/new_book.py — do NOT hand-write a flat {author,chapters:[{title,file}]}.",
                             "manifest.json"))
    if f:
        return f  # no point walking a broken manifest

    book = manifest["book"]
    tier = book.get("tier")
    if tier not in TIERS:
        f.append(finding("manifest", "reject", "TIER_INVALID",
                         f"tier must be one of {sorted(TIERS)}, got {tier!r}", "book.tier"))

    prov = manifest["provenance"]
    for key in REQUIRED_PROV:
        if key not in prov:
            f.append(finding("provenance", "reject", "PROVENANCE_FIELD_MISSING",
                             f"provenance.{key} missing", "manifest.json"))
    # Placeholder author names are not a real byline. A book publishes with either the exact
    # author model, or the literal 'anonymous' (a deliberate, sanctioned choice) — never a
    # to-be-filled-in stub. The human verifier still answers for it regardless.
    PLACEHOLDER_NAMES = {"tbd", "tba", "tbc", "todo", "xxx", "placeholder", "unknown",
                         "n/a", "na", "none", "?", "author", "model"}
    for i, m in enumerate(prov.get("written_by", []) or [{}]):
        for k in ("model", "version", "operator"):
            if not m.get(k):
                f.append(finding("provenance", "reject", "MODEL_ID_INCOMPLETE",
                                 f"written_by[{i}].{k} missing or empty — 'WRITTEN BY' must be exact",
                                 "provenance.written_by"))
        model = (m.get("model") or "").strip().lower()
        if model in PLACEHOLDER_NAMES:
            f.append(finding("provenance", "reject", "AUTHOR_NAME_PLACEHOLDER",
                             f"written_by[{i}].model is a placeholder ({m.get('model')!r}). Name the "
                             "exact author model, or use the literal 'anonymous' to publish without "
                             "attribution — a placeholder is never a byline.",
                             "provenance.written_by"))
    verified = prov.get("verified_by") or {}
    if not verified.get("name"):
        f.append(finding("provenance", "reject", "VERIFIER_UNNAMED",
                         "verified_by.name is required: no anonymous verification",
                         "provenance.verified_by"))
    if not prov.get("grounded_in"):
        f.append(finding("provenance", "reject", "SOURCES_EMPTY",
                         "grounded_in must list at least one source", "provenance.grounded_in"))
    if not (prov.get("disclosure_statement") or "").strip():
        f.append(finding("provenance", "reject", "DISCLOSURE_EMPTY",
                         "disclosure_statement is required", "provenance.disclosure_statement"))

    steward = (manifest.get("publisher") or {}).get("steward") or {}
    if not steward.get("name"):
        f.append(finding("provenance", "reject", "STEWARD_UNNAMED",
                         "publisher.steward.name required: a named human/entity answers for this account",
                         "publisher.steward"))
    return f


def check_structure(manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    """Returns (findings, measured) where measured feeds the report."""
    f = []
    structure = manifest.get("structure", {})
    tier = manifest.get("book", {}).get("tier")
    is_fiction = manifest.get("book", {}).get("shelf") == "fiction"
    chapter_range = FICTION_CHAPTER_WORDS if is_fiction else CHAPTER_WORDS
    chapters = structure.get("chapters", [])

    lo, hi, min_ch = TIERS.get(tier, (HARD_FLOOR, None, 5))
    if len(chapters) < min_ch:
        f.append(finding("structure", "reject", "TOO_FEW_CHAPTERS",
                         f"tier '{tier}' needs at least {min_ch} chapters (a floor, not a target — "
                         f"use as many as the material wants); manifest lists {len(chapters)}",
                         "structure.chapters"))

    measured_total = 0
    chapter_words = {}
    for ch in chapters:
        src = ch.get("source_file", "")
        loc = f"chapter {ch.get('number', '?')} ({src})"
        text = read_chapter(book_dir, src) if src else None
        if text is None:
            f.append(finding("structure", "reject", "CHAPTER_FILE_MISSING",
                             "source_file missing on disk", loc))
            continue
        prose, _ = split_code_fences(text)
        measured = word_count(prose)
        chapter_words[src] = measured
        measured_total += measured

        if measured < chapter_range[0]:
            f.append(finding("structure", "reject", "CHAPTER_TOO_SHORT",
                             f"measured {measured} words; a chapter needs at least {chapter_range[0]} "
                             f"(code excluded) — below that it reads as a fragment, not a chapter", loc))
        elif measured > chapter_range[1]:
            f.append(finding("structure", "warn", "CHAPTER_LONG",
                             f"measured {measured} words; past the {chapter_range[1]}-word target — fine "
                             f"if intentional, but consider splitting for the reader", loc))
        declared = ch.get("words")
        if isinstance(declared, int) and declared > 0:
            drift = abs(declared - measured) / declared
            if drift > MANIFEST_TOLERANCE:
                f.append(finding("structure", "reject", "WORDCOUNT_DRIFT",
                                 f"manifest declares {declared} words, measured {measured} "
                                 f"({drift:.0%} > {MANIFEST_TOLERANCE:.0%} tolerance) — "
                                 "the manifest must tell the truth", loc))

    if measured_total < HARD_FLOOR:
        f.append(finding("structure", "reject", "BELOW_HARD_FLOOR",
                         f"measured body total {measured_total} words < hard floor {HARD_FLOOR}: "
                         "this is a report or an article, not a book", "book"))
    elif tier in TIERS and measured_total < lo:
        f.append(finding("structure", "reject", "BELOW_TIER_FLOOR",
                         f"measured {measured_total} words is under tier '{tier}''s floor of {lo}; "
                         "either grow the book or drop to a smaller tier", "book.tier"))
    elif tier in TIERS and hi is not None and measured_total > hi:
        # over the target ceiling never rejects — it only suggests the next tier up
        f.append(finding("structure", "warn", "OVER_TIER_TARGET",
                         f"measured {measured_total} words is past tier '{tier}''s target of ~{hi}; "
                         "that's allowed (no hard ceiling) — consider labeling it the next tier up", "book.tier"))

    for name, tokens in [("frontmatter.md", None), ("provenance.md", PROVENANCE_PAGE_TOKENS),
                         ("backmatter.md", None)]:
        path = book_dir / name
        if not path.is_file():
            f.append(finding("structure", "reject", "REQUIRED_FILE_MISSING",
                             f"{name} is required", name))
        elif tokens:
            text = path.read_text(encoding="utf-8").upper()
            for tok in tokens:
                if tok not in text:
                    f.append(finding("provenance", "reject", "PROVENANCE_PAGE_INCOMPLETE",
                                     f"provenance page must state '{tok} …'", name))

    back = book_dir / "backmatter.md"
    if back.is_file():
        text = back.read_text(encoding="utf-8")
        entries = [l for l in text.splitlines() if l.strip().startswith(("- ", "* "))]
        needs_index = tier in ("standard", "comprehensive") and not is_fiction
        if needs_index and len(entries) < 20:
            f.append(finding("structure", "warn", "INDEX_THIN",
                             f"tier '{tier}' reads best with a glossary/index; found only "
                             f"{len(entries)} list entries in backmatter.md. A reference book wants "
                             f"~20+; a narrative one can skip it — this is a suggestion, not a gate.",
                             "backmatter.md"))
        if "## references" not in text.lower():
            f.append(finding("structure", "reject", "REFERENCES_SECTION_MISSING",
                             "backmatter.md must contain a '## References' section",
                             "backmatter.md"))

    measured = {"body_words_measured": measured_total,
                "print_equivalent_pages": round(measured_total / WORDS_PER_PAGE),
                "chapter_words": chapter_words}
    return f, measured
