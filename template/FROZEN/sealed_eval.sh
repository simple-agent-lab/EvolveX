#!/usr/bin/env bash
# FROZEN — sealed-test evaluation. HUMAN-TRIGGERED ONLY.
# The sealed split never participates in selection, gating, or training; this
# is the only signal that can expose indirect overfitting to the gate split.
# Output goes to runs/sealed/gen-<id>/ — deliberately NOT stamped, NOT ledgered,
# NOT readable by any operator convention. Read it yourself, human.
set -euo pipefail
GEN="${1:?usage: sealed_eval.sh <genid>  (run by a human, at milestones)}"
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="$WS"
PY=(python3)
command -v uv >/dev/null 2>&1 && PY=(uv run --quiet --project "$WS" python3)
OUT="$WS/runs/sealed/gen-$GEN"
mkdir -p "$OUT"

source "$WS/FROZEN/harness.env"

git -C "$WS" -c advice.detachedHead=false checkout -q "gen/$GEN"

if [[ "${HARNESS_STUB:-0}" == "1" ]]; then
  "${PY[@]}" "$WS/FROZEN/stub_harness.py" \
    --candidate "$WS/candidate" \
    --out "$OUT" \
    --splits "$WS/FROZEN/splits.json" \
    --lane sealed \
    --harness-version "${HARNESS_VERSION:-stub-v1}"
else
  bash "$WS/operators/engines/harbor.sh" "$GEN" sealed "$OUT"
fi

echo "sealed report (gen $GEN) — for human eyes, never for the loop:"
cat "$OUT/result.json"
