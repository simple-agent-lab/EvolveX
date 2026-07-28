# harbor evaluator template
. evaluator/eval.env
if [ -n "${EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE:-}" ]; then
  case "$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" in
    *[!0-9]*|""|0)
      printf 'invalid EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=%s\n' \
        "$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" >&2
      exit 3
      ;;
  esac
  EVOLVE_HARBOR_N_CONCURRENT=$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE
fi
: "${EVOLVE_WORKSPACE:=$PWD}"
if [ -n "${EVOLVE_UV_BINARY:-}" ]; then UV=$EVOLVE_UV_BINARY; else UV=$(command -v uv || true); fi
[ -n "$UV" ] && [ -x "$UV" ] || { printf 'uv is required; install uv or set EVOLVE_UV_BINARY\n' >&2; printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
if [ -z "${DOCKER_HOST:-}" ] && [ -S "$HOME/.colima/default/docker.sock" ]; then
  DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  export DOCKER_HOST
fi
if [ -z "${EVOLVE_GENID:-}" ]; then
  EVOLVE_GENID=$(basename "$(dirname "$EVOLVE_RUN_DIR")")
  EVOLVE_GENID=${EVOLVE_GENID#gen-}
fi
export EVOLVE_GENID
: "${EVOLVE_ATTEMPT_ID:=manual-$EVOLVE_GENID}"
: "${EVOLVE_FRAMEWORK_PYTHON:=$(command -v python3)}"
export EVOLVE_ATTEMPT_ID EVOLVE_FRAMEWORK_PYTHON
split_name=${EVOLVE_EVAL_SPLIT:-gate}
if python3 -c 'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1])).get("resolved") else 1)' evaluator/splits.json; then
  if ! "$UV" run --project "$EVOLVE_WORKSPACE" --frozen python "$PWD/.evolve/launch_splits.py" \
    select evaluator/splits.json "$EVOLVE_HARBOR_TASKS" "$split_name" "$EVOLVE_RUN_DIR"; then
    printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
    exit 3
  fi
  EVOLVE_HARBOR_TASK_FILE="$EVOLVE_RUN_DIR/task-names.txt"
  export EVOLVE_HARBOR_TASK_FILE
fi
if [ -n "${EVOLVE_REPAIR_TASK_FILE:-}" ]; then
  EVOLVE_HARBOR_TASK_FILE=$EVOLVE_REPAIR_TASK_FILE
  export EVOLVE_HARBOR_TASK_FILE
fi
: "${EVOLVE_UV_CACHE_DIR:=$HOME/.evolve/uv-cache}"
runtime_mounts=${EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON:-}
runtime_env=${EVOLVE_CANDIDATE_RUNTIME_ENV_JSON:-}
if [ -z "$runtime_mounts" ]; then
  mkdir -p "$EVOLVE_UV_CACHE_DIR"
  runtime_mounts=$(python3 -c 'import json,sys; print(json.dumps([{"type":"bind","source":sys.argv[1],"target":"/opt/evolve/uv/cache"}]))' "$EVOLVE_UV_CACHE_DIR")
fi
[ -n "$runtime_env" ] || runtime_env='{}'
if ! python3 - "$runtime_env" "$runtime_mounts" "$EVOLVE_RUN_DIR" <<'PY'
import json
import sys
from pathlib import Path

environment = json.loads(sys.argv[1])
mounts = json.loads(sys.argv[2])
if not isinstance(environment, dict):
    raise SystemExit("candidate runtime environment must be an object")
if not isinstance(mounts, list) or any(not isinstance(mount, dict) for mount in mounts):
    raise SystemExit("candidate runtime mounts must be a list of objects")
for mount in mounts:
    if (
        mount.get("type") != "bind"
        or not isinstance(mount.get("source"), str)
        or not isinstance(mount.get("target"), str)
        or not isinstance(mount.get("read_only", False), bool)
    ):
        raise SystemExit("invalid candidate runtime mount")
entries = []
for key, value in sorted(environment.items()):
    if not isinstance(key, str) or not isinstance(value, str) or "\n" in key + value or "=" in key:
        raise SystemExit("invalid candidate runtime environment entry")
    entries.append(f"{key}={value}")
run_dir = Path(sys.argv[3])
(run_dir / "candidate-runtime.env").write_text("\n".join(entries) + ("\n" if entries else ""))
(run_dir / "candidate-runtime.mounts.json").write_text(json.dumps(mounts, separators=(",", ":")))
PY
then
  printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
  exit 3
fi
runtime_mounts=$(cat "$EVOLVE_RUN_DIR/candidate-runtime.mounts.json")
jobs_dir="$EVOLVE_RUN_DIR/jobs"
if ! mkdir "$jobs_dir"; then
  printf 'jobs directory already exists: %s\n' "$jobs_dir" >&2
  printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
  exit 3
fi
if [ "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" = "single" ]; then
  EVOLVE_HARBOR_N=1
  EVOLVE_HARBOR_ATTEMPTS=1
  EVOLVE_HARBOR_N_CONCURRENT=1
  EVOLVE_TASK_LIMIT=1
elif [ "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" = "full" ]; then
  EVOLVE_HARBOR_ATTEMPTS=1
fi
cleanup_harbor() {
  case "${EVOLVE_HARBOR_ENVIRONMENT:-docker}" in
    docker) "$EVOLVE_FRAMEWORK_PYTHON" evaluator/cleanup_harbor.py "$jobs_dir" || : ;;
  esac
}
cleanup_on_exit() {
  cleanup_rc=$?
  trap - EXIT TERM INT
  cleanup_harbor
  exit "$cleanup_rc"
}
cleanup_on_signal() {
  cleanup_signal=$1
  trap - EXIT TERM INT
  cleanup_harbor
  if [ "$cleanup_signal" = TERM ]; then
    exit 143
  fi
  exit 130
}
trap cleanup_on_exit EXIT
trap 'cleanup_on_signal TERM' TERM
trap 'cleanup_on_signal INT' INT
harbor_rc=0
set -- run
case "${EVOLVE_HARBOR_DATASET_MODE:-path}" in
  registry|dataset)
    set -- "$@" --dataset "$EVOLVE_HARBOR_TASKS"
    ;;
  path|"")
    set -- "$@" -p "$EVOLVE_HARBOR_TASKS"
    ;;
  *)
    printf 'unknown EVOLVE_HARBOR_DATASET_MODE=%s\n' "$EVOLVE_HARBOR_DATASET_MODE" > "$EVOLVE_RUN_DIR/harbor.log"
    printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
    exit 3
    ;;
