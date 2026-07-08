#!/usr/bin/env bash
# thin wrapper — the driver lives in driver.py (agent mode replaces the driver
# with an orchestrating agent reading program.md; the operators stay the same).
set -euo pipefail
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$WS"
PY=(python3)
command -v uv >/dev/null 2>&1 && PY=(uv run --quiet --project "$WS" python3)
exec "${PY[@]}" "$WS/driver.py" "$@"
