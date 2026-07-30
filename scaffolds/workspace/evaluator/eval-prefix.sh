#!/bin/sh
set -eu
umask 077
: "${EVOLVE_RUN_DIR:=runs/gen-0/eval}"
mkdir -p "$EVOLVE_RUN_DIR"
if [ "${EVAL_STUB:-}" = "1" ]; then
  python3 evaluator/stub_eval.py "$EVOLVE_RUN_DIR"
  exit $?
fi
unset \
  EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_MAX_RETRIES
