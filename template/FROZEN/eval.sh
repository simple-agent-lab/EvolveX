#!/usr/bin/env bash
# FROZEN — canonical Harness (invariant #1: this file never changes inside the loop).
# Contract: candidate checkout -> runs/gen-<id>/{score, result.json, artifacts/}.
# Canonical protocol: GATE split only, fixed pins from harness.env. The dev lane
# belongs to rollout.py (advisory); the sealed lane to sealed_eval.sh (human).
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
    --splits "$WS/FROZEN/splits.json" \
    --lane gate \
    --harness-version "${HARNESS_VERSION:-stub-v1}"
else
  # real path (M1): the engine adapter runs harbor on the gate split with the
  # pins from harness.env; preflight has already verified harbor/docker/keys.
  bash "$WS/operators/engines/harbor.sh" "$GEN" gate "$OUT"
fi

echo "$OUT/result.json"
