#!/usr/bin/env bash
# thin wrapper — the driver lives in driver.py (agent mode replaces the driver
# with an orchestrating agent reading program.md; the operators stay the same).
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/driver.py" "$@"
