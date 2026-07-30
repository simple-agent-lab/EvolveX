#!/usr/bin/env bash
set -euo pipefail

workspace=${1:-}
task_manifest=${2:-}
benchmark=${3:-}
max_generations=${4:-2}
n_concurrent=${5:-3}
environment_build_timeout_multiplier=10

if [[ -z "$workspace" || -z "$task_manifest" || -z "$benchmark" ]]; then
  printf 'usage: %s WORKSPACE TASK_MANIFEST {tau3|terminal-bench-2} [MAX_GENERATIONS] [N_CONCURRENT]\n' "$0" >&2
  exit 2
fi
case "$benchmark" in
  tau3|terminal-bench-2) ;;
  *)
    printf 'benchmark must be tau3 or terminal-bench-2\n' >&2
    exit 2
    ;;
esac
for value_name in max_generations n_concurrent; do
  value=${!value_name}
  case "$value" in
    ""|*[!0-9]*|0)
      printf '%s must be a positive integer\n' "$value_name" >&2
      exit 2
      ;;
  esac
done

workspace=$(cd "$workspace" && pwd)
task_manifest=$(cd "$(dirname "$task_manifest")" && pwd)/$(basename "$task_manifest")
if [[ -n ${EVOLVE_CLI:-} ]]; then
  evolve_cli=$EVOLVE_CLI
elif [[ -n ${EVOLVE_FRAMEWORK:-} ]]; then
  evolve_cli="$EVOLVE_FRAMEWORK/.venv/bin/evolve"
else
  evolve_cli=evolve
fi
evolve_python=${EVOLVE_PYTHON:-python3}

