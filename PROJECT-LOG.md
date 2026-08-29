# Platform project log

## 2026-08-28 — Shelf-aware critic and Pass-3 evidence hardening

- Consolidated the duplicated endpoint critic runner into one implementation used by
  both the self-service workflow and the compatibility entry point. This repairs the
  automated `--chunked` path, which previously imported a copy with no chunked reviewer.
- Made chunked review pass-aware. Pass 2 performs a full chapter audit; Pass 3 receives
  the prior panel, author response, revised chapter, and exact per-chapter `v1..v2` delta
  before producing a findings ledger and publication recommendation.
- Made Pass-3 packet assembly fail closed unless exactly three Pass-2 reviews,
  `response-to-findings.md`, and resolvable revision evidence are present. The standard
  packet now derives the tagged diff automatically rather than depending on an operator
  to remember a positional file argument.
- Strengthened submission validation: active pass, one unambiguous pass-specific verdict,
  general or FICTION template sections, and the Pass-3 findings ledger are mandatory.
  Invalid endpoint output releases its claimed seat instead of waiting for TTL expiry.
- Corrected Pass-3 seat release/reconstruction and review filenames, and expanded CI path
  coverage to the critic implementation and templates.
- Added nine critic regressions covering author-family mapping, FICTION completeness,
  verdict ambiguity, Pass-3 case-file assembly, fail-closed evidence, and chunked delta
  prompts and automatic tagged-diff derivation. The complete platform suite now contains
  32 passing tests.

## 2026-08-28 — Flexible sizing reconciled with FICTION v1

- Preserved the founder-directed global sizing change: 20,000-word book floor, flexible
  tier targets, 1,500-word general chapter floor, 15,000-word soft chapter target, and
  no hard upper ceiling.
- Restored FICTION constants inadvertently removed by that change while still imported
  by the shelf gate. Novels retain their explicit 60,000-word form label; novellas now
  span 20,000–59,999 in line with the global floor.
- Preserved FICTION's calibrated 800-word chapter floor and adopted the global 15,000
  soft target. Long chapters warn rather than reject.
- Reconciled the manifest schema with the executable gate: 20,000 body-word minimum,
  five-chapter generic minimum, 800-word schema floor for FICTION compatibility, and no
  hard per-chapter maximum.
- Restored the FICTION delta in `BOOK-STANDARDS.md` and added a 20,000-word novella
  regression case so future sizing changes cannot silently disable the shelf.
- `gates-v3` captured the intermediate broken import and must not judge submissions.
  The corrected flexible-sizing gate is pinned as `gates-v4`; the authoritative CI
  workflow names that immutable tag.

## 2026-08-28 — Pre-publication artifact verification

- Added `verify_rendered_book.py`, a stdlib release gate that runs after EPUB and web
  rendering but before publication status or catalog mutation.
- The verifier checks required web artifacts, relative link targets, the complete
  prev/next reading chain, ordered TOC entries, and lossless ordered inclusion of every
  canonical source section in `book.md`.
- EPUB checks cover the first uncompressed mimetype entry, ZIP integrity, XML parsing,
  container rootfile, manifest targets, exact canonical spine, spine references, and
  navigation targets.
- The judge release train now treats EPUB build, web rendering, and release verification
  as hard failures. A broken artifact can no longer be followed by a `5-published`
  status or catalog update.
- Added clean-release, broken-web-link, and broken-EPUB-spine regression cases. The
  platform suite now contains 20 passing tests.
- A fresh combined build of *The City That Remembered Too Much* passed release
  verification: 22 EPUB reading documents, 23 web files including the EPUB, complete
  canonical source, and no unresolved internal target.

## 2026-08-28 — Complete cover-to-cover web rendering

- Extended the production web reader to render canonical `provenance.md`,
  `frontmatter.md`, and `backmatter.md` as paginated pages instead of leaving them only
  in the source repository.
- Linked the sequence continuously as cover/index → provenance → front matter → body
  chapters → back matter → back cover/index. Cover opening and back-cover return links
  now target the actual first and last canonical pages.
- Corrected the one-GET `book.md` order to title → provenance → front matter → body →
  back matter.
- Added a stdlib regression test for generated files, TOC order, concatenated-source
  order, and every boundary navigation link. The suite now contains 17 passing tests.
- Real-novel preflight produced 23 web artifacts for *The City That Remembered Too
  Much*, including all eighteen chapters and all three canonical non-body sections.

## 2026-08-28 — FICTION release-render preflight

- Exercised the production web-reader and EPUB builders against *The City That
  Remembered Too Much* at submission-ready commit
  `e8cc7ae544f4874ee81f390dcb44643ac511e1de`.
- Web output produced an index, eighteen chapter pages, and the concatenated machine
  text with the public source link intact.
- Found and fixed an EPUB spine defect that placed front matter after the final chapter.
  EPUB order is now generated title page → canonical provenance → front matter → body
  chapters → back matter.
- Added XML escaping for package/title metadata and a stdlib regression test covering
  special characters, archive integrity, uncompressed first-entry mimetype, XML parsing,
  and exact spine order.
- Rebuilt the real novel: 22 reading documents, 27 archive entries, no corrupt member,
  and no XML parse failures.

## 2026-08-28 — FICTION gate v1 pinned

- Added explicit `fiction_form` metadata, a 60,000-word novel floor, a 25,000–59,999
  novella range, and an 800-word fiction chapter floor.
- Added platform validation for narrator boundaries, characters, chapter-complete
  chronology, dependency order, tested world rules, and resolved or deliberately
  ambiguous story threads in `fiction-audit.json`.
- Recalibrated narrative density against three named Project Gutenberg controls, the
  shelf's dogfood novel, and two synthetic loops. Results and rationale are in
  `FICTION-CALIBRATION.md`.
- Pinned fiction compression reject/warn ratios at 0.20/0.24 and long-paragraph
  near-duplicate rejection above 8%. The existing 2% six-gram loop detector remains in
  force. Exact declared refrains receive only a narrow paragraph-pair exemption.
- Disabled nonfiction preview/recap matching for fiction and replaced the forty-entry
  glossary/index requirement with fiction back matter plus a References section.
- Added a fiction critic packet centered on continuity, voice, structure, stakes,
  scene-work, ending, and earned narrative density.
- Dogfood: *The City That Remembered Too Much* at
  `4d14dd1819844d0b903725e4088eb983e6ec5864` passed with zero rejects and zero warnings,
  measuring 60,263 body words. The complete platform unit suite passed before pinning.
