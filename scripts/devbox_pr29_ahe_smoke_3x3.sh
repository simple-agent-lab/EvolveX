#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

REPO_BUNDLE=${REPO_BUNDLE:-/data00/home/zimuwang/pr29-runtime-profiles-phase3.bundle}
RUN_ROOT=${RUN_ROOT:-/data00/home/zimuwang/pr29-ahe-3x3-$(date -u +%Y%m%dT%H%M%SZ)}
SOURCE_DATASET=${SOURCE_DATASET:-/data00/home/zimuwang/simple-evolve-agent-full89-20260724/datasets/tau3-banking-97-codex-safe-health-v033-1d244f5dca42944b67a379b44bfeb9f5748f189d}
ENV_ROOT=${ENV_ROOT:-/data00/home/zimuwang/modelhub-codex-smokes-20260804}
MODEL_ENV=$ENV_ROOT/evolve.env
RUNTIME_ENV=$ENV_ROOT/runtime.env
PROXY_ENV=$ENV_ROOT/proxy.env
TAU3_ENV_LOADER=${TAU3_ENV_LOADER:-/data00/home/zimuwang/simple-evolve-agent-full89-20260724/scripts/load_tau3_runtime_env.sh}
TASKS=3
GENERATIONS=3

REPO=$RUN_ROOT/repo
DATASET=$RUN_ROOT/dataset
WORKSPACE=$RUN_ROOT/workspace
LOG=$RUN_ROOT/run.log

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

finish() {
  status=$?
  if ((status != 0)); then
    printf 'FAILED: artifacts preserved at %s\n' "$RUN_ROOT" >&2
  fi
}
trap finish EXIT

[[ ! -e "$RUN_ROOT" ]] || fail "run root already exists: $RUN_ROOT"
for file in "$MODEL_ENV" "$RUNTIME_ENV" "$PROXY_ENV"; do
  [[ -f "$file" ]] || fail "private environment file is missing: $file"
done
[[ -f "$REPO_BUNDLE" ]] || fail "PR bundle is missing: $REPO_BUNDLE"
[[ -f "$TAU3_ENV_LOADER" ]] || fail "Tau3 environment loader is missing: $TAU3_ENV_LOADER"
[[ -d "$SOURCE_DATASET" ]] || fail "source dataset is missing: $SOURCE_DATASET"

source "$TAU3_ENV_LOADER" "$ENV_ROOT"

for command in git uv docker harbor; do
  command -v "$command" >/dev/null || fail "required command is unavailable: $command"
done
[[ -n ${OPENAI_API_KEY:-} ]] || fail "OPENAI_API_KEY is missing"

mkdir -p "$RUN_ROOT" "$DATASET"
exec > >(tee -a "$LOG") 2>&1
printf 'Run root: %s\n' "$RUN_ROOT"

pr_head=$(git bundle list-heads "$REPO_BUNDLE" HEAD | awk 'NR == 1 {print $1}')
[[ -n "$pr_head" ]] || fail "cannot resolve HEAD from PR bundle"
git clone --quiet "$REPO_BUNDLE" "$REPO"
[[ $(git -C "$REPO" rev-parse HEAD) == "$pr_head" ]] || fail "checkout does not match PR head"
printf 'PR commit: %s\n' "$pr_head"
uv --directory "$REPO" sync --dev --frozen