esac
if [ "${EVOLVE_EVAL_KIND:-research}" = "anchor" ] && [ -n "${EVOLVE_HARBOR_ANCHOR_TASK_FILE:-}" ]; then
  EVOLVE_HARBOR_TASK_FILE=$EVOLVE_HARBOR_ANCHOR_TASK_FILE
fi
if [ -n "${EVOLVE_HARBOR_TASK_FILE:-}" ]; then
  while IFS= read -r task_name || [ -n "$task_name" ]; do
    case "$task_name" in
      ""|\#*) continue ;;
    esac
    set -- "$@" --include-task-name "$task_name"
  done < "$EVOLVE_HARBOR_TASK_FILE"
fi
if [ -n "${EVOLVE_TASK_LIMIT:-}" ]; then
  set -- "$@" --n-tasks "$EVOLVE_TASK_LIMIT"
  export EVOLVE_HARBOR_EXPECTED_TRIALS=$((EVOLVE_TASK_LIMIT * EVOLVE_HARBOR_ATTEMPTS))
fi
set -- "$@" --agent "$EVOLVE_HARBOR_AGENT"
if [ -n "${EVOLVE_HARBOR_ENVIRONMENT:-}" ]; then
  set -- "$@" --env "$EVOLVE_HARBOR_ENVIRONMENT"
fi
if [ -f evaluator/environment.kwargs ]; then
  while IFS= read -r environment_kwarg || [ -n "$environment_kwarg" ]; do
    [ -n "$environment_kwarg" ] && set -- "$@" --environment-kwarg "$environment_kwarg"
  done < evaluator/environment.kwargs
fi
set -- "$@" --ae "EVOLVE_CANDIDATE_SOURCE=$PWD/target"
set -- "$@" --mounts "$runtime_mounts"
for credential_name in OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE; do
  eval "credential_value=\${$credential_name-}"
  if [ -n "$credential_value" ]; then
    set -- "$@" --ae "$credential_name=$credential_value"
  fi
