# O'AILLY Book Standards v1 (2026-08-27)

What a submission must be before the review pipeline will even look at it. These are
**acceptance requirements enforced at upload** (Pass 1 of the pipeline runs them
automatically — see `PUBLISHING-PIPELINE.md`).

## 1. Length: it must be a book

Grounding (industry data, 2026-08-27 scan): typical nonfiction runs 40–80k words and
under ~40k "is hard to take seriously"; technical/academic books run 60–120k words
(~200–400 pages); chapters run 8–20 per book, 4–10k words each. O'Reilly's own catalog
spans ~100–200-page pocket references up to 400+-page comprehensive guides — small to
long is fine; *thin* is not.

**Canonical metric is words, not pages** (pages vary with trim size and code density).
Print-equivalent pages (PEP) are computed as words ÷ 300 for display.

| Tier | Words | PEP | Chapters | Modeled on |
|---|---|---|---|---|
| **Pocket** | 25,000 – 45,000 | ~85–150 | ≥ 6 | O'Reilly pocket ref: "the stuff, not the fluff" |
| **Standard** | 45,000 – 90,000 | ~150–300 | 8 – 16 | Typical tech book |
| **Comprehensive** | 90,000 – 160,000 | ~300–530 | 12 – 24 | Definitive guide |

- **Hard floor: 25,000 words.** Below that it is a report or an article, not a book, and
  the platform does not accept it (a separate Reports shelf can exist later, clearly
  labeled — never mixed into the book catalog).
- **Soft ceiling: 160,000 words.** Above it, the judge must find that the length is
  earned; the default recommendation is splitting into volumes.
- Word count = body prose + captions; excludes front/back matter, code listings, and the
  provenance page. **Code cannot be length ballast.**

## 2. The anti-padding covenant (the floor's evil twin)

A minimum length given to LLM authors is an instruction to pad. So the floor is paired
with density gates, and **padding is a Pass-1 reject, not a critique**:

- **Compression test:** near-duplicate paragraph detection and n-gram repetition scoring
  across the manuscript; a book that compresses too well is restating itself.
- **Summary-shadow test:** chapter summaries/intros/outros may not exceed 15% of a
  chapter; "in this chapter we will / in this chapter we learned" scaffolding beyond that
  is padding.
- **Density sampling:** critics score sampled sections for information added per 1,000
  words; a Pocket book earns its tier the way a pocket ref does — by cutting, not by
  running out.
- Listicle inflation (content reformatted as bullets to occupy vertical space), repeated
  boilerplate disclaimers, and re-explained basics in every chapter are all named
  padding patterns and rejected as such.

## 3. Structure: it must be shaped like a book

Required, verified structurally at upload:

1. Front matter: title page, **provenance page** (see §5), table of contents.
2. **≥ 6 chapters** (tier minimums above), each 2,500–12,000 words, each with a stated
   purpose the TOC reflects. One-page "chapters" fail structure.
3. An introduction that states who the book is for and what it assumes.
4. Back matter: glossary or index (≥ 40 entries for Standard+), and a references section
   where **every citation resolves** (URL, ISBN, or DOI — checked automatically).
5. For technical books: runnable listings must run. Code is executed in a sandbox at
   Pass 1; listings that don't execute must be explicitly marked as fragments.

## 4. Human-readable AND machine-readable (both mandatory)

Every book is one canonical source + generated renderings + a manifest:

- **Canonical source:** structured Markdown (CommonMark + tables), one file per chapter,
  UTF-8, no rendering-tool lock-in. This is what critics, judges, and future models read.
- **Human renderings:** EPUB and print-ready PDF generated from source at publication;
  web reader on the portal. A submission that only renders is rejected; a submission
  that only parses is not a book yet.
- **Machine manifest:** `manifest.json` conforming to `book-manifest.schema.json` —
  title, tier, per-chapter word counts, full provenance block, source list, review-trail
  pointers. The manifest is the API surface of the book: a crawler, an agent, or a
  reader app can know what the book is, who wrote it, and what verified it without
  parsing prose.
- **Signing:** the source tree, renderings, and manifest are C2PA-signed at publication.

## 5. The provenance page (unchanged, now enforced)

Required fields, printed in front matter and mirrored in the manifest:
**WRITTEN BY** (models + versions, per chapter if mixed) · **GROUNDED IN** (source list)
· **VERIFIED BY** (named human) · **REVIEW TRAIL** (link to the published review record)
· **C2PA** manifest hash. A book missing any field does not enter review.

## 6. What these standards are not

Not a quality bar — that's the critics' and judge's job (pipeline doc). Standards answer
one question only: *is this artifact a real, honest, well-formed book?* Quality is decided
by review; adequacy is decided here, by machine, in minutes, for free.
