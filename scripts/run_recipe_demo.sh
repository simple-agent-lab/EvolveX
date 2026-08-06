#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RECIPE=${1:-${RECIPE:-ahe}}
WORKSPACE=${WORKSPACE:-./runs/${RECIPE}-demo}
TASKS=${TASKS:-}
GENERATIONS=${GENERATIONS:-1}
ENV_FILE=${ENV_FILE:-$ROOT/.env}
ASSET_ROOT=${EVOLVE_ASSET_DIR:-$ROOT/.evolve-assets/terminal-bench-2.0}
DATASET=$ASSET_ROOT/terminal-bench-2-30-v1
SUPPORTED=" aevolve ahe ahe_codex gepa hill_climb hill_climb_codex hyperagents hyperagents_codex "
[[ $SUPPORTED == *" $RECIPE "* ]] || { echo "unsupported recipe '$RECIPE'; supported recipes:$SUPPORTED" >&2; exit 2; }
[[ -d "$ASSET_ROOT/raw/terminal-bench" && -f "$DATASET/dataset-source.json" ]] || {
  echo "Terminal-Bench assets are missing; run ./scripts/setup_terminal_bench.sh $RECIPE" >&2; exit 2;
}

UV_RUN=(uv run --frozen)
[[ ! -f "$ENV_FILE" ]] || UV_RUN+=(--env-file "$ENV_FILE")
INIT_ARGS=(--recipe "$RECIPE" --dataset "$DATASET")
[[ -z "$TASKS" ]] || INIT_ARGS+=(--tasks "$TASKS")

cd "$ROOT"
uv sync --frozen
"${UV_RUN[@]}" python datasets/terminal_bench_2/prepare_dataset.py "$ASSET_ROOT/raw" "$DATASET"
"${UV_RUN[@]}" evolve init "$WORKSPACE" "${INIT_ARGS[@]}"
"${UV_RUN[@]}" "$WORKSPACE/evolve" preflight "$WORKSPACE" --smoke
"${UV_RUN[@]}" "$WORKSPACE/evolve" run "$WORKSPACE" --max-generations "$GENERATIONS" --children-per-gen 1
"${UV_RUN[@]}" "$WORKSPACE/evolve" status "$WORKSPACE"
"${UV_RUN[@]}" "$WORKSPACE/evolve" verify "$WORKSPACE"
