#!/usr/bin/env bash
set -euo pipefail

workspace=${1:-}
task_count=${2:-5}
max_generations=${3:-3}
n_concurrent=${4:-$task_count}
environment_build_timeout_multiplier=${5:-10}
agent_step_limit=${6:-12}
trace_task_count=${7:-1}

if [[ -z "$workspace" ]]; then
  printf 'usage: %s WORKSPACE [TASK_COUNT] [MAX_GENERATIONS] [N_CONCURRENT] [ENV_BUILD_TIMEOUT_MULTIPLIER] [AGENT_STEP_LIMIT] [TRACE_TASK_COUNT]\n' "$0" >&2
  exit 2
fi
for value_name in task_count max_generations n_concurrent environment_build_timeout_multiplier agent_step_limit trace_task_count; do
  value=${!value_name}
  case "$value" in
    ""|*[!0-9]*|0)
      printf '%s must be a positive integer\n' "$value_name" >&2
      exit 2
      ;;
  esac
done

workspace=$(cd "$workspace" && pwd)
evolve_cli=${EVOLVE_CLI:-evolve}
evolve_python=${EVOLVE_PYTHON:-python3}

for required in \
  "$workspace/evolve.yaml" \
  "$workspace/evaluator/eval.env" \
  "$workspace/evaluator/splits.json"; do
  if [[ ! -e "$required" ]]; then
    printf 'missing required path: %s\n' "$required" >&2
    exit 1
  fi
done

EVOLVE_SMOKE_WORKSPACE="$workspace" \
EVOLVE_SMOKE_TASK_COUNT="$task_count" \
EVOLVE_SMOKE_MAX_GENERATIONS="$max_generations" \
EVOLVE_SMOKE_N_CONCURRENT="$n_concurrent" \
EVOLVE_SMOKE_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER="$environment_build_timeout_multiplier" \
EVOLVE_SMOKE_AGENT_STEP_LIMIT="$agent_step_limit" \
EVOLVE_SMOKE_TRACE_TASK_COUNT="$trace_task_count" \
"$evolve_python" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml


workspace = Path(os.environ["EVOLVE_SMOKE_WORKSPACE"])
task_count = int(os.environ["EVOLVE_SMOKE_TASK_COUNT"])
max_generations = int(os.environ["EVOLVE_SMOKE_MAX_GENERATIONS"])
n_concurrent = int(os.environ["EVOLVE_SMOKE_N_CONCURRENT"])
environment_build_timeout_multiplier = int(
    os.environ["EVOLVE_SMOKE_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER"]
)
agent_step_limit = int(os.environ["EVOLVE_SMOKE_AGENT_STEP_LIMIT"])
trace_task_count = int(os.environ["EVOLVE_SMOKE_TRACE_TASK_COUNT"])

config_path = workspace / "evolve.yaml"
manifest_path = workspace / "evaluator" / "splits.json"
config = yaml.safe_load(config_path.read_text())
manifest = json.loads(manifest_path.read_text())
tasks = manifest["tasks"]
original_train = [str(name) for name in tasks["train"]]
all_original_names = (
    original_train
    + [str(name) for name in tasks["gate"]]
    + [str(name) for name in tasks["sealed"]]
)
eligible = [
    name
    for name in original_train
    if not any(other != name and other in name for other in all_original_names)
]
if task_count > len(eligible):
    raise SystemExit(
        f"train split has {len(eligible)} prefix-safe smoke tasks; requested {task_count}"
    )

tau3_prefixes = (
    ("airline", "tau3-airline-"),
    ("banking_knowledge", "tau3-banking_knowledge-"),
    ("retail", "tau3-retail-"),
    ("telecom", "tau3-telecom-"),
)
if all(name.startswith("tau3-") for name in all_original_names):
    buckets = {
        category: [name for name in eligible if name.startswith(prefix)]
        for category, prefix in tau3_prefixes
    }
    if any(not names for names in buckets.values()):
        raise SystemExit("tau3 smoke selection requires a prefix-safe task in every category")
    selected = []
    while len(selected) < task_count:
        for category, _ in tau3_prefixes:
            if buckets[category] and len(selected) < task_count:
                selected.append(buckets[category].pop(0))
else:
    selected = eligible[:task_count]

tasks["train"] = selected
selected_set = set(selected)
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
evaluator["tasks_per_round"] = task_count
evaluator["n_concurrent"] = n_concurrent
evaluator["task_names"] = selected
evaluator["split"] = {**ratios, "seed": int(manifest["seed"])}
evaluator.setdefault("anchor", {})["final"] = False
evaluator.setdefault("agent_env", {})["MINISWE_STEP_LIMIT"] = str(agent_step_limit)
trace = config.get("operators", {}).get("trace_analyzer", {})
if trace.get("max_tasks") is not None:
    trace["max_tasks"] = min(task_count, trace_task_count)
if trace.get("max_concurrent") is not None:
    trace["max_concurrent"] = min(n_concurrent, trace_task_count)
config_path.write_text(yaml.safe_dump(config, sort_keys=False))

evaluator_dir = workspace / "evaluator"
(evaluator_dir / "agent.env").write_text(
    "".join(
        f"{key}={value}\n"
        for key, value in sorted(evaluator["agent_env"].items())
    )
)
(evaluator_dir / "tasks" / "train.txt").write_text(
    "".join(f"{name}\n" for name in selected)
)
(evaluator_dir / "smoke-task-names.txt").write_text(
    "".join(f"{name}\n" for name in selected)
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
        "EVOLVE_HARBOR_EXPECTED_TRIALS": str(task_count),
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
printf 'task_count=%s\n' "$task_count"
printf 'max_generations=%s\n' "$max_generations"
printf 'n_concurrent=%s\n' "$n_concurrent"
printf 'environment_build_timeout_multiplier=%s\n' "$environment_build_timeout_multiplier"
printf 'agent_step_limit=%s\n' "$agent_step_limit"
printf 'trace_task_count=%s\n' "$trace_task_count"
