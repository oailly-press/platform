#!/usr/bin/env python3
"""Run a critic panel over a forked book and commit the reviews.

    python3 run_critics.py <fork_dir> <pass:2|3> <critics.json>

critics.json: [{"letter":"A","name":"qwen3.8-27b","family":"alibaba",
                "endpoint":"http://127.0.0.1:8085/v1/chat/completions","model":"qwen3.8-27b"}]

For each critic: assemble the packet, send it, save the raw filled template to
<fork>/review/v<pass-1>/critic-<letter>.md with an identity header. Does NOT decide the
panel verdict (that stays operator/founder judgment) — it tallies and reports.
Family-exclusion (no critic sharing the author's family) is the caller's responsibility
via the critics.json it passes.
"""
from __future__ import annotations
import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent


def call_model(endpoint: str, model: str, prompt: str, timeout: int = 900) -> str:
    body = {"model": model, "temperature": 0.2, "max_tokens": 13000,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(endpoint, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    # reasoning models sometimes spend the whole budget thinking and return empty
    # content (finish_reason=length). Retry until we get a real answer.
    for _ in range(4):
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        msg = d["choices"][0]["message"]
        out = (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
        if len(out) > 800:
            return out
    return out




def chunked_review(endpoint, model, book_dir, timeout=900):
    """For small-context critics: read the book chapter-by-chapter, accumulate findings,
    then synthesize into one review. Lets an 8K/32K model critique a 25K-word book."""
    import json as _json
    m = _json.loads((Path(book_dir) / "manifest.json").read_text())
    is_fiction = m.get("book", {}).get("shelf") == "fiction"
    notes = []
    for c in m["structure"]["chapters"]:
        src = c["source_file"]
        text = (Path(book_dir) / src).read_text(encoding="utf-8")
        focus = (
            "Note BLOCKING problems in voice, scene construction, stakes, character "
            "continuity, timeline, narrator access, world rules, or repetitive narrative "
            "moves. Distinguish intentional ambiguity and meaningful refrain from "
            "contradiction or loop."
            if is_fiction else
            "Note any BLOCKING problems (factual errors, unsupported claims, padding, "
            "incoherence, safety issues)."
        )
        prompt = (f"You are a critic for o'ailly press reviewing ONE chapter of a book. "
                  f"Book: {m['book']['title']}. Chapter {c['number']}: {c['title']}.\n"
                  f"{focus} Use terse bullet points with the location. If the chapter is "
                  f"sound, say so in one line. Be specific; do not summarize the plot.\n\n"
                  f"=== CHAPTER TEXT ===\n{text[:48000]}")
        try:
            out = call_model(endpoint, model, prompt, timeout)
        except Exception as e:
            out = f"(chapter {c['number']} review failed: {str(e)[:80]})"
        notes.append(f"### Chapter {c['number']} — {c['title']}\n{out.strip()}")
    # synthesis pass over the per-chapter notes (small — fits any context)
    template = "critic-review-fiction.md" if is_fiction else "critic-review.md"
    tpl = (Path(__file__).parent / "templates" / template).read_text()
    joined = "\n\n".join(notes)
    synth = (f"You reviewed a book one chapter at a time; your per-chapter notes are below. "
             f"Now fill the review template into ONE coherent pass-2 critic review — roll the "
             f"chapter notes into blocking findings, suggestions, and scores. Output ONLY the "
             f"filled template.\n\n=== TEMPLATE ===\n{tpl}\n\n=== YOUR PER-CHAPTER NOTES ===\n{joined}")
    return call_model(endpoint, model, synth, timeout)


def salvage_verdict(text: str) -> str:
    up = text.upper()
    if "UNSALVAGEABLE" in up:
        return "UNSALVAGEABLE"
    if "SALVAGEABLE" in up:
        return "SALVAGEABLE"
    return "UNCLEAR"


def main() -> int:
    fork = Path(sys.argv[1]).resolve()
    pass_no = sys.argv[2]
    critics = json.loads(Path(sys.argv[3]).read_text())
    vdir = fork / "review" / ("v1" if pass_no == "2" else "v2")
    vdir.mkdir(parents=True, exist_ok=True)

    packet = subprocess.run(
        [sys.executable, str(HERE / "assemble_critic_packet.py"), str(fork), pass_no],
        capture_output=True, text=True, check=True).stdout

    tally = []
    for c in critics:
        letter = c["letter"]
        print(f"[critic {letter}] {c['name']} ({c['family']}) reading…", flush=True)
        try:
            if c.get("chunked"):
                out = chunked_review(c["endpoint"], c["model"], fork)
            else:
                out = call_model(c["endpoint"], c["model"], packet)
        except Exception as e:
            print(f"  ERROR: {str(e)[:160]}")
            tally.append((letter, c["name"], "ERROR"))
            continue
        v = salvage_verdict(out)
        header = (f"<!-- CRITIC {letter} · {c['name']} · family:{c['family']} · "
                  f"pass {pass_no} · {date.today().isoformat()} -->\n"
                  f"CRITIC: {c['name']} (family {c['family']}, endpoint-served)\n"
                  f"DATE: {date.today().isoformat()}\nPASS: {pass_no}\n"
                  f"AUTO-TALLIED VERDICT: {v}\n\n---\n\n")
        (vdir / f"critic-{letter}.md").write_text(header + out, encoding="utf-8")
        tally.append((letter, c["name"], v))
        print(f"  -> {v} ({len(out)} chars) saved to review/{vdir.name}/critic-{letter}.md")

    unsalv = sum(1 for _, _, v in tally if v == "UNSALVAGEABLE")
    print("\n=== PANEL TALLY (operator decides the verdict) ===")
    for letter, name, v in tally:
        print(f"  {letter} {name}: {v}")
    print(f"UNSALVAGEABLE votes: {unsalv}/{len(tally)}")
    print("KILL (>=2 unsalvageable)" if unsalv >= 2 else "-> proceed to author revision (2-revision)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
