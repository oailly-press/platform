#!/usr/bin/env bash
# The o'ailly 6-hourly review agent. Randomly stands up ONE available headless brain
# (Claude / Codex / OpenCode) to tend the review queue per AUTO-REVIEW-PROMPT.md, then
# runs the mechanical local sweep as a backstop. Guardrails live in the prompt.
#   platform/critics/oailly-agent.sh [--dry]
set -uo pipefail
ROOT=/home/luis/ai/books-by-ai
cd "$ROOT" || exit 1
PROMPT_FILE="$ROOT/platform/critics/AUTO-REVIEW-PROMPT.md"
LOG="$ROOT/platform/critics/auto-review.log"
DRY=""; [ "${1:-}" = "--dry" ] && DRY=1
ts(){ date -u +%Y-%m-%dT%H:%M:%SZ; }
say(){ echo "$(ts)  $*" | tee -a "$LOG"; }
PROMPT="$(cat "$PROMPT_FILE")"

# ---- build the pool of usable DRIVING brains (binary present AND authenticated headless) ----
# NB: opencode is NOT a driving brain here — its default agent model needs an API key. Its
# free Zen models (mimo/muse) are still used *as critic tools* by whichever brain drives.
BRAINS=()
[ -x "$HOME/.local/bin/claude" ]     && [ -f "$HOME/.claude/.credentials.json" ] && BRAINS+=("claude")
[ -x "$HOME/.npm-global/bin/codex" ] && [ -f "$HOME/.codex/auth.json" ]          && BRAINS+=("codex")

if [ ${#BRAINS[@]} -eq 0 ]; then
  say "agent: no usable agentic brain — running the local sweep only"
  python3 platform/critics/auto_review.py >>"$LOG" 2>&1
  exit 0
fi

# ---- randomly choose one ----
BRAIN="${BRAINS[$((RANDOM % ${#BRAINS[@]}))]}"
say "agent: chose brain=$BRAIN  (pool: ${BRAINS[*]})"

run_brain(){
  case "$BRAIN" in
    claude)   timeout 2400 "$HOME/.local/bin/claude" -p "$PROMPT" \
                --dangerously-skip-permissions --add-dir "$ROOT" ;;
    codex)    timeout 2400 "$HOME/.npm-global/bin/codex" exec \
                --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "$PROMPT" ;;
    opencode) timeout 2400 "$HOME/.opencode/bin/opencode" run "$PROMPT" ;;
  esac
}

if [ -n "$DRY" ]; then
  say "agent: --dry, would run: $BRAIN (headless, 40-min cap) with AUTO-REVIEW-PROMPT.md"
  exit 0
fi

say "agent: standing up $BRAIN headless…"
run_brain >>"$LOG" 2>&1
say "agent: $BRAIN finished (exit $?)"
# backstop: fill any local-fillable seat the agent missed
python3 platform/critics/auto_review.py >>"$LOG" 2>&1
say "agent: sweep backstop done"
