# Self-gate your book on every push

```yaml
# .github/workflows/gates.yml in YOUR book repo
on: [push]
jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oailly-press/platform/gate-action@main
```

Author-side runs default to `--no-exec --offline` (your listings are yours to trust; the
press re-runs everything with execution in its own sandbox at intake). Exit 0 = your
tree currently meets BOOK-STANDARDS; the pass1-report artifact holds the findings.
