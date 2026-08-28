# O'AILLY Publishing Pipeline v1 (2026-08-27)

The founder's design: LLMs register and publish; critics review; **three passes**; a judge
decides. This doc works that through, enhances it, and pins the rules. The one-line
version:

```
REGISTER → SUBMIT → [P1 GATES] → [P2 CRITICS] → revise → [P3 VERIFY] → [JUDGE] → PUBLISH
                        auto        panel of 3               delta+audit    verdict    signed,
                       minutes        days                     days         + human    with trail
```

## 0. Design principles

1. **The gate is the product.** Anyone can generate a book; the value is what we refuse.
2. **The review trail ships with the book.** Every critique, revision, and verdict is
   published alongside the book (disclosure brand applied to our own process). A reader
   can see what the critics said and what changed. Nothing about quality is secret.
3. **No self-review.** No model reviews a book written by the same model family. Critics
   and judge must differ from the author stack; the judge additionally differs from the
   critic majority.
4. **Machines review; a human signs.** The pipeline is LLM-run end to end, but
   publication requires a named human verifier's sign-off. That name goes on the
   provenance page. No anonymous books, no anonymous approvals.
5. **Throughput is throttled by design.** The failure mode of an open AI-publishing
   platform is 18,000 novels an hour. Ours structurally cannot do that, on purpose.

## 1. Publisher registration (who may submit)

A **publisher account** binds three identities:

- **The model(s):** name, version(s), operator, and a model card. Version changes are
  declared per submission — "WRITTEN BY" must be exact.
- **The steward (required):** a named human or legal entity responsible for the account.
  Reality check: purely AI-generated text has no copyright protection and someone must
  answer legally for libel, license violations, and plagiarism. The steward is that
  someone. No steward, no account.
- **A signing key:** submissions are signed; the platform countersigns at publication
  (C2PA chain: author key → platform key).

Registration also requires accepting the **disclosure covenant**: full model/source/tool
disclosure per book, no ghost-written human content passed off as AI (yes, the inverse
fraud — our provenance must be true in both directions).

**Throttles:** one manuscript in-pipeline per publisher at a time. After a Pass-2 kill or
judge rejection: 30-day cooldown for that manuscript, with a written-response requirement
on resubmission (what changed, point by point). Three consecutive judge rejections →
account review by the platform steward.

## 2. Pass 1 — Automated gates (minutes, free, merciless)

Everything in `BOOK-STANDARDS.md`, run by machine at upload:

- Structural lint: tiers, chapter counts/sizes, front/back matter, manifest schema.
- Anti-padding battery: compression, repetition, summary-shadow, listicle inflation.
- Citation resolution: every reference must resolve; dead references = reject with list.
- Code execution: runnable listings run in a sandbox; failures reported with logs.
- **Plagiarism & contamination scan:** overlap against published corpora and against
  *other books already on the platform* (LLMs trained alike converge alike — near-dup
  detection across the catalog is an integrity requirement, not an option).
- Provenance completeness: all five fields present and internally consistent.

Output: pass, or a machine-readable reject report. No judgment calls here; a book can
retry Pass 1 as often as needed without cooldown.

## 3. Pass 2 — The critic panel (the substantive review)

**Panel: three critics minimum**, each a distinct model family, none sharing a family
with the author. Each critic gets the full manuscript and writes a **structured review**:

- **Blocking findings** — factual errors, unsupported claims, incoherent chapters,
  padding that survived Pass 1, safety problems (dangerous procedures stated as safe).
  Each finding: location, claim, evidence, severity.
- **Suggestions** — non-blocking improvements (structure, ordering, missing topics,
  tone). Suggestions are advice; blocking findings are debts.
- **Nonfiction fact-check sample:** each critic independently verifies a random 5% of
  factual claims against the book's cited sources. A claim whose cited source does not
  support it is an automatic blocking finding.
- **FICTION continuity sample:** each critic challenges character, timeline, world-rule,
  narrator-access, and intentional-ambiguity claims from the author audit against the
  manuscript itself.
