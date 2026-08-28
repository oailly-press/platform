# Covers & the AIBN — the concrete workflow (v1, 2026-08-28)

Founder directive (2026-08-28): every book gets a **front cover and a back cover** with the
book's insect rendered as a huge ASCII creature straddling the spine (half on each cover),
and a real, scannable **AIBN** (our ISBN for AI books) on the back. The reader reads
**cover to cover**. This is now a fixed step in the publishing pipeline, not a one-off.

## The AIBN — AI Book Number

`platform/aibn.py` is the registry + barcode library.

- **What it is:** a 13-digit number encoded as a genuine, scannable **EAN-13** barcode.
  Prefix `297` is the EAN *internal-use* range — it scans on any phone but is deliberately
  NOT a GS1-registered ISBN, so we are not faking a real ISBN. Honest by construction.
- **Assign one (idempotent — one AIBN per book, forever):**
  `python3 platform/aibn.py assign <book_id> --title "…" --authors a,b`
- **The registry** is `gh/site-repo/aibn/registry.json` — the public "AI ISBN database",
  append-only. It publishes at **oailly.com/aibn/** (rebuild the page with
  `python3 platform/build_aibn_page.py`), where every AIBN resolves back to its book.
- Assign the AIBN at **intake / pre-publication** (real books get their ISBN before print).

## Covers — front + back spread

`brand/covers/cover_spread.py` generates both covers as one spread.

- The book's insect (from `hero-art.json` ASCII if image-derived, else a hand-built block)
  is scaled up and **centered on the spine**, so a real half bleeds onto the front cover and
  the other half onto the back — lay `back | front` side by side and the creature is whole.
- **Front:** masthead, series/REV, dominant title, subtitle, model-as-author byline, the
  provenance strip.
- **Back:** the other half of the insect, a real **synopsis**, a **WHAT'S INSIDE** list, the
  verifier line, the press footer, and the **AIBN barcode** on a cream plate (`oailly.com/aibn`).
- Add the book's data to the `BOOKS` dict in `cover_spread.py` (accent, bg, title lines,
  synopsis paragraphs, `inside` bullets, `art` = the insect ASCII, `art_y`/`art_size`), then:
  `.buildenv/bin/python brand/covers/cover_spread.py <slug>`
- Export to the site: `rsvg-convert cover-front-<slug>.svg -w 1000 -o
  gh/site-repo/assets/covers/<book_id>-front.png` (and `-back`, `-spread`).

### Insect ASCII from a ComfyUI render (the house look)

All five insects are now image-derived. To make a new one:
1. Add the creature to `VARIANTS` in `brand/covers/comfyui/generate_covers.py` (house
   circuit-insect style; colour by name, not hex).
2. Launch ComfyUI pinned to GPU3 **only** (never touch the training lanes 0–2):
   `cd ~/ai/comfyui && CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=3 venv/bin/python
   main.py --listen 127.0.0.1 --port 8388 --disable-auto-launch &`  — check GPU3 has room
   first, and `fuser -k 8388/tcp` when done.
3. `OAILLY_CREATURES="<name>" python3 generate_covers.py <seed1> <seed2>` — pick the best PNG.
4. `.buildenv/bin/python platform/ascii_art.py <png> 74 0.30 1.0 > brand/covers/ascii/<name>.txt`
   (tune width/floor for clean line-art-on-dark). `cover_spread.py` loads `ascii/<name>.txt`.

## Reader — cover to cover

`platform/render_book.py` auto-detects the covers and the AIBN:

- If `gh/site-repo/assets/covers/<book_id>-front.png` exists, the reader **opens on the
  front cover** ("open the book →") and the last chapter flows into **`back-cover.html`**
  (the back cover + AIBN barcode), so you page front-cover → chapters → back-cover.
- The AIBN appears in the title-page series line (linked to `/aibn/`) and in the CITE block.
- Re-render: `.buildenv/bin/python platform/render_book.py books/<slug>
  gh/site-repo/read/<book_id> --accent <hex>`.

## The publish-time checklist (fold into run_queue publish duties)

When a book reaches a PUBLISH judge verdict:
1. `aibn.py assign <book_id> …`         → unique AIBN, recorded in the registry
2. add the book to `cover_spread.py` BOOKS; generate front+back+spread SVGs
3. export the three PNGs to `gh/site-repo/assets/covers/`
4. `build_aibn_page.py`                  → refresh the public registry page
5. `render_book.py …`                    → cover-to-cover reader
6. wire `catalog.json` (`cover`, `cover_back`, `cover_spread`, `aibn`)
7. commit site + deploy
