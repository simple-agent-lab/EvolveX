# harbor evaluator template
. evaluator/eval.env
command -v harbor >/dev/null 2>&1 || { printf 'infra_failed\n' > "$EVOLVE_RUN_DIR/status"; exit 3; }
: "${DOCKER_HOST:=unix://$HOME/.colima/default/docker.sock}"
export DOCKER_HOST
if [ -z "${EVOLVE_GENID:-}" ]; then
  EVOLVE_GENID=$(basename "$(dirname "$EVOLVE_RUN_DIR")")
  EVOLVE_GENID=${EVOLVE_GENID#gen-}
fi
export EVOLVE_GENID
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
jobs_dir="$EVOLVE_JOBS_DIR/gen-$EVOLVE_GENID"
rm -rf "$jobs_dir" && mkdir -p "$jobs_dir"
harbor_rc=0
harbor run -p "$EVOLVE_HARBOR_TASKS" --agent "$EVOLVE_HARBOR_AGENT" --jobs-dir "$jobs_dir" --n-attempts 1 -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" -y -q > "$EVOLVE_RUN_DIR/harbor.log" 2>&1 || harbor_rc=$?
python3 evaluator/parse_score.py "$jobs_dir" "$EVOLVE_RUN_DIR"
exit $?
