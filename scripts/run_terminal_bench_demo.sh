#!/usr/bin/env bash
set -euo pipefail

WORKSPACE=${WORKSPACE:-./runs/terminal-bench-demo}
DATASET=${DATASET:-terminal-bench@2.0}
TASKS=${TASKS:-3}
GENERATIONS=${GENERATIONS:-1}

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this demo}"

uv sync --frozen
uv run evolve init "$WORKSPACE" \
  --recipe ahe \
  --dataset "$DATASET" \
  --tasks "$TASKS"

umask 077
printf 'OPENAI_API_KEY=%s\n' "$OPENAI_API_KEY" >"$WORKSPACE/.env"
if [[ -n "${OPENAI_BASE_URL:-}" ]]; then
  printf 'OPENAI_BASE_URL=%s\n' "$OPENAI_BASE_URL" >>"$WORKSPACE/.env"
fi

"$WORKSPACE/evolve" preflight "$WORKSPACE" --smoke
"$WORKSPACE/evolve" run "$WORKSPACE" --max-generations "$GENERATIONS" --children-per-gen 1
"$WORKSPACE/evolve" status "$WORKSPACE"
"$WORKSPACE/evolve" verify "$WORKSPACE"
