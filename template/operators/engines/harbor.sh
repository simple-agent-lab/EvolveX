#!/usr/bin/env bash
# engine adapter — harbor (default rollout/eval engine).
# Engine contract: (genid, lane, outdir) -> outdir/{result.json, score, artifacts/}
# with result.json carrying score / score_ci / task_vector / task_ids / lane /
# harness_version — the same shape the stub emits, so FROZEN/stamp.py and every
# operator are engine-agnostic.
#
# Code-complete against harbor's CLI; requires harbor + docker + model API keys
# on the host (verified by preflight). Task subsetting per splits.json is
# resolved via the dataset's task registry (M1 finalizes the id<->task mapping).
set -euo pipefail
GEN="${1:?usage: harbor.sh <genid> <lane> <outdir>}"
LANE="${2:?lane (dev|gate|sealed)}"
OUT="${3:?outdir}"
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source "$WS/FROZEN/harness.env"

if ! command -v harbor >/dev/null; then
  echo "harbor binary not found — install harbor and pin HARBOR_VERSION in FROZEN/harness.env (M1)" >&2
  exit 3 # EXIT_NOT_WIRED
fi

: "${DATASET:?DATASET must be pinned in FROZEN/harness.env}"
: "${N_ATTEMPTS:=2}"
: "${N_CONCURRENT:=4}"
: "${HARBOR_ENV:=docker}"

mkdir -p "$OUT"
harbor run \
  --agent candidate:Agent \
  --dataset "$DATASET" \
  --n-attempts "$N_ATTEMPTS" \
  --n-concurrent "$N_CONCURRENT" \
  --env "$HARBOR_ENV" \
  --job-name "gen-$GEN-$LANE" \
  --jobs-dir "$WS/runs"

python3 "$WS/operators/engines/harbor_parse.py" \
  --job-dir "$WS/runs/gen-$GEN-$LANE" \
  --splits "$WS/FROZEN/splits.json" \
  --lane "$LANE" \
  --harness-version "${HARNESS_VERSION:?}" \
  --out "$OUT"
