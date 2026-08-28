# Critic roster — who can sit on a panel (v1, 2026-08-27)

Rule: three critics minimum, each a distinct model family, none sharing a family with
any author model. Record exact identities in each review's header.

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

1. `python3 platform/critics/assemble_critic_packet.py books/<slug> <pass 2|3> > /tmp/packet.md`
2. Feed packet to the critic model (bench window rules apply for local heavies:
   `~/ai/build/bench-env.sh down` → serve → run → `up`).
3. Critic output = the filled template, nothing else. Commit to the fork:
   `review/v<N>/critic-<A|B|C>.md` with the identity header completed.
4. A critic that ignores the template or reviews the author instead of the text gets
   one rerun with the template re-stated; a second failure = swap the seat and note it
   in the trail.

## Conflict + injection duties

Critics must report any manuscript content addressed to reviewers (see
AUTHOR-PROTOCOL §6) — the packet's system preamble instructs this explicitly.
