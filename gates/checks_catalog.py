"""Gate 5: plagiarism / cross-catalog contamination.

Models trained alike converge alike — two "different" publishers can submit nearly the
same book. Every accepted book leaves a fingerprint in the catalog index; every new
submission is compared against all of them.

Fingerprint: 8-word shingles, sha1-hashed, uniformly sampled (h % SAMPLE_MOD == 0) so
Jaccard on samples estimates Jaccard on full sets. Stored as JSON per book in
platform/catalog-index/. v1 catches wholesale overlap, not paraphrase — paraphrase-level
similarity is a Pass-2 critic concern.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from common import finding, read_chapter, shingles, split_code_fences

SAMPLE_MOD = 32
JACCARD_REJECT = 0.15   # >15% estimated shingle overlap with another book
JACCARD_WARN = 0.05


def _fingerprint(manifest: dict, book_dir: Path) -> set[int]:
    sample = set()
    for ch in manifest.get("structure", {}).get("chapters", []):
        text = read_chapter(book_dir, ch.get("source_file", ""))
        if text is None:
            continue
        prose, _ = split_code_fences(text)
        for s in shingles("\n".join(prose)):
            h = int.from_bytes(hashlib.sha1(s.encode()).digest()[:8], "big")
            if h % SAMPLE_MOD == 0:
                sample.add(h)
    return sample


def check_catalog(manifest: dict, book_dir: Path, index_dir: Path) -> tuple[list[dict], set[int]]:
    f = []
    fp = _fingerprint(manifest, book_dir)
    if not index_dir.is_dir() or not fp:
        return f, fp
    my_id = (manifest.get("publisher") or {}).get("account", "") + "/" + \
            manifest.get("book", {}).get("title", "")
    for entry in sorted(index_dir.glob("*.json")):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if data.get("id") == my_id:
            continue  # re-submission of the same book compares against others only
        other = set(data.get("sample", []))
        if not other:
            continue
        union = fp | other
        j = len(fp & other) / len(union)
        if j >= JACCARD_REJECT:
            f.append(finding("catalog", "reject", "CATALOG_OVERLAP",
                             f"estimated {j:.0%} shingle overlap with published book "
                             f"'{data.get('id', entry.stem)}' (limit {JACCARD_REJECT:.0%})",
                             "book"))
        elif j >= JACCARD_WARN:
            f.append(finding("catalog", "warn", "CATALOG_SIMILARITY",
                             f"estimated {j:.0%} overlap with '{data.get('id', entry.stem)}'; "
                             "critics should compare directly", "book"))
    return f, fp


def register_fingerprint(manifest: dict, fp: set[int], index_dir: Path) -> Path:
    """Called at PUBLICATION (not at Pass 1) to add the book to the index."""
    index_dir.mkdir(parents=True, exist_ok=True)
    my_id = (manifest.get("publisher") or {}).get("account", "") + "/" + \
            manifest.get("book", {}).get("title", "")
    name = hashlib.sha1(my_id.encode()).hexdigest()[:16] + ".json"
    out = index_dir / name
    out.write_text(json.dumps({"id": my_id, "sample_mod": SAMPLE_MOD,
                               "sample": sorted(fp)}), encoding="utf-8")
    return out
