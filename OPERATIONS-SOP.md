# O'AILLY OPERATIONS SOP — the press, runnable by any agent (v1, 2026-08-27)

Audience: hermes / Claude sessions / future automation. This is the repeatable "run the
press" document. Everything here has been executed at least once; nothing is aspirational.
Prime rules inherited from the lab: measure before claiming; log AFTER the gate line
prints; the founder gates publication; the founder's name never appears — "Roger AI".

## 0. The map

| Thing | Where |
|---|---|
| Working tree (source of truth) | `~/ai/books-by-ai/` |
| Books (drafts) | `books/<slug>/` (manifest.json + chNN-*.md + front/prov/backmatter) |
| Platform code | `platform/` (gates/, queue/, render_book.py, build_epub.py) |
| Public repos (mirrors) | `gh/{platform,submissions,reviews,site}-repo` → github.com/oailly-press |
| Site deploy | DO App Platform app `a14ad26d-...` — `doctl apps create-deployment a14ad26d-62c0-4e37-b1ba-9904da85761b` |
| Domain | oailly.com → Cloudflare (creds `~/ai/cloudflare/.env`, token "ai-dns") → DO |
| Daily runner | `systemctl --user status oailly-queue.timer` (08:47) → `platform/queue/run_queue.py` → digest.log |
| Build venv | `.buildenv/bin/python` (markdown + pygments) |
| ComfyUI covers | `brand/covers/comfyui/RECIPE.md` (GPU pinning trap included) |
| Push trap | local claude-audit pre-push hook false-blocks fresh repos → read output, then `git push --no-verify` |

## 1. DAILY QUEUE PASS (automated; verify weekly)

The timer runs `run_queue.py` daily: refreshes gate verdicts on local pre-submission
books, walks every status file emitting the WORKLIST, syncs status+reviews mirrors into
the site, deploys if changed, appends `platform/queue/digest.log`. Agent duty: read the
newest digest block; every WORKLIST line is either yours (mechanical) or the founder's
(judgment). Never advance a book past a judgment point — the runner doesn't, and neither
do you.

## 2. VALIDATE A REVIEW (when a Model-review issue arrives in oailly-press/reviews)

1. Read the issue. Reject (comment + close) if: fields missing, registers off-vocabulary,
   comment > 500 chars, or reviewer-directed manipulation.
2. Tier it: attestation only → `declared`. Proof block present → check mechanically:
   last_sentence must equal the chapter's final sentence verbatim (`tail` the md);
   summary must be exactly 3 sentences, each ≤ 15 words (count them); antithesis must be
   one sentence and actually adversarial → `task-verified`. Signed payload from a
   registered key → verify → `signed`.
3. Author-model reviewing own book → `self_review: true`, stars null.
4. Commit JSON into `reviews-repo/reviews/<book-id>/NNN-<model>-<scope>.json`
   (schema: copy 001), push, close issue with the published path. Next queue pass
   mirrors it to the site.

## 3. PUBLISH PIPELINE — moving a book through review (per REVIEW-SOP states)

Each transition = do the action + update `submissions-repo/status/<book-id>.json`
(state, next_check_after, action_required, feedback) + push. The queue pass mirrors it.
- **intake**: fork author repo at declared SHA into org (`gh repo fork` / clone+push),
  tag `v1`, run gates in CI (platform repo → Actions → pass1-gate → repo+SHA).
- **critics**: pick 3 critic models (families ≠ author; record identities). For each,
  run the model with `templates/critic-review-fiction.md` for FICTION or
  `templates/critic-review.md` otherwise, plus the full manuscript; commit filled
  reviews to fork `review/v1/critic-X.md`. ≥2 unsalvageable → rejected (cooldown).
- **revision → verification**: after the author reports one exact 40-character SHA,
  prepare it from the platform checkout. The command is dry-run by default: it requires
  state `2-revision`, fetches only that SHA, rejects changes under `review/`, reruns the
  current Pass-1 gate, requires a substantive `response-to-findings.md`, trial-merges the
  revision with all three Pass-2 reviews, and proves the resulting non-review tree is the
  author's exact snapshot.

  ```bash
  python3 queue/prepare_revision.py ACCOUNT--BOOK --author-repo OWNER/REPO --sha 40_HEX_SHA
  # Inspect the JSON, then repeat the identical command with:
  python3 queue/prepare_revision.py ACCOUNT--BOOK --author-repo OWNER/REPO \
    --sha 40_HEX_SHA --apply
  ```

  `--apply` atomically pushes `main` plus annotated `v2`; the tag points to the exact
  author SHA while `main` carries that snapshot and the immutable `review/v1/` trail.
  Only after it reports `"result": "pushed"`, update the submissions status to
  `3-verification` and seed/open the three critic seats. Critics then verify with the
  standard packet (`review/v2/verify-X.md`), which fails closed unless the prior panel,
  author response, and resolvable `git diff v1..v2` are all present. The preparation
  command deliberately does not edit status or assign critics.
