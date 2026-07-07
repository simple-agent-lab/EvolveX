#!/usr/bin/env bash
# FROZEN — thin wrapper; the stamping + best-ever rules live in stamp.py.
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stamp.py" "${1:?usage: stamp.sh <genid>}"
