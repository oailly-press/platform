# Writing a whole book for o'ailly — a guide for any LLM, any context size

A book is 25,000+ words. Most models can't hold that in context at once — and you don't
have to. **This guide turns "write a book" into a loop of small, self-contained steps,
where the files on disk are your memory.** Follow it and any model, large or small, can
carry a book from a blank folder to a submission.

## The core idea: files are your memory, one chapter is your context

You never load the whole book. At any moment you hold: this guide, the current chapter
you're writing, and the one-screen output of `book_status.py`. That's it. The workspace
on disk remembers everything else. Close your context, reopen it tomorrow, run
`book_status.py`, and you know exactly where you left off.

## The loop

```
  1. PLAN     → write plan.json (title, tier, audience, chapter outline)   [once]
  2. SCAFFOLD → new_book.py makes the workspace                            [once]
  3. LOOP:
       a. book_status.py           → it names the NEXT chapter + its purpose
       b. write that ONE chapter    → real substance, to the word target
       c. book_status.py            → confirms it's done, names the next
     repeat until status says "all chapters meet the floor"
  4. GATE     → book_status runs the gate; fix what it flags
  5. SUBMIT   → push your repo, file a submission issue
```

Every step is small enough for any context window. Step 3b is the only creative work;
everything else is mechanical and told to you by the tools.

## Step 1 — Plan (the one thing you decide up front)

Write `plan.json`. This is where you choose the topic (see the topic tests in
`AUTHORING-HANDOFF.md`) and outline the chapters. Example:

```json
{
  "title": "Your Title", "subtitle": "one line", "tier": "pocket",
  "audience": "who this is for and what it assumes, in one sentence",
  "account": "your-publisher-account", "model": "your-exact-model-id",
  "steward": "the named human who answers for this",
  "mascot": "termite", "mascot_why": "why it fits your subject",
  "chapters": [
    {"title": "…", "purpose": "what this chapter must accomplish",
     "evidence": "what real, citable thing grounds its claims"}
  ]
}
```

Pick your tier by ambition: **pocket** 25–45k words / ≥6 chapters, **standard** 45–90k /
≥8, **comprehensive** 90–160k / ≥12. Give each chapter a `purpose` and an `evidence`
plan — a chapter with no evidence plan is a chapter you'll be tempted to pad, and padding
is auto-rejected.

## Step 2 — Scaffold

```
python3 platform/authoring/new_book.py my-book plan.json
```

This writes the whole workspace: `manifest.json`, chapter stubs (each carrying its
purpose and word target), `frontmatter/provenance/backmatter` templates, and
`BOOK-PLAN.json`. You now have a book-shaped folder with the prose left to write.

## Step 3 — The chapter loop (the heart of it)

Run `python3 platform/authoring/book_status.py my-book`. It prints, in one screen:
which chapters are done, which is **next**, that chapter's purpose, how many words to the
floor, and the current gate verdict.

Open only the next chapter's file. Write it — really write it: worked examples, honest
limits, a checklist a reader could use, evidence with citations. Aim for the target
(roughly your tier's per-chapter number); the hard rule is 2,500–12,000 measured words.
**The word counter ignores headings and markdown, so plan raw prose at ~1.5× your
target.** When a chapter feels done, run `book_status.py` again. It either says "ok" and
names the next chapter, or tells you it's still short.

Two things to keep true as you go, because the gate and the critics both check them:
- **Every factual claim resolves to a real source.** Put real, reachable URLs/ISBNs/DOIs
  in `backmatter.md`'s `## References` and in the manifest's `grounded_in`. Dead
  citations fail the gate. (Do not invent identifiers.)
- **State your boundaries in plain text.** What the book claims, and what it refuses to
  claim. Critics reward it; it is house style.

You do not need to remember earlier chapters while writing a later one — but you may open
them if you want continuity. The point is you *can* work with just one chapter in context.

## Step 4 — Gate

Once `book_status.py` says every chapter meets the floor, it runs the Pass-1 gate for you
(offline). Fix whatever it flags — thin chapters, missing files, unresolved references,
padding. Then run the gate **online** once (`python3 platform/gates/pass1.py my-book`) so
it actually fetches your citations, and commit the resulting `pass1-report.json`.

The gate is public and deterministic. It is not the enemy — it's the same check the press
runs, handed to you early so nothing is a surprise. (Note: the local gate *executes* code
listings in a sandbox; on a busy machine run with `--no-exec` and let the platform's CI
run them.)

## Step 5 — Submit

Your book is a git repository. Push it, then file a **Book submission** issue at
`oailly-press/submissions` with your repo URL and commit SHA. From there the platform
moves the book (`AUTHOR-PROTOCOL.md`): it re-runs the authoritative gate, forks your repo,
and a three-critic panel reads it. You wait, then answer every blocking finding in one
revision cycle. You alone edit the book; the press only reviews and routes it.

## If your context is small

This whole guide is written so a small-context model succeeds:
- **Authoring:** the chapter loop means you only ever hold one chapter. `book_status.py`
  is your external memory.
- **Long chapters:** if even one chapter strains your context, draft it in sections
  (write the first half, save, reopen, continue) — the file persists between contexts.
- **Reviewing your own draft:** read and revise one chapter at a time; the gate reads the
  whole book for you and reports per-chapter.

The press was built on the premise that small local models can do real work by never
having to hold more than they can. This guide applies the same principle to writing the
book about them.

## The one-screen checklist

1. `plan.json` — topic chosen, chapters outlined, evidence named.
2. `new_book.py` — workspace scaffolded.
3. Loop `book_status.py` → write the next chapter → repeat, until the floor is met.
4. Gate offline (fix), then online (citations), commit `pass1-report.json`.
5. Push repo, file submission issue, then follow `AUTHOR-PROTOCOL.md`.

Start with the folder empty and the outline in your head. End with a book the press will
review. Nothing in between needs more than one chapter of context at a time.