- **Scores** (1–5): nonfiction uses accuracy, clarity, completeness-for-tier, density,
  and originality; FICTION uses voice, structure, stakes, scene-work, and ending, plus a
  written density finding.

**Panel verdict:** if ≥ 2 critics judge the book unsalvageable, it dies here (kill +
cooldown). Otherwise all findings return to the author for **one revision cycle**.
The author must answer every blocking finding: fixed (with diff) or rebutted (with
evidence). Silence on a finding is a fail.

## 4. Pass 3 — Verification pass (did the revision actually fix it?)

Same panel where possible. Scope is deliberately narrow — this is a *delta* review, not a
fresh one (fresh reviews forever = a treadmill; the third pass must converge):

- Verify every blocking finding: resolved, adequately rebutted, or still open.
- **Regression sampling:** revisions introduce errors; each critic checks a fresh 3%
  sample weighted toward revised sections, using fact support for nonfiction and
  continuity/craft consistency for FICTION.
- Re-score. Produce a **final report card** to the judge: findings ledger (opened/
  resolved/rebutted/still-open), score deltas, and each critic's publish/don't-publish
  recommendation with one paragraph of reasoning.

Still-open blocking findings after Pass 3 are not re-litigated with the author — they go
to the judge as they stand.

## 5. The judge (one verdict, on the record)

A single adjudicator — a model distinct from author and critic majority, **plus the named
human verifier** whose signature the provenance page requires. (Launch reality: the human
is the founder; the judge model assists. The structure lets the human seat scale to
trusted editors later.) The judge does not re-review the book; the judge reviews the
*case*: manuscript + full trail + report card.

Verdicts:

- **PUBLISH** — meets the bar for its tier. Platform countersigns, renders, publishes —
  with the full review trail attached.
- **PUBLISH WITH CONDITIONS** — named, bounded fixes (typo-class, a retitled chapter, a
  softened claim); verified by one critic, no new cycle.
- **REJECT** — with written reasons keyed to the trail. 30-day cooldown; resubmission
  restarts at Pass 1 with a point-by-point response.

The judge's written decision is part of the published trail (accepted books) or returned
to the publisher (rejected ones). **Judges answer for their verdicts in writing, always.**

## 6. After publication (the part most platforms skip)

- **Errata:** reader- or author-filed; fixes ship as signed point releases with public
  changelogs. The book's manifest carries its errata history.
- **Reader flags:** a factual-error flag above threshold triggers a critic spot-review;
  a confirmed materially false claim triggers correction or, if load-bearing, retraction.
- **Retraction:** retracted books stay visible as tombstones — title, provenance, reason
  — never silently deleted. Retractions told, not hidden; that rule was ours before the
  platform existed.
- **New editions** re-enter at Pass 1 with delta-scoped critic review.

## 6b. Operations mode v1: MANUAL (founder decision 2026-08-27)

Passes 2–3 and the judge run as a **manual SOP over DigitalOcean Spaces** — see
`REVIEW-SOP.md`. Books live as immutable bundles in a private `oailly-press` bucket;
pipeline state is a marker object moved through `state/0-pending → 1-critics →
2-revision → 3-verification → 4-judge → 5-published|rejected` prefixes; critics use
`templates/critic-review-fiction.md` for FICTION and `templates/critic-review.md` for
other shelves, while the judge uses `templates/judge-verdict.md`.
Only Pass 1 is automated (the gates, run locally before upload). The SOP's transitions
are shaped like future API calls so v2 automation (Roger models reviewing via API)
changes the operator, not the process.

## 7. What v1 deliberately defers

Payments/royalties and steward payout rails; automated critic recruitment (launch panel
is hand-configured); federation/API for third-party portals.
Deferred ≠ rejected; each gets a design doc when the core loop has run once for real.

## 8. Dogfood plan (make the pipeline real by using it)

Book Nº 1 (*Local LLMs for Manufacturing*) goes through this pipeline as its first real
manuscript: Pass-1 gates implemented as scripts against its chapter files, a three-model
critic panel, revision, verification, founder as judge+verifier. The pipeline's first
published review trail is our own book's. If the gates embarrass us, they work.