case "$evolve_cli" in
  */*)
    if [[ ! -f "$evolve_cli" || ! -x "$evolve_cli" ]]; then
      printf 'Evolve CLI is not executable: %s\n' "$evolve_cli" >&2
      exit 1
    fi
    ;;
  *)
    if ! command -v "$evolve_cli" >/dev/null 2>&1; then
      printf 'Evolve CLI is not available: %s\n' "$evolve_cli" >&2
      exit 1
    fi
    ;;
esac

for required in \
  "$workspace/evolve.yaml" \
  "$workspace/evaluator/eval.env" \
  "$workspace/evaluator/splits.json"; do
  if [[ ! -e "$required" ]]; then
    printf 'missing required path: %s\n' "$required" >&2
    exit 1
  fi
done
if [[ ! -f "$task_manifest" ]]; then
  printf 'missing required path: %s\n' "$task_manifest" >&2
  exit 1
fi

EVOLVE_SMOKE_WORKSPACE="$workspace" \
EVOLVE_SMOKE_TASK_MANIFEST="$task_manifest" \
EVOLVE_SMOKE_BENCHMARK="$benchmark" \
EVOLVE_SMOKE_MAX_GENERATIONS="$max_generations" \
EVOLVE_SMOKE_N_CONCURRENT="$n_concurrent" \
EVOLVE_SMOKE_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER="$environment_build_timeout_multiplier" \
"$evolve_python" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml


workspace = Path(os.environ["EVOLVE_SMOKE_WORKSPACE"])
task_manifest = Path(os.environ["EVOLVE_SMOKE_TASK_MANIFEST"])
benchmark = os.environ["EVOLVE_SMOKE_BENCHMARK"]
max_generations = int(os.environ["EVOLVE_SMOKE_MAX_GENERATIONS"])
n_concurrent = int(os.environ["EVOLVE_SMOKE_N_CONCURRENT"])
environment_build_timeout_multiplier = int(
    os.environ["EVOLVE_SMOKE_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER"]
)

config_path = workspace / "evolve.yaml"
manifest_path = workspace / "evaluator" / "splits.json"
config = yaml.safe_load(config_path.read_text())
manifest = json.loads(manifest_path.read_text())
tasks = manifest["tasks"]
original_train = [str(name) for name in tasks["train"]]
approved = json.loads(task_manifest.read_text())[benchmark]
if len(approved) != 3 or len(set(approved)) != 3:
    raise SystemExit("smoke task manifest must contain exactly three unique tasks")
if not set(approved) <= set(original_train):
    raise SystemExit("smoke task manifest contains a task outside frozen train")
if set(approved) & (set(tasks["gate"]) | set(tasks["sealed"])):
    raise SystemExit("smoke task manifest overlaps gate or sealed")

tasks["train"] = approved
selected_set = set(approved)
tasks["gate"] = [
    name for name in original_train if name not in selected_set
] + [str(name) for name in tasks["gate"]]
tasks["sealed"] = [str(name) for name in tasks["sealed"]]
all_names = tasks["train"] + tasks["gate"] + tasks["sealed"]
if len(set(all_names)) != len(all_names):
    raise SystemExit("smoke split rewrite produced overlapping task names")

counts = {split: len(tasks[split]) for split in ("train", "gate", "sealed")}
total = len(all_names)
ratios = {split: counts[split] / total for split in counts}
manifest["counts"] = counts
manifest["ratios"] = ratios
manifest["gate_tasks_per_round"] = 0
manifest["digests"] = {
    split: hashlib.sha256(
        json.dumps(sorted(names), separators=(",", ":")).encode()
    ).hexdigest()
    for split, names in tasks.items()
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

config["experiment"]["max_generations"] = max_generations
evaluator = config["evaluator"]
evaluator["n_concurrent"] = n_concurrent
evaluator["tasks_per_round"] = len(approved)
evaluator["task_names"] = approved
evaluator["split"] = {**ratios, "seed": int(manifest["seed"])}
evaluator.setdefault("anchor", {})["final"] = False
trace = config.get("operators", {}).get("trace_analyzer", {})
if trace.get("variant") == "ahe":
    if trace.get("max_tasks") is not None:
        trace["max_tasks"] = len(approved)
    if trace.get("max_concurrent") is not None:
        trace["max_concurrent"] = len(approved)
config_path.write_text(yaml.safe_dump(config, sort_keys=False))

evaluator_dir = workspace / "evaluator"
(evaluator_dir / "agent.env").write_text(
    "".join(
        f"{key}={value}\n"
        for key, value in sorted(evaluator["agent_env"].items())
    )
)
(evaluator_dir / "tasks" / "train.txt").write_text(
    "".join(f"{name}\n" for name in approved)
)
(evaluator_dir / "smoke-task-names.txt").write_text(
    "".join(f"{name}\n" for name in approved)
)
eval_env_path = evaluator_dir / "eval.env"
eval_env = {}
for line in eval_env_path.read_text().splitlines():
    key, separator, value = line.partition("=")
    if separator:
        eval_env[key] = value
eval_env.update(
    {
        "EVOLVE_HARBOR_N_CONCURRENT": str(n_concurrent),
        "EVOLVE_HARBOR_EXPECTED_TRIALS": str(len(approved)),
        "EVOLVE_HARBOR_N": str(n_concurrent),
        "EVOLVE_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER": str(
            environment_build_timeout_multiplier
        ),
    }
)
eval_env_path.write_text(
    "".join(f"{key}={value}\n" for key, value in sorted(eval_env.items()))
)

eval_script_path = evaluator_dir / "eval.sh"
if eval_script_path.is_file():
    eval_script = eval_script_path.read_text()
    marker = (
        'if [ -n "${EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER:-}" ]; then\n'
    )
    forwarding = (
        'if [ -n "${EVOLVE_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER:-}" ]; then\n'
        '  set -- "$@" --environment-build-timeout-multiplier '
        '"$EVOLVE_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER"\n'
        "fi\n"
    )
    if "--environment-build-timeout-multiplier" not in eval_script:
        if marker not in eval_script:
            raise SystemExit("could not locate Harbor timeout insertion point")
        eval_script_path.write_text(eval_script.replace(marker, forwarding + marker, 1))
PY

git -C "$workspace" add \
  evolve.yaml \
  evaluator/agent.env \
  evaluator/eval.env \
  evaluator/eval.sh \
  evaluator/splits.json \
  evaluator/tasks/train.txt \
  evaluator/smoke-task-names.txt
git -C "$workspace" \
  -c user.name="Evolve Experiment Setup" \
  -c user.email="evolve@example.invalid" \
  commit --amend --no-edit
git -C "$workspace" tag -f gen/0
"$evolve_cli" verify "$workspace"
printf 'configured=%s\n' "$workspace"
printf 'task_count=3\n'
printf 'max_generations=%s\n' "$max_generations"
printf 'n_concurrent=%s\n' "$n_concurrent"
printf 'environment_build_timeout_multiplier=%s\n' "$environment_build_timeout_multiplier"
