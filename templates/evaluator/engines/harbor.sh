# harbor evaluator template
. evaluator/eval.env
command -v harbor >/dev/null 2>&1 || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
if [ -n "${DOCKER_HOST:-}" ]; then export DOCKER_HOST; fi
if [ -z "${EVOLVE_GENID:-}" ]; then
  EVOLVE_GENID=$(basename "$(dirname "$EVOLVE_RUN_DIR")")
  EVOLVE_GENID=${EVOLVE_GENID#gen-}
fi
export EVOLVE_GENID
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
split_name=${EVOLVE_EVAL_SPLIT:-gate}
if [ -n "${EVOLVE_ROUND:-}" ]; then
  if ! PYTHONPATH="$PWD/.evolve${PYTHONPATH:+:$PYTHONPATH}" python3 -m evolve.splits \
    select evaluator/splits.json "$EVOLVE_HARBOR_TASKS" "$split_name" "$EVOLVE_RUN_DIR" "$EVOLVE_ROUND"; then
    printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
    exit 3
  fi
else
  if ! PYTHONPATH="$PWD/.evolve${PYTHONPATH:+:$PYTHONPATH}" python3 -m evolve.splits \
    select evaluator/splits.json "$EVOLVE_HARBOR_TASKS" "$split_name" "$EVOLVE_RUN_DIR"; then
    printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"
    exit 3
  fi
fi
run_label=$(basename "$EVOLVE_RUN_DIR")
jobs_dir="$EVOLVE_JOBS_DIR/gen-$EVOLVE_GENID"
if [ "$run_label" != "eval" ]; then jobs_dir="$jobs_dir-$run_label"; fi
rm -rf "$jobs_dir" && mkdir -p "$jobs_dir"
harbor_rc=0
set -- harbor run -p "$EVOLVE_HARBOR_TASKS" --agent "$EVOLVE_HARBOR_AGENT" --jobs-dir "$jobs_dir" \
  --n-attempts "${EVOLVE_HARBOR_K:-1}" -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" \
  --agent-setup-timeout-multiplier "${EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER:-1}" \
  --max-retries "${EVOLVE_HARBOR_MAX_RETRIES:-0}" -y
if [ "${EVOLVE_LIVE_OUTPUT:-0}" != "1" ]; then set -- "$@" -q; fi
proxy_http=${EVOLVE_HARBOR_HTTP_PROXY:-${http_proxy:-${HTTP_PROXY:-}}}
proxy_https=${EVOLVE_HARBOR_HTTPS_PROXY:-${https_proxy:-${HTTPS_PROXY:-}}}
proxy_no=${EVOLVE_HARBOR_NO_PROXY:-${no_proxy:-${NO_PROXY:-}}}
for proxy_entry in \
  "http_proxy=$proxy_http" "HTTP_PROXY=$proxy_http" \
  "https_proxy=$proxy_https" "HTTPS_PROXY=$proxy_https" \
  "no_proxy=$proxy_no" "NO_PROXY=$proxy_no"; do
  if [ -n "${proxy_entry#*=}" ]; then set -- "$@" --ae "$proxy_entry" --ve "$proxy_entry"; fi
done
while IFS= read -r task_name; do
  set -- "$@" --include-task-name "$task_name"
done < "$EVOLVE_RUN_DIR/task-names.txt"
if [ "${EVOLVE_LIVE_OUTPUT:-0}" = "1" ]; then
  "$@" 2>&1 | tee "$EVOLVE_RUN_DIR/harbor.log" || harbor_rc=$?
else
  "$@" > "$EVOLVE_RUN_DIR/harbor.log" 2>&1 || harbor_rc=$?
fi
python3 evaluator/parse_score.py "$jobs_dir" "$EVOLVE_RUN_DIR"
exit $?
