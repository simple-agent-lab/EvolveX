#!/usr/bin/env bash
# preflight — fail fast before burning a generation (infra guarantees).
set -euo pipefail
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="$WS"
PY=(python3)
command -v uv >/dev/null 2>&1 && PY=(uv run --quiet --project "$WS" python3)

command -v python3 >/dev/null || { echo "preflight: python3 not found" >&2; exit 1; }
command -v git >/dev/null || { echo "preflight: git not found" >&2; exit 1; }

"${PY[@]}" - "$WS" <<'PY'
import json, sys
splits = json.load(open(f"{sys.argv[1]}/FROZEN/splits.json"))
lanes = [set(splits["dev"]), set(splits["gate"]), set(splits["sealed_test"])]
for i, a in enumerate(lanes):
    for b in lanes[i + 1:]:
        assert not (a & b), f"preflight: split lanes overlap: {sorted(a & b)}"
PY

if [[ "${HARNESS_STUB:-0}" == "1" ]]; then
  exit 0
fi

# real path (M1): harbor + docker + pins + keys must all be present
command -v harbor >/dev/null || { echo "preflight: harbor binary not found (real harness needs it; or set HARNESS_STUB=1)" >&2; exit 1; }
command -v docker >/dev/null || { echo "preflight: docker not found" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "preflight: docker daemon unreachable" >&2; exit 1; }
source "$WS/FROZEN/harness.env"
[[ -n "${DATASET:-}" ]] || { echo "preflight: DATASET not pinned in FROZEN/harness.env" >&2; exit 1; }
[[ -n "${HARBOR_VERSION:-}" ]] || { echo "preflight: HARBOR_VERSION not pinned in FROZEN/harness.env" >&2; exit 1; }
harbor --version 2>/dev/null | grep -qF "$HARBOR_VERSION" \
  || { echo "preflight: installed harbor does not match pinned HARBOR_VERSION=$HARBOR_VERSION" >&2; exit 1; }
[[ -n "${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}" ]] \
  || { echo "preflight: no model API key in env for the candidate agent" >&2; exit 1; }
