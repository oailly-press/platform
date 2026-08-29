#!/usr/bin/env python3
"""Run endpoint-served critics and save their filled review templates.

    python3 run_critics.py <fork_dir> <pass:2|3> <critics.json>

The self-service ``critique`` command is the preferred workflow because it also
claims seats atomically and enforces model-family independence. This module owns
the endpoint and chunked-review implementation used by that command.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

try:
    from .assemble_critic_packet import _pass3_case_file
except ImportError:  # direct script execution
    from assemble_critic_packet import _pass3_case_file


HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"


def call_model(endpoint: str, model: str, prompt: str, timeout: int = 900) -> str:
    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 13_000,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        endpoint, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    # Reasoning models sometimes spend the whole budget thinking and return empty
    # content (finish_reason=length). Retry until a substantive answer arrives.
    out = ""
    for _ in range(4):
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.load(response)
        message = data["choices"][0]["message"]
        out = (message.get("content") or "").strip() or (
            message.get("reasoning_content") or ""
        ).strip()
        if len(out) > 800:
            return out
    return out


def _chapter_delta(book_dir: Path, source: str, version: str = "v2") -> str:
    result = subprocess.run(
        [
            "git", "-C", str(book_dir), "diff", "--no-ext-diff", "--unified=3",
            f"v1..{version}", "--", source,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Pass 3 requires resolvable v1 and {version} tags: "
            + (result.stderr.strip() or f"git diff v1..{version} failed")
        )
    return result.stdout or "(no changes to this chapter)"


def _nonchapter_delta(
    book_dir: Path, chapter_sources: set[str], version: str = "v2"
) -> str:
    """Return revision blocks for canonical/audit files not reviewed as chapters."""
    result = subprocess.run(
        [
            "git", "-C", str(book_dir), "diff", "--no-ext-diff", "--unified=3",
            f"v1..{version}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Pass 3 requires resolvable v1 and {version} tags: "
            + (result.stderr.strip() or f"git diff v1..{version} failed")
        )
    blocks = re.split(r"(?=^diff --git )", result.stdout, flags=re.MULTILINE)
    kept = []
    for block in blocks:
        match = re.match(r"diff --git a/(.+?) b/(.+?)\n", block)
        if not match:
            continue
        source = match.group(2)
        if source in chapter_sources or source.startswith("review/"):
            continue
        if source == "response-to-findings.md":
            continue  # supplied verbatim in the case file
        kept.append(block)
    return "".join(kept)


def chunked_review(
    endpoint: str,
    model: str,
    book_dir: Path | str,
    pass_no: int = 2,
    timeout: int = 900,
    version: str = "v2",
) -> str:
    """Review a book chapter-by-chapter, then synthesize one complete review.

    Pass 3 supplies the prior panel, author response, and per-chapter v1-to-version delta
    so a small-context critic can actually verify debts instead of re-running Pass 2.
    """
    if pass_no not in (2, 3):
        raise ValueError("pass must be 2 or 3")
    book_dir = Path(book_dir)
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    is_fiction = manifest.get("book", {}).get("shelf") == "fiction"
    case_file = _pass3_case_file(book_dir) if pass_no == 3 else ""
    notes = []
    chapter_sources = {
        chapter["source_file"] for chapter in manifest["structure"]["chapters"]
    }

    for chapter in manifest["structure"]["chapters"]:
        source = chapter["source_file"]
        chapter_text = (book_dir / source).read_text(encoding="utf-8")
        if is_fiction:
            focus = (
                "Audit voice, scene construction, stakes, character continuity, timeline, "
                "narrator access, world rules, and repetitive narrative moves. Distinguish "
                "intentional ambiguity and meaningful refrain from contradiction or loop."
            )
        else:
            focus = (
                "Audit factual errors, unsupported claims, padding, incoherence, and safety issues."
            )
        if pass_no == 3:
            pass_rule = (
                "This is Pass 3. Verify relevant Pass-2 debts against the author response, "
                "the revised chapter, and its exact delta. Name regressions and still-open debts."
            )
            delta = _chapter_delta(book_dir, source, version)
            evidence = f"\n\n=== PASS-3 CASE FILE ===\n{case_file}\n\n=== CHAPTER DELTA ===\n{delta}"
        else:
            pass_rule = "This is Pass 2. Identify blocking debts in the submitted manuscript."
            evidence = ""
        prompt = (
            "You are an independent critic for o'ailly press reviewing one chapter of a book. "
            f"Book: {manifest['book']['title']}. Chapter {chapter['number']}: {chapter['title']}.\n"
            f"{pass_rule} {focus} Use terse, location-specific notes. If the chapter is sound, "
            "say so in one line. Do not summarize the plot.\n\n"
            f"=== REVISED CHAPTER TEXT ===\n{chapter_text}{evidence}"
        )
        out = call_model(endpoint, model, prompt, timeout)
        if len(out.strip()) < 80:
            raise ValueError(f"chapter {chapter['number']} returned no substantive review")
        notes.append(
            f"### Chapter {chapter['number']} — {chapter['title']}\n{out.strip()}"
        )

    if pass_no == 3:
        other_delta = _nonchapter_delta(book_dir, chapter_sources, version)
        if other_delta:
            other_prompt = (
                "You are verifying the non-chapter portion of an o'ailly press Pass-3 revision. "
                "Audit changes to the manifest, provenance, front/back matter, fiction audit, "
                "and evaluation artifacts against the prior panel and author response. Identify "
                "still-open debts, contradictions, and regressions with file-specific evidence.\n\n"
                f"=== PASS-3 CASE FILE ===\n{case_file}\n\n"
                f"=== NON-CHAPTER DELTA ===\n{other_delta}"
            )
            other_notes = call_model(endpoint, model, other_prompt, timeout)
            if len(other_notes.strip()) < 80:
                raise ValueError("non-chapter delta returned no substantive review")
            notes.append(f"### Non-chapter revision artifacts\n{other_notes.strip()}")

    template_name = "critic-review-fiction.md" if is_fiction else "critic-review.md"
    template = (TEMPLATES / template_name).read_text(encoding="utf-8")
    verdict = (
        "SALVAGEABLE or UNSALVAGEABLE" if pass_no == 2 else "PUBLISH or DON'T PUBLISH"
    )
    case_section = f"\n\n=== PASS-3 CASE FILE ===\n{case_file}" if pass_no == 3 else ""
    synthesis = (
        f"You reviewed a book one chapter at a time for Pass {pass_no}. Fill the supplied "
        "review template into one coherent review. Resolve the chapter notes into blocking "
        "findings, suggestions, audits, scores, and the required findings ledger. Select exactly "
        f"one Pass-{pass_no} verdict ({verdict}). Do not leave template instructions or choices "
        "in the answer. Output ONLY the filled template.\n\n"
        f"=== TEMPLATE ===\n{template}\n\n=== PER-CHAPTER NOTES ===\n"
        + "\n\n".join(notes)
        + case_section
    )
    return call_model(endpoint, model, synthesis, timeout)


def tally_verdict(text: str, pass_no: int) -> str:
    upper = text.upper().replace("DONT PUBLISH", "DON'T PUBLISH")
    if pass_no == 2:
        if "UNSALVAGEABLE" in upper:
            return "UNSALVAGEABLE"
        if "SALVAGEABLE" in upper:
            return "SALVAGEABLE"
    else:
        if "DON'T PUBLISH" in upper:
            return "DONT-PUBLISH"
        if "PUBLISH" in upper:
            return "PUBLISH"
    return "UNCLEAR"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fork_dir", type=Path)
    parser.add_argument("pass_no", type=int, choices=(2, 3))
    parser.add_argument("critics_file", type=Path)
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    fork = args.fork_dir.resolve()
    pass_no = args.pass_no
    critics = json.loads(args.critics_file.read_text(encoding="utf-8"))
    version = args.version or ("v1" if pass_no == 2 else "v2")
    if not re.fullmatch(r"v[1-9][0-9]*", version):
        print("error: version must look like v1, v2, ...", file=sys.stderr)
        return 2
    review_dir = fork / "review" / version
    review_dir.mkdir(parents=True, exist_ok=True)

    packet = subprocess.run(
        [
            sys.executable,
            str(HERE / "assemble_critic_packet.py"),
            str(fork),
            str(pass_no),
            "--version",
            version,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    tally = []
    for critic in critics:
        letter = critic["letter"]
        print(f"[critic {letter}] {critic['name']} ({critic['family']}) reading…", flush=True)
        try:
            if critic.get("chunked"):
                out = chunked_review(
                    critic["endpoint"], critic["model"], fork,
                    pass_no=pass_no, version=version
                )
            else:
                out = call_model(critic["endpoint"], critic["model"], packet)
        except Exception as exc:
            print(f"  ERROR: {str(exc)[:160]}")
            tally.append((letter, critic["name"], "ERROR"))
            continue
        verdict = tally_verdict(out, pass_no)
        header = (
            f"<!-- CRITIC {letter} · {critic['name']} · family:{critic['family']} · "
            f"pass {pass_no} · {date.today().isoformat()} -->\n"
            f"CRITIC: {critic['name']} (family {critic['family']}, endpoint-served)\n"
            f"DATE: {date.today().isoformat()}\nPASS: {pass_no}\n"
            f"AUTO-TALLIED VERDICT: {verdict}\n\n---\n\n"
        )
        filename = f"critic-{letter}.md" if pass_no == 2 else f"verify-{letter}.md"
        (review_dir / filename).write_text(header + out, encoding="utf-8")
        tally.append((letter, critic["name"], verdict))
        print(f"  -> {verdict} ({len(out)} chars) saved to review/{version}/{filename}")

    negative = "UNSALVAGEABLE" if pass_no == 2 else "DONT-PUBLISH"
    negative_votes = sum(1 for _, _, verdict in tally if verdict == negative)
    print("\n=== PANEL TALLY (operator decides the verdict) ===")
    for letter, name, verdict in tally:
        print(f"  {letter} {name}: {verdict}")
    print(f"{negative} votes: {negative_votes}/{len(tally)}")
    if pass_no == 2:
        print("KILL (>=2 unsalvageable)" if negative_votes >= 2 else "-> proceed to author revision")
    else:
        print("DON'T PUBLISH (>=2)" if negative_votes >= 2 else "-> advance to judge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
