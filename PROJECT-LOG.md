# Platform project log

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
