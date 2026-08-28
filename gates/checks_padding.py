"""Gate 2: the anti-padding battery.

A length floor given to an LLM author is an instruction to pad; this gate is the
counterweight. Four independent detectors; thresholds are v1 calibrations, tuned by
running real manuscripts through them (log recalibrations in PROJECT-LOG).
"""

from __future__ import annotations

import zlib
from collections import Counter
import json
from pathlib import Path

from common import (BULLET_RE, SCAFFOLD_RE, finding, paragraphs, read_chapter,
                    normalize, shingles, split_code_fences)

# v1 thresholds
# Compression calibration (2026-08-27, measured): real prose runs 0.39-0.52 zlib ratio
# even at 5MB scale (5.3MB of lab markdown = 0.392); a 3-paragraph-loop padded book
# measures 0.021. 0.22 rejects with ~2x margin against real writing.
COMPRESSION_REJECT = 0.22   # zlib ratio below this = text restates itself
COMPRESSION_WARN = 0.26
NEARDUP_JACCARD = 0.5       # paragraph-pair shingle overlap
NEARDUP_REJECT_FRACTION = 0.05  # >5% of paragraphs near-duplicated = reject
SCAFFOLD_LIMIT = 0.15       # summary/preview scaffolding per chapter
BULLET_REJECT = 0.55        # >55% of non-blank prose lines are bullets = listicle
NGRAM_K = 6
NGRAM_TOP_REJECT = 0.02     # one 6-gram >2% of all 6-grams = boilerplate loop

# FICTION v1 calibration: narrative prose legitimately repeats short refrains and
# chapter scaffolding language is not a meaningful proxy for padding. Compression still
# catches loops; declared exact refrains are exempt only from paragraph-pair counting.
FICTION_COMPRESSION_REJECT = 0.20
FICTION_COMPRESSION_WARN = 0.24
FICTION_NEARDUP_REJECT_FRACTION = 0.08


