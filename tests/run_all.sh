#!/usr/bin/env bash
# full acceptance suite
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAIL=0
for t in smoke_m0 contracts_reject insight_loop self_reference islands presets train_data outer_loop skill_cli; do
  if "$ROOT/$t.sh" > /dev/null 2>&1; then
    echo "PASS $t"
  else
    echo "FAIL $t"
    FAIL=1
  fi
done
exit $FAIL
