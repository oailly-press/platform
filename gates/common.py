"""Shared helpers for O'AILLY Pass-1 gates.

A "book source tree" is a directory containing:
  manifest.json           - conforms to ../book-manifest.schema.json
  <chapter files>.md      - one per manifest structure.chapters[].source_file
  provenance.md           - printed provenance page (must mirror manifest)
  frontmatter.md          - title page + TOC + introduction
  backmatter.md           - glossary/index + "## References" section

Findings are dicts: {gate, severity: 'reject'|'warn', code, message, location}.
Any 'reject' finding fails Pass 1. Stdlib only, on purpose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TIERS = {
    "pocket": (25_000, 45_000, 6),
    "standard": (45_000, 90_000, 8),
    "comprehensive": (90_000, 160_000, 12),
}
HARD_FLOOR = 25_000
CHAPTER_WORDS = (2_500, 12_000)
WORDS_PER_PAGE = 300
MANIFEST_TOLERANCE = 0.05  # declared vs measured word counts

FENCE_RE = re.compile(r"^(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
BULLET_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
SCAFFOLD_RE = re.compile(
    r"^(in this (chapter|section|book)|this (chapter|section) (will|covers|explores|has shown|showed)"
    r"|by the end of this|as we (have seen|saw|will see)|let's recap|to summarize|in summary"
    r"|now that (we|you) (have|know|understand))",
    re.IGNORECASE,
)


def finding(gate: str, severity: str, code: str, message: str, location: str = "") -> dict:
    return {"gate": gate, "severity": severity, "code": code,
            "message": message, "location": location}


def load_manifest(book_dir: Path) -> tuple[dict | None, list[dict]]:
    path = book_dir / "manifest.json"
    if not path.is_file():
        return None, [finding("manifest", "reject", "MANIFEST_MISSING",
                              "manifest.json not found", str(path))]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, [finding("manifest", "reject", "MANIFEST_UNPARSEABLE",
                              f"manifest.json is not valid JSON: {e}", str(path))]


def split_code_fences(text: str) -> tuple[list[str], list[dict]]:
    """Return (prose_lines, code_blocks). Code block: {info, lines, start_line}."""
    prose, blocks = [], []
    in_fence, current = False, None
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line.strip()):
            if in_fence:
                blocks.append(current)
                in_fence, current = False, None
            else:
                in_fence = True
                current = {"info": line.strip().lstrip("`~").strip(),
                           "lines": [], "start_line": i}
            continue
        if in_fence:
            current["lines"].append(line)
        else:
            prose.append(line)
    if in_fence:  # unterminated fence: keep as code, structure gate flags separately
        blocks.append(current)
    return prose, blocks


def word_count(prose_lines: list[str]) -> int:
    n = 0
    for line in prose_lines:
        if HEADING_RE.match(line):
            continue
        # strip inline markdown noise; count word-ish tokens
        clean = re.sub(r"[`*_>#|\[\]()]", " ", line)
        n += len([t for t in clean.split() if any(c.isalnum() for c in t)])
    return n


def paragraphs(prose_lines: list[str]) -> list[str]:
    paras, cur = [], []
    for line in prose_lines:
        if line.strip() == "" or HEADING_RE.match(line):
            if cur:
                paras.append(" ".join(cur))
                cur = []
        else:
            cur.append(line.strip())
    if cur:
        paras.append(" ".join(cur))
    return paras


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower())


def shingles(text: str, k: int = 8) -> set[str]:
    words = normalize(text).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def read_chapter(book_dir: Path, source_file: str) -> str | None:
    path = (book_dir / source_file).resolve()
    try:
        path.relative_to(book_dir.resolve())
    except ValueError:
        return None  # manifest tried to reach outside the book tree
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
