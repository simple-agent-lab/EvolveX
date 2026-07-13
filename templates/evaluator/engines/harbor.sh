# harbor evaluator template
. evaluator/eval.env
command -v harbor >/dev/null 2>&1 || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
if [ -z "${DOCKER_HOST:-}" ] && [ -S "$HOME/.colima/default/docker.sock" ]; then
  DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
  export DOCKER_HOST
fi
if [ -z "${EVOLVE_GENID:-}" ]; then
  EVOLVE_GENID=$(basename "$(dirname "$EVOLVE_RUN_DIR")")
  EVOLVE_GENID=${EVOLVE_GENID#gen-}
fi
export EVOLVE_GENID
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
: "${EVOLVE_UV_CACHE_DIR:=$HOME/.evolve/uv-cache}"
mkdir -p "$EVOLVE_UV_CACHE_DIR"
uv_mount=$(python3 -c 'import json,sys; print(json.dumps([{"type":"bind","source":sys.argv[1],"target":"/installed-agent/uv-cache"}]))' "$EVOLVE_UV_CACHE_DIR")
jobs_dir="$EVOLVE_JOBS_DIR/gen-$EVOLVE_GENID"
if [ -n "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" ]; then
  [ -n "${EVOLVE_CANDIDATE_SMOKE_JOBS_DIR:-}" ] || exit 3
  jobs_dir=$EVOLVE_CANDIDATE_SMOKE_JOBS_DIR
  EVOLVE_HARBOR_N=1
  EVOLVE_HARBOR_ATTEMPTS=1
  EVOLVE_HARBOR_N_CONCURRENT=1
  EVOLVE_TASK_LIMIT=1
fi
rm -rf "$jobs_dir" && mkdir -p "$jobs_dir"
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
set -- "$@" --mounts "$uv_mount"
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
set -- "$@" --jobs-dir "$jobs_dir" --n-attempts "${EVOLVE_HARBOR_ATTEMPTS:-1}" -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" -y -q
if [ -n "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" ]; then
  harbor "$@"
  exit $?
fi
harbor "$@" > "$EVOLVE_RUN_DIR/harbor.log" 2>&1 || harbor_rc=$?
python3 evaluator/parse_score.py "$jobs_dir" "$EVOLVE_RUN_DIR" "$harbor_rc"
parser_rc=$?
[ "$harbor_rc" -eq 0 ] || exit 3
exit "$parser_rc"
