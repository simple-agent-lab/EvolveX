#!/usr/bin/env bash
# FROZEN — canonical Harness (invariant #1: this file never changes inside the loop).
# Contract: candidate checkout -> runs/gen-<id>/{score, result.json, artifacts/}.
# M0: HARNESS_STUB=1 short-circuits to a deterministic fake harness.
# M1: wires harbor (see harness.env pins). Operators/agents have no write access here.
set -euo pipefail
GEN="${1:?usage: eval.sh <genid>}"
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$WS/runs/gen-$GEN"
mkdir -p "$OUT"

# pinned protocol
# shellcheck source=harness.env
source "$WS/FROZEN/harness.env"

if [[ "${HARNESS_STUB:-0}" == "1" ]]; then
  python3 "$WS/FROZEN/stub_harness.py" \
    --candidate "$WS/candidate" \
    --out "$OUT" \
    --n-tasks "${N_TASKS:-20}" \
    --harness-version "${HARNESS_VERSION:-stub-v1}"
else
  echo "real harbor harness lands at M1 — run with HARNESS_STUB=1 for now" >&2
  echo "(M1: harbor run --agent candidate:Agent --dataset \$DATASET --n-attempts \$N_ATTEMPTS \\" >&2
  echo "     --n-concurrent \$N_CONCURRENT --env docker --job-name gen-$GEN --jobs-dir runs)" >&2
  exit 2
fi

echo "$OUT/result.json"
