#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'usage: %s WORKSPACE_NAME [MAX_GENERATIONS] [--dry-run]\n' "$0" >&2
}

name=${1:-}
max_generations=${2:-10}
mode=${3:-}

case "$name" in
  ""|*[!A-Za-z0-9._-]*)
    usage
    exit 2
    ;;
esac

case "$max_generations" in
  ""|*[!0-9]*|0)
    printf 'MAX_GENERATIONS must be a positive integer\n' >&2
    exit 2
    ;;
esac

if [[ -n "$mode" && "$mode" != "--dry-run" ]]; then
  printf 'unknown option: %s\n' "$mode" >&2
  exit 2
fi

root=${EVOLVE_EXPERIMENT_ROOT:-/data00/home/zimuwang/evolve-experiments}
framework=${EVOLVE_FRAMEWORK:-/data00/home/zimuwang/simple-evolve-agent-main}
workspace="$root/workspaces/$name"
runner=${EVOLVE_CLI:-$framework/.venv/bin/evolve}
framework_python=${EVOLVE_PYTHON:-$framework/.venv/bin/python}

printf 'workspace=%s\n' "$workspace"
printf 'runner=%s\n' "$runner"
printf 'framework_python=%s\n' "$framework_python"
printf 'max_generations=%s\n' "$max_generations"

if [[ "$mode" == "--dry-run" ]]; then
  exit 0
fi

for required in \
  "$workspace" \
  "$runner" \
  "$framework_python" \
  "$root/evolve.env" \
  "$root/runtime.env"; do
  if [[ ! -e "$required" ]]; then
    printf 'missing required path: %s\n' "$required" >&2
    exit 1
  fi
done

set -a
. "$root/evolve.env"
if [[ -f "$root/proxy.env" ]]; then
  . "$root/proxy.env"
fi
. "$root/runtime.env"
if [[ -f "$workspace/evaluator/simulator.env" ]]; then
  . "$workspace/evaluator/simulator.env"
fi
set +a

workspace_concurrency=$(
  sed -n 's/^EVOLVE_HARBOR_N_CONCURRENT=//p' \
    "$workspace/evaluator/eval.env" 2>/dev/null | tail -1
)
case "$workspace_concurrency" in
  ""|*[!0-9]*|0)
    printf 'invalid EVOLVE_HARBOR_N_CONCURRENT in %s\n' \
      "$workspace/evaluator/eval.env" >&2
    exit 1
    ;;
esac

codex_subscription=$(
  sed -n 's/^EVOLVE_HARBOR_CODEX_SUBSCRIPTION=//p' \
    "$workspace/evaluator/eval.env" 2>/dev/null | tail -1
)
if [[ "$codex_subscription" == "1" ]]; then
  export CODEX_FORCE_AUTH_JSON=1
  codex_auth_json=${CODEX_AUTH_JSON_PATH:-$HOME/.codex/auth.json}
  if ! "$framework_python" - "$codex_auth_json" <<'PY'
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
try:
    valid = (
        path.is_file()
        and path.stat().st_size > 0
        and stat.S_IMODE(path.stat().st_mode) == 0o600
    )
except OSError:
    valid = False
raise SystemExit(0 if valid else 1)
PY
  then
    printf 'Codex auth file is not a non-empty regular file with mode 0600\n' >&2
    exit 1
  fi

  for proxy_name in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY; do
    if [[ -z "${!proxy_name:-}" ]]; then
      printf 'missing required proxy environment variable: %s\n' "$proxy_name" >&2
      exit 1
    fi
  done

  printf 'codex_auth=present\n'
  printf 'codex_proxies=present\n'
fi

export EVOLVE_FRAMEWORK_PYTHON="$framework_python"
export EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE="$workspace_concurrency"

"$runner" verify "$workspace"
if [[ "$codex_subscription" == "1" ]]; then
  "$runner" candidate-smoke --full --checkout "$workspace"
fi
exec "$runner" run "$workspace" --max-generations "$max_generations"
