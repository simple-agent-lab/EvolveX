#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RECIPE=${1:-}
ASSET_ROOT=${EVOLVE_ASSET_DIR:-$ROOT/.evolve-assets/terminal-bench-2.0}
RAW_DATASET=$ASSET_ROOT/raw
DATASET=$ASSET_ROOT/terminal-bench-2-30-v1
RAW_PENDING=$ASSET_ROOT/.raw.pending
OWNS_PENDING=0

cleanup() {
  if [[ $OWNS_PENDING == 1 ]]; then
    rm -rf -- "$RAW_PENDING"
  fi
}
trap cleanup EXIT

case "$RECIPE" in
  ahe|hyperagents)
    IMAGE=evolve-meta-agent-app:20260724-tools-mswe245
    IMAGE_CONTEXT=$ROOT/containers/meta-agent
    BUILD_ARGS=(--build-arg MINISWE_VERSION=2.4.5)
    ;;
  aevolve|ahe_codex|gepa|hill_climb|hill_climb_codex|hyperagents_codex)
    IMAGE=evolve-meta-agent-codex:20260805-codex0145
    IMAGE_CONTEXT=$ROOT/containers/meta-agent-codex
    BUILD_ARGS=(--build-arg CODEX_VERSION=0.145.0)
    ;;
  *)
    echo "unsupported recipe '$RECIPE'; supported recipes: aevolve, ahe, ahe_codex, gepa, hill_climb, hill_climb_codex, hyperagents, hyperagents_codex" >&2
    exit 2
    ;;
esac

for tool in uv git docker; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 2; }
done
docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable" >&2; exit 2; }

cd "$ROOT"
uv sync --frozen
mkdir -p "$ASSET_ROOT"
if [[ ! -d "$RAW_DATASET/terminal-bench" ]]; then
  [[ ! -e "$RAW_PENDING" ]] || { echo "incomplete setup directory exists: $RAW_PENDING" >&2; exit 2; }
  OWNS_PENDING=1
  uv run --frozen harbor download terminal-bench@2.0 --export -o "$RAW_PENDING"
  mv "$RAW_PENDING" "$RAW_DATASET"
  OWNS_PENDING=0
fi
uv run --frozen python datasets/terminal_bench_2/prepare_dataset.py "$RAW_DATASET" "$DATASET"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build "${BUILD_ARGS[@]}" -t "$IMAGE" "$IMAGE_CONTEXT"
fi

echo "Terminal-Bench 2.0 setup is ready at $DATASET"
echo "EVOLVE_ASSET_DIR=\"$ASSET_ROOT\" ./scripts/run_recipe_demo.sh $RECIPE"
