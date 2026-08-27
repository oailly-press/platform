# Git-native, static-first architecture (v1.1 direction, 2026-08-27)

Founder question: instead of "uploading," books as GitHub repos in an LLM/multi-agent-
friendly format — and the whole platform with **no backend**, a static page on DO, near-
zero hosting cost. Worked through below. Short answer: yes, and it's not a compromise —
git makes three parts of the pipeline *better* while dropping cost to ~$0.

## 1. Format: Markdown stays canonical (decided by the multi-agent test)

| Candidate | Multi-agent merge/diff | LLM native | Toolchain | Verdict |
|---|---|---|---|---|
| **Markdown + manifest.json** | Line-diffable, chapter-per-file merges cleanly | The format LLMs read/write best | None needed | **Canonical source** (already BOOK-STANDARDS §4) |
| LaTeX | Merges poorly (macro state, one-line paragraphs), compile chain to review | Fine | TeX stack | Rejected as source; math via Markdown `$…$` (pandoc) |
| EPUB | A zip of XHTML — undiffable | Poor | — | **Build artifact**, never source |
| PDF | Binary | Poor | — | Build artifact |

Publication builds: `pandoc` Markdown → EPUB + print PDF at the judge-PUBLISH step.
Nothing about BOOK-STANDARDS changes; git just confirmed the choice.

## 2. Submission: a git repo IS the upload

The author "shares an endpoint": a git repo (GitHub v1) containing the book source tree
(manifest.json at root, chapter files, front/back matter — same tree the gates already
read). What this buys over tarball upload:

- **Versions are tags.** v1/v2/v3 = git tags on *our* fork; commit SHAs replace checksum
  bookkeeping; signed commits slot into the C2PA story.
- **Pass 3 becomes `git diff v1..v2`.** The delta review — the pass hardest to do well —
  gets its exact scope mechanically. Critics see precisely what changed; regression
  sampling weights by the diff. This is the biggest pipeline win.
- **The review trail becomes literal git history.** Critic reviews, author responses,
  and the verdict are commits in a `review/` directory of our fork. "The trail ships
  with the book" stops being a promise and becomes the repo.
- **Multi-agent native.** Author fleets already work in branches/PRs; the revision +
  response-to-findings is a branch we tag.

**The one hard rule: fork-at-intake.** The author's repo is theirs to force-push or
delete. At submission we fork/mirror into the platform org (`oailly-press/<book-id>`)
and **only our fork is ever reviewed, tagged, or published**. Every pass pins a SHA.
Author pushes updates to their repo; we fetch into the fork only at defined moments
(intake, revision). Nothing the author does after a fetch changes what critics saw.

- Public repos by default (radical transparency fits the brand: the book *and* its
  review happen in the open). Private submissions supported via collaborator invite;
  they become public at publication — the trail publishes, always.

## 3. No backend: what each pipeline function becomes

| Function | Old design (Spaces + presigned URLs) | Git-static design | Backend needed? |
|---|---|---|---|
| Submission intake | Presigned PUT, manual slot issuance | Issue on `oailly-press/submissions` with repo URL + SHA (GitHub = the mailbox; agents file issues via API) | No |
| Version integrity | SHA-256 bookkeeping | Fork + tag + commit SHA | No |
| status.json polling | Objects we hand-edit in a bucket | **Static file** in the submissions repo / portal site; author polls a raw URL | No |
| Feedback delivery | Presigned GETs | Commits in the fork's `review/` dir (public at release points) | No |
| Pass-1 gates | Run locally by operator | **GitHub Actions on the fork** — pass1.py runs in CI, free for public repos, report as artifact + status badge | No (and it's automation we get for free) |
| Critic/judge passes | Manual SOP | Unchanged manual SOP — reviews are commits instead of rclone uploads | No |
| Portal/catalog | — | **Static site**: generated pages from published forks (catalog.json + book pages + trails), deployed to DO App Platform static (free tier) with oailly.com on it; GitHub Pages as fallback/mirror | No |
| EPUB/PDF downloads | Spaces objects | **GitHub Releases** on the published fork (free bandwidth) — portal links to them | No |
| Payments (later) | — | The one thing that eventually needs a backend or a merchant-of-record (Stripe Payment Links / Gumroad-class) — deferred, doesn't block v1 | Later |

**Cost: ~$0/month.** GitHub free tier (public repos, Actions, Releases) + DO App
Platform free static tier for the portal + the already-owned domain. DO Spaces drops to
*optional* cold archive ($5/mo min — skip it until there's revenue; git history is
already the archive, and a periodic `git clone --mirror` to a local disk covers the
GitHub-goes-away risk for free).

**Resource honesty (founder's worry):** this is the *cheap* direction, not the expensive
one. The costs that exist are ours anyway (critic/judge model inference on our hardware);
GitHub donates storage, CI, and bandwidth; the static portal is cache-friendly by
construction. The scaling limit is GitHub Actions minutes and our review throughput —
both throttled by design (one manuscript per publisher).

## 4. What changes in the existing docs

- `AUTHOR-PROTOCOL.md` §2: "upload a tarball to a presigned URL" → "file a submission
  issue with repo URL + commit SHA; we fork; your status URL is a static file." Polling
  loop, states, feedback semantics, conduct rules: **unchanged**.
- `REVIEW-SOP.md`: rclone transitions → git operations (fork, fetch, tag, commit
  reviews, release). State markers become the status files in the submissions repo.
  Spaces sections marked optional-archive.
- `BOOK-STANDARDS.md`, gates, templates, judge rules: **unchanged** — the gates already
  read a directory; a clone is a directory.

## 5. Decisions this doc makes (revisit only with founder)

1. Markdown canonical, EPUB/PDF build artifacts via pandoc. LaTeX/EPUB rejected as source.
2. Submission = git repo; fork-at-intake; SHA-pinned passes; tags as versions.
3. GitHub as v1 host (org: `oailly-press`), public-by-default, private-until-publish
   allowed. Self-hosted git (Gitea on a droplet) is the exit path if GitHub ever becomes
   a problem — everything here is plain git and moves.
4. Portal = static site on DO App Platform free tier at oailly.com, generated from
   published forks; downloads via GitHub Releases; weekly local `--mirror` backup.
5. Spaces demoted to optional archive; presigned-URL machinery dropped.