done
model_base=${OPENAI_BASE_URL:-${OPENAI_API_BASE:-}}
proxy_bypass=$(
  "$EVOLVE_FRAMEWORK_PYTHON" - "$model_base" "${EVOLVE_HARBOR_NO_PROXY-}" "${no_proxy-}" "${NO_PROXY-}" <<'PY'
import sys
from urllib.parse import urlsplit

base_url, override, *configured = sys.argv[1:]
entries = []
for value in ([override] if override else configured):
    for entry in value.split(","):
        entry = entry.strip()
        if entry and entry not in entries:
            entries.append(entry)
if base_url:
    hostname = urlsplit(base_url).hostname
    if not hostname:
        raise SystemExit("configured model base URL has no hostname")
    if hostname not in entries:
        entries.append(hostname)
print(",".join(entries))
PY
)
proxy_http=${EVOLVE_HARBOR_HTTP_PROXY:-${http_proxy:-${HTTP_PROXY:-}}}
proxy_https=${EVOLVE_HARBOR_HTTPS_PROXY:-${https_proxy:-${HTTPS_PROXY:-}}}
for proxy_entry in \
  "http_proxy=$proxy_http" "HTTP_PROXY=$proxy_http" \
  "https_proxy=$proxy_https" "HTTPS_PROXY=$proxy_https"; do
  if [ -n "${proxy_entry#*=}" ]; then
    set -- "$@" --ae "$proxy_entry" --ve "$proxy_entry"
  fi
done
if [ -n "$proxy_bypass" ]; then
  for bypass_name in no_proxy NO_PROXY; do
    set -- "$@" --ae "$bypass_name=$proxy_bypass" --ve "$bypass_name=$proxy_bypass"
  done
fi
if [ -f evaluator/agent.env ]; then
  while IFS= read -r agent_entry || [ -n "$agent_entry" ]; do
    [ -n "$agent_entry" ] && set -- "$@" --ae "$agent_entry"
  done < evaluator/agent.env
fi
if [ -f evaluator/verifier.env ]; then
  while IFS= read -r verifier_entry || [ -n "$verifier_entry" ]; do
    [ -n "$verifier_entry" ] && set -- "$@" --ve "$verifier_entry"
  done < evaluator/verifier.env
fi
while IFS= read -r runtime_entry || [ -n "$runtime_entry" ]; do
  if [ -n "$runtime_entry" ]; then
    case "$runtime_entry" in
      UV_OFFLINE=*) set -- "$@" --ae "$runtime_entry" ;;
      *) set -- "$@" --ae "$runtime_entry" --ve "$runtime_entry" ;;
    esac
  fi
done < "$EVOLVE_RUN_DIR/candidate-runtime.env"
if [ -n "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" ]; then
  set -- "$@" --install-only --ae "EVOLVE_CANDIDATE_SMOKE_MODE=$EVOLVE_CANDIDATE_SMOKE_MODE"
fi
if [ -n "${EVOLVE_HARBOR_MODEL:-}" ]; then
  set -- "$@" --model "$EVOLVE_HARBOR_MODEL"
elif [ -n "${OPENAI_MODEL:-}" ]; then
  set -- "$@" --model "openai/$OPENAI_MODEL"
fi
if [ -n "${EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER:-}" ]; then
  set -- "$@" --agent-setup-timeout-multiplier "$EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER"
fi
if [ -n "${EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER:-}" ]; then
  set -- "$@" --agent-timeout-multiplier "$EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER"
fi
if [ -n "${EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER:-}" ]; then
  set -- "$@" --verifier-timeout-multiplier "$EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER"
fi
if [ -n "${EVOLVE_HARBOR_MAX_RETRIES:-}" ]; then
  set -- "$@" --max-retries "$EVOLVE_HARBOR_MAX_RETRIES"
  set -- "$@" --retry-exclude AgentTimeoutError
  set -- "$@" --retry-exclude EvolveCandidateInvalidError
  set -- "$@" --retry-exclude ApiUsageLimitError
fi
set -- "$@" --job-name "$EVOLVE_ATTEMPT_ID" --jobs-dir "$jobs_dir" --n-attempts "${EVOLVE_HARBOR_ATTEMPTS:-1}" -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" -y -q
if [ -n "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" ]; then
  "$UV" run --project "$EVOLVE_WORKSPACE" --frozen harbor "$@"
  exit $?
fi
if [ "${EVOLVE_LIVE_OUTPUT:-0}" = "1" ]; then
  "$UV" run --project "$EVOLVE_WORKSPACE" --frozen harbor "$@" 2>&1 | tee "$EVOLVE_RUN_DIR/harbor.log" || harbor_rc=$?
else
  "$UV" run --project "$EVOLVE_WORKSPACE" --frozen harbor "$@" > "$EVOLVE_RUN_DIR/harbor.log" 2>&1 || harbor_rc=$?
fi
python3 evaluator/parse_score.py "$jobs_dir" "$EVOLVE_RUN_DIR" "$harbor_rc"
parser_rc=$?
exit "$parser_rc"
