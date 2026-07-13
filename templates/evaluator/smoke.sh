#!/bin/sh
set -eu
: "${EVOLVE_RUN_DIR:?EVOLVE_RUN_DIR is required}"
export EVOLVE_CANDIDATE_SMOKE_MODE=full
export EVOLVE_CANDIDATE_SMOKE_JOBS_DIR="$EVOLVE_RUN_DIR/jobs"
exec ./evaluator/eval.sh