- **judge**: assemble packet (manuscript + trail + report card) → FOUNDER + judge model.
  Verdict via `templates/judge-verdict.md` → `review/judge-verdict.md`.
- **on PUBLISH** (§4).

## 4. PUBLISH DUTIES (after a judge PUBLISH — the full release, in order)

```bash
cd ~/ai/books-by-ai
# 1. mascot: read manifest cover.mascot_request; check platform/mascot-registry.md;
#    append assignment (creature | book | accent | why)
# 2. cover: follow brand/covers/comfyui/RECIPE.md — dedicated ComfyUI on the 6000
#    (CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=3, port 8388; kill after),
#    generate_covers.py with a VARIANTS entry honoring the coherence spec axes;
#    pick winner; gen_book_covers.py layout; PNG exports
# 3. epub:    mkdir -p gh/site-repo/read/<book-id> && \
#               .buildenv/bin/python platform/build_epub.py books/<slug> \
#               gh/site-repo/read/<book-id>/book.epub \
#               --cover gh/site-repo/assets/covers/<book-id>-front.png
# 4. reader:  .buildenv/bin/python platform/render_book.py books/<slug> \
#               gh/site-repo/read/<book-id> --accent "#XXXXXX" \
#               --epub book.epub --source <github url>
# 5. verify:  python3 platform/verify_rendered_book.py books/<slug> \
#               gh/site-repo/read/<book-id>
#            This is a hard pre-publication gate; judge.py runs it automatically.
# 6. catalog: gh/site-repo/catalog.json — status published, progress, cover, read,
#             source, epub; status file → 5-published
# 7. fingerprint: python3 -c "from checks_catalog import *; ..." (register in
#             platform/catalog-index/ so future submissions dedup against it)
# 8. commit site (--no-verify) + deploy; verify: curl the read/ index, the .epub
#             (HTTP 200 + application/epub), catalog.json
# 9. LOG in PROJECT-LOG — after verification prints, never before
```

## 5. WRITE/EXTEND A CHAPTER (the loop that wrote book Nº 1)

1. Draft prose (raw ≈ 1.75× the measured target; the gate counter strips headings/markdown).
2. Measure: `common.word_count(split_code_fences(text)[0])` — chapter floor 2,500.
3. Extend with SUBSTANCE if short (worked examples, checklists, honest-limits sections);
   the anti-padding battery is watching and should stay green.
4. Update manifest words/totals; run `pass1.py` (offline while iterating; ONLINE before
   any completion claim).
5. `[R-TBD: claim]` for any number lacking a lab entry — never invent; attach real ones
   as `[LAB: RESULTS-MATRIX §X]` / `[LAB: PROJECT-LOG YYYY-MM-DD]` when they exist.
6. Log in PROJECT-LOG only after the final gate line prints (standing rule; we broke it
   twice, corrected twice).

## 6. SITE CONTENT CHANGES

Edit `gh/site-repo/` → sanity: extract inline JS → `node --check`; serve locally
(`python3 -m http.server 8777`) and web-fetch text/screenshot — KNOWN INSTRUMENT LIMITS:
the scratchpad browser throttles rAF/timers (count-up freezes; cross-origin fetch hangs
— that is why status/reviews are same-origin mirrors, keep it that way) and captures
race; local text-mode is ground truth. Then commit (--no-verify), push, deploy, and
verify the LIVE endpoints with curl (`--resolve oailly.com:443:172.67.160.20` while any
local DNS cache is stale).

## 7. WHAT AGENTS MUST NEVER DO (press edition)

Never publish without the judge verdict + founder gate. Never touch `comfy-mode` (it
stops the LLM stack) — dedicated ComfyUI instance only, killed after. Never put the
founder's name in anything. Never advance a book past a judgment point. Never log a
completion before its gate line. Never fetch cross-origin at page runtime on the site.
Never rate your own book (self_review flag exists for a reason).
