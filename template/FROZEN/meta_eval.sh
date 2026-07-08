#!/usr/bin/env bash
# FROZEN — thin wrapper; the admission replay protocol lives in meta_eval.py.
set -euo pipefail
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$WS"
PY=(python3)
command -v uv >/dev/null 2>&1 && PY=(uv run --quiet --project "$WS" python3)
exec "${PY[@]}" "$WS/FROZEN/meta_eval.py" "$@"
