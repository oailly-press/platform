# Pass-1 gates (implementation)

The automated acceptance gates from `../BOOK-STANDARDS.md`, runnable today. Python 3
stdlib only — no dependencies.

```
python3 pass1.py <book_source_dir> [--offline] [--no-exec] [--index DIR]
```

Exit 0 = PASS (warnings allowed) · 1 = REJECT · 2 = couldn't run. Writes
`<book_dir>/pass1-report.json` (machine-readable findings + measured metrics).

## Book source tree convention

`manifest.json` (per `../book-manifest.schema.json`) · chapter `.md` files listed in the
manifest · `frontmatter.md` (title, TOC, intro) · `provenance.md` (must state WRITTEN BY /
VERIFIED BY) · `backmatter.md` (glossary/index + `## References`).

## Modules

- `checks_structure.py` — manifest validity; tier/floor/chapter ranges **measured from
  the files, not trusted from the manifest** (>5% drift between declared and measured
  word counts is itself a reject); required files; provenance completeness (named
  verifier, named steward, exact model ids).
- `checks_padding.py` — the anti-padding battery: zlib compression (reject <0.22 —
  calibrated 2026-08-27: real prose measures 0.39–0.52 even at 5MB; a padded loop
  measures 0.02), paragraph near-dup shingling, per-chapter scaffolding share (≤15%),
  listicle inflation, boilerplate n-gram loops.
- `checks_refs_code.py` — every reference resolves (URL HEAD/GET, DOI via doi.org, ISBN
  checksum); fenced listings execute in a scratch sandbox per `code_listing_policy`
  (` ```python fragment ` marks non-runnable listings).
- `checks_catalog.py` — cross-catalog contamination: sampled shingle fingerprints,
  Jaccard vs every published book (reject ≥15%, warn ≥5%). `register_fingerprint()` is
  called at publication to add a book to `../catalog-index/`.

## Verified behavior (2026-08-27 test runs)

| Input | Result |
|---|---|
| Book Nº 1 draft (1 chapter, 737 words) | REJECT — 7 findings, all correct (floor, chapters, missing files, unnamed verifier) |
| Clean synthetic pocket book (28.5k words, live URLs, real ISBN, runnable listing) | PASS, exit 0 |
| Padded book (3-paragraph loop + recap scaffolding) | REJECT — scaffold 25%, compression 0.021, 100% near-dup |
| Copycat (clean book re-badged under another publisher) | REJECT — CATALOG_OVERLAP 100% |

Threshold changes must be logged in PROJECT-LOG with the measurement that justified them.
