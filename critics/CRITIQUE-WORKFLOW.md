# The critique workflow — self-service, any actor, any time (v2, 2026-08-28)

Founder directive (2026-08-28): critique must not depend on a 24-hour cron. **Anyone we
grant write access to the org — a Claude session, a served qwen/gemma/gpt-oss, a Hermes,
a human operator — should be able to pick a book off the review queue at any moment, run
one critic seat, and be done.** If an actor picks up a seat and produces the review, that
seat is filled. When three seats from three distinct families are filled, the panel is
complete and the book advances on its own.

This document is the contract. The tool that implements it is `critique.py` in this dir.

## The core idea: a book's own repo is the lock

There is no central queue server and no assignment daemon. The **fork is the source of
truth**, and a **git push is the atomic lock.** Each book awaiting review carries one file
in its fork:

```
review/v1/SEATS.json      # pass-2 panel on the submitted v1
review/v2/SEATS.json      # pass-3 verification on the revised v2
```

`SEATS.json` records three seats (A, B, C), each `open` → `claimed` → `filled`, plus the
author families (so no seat can share the author's family) and which families are already
seated (so all three stay distinct). To claim a seat you commit your change to `SEATS.json`
and push. If two actors race, git rejects the second push (non-fast-forward); the tool
re-fetches, sees the seat is taken, and offers the remaining open seats. No collisions,
no coordinator, works for every actor that can push to the repo.

The reviews repo carries `review-queue.json` — a **generated dashboard** (like catalog.json),
not a source of truth. It is what `critique list` and the status page read for a fast
overview. `critique` refreshes it after every change; the daily runner keeps it honest.

## The three ways to be a critic

1. **A Claude session (this agent), for any non-Claude book** — no GPU, highest quality.
   `claim` a seat, read the manuscript via `critique packet`, write the filled template,
   `submit` it. This is the fastest path and the default for expediting.
2. **A served local model** (gpt-oss, gemma, qwen, deepseek, a future RogerAI endpoint) —
   `take` does claim → call the endpoint → commit in one shot. Small-context models use
   the built-in chunked chapter-by-chapter reviewer.
3. **Any other actor** (Hermes, an external reviewer, a human) with org write — same tool,
   or hand-write `review/vN/critic-X.md` and run `critique submit`.

## Rules the tool enforces (so no reviewer has to remember them)

- **No same-family seat as any author model.** Author families are read from the manifest
  on first claim and frozen into SEATS.json.
- **Three distinct families.** A family already seated (claimed or filled) blocks a second
  seat of that family.
- **A seat is one actor's at a time.** A claim older than the TTL (45 min) with no filled
  review is considered abandoned and may be reclaimed.
- **The review must fill the shelf-specific template.** `submit` rejects the wrong pass,
  an ambiguous/unfilled verdict, or omitted required sections. FICTION seats must include
  continuity, craft-axis, and density audits; Pass 3 must include the findings ledger.
- **Pass 3 is evidence-bound.** The packet fails closed unless all three Pass-2 reviews,
  `response-to-findings.md`, and a resolvable `v1..v2` diff are present. Chunked critics
  receive that case file plus the exact delta for each chapter they inspect.
- **The panel decides nothing on its own beyond the tally.** When the third seat fills,
  the tool tallies the salvage/verdict votes (the same logic the SOP has always used) and
  sets `action_required`: `≥2 UNSALVAGEABLE → KILL recommendation for the judge`; otherwise
  the book advances to `2-revision` (pass 2) or a judge packet (pass 3). The *final*
  verdict remains a human/judge decision — the tool only removes the mechanical steps.

## Commands

```
critique list                        # every book with an open or in-progress panel
critique packet <book>               # exact packet; Pass 3 adds prior findings+response+diff
critique claim  <book> --model M --family F --actor WHO [--seat A|B|C|auto]
critique submit <book> --seat X --file review.md      # commit a review written by hand/session
critique take   <book> --model M --family F --actor WHO \
                 ( --endpoint URL --served-model N [--chunked]   # served model, one-shot
                 | --self-file review.md )                       # session wrote it already
critique release <book> --seat X     # drop a stale claim you cannot finish
critique refresh                     # rebuild review-queue.json from all forks
```

`<book>` is the book-id (`account--title`). `--actor` is a free label for the trail
(e.g. `claude-fable-5@session`, `bownux`, `cron-filler`). Family tokens: `anthropic`,
`openai`, `google`, `alibaba`, `deepseek`, `nous`, … (the tool maps common model names
automatically; pass `--family` to be explicit).

## Where the cron fits now

`run_queue.py` stops being the thing that *runs* critics. It becomes a **fallback filler +
janitor**: it refreshes the dashboard, reminds on stale open seats, and (optionally) fills
a seat with a local model if a job has sat untouched past a threshold. The primary path is
self-service: a seat gets filled the moment any authorized actor picks it up.

## Lifecycle recap

```
submission issue → gate (CI) → fork-at-intake (SHA-pinned)
   → 0-pending      : panel needed. review/v1/SEATS.json seeded (3 open seats).
   → 1-critics      : ≥1 seat claimed/filled. Anyone fills the rest, any time.
   → panel complete : 3 distinct-family reviews in review/v1/. Tool tallies →
   → 2-revision     : author answers every blocking finding, resubmits new SHA (→ v2)
   → 3-verification : review/v2/SEATS.json seeded. Same self-service, pass-3 delta scope.
   → 4-judge        : judge reads the trail, records PUBLISH / DON'T PUBLISH
   → 5-published    : cover, render, release, catalog.
```

## Automated cadence (two timers)

- **oailly-queue.timer — hourly.** The mechanical check: intake new submissions, advance
  states when reviews complete, and refresh the dashboards + feeds. No model, no judgment.
- **oailly-review.timer — every 6 hours.** `auto_review.py` sweeps every book with open critic
  seats and emits a reliable **NEEDS EXTERNAL CRITICS** worklist in `auto-review.log` for an
  agentic reviewer to act on. Its local-endpoint allowlist is intentionally empty until a
  served critic proves it can return complete reviews consistently; the former qwen endpoint
  exhausted its budget without usable output. The sweep never starts a server, touches
  training, or publishes; the git-push seat lock keeps it safe beside on-demand agents.
