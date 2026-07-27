#!/bin/sh
set -eu
umask 077
: "${EVOLVE_RUN_DIR:=runs/gen-0/eval}"
mkdir -p "$EVOLVE_RUN_DIR"
if [ "${EVAL_STUB:-}" = "1" ]; then
  python3 evaluator/stub_eval.py "$EVOLVE_RUN_DIR"
  exit $?
fi
