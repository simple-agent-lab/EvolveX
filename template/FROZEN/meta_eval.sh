#!/usr/bin/env bash
# FROZEN — thin wrapper; the admission replay protocol lives in meta_eval.py.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/meta_eval.py" "$@"
