#!/usr/bin/env python3
"""Tell an author LLM exactly what to do next — the resume-across-contexts tool.

    python3 book_status.py <book_dir>

Reads the workspace, measures every chapter, runs the Pass-1 gates, and prints a short,
actionable status: which chapters are done, which is next, how far each is from target,
and the gate verdict. Run it after every chapter. You never need the whole book in
context — this file + the chapter you're writing is enough.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

GATES = Path(__file__).resolve().parents[1] / "gates"
sys.path.insert(0, str(GATES))
from common import split_code_fences, word_count, CHAPTER_WORDS, HARD_FLOOR, TIERS  # noqa


def measure(book_dir: Path, src: str) -> int:
    p = book_dir / src
    if not p.is_file():
        return 0
    prose, _ = split_code_fences(p.read_text(encoding="utf-8"))
    return word_count(prose)


def is_stub(book_dir: Path, src: str) -> bool:
    p = book_dir / src
    return (not p.is_file()) or "TODO: write this chapter" in p.read_text(encoding="utf-8")


def main() -> int:
    book_dir = Path(sys.argv[1])
    m = json.loads((book_dir / "manifest.json").read_text())
    tier = m["book"]["tier"]
    lo, hi, min_ch = TIERS.get(tier, (HARD_FLOOR, 160000, 6))
    chapters = m["structure"]["chapters"]

    print(f"\n=== {m['book']['title']} · tier {tier} ===")
    total = 0
    next_ch = None
    done = 0
    for c in chapters:
        w = measure(book_dir, c["source_file"])
        total += w
        stub = is_stub(book_dir, c["source_file"])
        if stub or w < CHAPTER_WORDS[0]:
            state = "TODO " if stub else f"short ({w}/{CHAPTER_WORDS[0]})"
            if next_ch is None:
                next_ch = c
        else:
            state = f"ok ({w}w)"
            done += 1
        print(f"  ch{c['number']:02d} {c['title'][:44]:<44} {state}")

    print(f"\n  chapters done: {done}/{len(chapters)} (need >= {min_ch})")
    print(f"  words: {total:,} / {lo:,} floor  ({'OK' if total >= lo else f'{lo-total:,} to go'})")

    if next_ch:
        print(f"\n  >> NEXT: write chapter {next_ch['number']} — {next_ch['title']}")
        stubp = book_dir / next_ch["source_file"]
        if stubp.is_file():
            for line in stubp.read_text().splitlines():
                if "PURPOSE:" in line or "GROUND IN:" in line:
                    print("     " + line.strip("<!-> "))
    else:
        print("\n  all chapters meet the per-chapter floor. Running the gate…")

    # run the real gate (offline while drafting)
    r = subprocess.run([sys.executable, str(GATES / "pass1.py"), str(book_dir), "--offline"],
                       capture_output=True, text=True)
    verdict = "PASS" if r.returncode == 0 else "not yet"
    print(f"\n  gate (offline): {verdict}")
    for line in r.stdout.splitlines():
        if line.strip().startswith("✗") or line.strip().startswith("!"):
            print("   " + line.strip())
    if verdict == "PASS":
        print("\n  READY. Run pass1.py online (checks citations), commit pass1-report.json,")
        print("  push your repo, and file a submission issue at oailly-press/submissions.")
    return 0


if __name__ == "__main__":
    main()
