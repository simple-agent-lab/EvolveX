#!/usr/bin/env bash
set -euo pipefail

RECIPE=${1:-${RECIPE:-ahe}}
WORKSPACE=${WORKSPACE:-./runs/${RECIPE}-demo}
TASKS=${TASKS:-3}
GENERATIONS=${GENERATIONS:-1}
ENV_FILE=${ENV_FILE:-.env}

UV_RUN=(uv run --frozen)
[[ ! -f "$ENV_FILE" ]] || UV_RUN+=(--env-file "$ENV_FILE")
INIT_ARGS=(--recipe "$RECIPE" --tasks "$TASKS")
[[ -z "${DATASET:-}" ]] || INIT_ARGS+=(--dataset "$DATASET")
[[ -z "${SEED:-}" ]] || INIT_ARGS+=(--seed "$SEED")

uv sync --frozen
"${UV_RUN[@]}" sh -c ': "${OPENAI_API_KEY:?Set OPENAI_API_KEY in the environment or ENV_FILE}"'
"${UV_RUN[@]}" evolve init "$WORKSPACE" "${INIT_ARGS[@]}"
"${UV_RUN[@]}" "$WORKSPACE/evolve" preflight "$WORKSPACE" --smoke
"${UV_RUN[@]}" "$WORKSPACE/evolve" run "$WORKSPACE" --max-generations "$GENERATIONS" --children-per-gen 1
"${UV_RUN[@]}" "$WORKSPACE/evolve" status "$WORKSPACE"
"${UV_RUN[@]}" "$WORKSPACE/evolve" verify "$WORKSPACE"
