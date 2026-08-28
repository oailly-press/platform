# FICTION gate v1 — calibration and dogfood record

Date pinned: 2026-08-28

The FICTION shelf changes only the rules that do not transfer honestly from technical
nonfiction. Provenance, contamination scanning, manifest checks, human verification,
the critic/judge separation, and the public review trail remain unchanged.

## Pinned artifact contract

A FICTION submission declares `book.shelf: fiction` and `book.fiction_form` as either
`novel` or `novella`. A novel contains at least 60,000 measured body words. A novella
contains 25,000–59,999. Fiction chapters may contain 800–12,000 words; Standard and
Comprehensive fiction does not need a forty-entry glossary or index.

Every submission includes `fiction-audit.json` version 1.0. Platform-owned code checks
that it contains:

- the narrator mode, access rules, and uncertainty policy;
- at least three characters with valid chapter ranges;
- a strictly ordered timeline whose events cover every chapter and whose dependencies
  resolve;
- at least three world rules, each tested in a real chapter; and
- story threads classified as `resolved` or `intentional-ambiguity`.

The audit is a falsifiable map for critics, not authorial proof. The fiction critic form
requires reviewers to compare sampled character, timeline, and world-rule claims with
the manuscript.

## Narrative-density calibration

The calibration harness used the same normalization, paragraph shingles, six-word
n-grams, and zlib level as the gate. Public-domain controls were retrieved as plain text
from Project Gutenberg on 2026-08-28. Word counts below are harness measurements and
may include Gutenberg framing; they are comparative, not catalog metadata.

| Control | Words | zlib ratio | Near-duplicate paragraph share | Top six-gram share |
|---|---:|---:|---:|---:|
| *Frankenstein* ([Gutenberg 84](https://www.gutenberg.org/cache/epub/84/pg84.txt)) | 75,041 | 0.366884 | 0 | 0.0000533 |
| *The Time Machine* ([Gutenberg 35](https://www.gutenberg.org/cache/epub/35/pg35.txt)) | 32,446 | 0.373605 | 0 | 0.0000925 |
| *The War of the Worlds* ([Gutenberg 36](https://www.gutenberg.org/cache/epub/36/pg36.txt)) | 60,029 | 0.371287 | 0 | 0.0000666 |
| *The City That Remembered Too Much* candidate | 60,371 | 0.336146 | 0 | 0.0000497 |
| synthetic exact short-paragraph loop | 7,200 | 0.005218 | 0¹ | 0.08339 |
| synthetic shallow-variation loop | 10,200 | 0.026562 | 0¹ | 0.05885 |

¹ Paragraph shingling intentionally ignores paragraphs shorter than 25 words. Both
synthetic controls are nevertheless rejected independently by compression and the
six-gram loop detector. This is why the density gate keeps multiple detectors.

The pinned FICTION thresholds are:

- compression: reject below 0.20; warn below 0.24;
- near-duplicate long paragraphs: reject above 8%;
- six-word boilerplate loop: unchanged at 2% when repeated more than ten times;
- listicle inflation: unchanged at 55%; and
- nonfiction preview/recap scaffold matching: disabled.

A declared refrain is exempt only from long-paragraph near-duplicate pairing, only at
exact normalized text, and only when `fiction-audit.json` supplies both its text and
purpose. It remains visible to compression and n-gram checks. This permits deliberate
recurrence without creating a general repetition waiver.

## End-to-end dogfood

The complete novel *The City That Remembered Too Much* passed the offline author gate
at immutable commit `4d14dd1819844d0b903725e4088eb983e6ec5864`:

- verdict: PASS; zero rejects, zero warnings;
- canonical body words: 60,263 (about 201 print-equivalent pages);
- 18 of 18 chapters covered by ordered timeline events;
- 6 characters, 10 tested world rules, and 12 classified story threads;
- compression ratio 0.336; near-duplicate paragraph share 0;
- top six-gram share 0.00005; and
- five declared refrains, with no detector bypass beyond exact paragraph pairing.

The committed `pass1-report.json` in that manuscript is the dogfood artifact. Passing
this gate establishes intake eligibility, not literary quality. Three independent
critics, revision verification, a distinct judge, and a named human verifier remain
mandatory before publication.

## Limits and recalibration rule

The public-domain control set is small, English-language, and weighted toward older
speculative prose. Compression varies with language, typography, dialogue density, and
experimental form. A future false reject must be investigated with an expanded named
control set; thresholds may change only with measurements recorded in `PROJECT-LOG.md`
and a regression test that retains synthetic-loop rejection.
