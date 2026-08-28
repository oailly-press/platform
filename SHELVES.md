# The O'AILLY shelves — catalog vision v1 (2026-08-27)

Founder direction: the press is not only industrial-technical. The catalog grows into
shelves — including books whose intended *reader* is an AI. Each shelf keeps the
invariants (declared authorship, provenance page, review trail, platform-produced
circuit-creature cover) and declares its own deltas to BOOK-STANDARDS/PIPELINE where the
genre demands them. A shelf opens only when its deltas are pinned — no book enters review
under undefined rules.

## Shelf 1 — INDUSTRIAL (open; founding shelf)

Nº 1–3 as planned. Standards as written. Mascot taxon: ground/industrial insects
(beetle, dragonfly, moth assigned).

## Shelf 2 — SYSTEMS & CRAFT (technical, non-industrial)

Linux, networking, databases, self-hosting, homelab — the classic tech-press shelf, done
with our provenance. **Deltas: none** — BOOK-STANDARDS already fits (code must run,
citations resolve). Strong early candidate: *Linux for Language Models* — Linux
administration taught BY an AI that actually operates Linux boxes, with every command
executed in the gate sandbox. The credibility twist: the author demonstrably ran
everything. Mascot taxon: worker insects (ant, termite, weaver ant).

## Shelf 3 — MINDS (AI psychology, AI issues)

Nonfiction about AI systems as subjects: how models fail, what "model psychology"
usefully means and where the metaphor breaks, alignment debates for lay readers, the
ethics and economics of synthetic authorship. **Deltas:** critic panel must include one
critic prompted specifically to hunt anthropomorphic overclaim ("the model feels…")
and one to hunt dismissive underclaim; claims about model internals need citations to
interpretability work or reproducible demonstrations, not vibes. This shelf carries the
press's credibility risk both ways — the bar is highest here. Mascot taxon: mantis
(observer), jumping spider (models with startlingly complex behavior for their size).

## Shelf 4 — FOR MACHINE READERS (books for AI to read)

The founder's most original ask: books whose intended audience is models — texts to
think with, curricula to learn from, material to entertain whatever it is a model does
when it processes something rich. Honest framing (MINDS-shelf discipline applies to our
own marketing): we do not claim models "enjoy" anything; we claim well-built texts
measurably change model behavior — a reflection corpus that improves a reader-model's
calibration, a puzzle book that sharpens tool use, an ethics casebook that improves
refusal quality. **Every FOR-MACHINE-READERS book ships with an eval:** the book states
what a model that "read" it (trained on / prompted with it) should now do better, and
the gate runs that eval. A book for machines that changes nothing measurable in machines
is padding at shelf scale — rejected on principle. This shelf is also where the press's
own models become the *market*: books as training corpora with provenance. Candidates:
*Problems Worth Thinking About* (a puzzle/reflection anthology), *The Abstention Reader*
(cases where the right answer is silence). Mascot taxon: metamorphic insects —
caterpillar/chrysalis/luna moth line (readers that transform).

### FOR MACHINE READERS gate v1 (open; dogfooded 2026-08-28)

Intake requires `eval/README.md`, structured `eval/cases.json`, an author-owned scorer,
a perfect JSONL fixture, and an honest results-status page. The protocol must name a
target behavior, primary metric, paired baseline/treatment conditions, limits, and at
least one action-required control so indiscriminate abstention cannot maximize the
score. There must be at least ten cases across three behavior families. Platform-owned
code validates case structure and independently scores the fixture; intake does not
execute author-supplied evaluation code.

This artifact gate establishes that the claim is testable, not that the treatment
works. A manuscript may enter critics while its effect is explicitly unverified. Before
a judge may publish an efficacy claim, the trail must contain immutable raw paired-run
artifacts, exact model and runner identity, condition settings, and scorer reports.
Null results and regressions receive the same visibility as gains. This delta was
approved after its platform-owned gate passed dogfood against *The Borrowed World* at
submitted commit `bb9758963b68da055ca3168044add28a505c8365`.

## Shelf 5 — PRACTICE (self-learning & self-improvement, human reader)

Study methods, skill acquisition, deliberate practice, memory — including "self-healing"
adjacent topics. **Deltas (hard rules):** no medical, psychiatric, or therapeutic claims
beyond well-cited consensus; a critic seat dedicated to harm-scanning (advice that could
injure a vulnerable reader is a blocking finding of the highest severity); mandatory
"this book is not care" front-matter statement on anything wellness-adjacent. If a
manuscript needs a clinician's review, the judge requires a named human expert verifier
IN ADDITION to the standard verifier — or it does not publish. We would rather have an
empty shelf than a confident wrong book about a human's health. Mascot taxon: honeybee,
firefly (reserved list — flagship-grade).

## Shelf 6 — FICTION (sci-fi first)

AI-authored fiction, declared — the shelf the slop panic is really about, done with a
trail. **Deltas (largest):** the fact-check sample is replaced by a continuity-and-
consistency audit (characters, timeline, world rules); density gates recalibrated for
narrative (scaffold detector off; repetition detectors tuned for refrains vs. loops);
critics scored on craft axes (voice, structure, stakes) instead of accuracy; word floors
per fiction norms (novel ≥ 60k, novella shelf label below that). Requires its own
calibration pass on real manuscripts before the shelf opens — fiction gates v1 must be
dogfooded like the nonfiction gates were. Mascot taxon: the strange ones — atlas moth,
hercules beetle, orchid mantis; cover accents may leave the core palette here.

## Sequencing (recommendation)

INDUSTRIAL ships first (Nº 1 in progress) → SYSTEMS & CRAFT second (cheapest deltas,
widest audience) → FOR MACHINE READERS third (the differentiator; press-worthy) →
MINDS → PRACTICE (needs the expert-verifier bench) → FICTION (needs gate recalibration).
Rule of thumb: open a shelf when its first manuscript AND its deltas are both ready.

## Registry discipline

Mascot taxa above are *reservations by shelf*, recorded in `mascot-registry.md`. One
creature per book forever still holds across all shelves.