def _fiction_refrains(manifest: dict, book_dir: Path) -> set[str]:
    if manifest.get("book", {}).get("shelf") != "fiction":
        return set()
    path = book_dir / "fiction-audit.json"
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    out = set()
    for item in audit.get("refrains", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            value = normalize(item["text"]).strip()
            if value:
                out.add(value)
    return out


def _chapter_texts(manifest: dict, book_dir: Path):
    for ch in manifest.get("structure", {}).get("chapters", []):
        src = ch.get("source_file", "")
        text = read_chapter(book_dir, src)
        if text is not None:
            prose, _ = split_code_fences(text)
            yield src, prose


def check_padding(manifest: dict, book_dir: Path) -> tuple[list[dict], dict]:
    f = []
    is_fiction = manifest.get("book", {}).get("shelf") == "fiction"
    declared_refrains = _fiction_refrains(manifest, book_dir)
    compression_reject = FICTION_COMPRESSION_REJECT if is_fiction else COMPRESSION_REJECT
    compression_warn = FICTION_COMPRESSION_WARN if is_fiction else COMPRESSION_WARN
    neardup_reject = (FICTION_NEARDUP_REJECT_FRACTION if is_fiction
                      else NEARDUP_REJECT_FRACTION)
    all_paras: list[tuple[str, str]] = []   # (chapter, paragraph)
    all_words: list[str] = []
    metrics: dict = {
        "profile": "fiction-v1" if is_fiction else "nonfiction-v1",
        "declared_refrains": len(declared_refrains),
        "chapters": {},
    }

    for src, prose in _chapter_texts(manifest, book_dir):
        paras = paragraphs(prose)
        all_paras += [(src, p) for p in paras]
        text_join = "\n".join(prose)
        all_words += text_join.lower().split()

        # summary-shadow: scaffolding paragraphs per chapter
        if paras and not is_fiction:
            scaffold = sum(1 for p in paras if SCAFFOLD_RE.match(p.strip()))
            share = scaffold / len(paras)
            metrics["chapters"][src] = {"scaffold_share": round(share, 3)}
            if share > SCAFFOLD_LIMIT:
                f.append(finding("padding", "reject", "SUMMARY_SHADOW",
                                 f"{share:.0%} of paragraphs are preview/recap scaffolding "
                                 f"(limit {SCAFFOLD_LIMIT:.0%})", src))

        # listicle inflation per chapter
        content_lines = [l for l in prose if l.strip()]
        if content_lines:
            bullet_share = sum(1 for l in content_lines if BULLET_RE.match(l)) / len(content_lines)
            metrics["chapters"].setdefault(src, {})["bullet_share"] = round(bullet_share, 3)
            if bullet_share > BULLET_REJECT:
                f.append(finding("padding", "reject", "LISTICLE_INFLATION",
                                 f"{bullet_share:.0%} of content lines are bullets "
                                 f"(limit {BULLET_REJECT:.0%}): bullets are not a book", src))

    # compression test over the whole body
    body = " ".join(p for _, p in all_paras).encode("utf-8")
    if len(body) > 10_000:
        ratio = len(zlib.compress(body, 9)) / len(body)
        metrics["compression_ratio"] = round(ratio, 4)
        if ratio < compression_reject:
            f.append(finding("padding", "reject", "COMPRESSES_TOO_WELL",
                             f"zlib ratio {ratio:.3f} < {compression_reject}: "
                             "the manuscript is restating itself", "book"))
        elif ratio < compression_warn:
            f.append(finding("padding", "warn", "COMPRESSION_LOW",
                             f"zlib ratio {ratio:.3f}: repetition is elevated; critics "
                             "should sample for restatement", "book"))

    # paragraph near-duplicate detection (shingle Jaccard, bucketed by first shingle)
    sigs = [
        (loc, p, shingles(p))
        for loc, p in all_paras
        if len(p.split()) >= 25 and normalize(p).strip() not in declared_refrains
    ]
    buckets: dict[str, list[int]] = {}
    for i, (_, _, sh) in enumerate(sigs):
        for s in sh:
            buckets.setdefault(s, []).append(i)
    dup_idx: set[int] = set()
    seen_pairs: set[tuple[int, int]] = set()
    for idxs in buckets.values():
        if len(idxs) < 2:
            continue
        for a in idxs:
            for b in idxs:
                if a >= b or (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                sa, sb = sigs[a][2], sigs[b][2]
                if sa and sb:
                    j = len(sa & sb) / len(sa | sb)
                    if j >= NEARDUP_JACCARD:
                        dup_idx |= {a, b}
    if sigs:
        dup_share = len(dup_idx) / len(sigs)
        metrics["near_duplicate_paragraph_share"] = round(dup_share, 4)
        if dup_share > neardup_reject:
            examples = "; ".join(sorted({sigs[i][0] for i in list(dup_idx)[:6]}))
            f.append(finding("padding", "reject", "NEAR_DUPLICATE_PARAGRAPHS",
                             f"{dup_share:.1%} of paragraphs are near-duplicates "
                             f"(limit {neardup_reject:.0%}); e.g. in: {examples}",
                             "book"))

    # boilerplate n-gram loop
    if len(all_words) > NGRAM_K:
        grams = Counter(tuple(all_words[i:i + NGRAM_K])
                        for i in range(len(all_words) - NGRAM_K + 1))
        gram, count = grams.most_common(1)[0]
        top_share = count / max(1, sum(grams.values()))
        metrics["top_ngram"] = {"ngram": " ".join(gram), "share": round(top_share, 5)}
        if top_share > NGRAM_TOP_REJECT and count > 10:
            f.append(finding("padding", "reject", "BOILERPLATE_LOOP",
                             f"6-gram '{' '.join(gram)}' is {top_share:.1%} of all 6-grams "
                             f"({count}×): repeated boilerplate", "book"))

    return f, metrics
