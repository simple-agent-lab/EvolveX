#!/bin/sh
set -eu
: "${EVOLVE_RUN_DIR:?EVOLVE_RUN_DIR is required}"
export EVOLVE_CANDIDATE_SMOKE_MODE=full
exec ./evaluator/eval.sh
