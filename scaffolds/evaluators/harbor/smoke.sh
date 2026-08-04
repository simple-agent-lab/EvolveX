#!/bin/sh
set -eu
: "${EVOLVE_RUN_DIR:?EVOLVE_RUN_DIR is required}"
: "${EVOLVE_CANDIDATE_SMOKE_MODE:=install}"
export EVOLVE_CANDIDATE_SMOKE_MODE
exec ./evaluator/eval.sh
