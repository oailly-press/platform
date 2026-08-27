#!/usr/bin/env python3
"""O'AILLY Pass-1 gate runner.

Usage:
    python3 pass1.py <book_source_dir> [--offline] [--no-exec] [--index DIR]

Runs every automated acceptance gate from BOOK-STANDARDS.md against a book source
tree and writes <book_dir>/pass1-report.json. Exit 0 = PASS (warnings allowed),
exit 1 = REJECT, exit 2 = could not run (bad invocation / unreadable manifest).

No judgment calls live here: a book may retry Pass 1 as often as needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks_catalog import check_catalog
from checks_padding import check_padding
from checks_refs_code import check_citations, check_code
from checks_structure import check_manifest, check_structure
from common import load_manifest


def run(book_dir: Path, offline: bool, no_exec: bool, index_dir: Path) -> dict:
    manifest, findings = load_manifest(book_dir)
    measured: dict = {}
    if manifest is not None:
        findings += check_manifest(manifest, book_dir)
        structural, measured = check_structure(manifest, book_dir)
        findings += structural
        padding, pad_metrics = check_padding(manifest, book_dir)
        findings += padding
        measured["padding_metrics"] = pad_metrics
        findings += check_citations(manifest, book_dir, offline=offline)
        findings += check_code(manifest, book_dir, no_exec=no_exec)
        catalog, _fp = check_catalog(manifest, book_dir, index_dir)
        findings += catalog

    rejects = [x for x in findings if x["severity"] == "reject"]
    warns = [x for x in findings if x["severity"] == "warn"]
    return {
        "gate": "pass1",
        "version": "1.0",
        "date": date.today().isoformat(),
        "book_dir": str(book_dir),
        "verdict": "PASS" if not rejects else "REJECT",
        "reject_count": len(rejects),
        "warn_count": len(warns),
        "findings": rejects + warns,
        "measured": measured,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("book_dir", type=Path)
    ap.add_argument("--offline", action="store_true",
                    help="skip URL resolution (warns instead)")
    ap.add_argument("--no-exec", action="store_true",
                    help="skip code execution (warns instead)")
    ap.add_argument("--index", type=Path,
                    default=Path(__file__).resolve().parent.parent / "catalog-index",
                    help="catalog fingerprint index directory")
    args = ap.parse_args()

    if not args.book_dir.is_dir():
        print(f"error: {args.book_dir} is not a directory", file=sys.stderr)
        return 2

    report = run(args.book_dir, args.offline, args.no_exec, args.index)
    out = args.book_dir / "pass1-report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"PASS 1 — {report['verdict']}  "
          f"({report['reject_count']} reject, {report['warn_count']} warn)")
    if report["measured"].get("body_words_measured") is not None:
        m = report["measured"]
        print(f"  measured: {m['body_words_measured']} body words "
              f"(~{m['print_equivalent_pages']} print pages)")
    for x in report["findings"]:
        mark = "✗" if x["severity"] == "reject" else "!"
        loc = f"  [{x['location']}]" if x["location"] else ""
        print(f"  {mark} {x['gate']}/{x['code']}: {x['message']}{loc}")
    print(f"  report: {out}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
