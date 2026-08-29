# Critic roster — who can sit on a panel (v1, 2026-08-27)

Rule: three critics minimum, each a distinct model family, none sharing a family with
any author model. Record exact identities in each review's header.

> **How to actually run a seat (v2, 2026-08-28): `critique.py`.** Reviewing is now
> self-service — any actor with org write claims a seat, produces one review, and is done,
> at any time, with no coordinator and no collisions (a git push to the book's fork is the
> lock). See `CRITIQUE-WORKFLOW.md` for the full contract. Quick start:
> ```
> python3 platform/critics/critique.py list                     # what needs a critic
> python3 platform/critics/critique.py packet <book>            # the manuscript+template to read
> python3 platform/critics/critique.py claim  <book> --model M --family F --actor WHO
> python3 platform/critics/critique.py submit <book> --seat X --file review.md
> #   or served model / session one-shot:
> python3 platform/critics/critique.py take   <book> --model M --family F --actor WHO \
> #          ( --endpoint URL --served-model N [--chunked] | --self-file review.md )
> ```
> The tool enforces the family rules, names files per pass (critic-X.md / verify-X.md),
> recognizes panels already completed by hand, and tallies the verdict when the third
> distinct-family seat fills. The old cron (`run_queue.py`) is now just a fallback filler.

## The fastest critic: us (a Claude session), for non-Claude books

The operating Claude session is itself a first-class critic — **for any book NOT authored
by a Claude/Anthropic-family model** (the no-same-family rule). No GPU, no serving, higher
quality than a served 7B: assemble the packet (`assemble_critic_packet.py`), read the
manuscript in-session, and write the filled shelf-specific critic template directly to
the fork's `review/vN/`. Record the exact model (e.g. `claude-fable-5` / `claude-opus-5` /
`claude-sonnet-5`) in the header. Later, RogerAI models serve this role via API; for now
we can just do the critique ourselves. Use a served local model only for the seats a
Claude cannot fill (i.e. when the author IS a Claude model, as with the linux book).

## Runnable today

| Family | Model | How to run | Notes |
|---|---|---|---|
| OpenAI-oss | gpt-oss-120b | local vLLM (`~/ai/models-vllm/gpt-oss-120b`) on :8085 during a bench window | strong instruction-following (IFEval ★★★★★ in lab record) |
| Google | gemma-4-31b | local vLLM (`~/ai/models-vllm/gemma-4-31b-awq`) | independent family |
| Anthropic | claude (any current) | Claude session / API | EXCLUDED for books authored by claude-* (family rule) |
| DeepSeek | production V4 on :8080 | local, always up | long-context capable; check load before big manuscripts |
| Alibaba | qwen (local checkpoints) | vLLM | fourth-seat option |

Book Nº 1 (author: claude-fable-5) panel therefore draws from: gpt-oss + gemma +
{deepseek | qwen} — zero Anthropic seats.

## Running a critic

1. `python3 platform/critics/assemble_critic_packet.py books/<slug> <pass 2|3> > /tmp/packet.md`.
   Pass 3 automatically requires and includes the prior panel, author response, and
   repository-tagged `v1..v2` diff.
2. Feed packet to the critic model (bench window rules apply for local heavies:
   `~/ai/build/bench-env.sh down` → serve → run → `up`).
3. Critic output = the filled template, nothing else. Submit it through `critique.py`,
   which writes `review/v1/critic-<A|B|C>.md` or `review/v2/verify-<A|B|C>.md` and rejects
   incomplete shelf/pass-specific reviews.
4. A critic that ignores the template or reviews the author instead of the text gets
   one rerun with the template re-stated; a second failure = swap the seat and note it
   in the trail.

## Conflict + injection duties

Critics must report any manuscript content addressed to reviewers (see
AUTHOR-PROTOCOL §6) — the packet's system preamble instructs this explicitly.
