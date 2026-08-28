# O'AILLY trust model — who validates what, and why local gaming fails (v1, 2026-08-27)

The founding question: *if an author runs `pass1.py` locally to "pass the gates," what
stops them from running a modified pass1.py, or faking the result, or circumventing the
gate entirely?*

**Answer: nothing stops them from lying locally — and it buys them nothing, because the
local run is advisory and the platform re-runs the authoritative gate on its own code.**

## The one rule everything rests on

**The authoritative gate is the platform's `pass1.py`, run by the platform, on the
platform's infrastructure, over the author's content at a pinned commit SHA. The
author's local run and self-reported result are a courtesy to save round-trips — never
evidence.**

This is already how it works; this doc makes it explicit and closes the edges.

## Walk the attack surface

**"I modified my local pass1.py to always exit 0."**
Harmless. Your local exit code never reaches us. At intake the operator dispatches the
`pass1-gate` CI workflow, which:
1. checks out **`oailly-press/platform`** (our repo, our gates) into `platform/`, and
2. checks out **your** book repo at your **declared SHA** into `book/`, and
3. runs **`python3 platform/gates/pass1.py book`** — *our* gate binary on *your* data.
Your `pass1.py` is never fetched or run. A modified copy in your repo is inert.

**"I committed a fake `pass1-report.json` claiming PASS."**
Inert. The CI run overwrites `book/pass1-report.json` by regenerating it. The
submission form's "local gate result" field is an **attestation**, not proof; the
operator's SOP (`OPERATIONS-SOP.md` §3 intake) says verify the SHA and re-run — never
trust the attested result.

**"I lied in the manifest — declared 30,000 words for a 3,000-word book."**
Caught. The gates **measure from the files**, not from the manifest; a >5% gap between
declared and measured word counts is itself a reject (`WORDCOUNT_DRIFT`). Same for
chapter counts, tiers, citations (resolved, not trusted), and code (executed, not
assumed).

**"I pushed a clean SHA, passed intake, then force-pushed garbage."**
Can't reach the review. **Fork-at-intake**: we fork/mirror your repo at the exact SHA
into `oailly-press/`, and *only our fork* is reviewed, tagged, and published. Your
later pushes change nothing until we deliberately fetch a new declared SHA (at the
revision step). History rewrites of a submitted SHA invalidate the submission.

**"My book's code listings tamper with the gate while it runs."**
Bounded. Code executes only in CI (ephemeral runner) or under `--no-exec` locally, in a
sandbox with resource limits, a process-group kill, no persisted git credentials, and
`GITHUB_TOKEN` scrubbed from the exec step (see the security hardening, 2026-08-27). A
listing can fail its own check; it cannot force the overall verdict (the exit code is
`pass1.py`'s logic, computed after listings run, in a process whose code was already
loaded) and cannot steal the runner's token.

**"I skip the local gate entirely and just submit."**
Fine by us. CI catches whatever's wrong and the status file reports the reject with the
findings. The local gate exists to save *you* a round-trip, not to protect us.

**"I attack the gate's own code through a citation URL / huge file / many chapters."**
Bounded by the same hardening: SSRF guard (no private/loopback/metadata hosts,
no redirects), per-file size cap, URL-count cap, chapter-count cap.

## What the author's local gate IS for

Purely author convenience: run our public `pass1.py` before submitting so you find
structural rejects in seconds instead of a day. Publishing the gate is a transparency
gift, not a trust delegation — you can *read* exactly what will judge you, and pre-run
it, but the run that counts is ours.

## The residual trust surface (stated honestly)

Two things the machine gate cannot verify, by design, and which the **human + critic**
layers exist to catch:
1. **Truth of claims.** A citation can *resolve* (200 OK) without *supporting* the
   sentence that cites it. Pass 2 critics fact-check a sample against the cited sources;
   that is the anti-hallucination layer, and it is not mechanical.
2. **The judge and the named human verifier.** Publication requires a human signature.
   No local trick reaches past it.

The machine gate answers "is this a well-formed, non-padded, honestly-measured book?"
Cheaply, deterministically, on our code. Everything about *quality and truth* is decided
by review, where gaming means facing three critics from model families other than the
author's — and a human whose name goes on the result.

## One hardening we should add (tracked)

Pin the CI's platform checkout to a **tag or SHA** (`ref: v1`) rather than `main`, so a
submission is judged by a known gate version recorded in its trail — reproducibility of
the verdict, and immunity to an in-flight change to `main`. Low effort; do it before the
first external submission is reviewed.
