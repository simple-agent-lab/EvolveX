#!/usr/bin/env bash
# engine adapter — training engine (outer loop T4).
# Train-Engine contract (symmetric to the Harness contract):
#   input : base checkpoint ref + data manifest (MUST carry a matching
#           decontam stamp) + recipe
#   output: new checkpoint ref (ckpts/gen-<id>) + train_metrics.json
#
# The stamp check below is live NOW (invariant #4 enforcement point); the
# actual training backend (tinker-class fine-tuning API / hf peft) lands at
# M6 with an open-weights policy model + GPU or API access.
set -euo pipefail
BASE="${1:?usage: train_tinker.sh <base-ckpt> <manifest> <recipe> <out-ckpt>}"
MANIFEST="${2:?manifest}"
RECIPE="${3:?recipe}"
OUT="${4:?out-ckpt}"
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export PYTHONPATH="$WS"
PY=(python3)
command -v uv >/dev/null 2>&1 && PY=(uv run --quiet --project "$WS" python3)

# invariant #4: unstamped or tampered manifests are rejected before anything else
"${PY[@]}" "$WS/FROZEN/decontam.py" verify "$MANIFEST" \
  || { echo "train engine: manifest rejected by decontam — refusing to train" >&2; exit 1; }

echo "train engine backend lands at M6 (needs an open-weights policy model + GPU/API)" >&2
exit 3 # EXIT_NOT_WIRED