mapfile -t task_dirs < <(
  find "$SOURCE_DATASET" -mindepth 2 -maxdepth 2 -name task.toml -printf '%h\n' |
    sort |
    head -n "$TASKS"
)
((${#task_dirs[@]} == TASKS)) || fail "source dataset has fewer than $TASKS tasks"
for task_dir in "${task_dirs[@]}"; do
  cp -a "$task_dir" "$DATASET/"
done
[[ $(find "$DATASET" -mindepth 2 -maxdepth 2 -name task.toml | wc -l) -eq $TASKS ]] ||
  fail "copied dataset does not contain exactly $TASKS tasks"

runtime_digest=$(uv --directory "$REPO" run python - "$DATASET" <<'PY'
from pathlib import Path
import re
import sys
import tomllib

dataset = Path(sys.argv[1])
task_files = sorted(dataset.glob("*/task.toml"))
images = set()
for path in task_files:
    with path.open("rb") as stream:
        task = tomllib.load(stream)
    images.add(task["environment"]["docker_image"])

if len(images) != 1:
    raise SystemExit("selected tasks do not share one evaluator image")
image = images.pop()
if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
    raise SystemExit("selected task image is not an immutable SHA-256 reference")
print(image)
PY
)
docker image inspect "$runtime_digest" >/dev/null || fail "runtime image is unavailable: $runtime_digest"
export EVOLVE_RUNTIME_DIGEST=$runtime_digest

uv --directory "$REPO" run evolve init "$WORKSPACE" --recipe ahe --dataset "$DATASET"
cat "$MODEL_ENV" "$RUNTIME_ENV" "$PROXY_ENV" >"$WORKSPACE/.env"
{
  printf '\nEVOLVE_RUNTIME_DIGEST=%s\n' "$EVOLVE_RUNTIME_DIGEST"
  printf 'TAU3_RUNTIME_API_KEY=%s\n' "$TAU3_RUNTIME_API_KEY"
  printf 'TAU3_RUNTIME_BASE_URL=%s\n' "$TAU3_RUNTIME_BASE_URL"
  printf 'TAU3_RUNTIME_API_KIND=%s\n' "$TAU3_RUNTIME_API_KIND"
  printf 'TAU3_RUNTIME_USER_MODEL=%s\n' "$TAU3_RUNTIME_USER_MODEL"
  printf 'TAU3_RUNTIME_USER_REASONING_EFFORT=%s\n' "$TAU3_RUNTIME_USER_REASONING_EFFORT"
  printf 'TAU3_RUNTIME_NL_ASSERTIONS_MODEL=%s\n' "$TAU3_RUNTIME_NL_ASSERTIONS_MODEL"
  printf 'NO_PROXY=%s\n' "$NO_PROXY"
  printf 'no_proxy=%s\n' "$no_proxy"
} >>"$WORKSPACE/.env"
chmod 600 "$WORKSPACE/.env"

"$WORKSPACE/evolve" preflight "$WORKSPACE"
"$WORKSPACE/evolve" preflight "$WORKSPACE" --smoke
"$WORKSPACE/evolve" run "$WORKSPACE" \
  --max-generations "$GENERATIONS" \
  --children-per-gen 1 \
  --verbose
"$WORKSPACE/evolve" status "$WORKSPACE"
"$WORKSPACE/evolve" verify "$WORKSPACE"

for generation in $(seq 0 "$GENERATIONS"); do
  git -C "$WORKSPACE" rev-parse --verify --quiet "refs/tags/gen/$generation" >/dev/null ||
    fail "missing generation tag: gen/$generation"
done

archive=$WORKSPACE/archive.jsonl
[[ -f "$archive" ]] || fail "archive is missing"
uv --directory "$REPO" run python - "$archive" "$TASKS" "$GENERATIONS" <<'PY'
import json
from pathlib import Path
import sys

archive = Path(sys.argv[1])
tasks = int(sys.argv[2])
generations = int(sys.argv[3])
records = [json.loads(line) for line in archive.read_text().splitlines()]

for generation in range(generations + 1):
    purpose = "genesis" if generation == 0 else "candidate"
    certified = any(
        record.get("_evolve_mechanism_eval") is True
        and record.get("genid") == str(generation)
        and record.get("purpose") == purpose
        and record.get("outcome") == "benchmark_complete"
        and record.get("expected_trials") == tasks
        and len(record.get("task_set_members", [])) == tasks
        and record.get("contract_certified") is True
        for record in records
    )
    if not certified:
        raise SystemExit(
            f"generation {generation} lacks certified three-task evidence"
        )
PY

printf 'PASS: AHE completed %s tasks across gen/1 through gen/%s at %s\n' \
  "$TASKS" "$GENERATIONS" "$RUN_ROOT"
