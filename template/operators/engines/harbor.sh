#!/usr/bin/env bash
# engine adapter — harbor (default rollout/eval engine, wired at M1).
# Contract: candidate checkout -> runs/<job>/result.json (score, per-task, artifacts).
# harbor run --agent candidate:Agent --dataset "$DATASET" \
#   --n-attempts "$N_ATTEMPTS" --n-concurrent "$N_CONCURRENT" --env "$HARBOR_ENV" \
#   --job-name "gen-$GEN" --jobs-dir runs
echo "harbor engine adapter lands at M1" >&2
exit 2
