#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'usage: %s {ahe|hyperagents} {miniswe|codex} {tau3|terminal-bench-2} WORKSPACE_NAME N_CONCURRENT [--dry-run]\n' "$0" >&2
}

method=${1:-}
target=${2:-}
benchmark=${3:-}
name=${4:-}
n_concurrent=${5:-}
mode=${6:-}

case "$method" in
  ahe|hyperagents) ;;
  *)
    usage
    exit 2
    ;;
esac

case "$target" in
  miniswe|codex) ;;
  *)
    usage
    exit 2
    ;;
esac

case "$benchmark" in
  tau3)
    train_count=100
    gate_count=100
    sealed_count=175
    seed=42
    simulator_model=openai/gpt-5.4-2026-03-05
    simulator_effort=low
    ;;
  terminal-bench-2)
    train_count=50
    gate_count=19
    sealed_count=20
    seed=0
    simulator_model=n/a
    simulator_effort=n/a
    ;;
  *)
    usage
    exit 2
    ;;
esac

case "$name" in
  ""|*[!A-Za-z0-9._-]*)
    printf 'invalid workspace name: %s\n' "$name" >&2
    exit 2
    ;;
esac

case "$n_concurrent" in
  ""|*[!0-9]*|0)
    printf 'N_CONCURRENT must be a positive integer\n' >&2
    exit 2
    ;;
esac

if [[ -n "$mode" && "$mode" != "--dry-run" ]]; then
  printf 'unknown option: %s\n' "$mode" >&2
  exit 2
fi

root=${EVOLVE_EXPERIMENT_ROOT:-/data00/home/zimuwang/evolve-experiments}
framework=${EVOLVE_FRAMEWORK:-/data00/home/zimuwang/simple-evolve-agent-main}

if [[ "$benchmark" == "tau3" ]]; then
  dataset=${TAU3_DATASET:-$root/datasets/tau3-bench-375}
  manifest=${TAU3_MANIFEST:-$root/manifests/tau3-bench-100-100-175.json}
else
  dataset=${TB2_DATASET:-$root/datasets/terminal-bench-2-50-19-20}
  manifest=${TB2_MANIFEST:-$root/manifests/terminal-bench-2-50-19-20.json}
fi

workspace="$root/workspaces/$name"

printf 'method=%s\n' "$method"
printf 'target=%s\n' "$target"
printf 'benchmark=%s\n' "$benchmark"
printf 'workspace=%s\n' "$workspace"
printf 'framework=%s\n' "$framework"
printf 'dataset=%s\n' "$dataset"
printf 'manifest=%s\n' "$manifest"
printf 'tasks_per_round=%s\n' "$train_count"
printf 'train_count=%s\n' "$train_count"
printf 'gate_count=%s\n' "$gate_count"
printf 'sealed_count=%s\n' "$sealed_count"
printf 'seed=%s\n' "$seed"
printf 'n_concurrent=%s\n' "$n_concurrent"
printf 'simulator_model=%s\n' "$simulator_model"
printf 'simulator_effort=%s\n' "$simulator_effort"

if [[ "$mode" == "--dry-run" ]]; then
  exit 0
fi

evolve_cli=${EVOLVE_CLI:-$framework/.venv/bin/evolve}
evolve_python=${EVOLVE_PYTHON:-$framework/.venv/bin/python}
runtime_env="$root/runtime.env"

for required in "$evolve_cli" "$evolve_python" "$dataset" "$manifest" "$runtime_env"; do
  if [[ ! -e "$required" ]]; then
    printf 'missing required path: %s\n' "$required" >&2
    exit 1
  fi
done

if [[ ! -f "$runtime_env" ]]; then
  printf 'missing required path: %s\n' "$runtime_env" >&2
  exit 1
fi

if [[ -e "$workspace" ]]; then
  printf 'workspace already exists: %s\n' "$workspace" >&2
  exit 1
fi

mkdir -p "$root/workspaces"
init_args=(init "$workspace" --recipe "$method" --dataset "$dataset")
if [[ "$target" == "codex" ]]; then
  profile_dir=$(mktemp -d "${TMPDIR:-/tmp}/evolve-codex-profile.XXXXXX")
  trap 'rm -rf "$profile_dir"' EXIT
  script_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
  "$evolve_python" - "$script_root/recipes/$method/evolve.yaml" "$profile_dir/evolve.yaml" <<'PY'
from pathlib import Path
import sys

import yaml


source, destination = map(Path, sys.argv[1:])
config = yaml.safe_load(source.read_text())
config["target"] = {"seed": "builtin-codex"}
evaluator = config["evaluator"]
evaluator["agent"] = "target.agent:HarborAgent"
evaluator["model"] = "gpt-5.4"
evaluator.pop("candidate_runtime", None)
evaluator["agent_env"] = {}
destination.write_text(yaml.safe_dump(config, sort_keys=False))
PY
  init_args=(init "$workspace" --recipe-path "$profile_dir/evolve.yaml" --dataset "$dataset")
  init_args+=(--seed builtin-codex)
elif [[ -n "${EVOLVE_TARGET_SEED:-}" ]]; then
  init_args+=(--seed "$EVOLVE_TARGET_SEED")
fi
set -a
. "$runtime_env"
set +a
"$evolve_cli" "${init_args[@]}"

EVOLVE_SETUP_WORKSPACE="$workspace" \
EVOLVE_SETUP_DATASET="$dataset" \
EVOLVE_SETUP_MANIFEST="$manifest" \
EVOLVE_SETUP_BENCHMARK="$benchmark" \
EVOLVE_SETUP_NAME="$name" \
EVOLVE_SETUP_METHOD="$method" \
EVOLVE_SETUP_TARGET="$target" \
EVOLVE_SETUP_TRAIN_COUNT="$train_count" \
EVOLVE_SETUP_GATE_COUNT="$gate_count" \
EVOLVE_SETUP_SEALED_COUNT="$sealed_count" \
EVOLVE_SETUP_SEED="$seed" \
EVOLVE_SETUP_N_CONCURRENT="$n_concurrent" \
"$evolve_python" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml


workspace = Path(os.environ["EVOLVE_SETUP_WORKSPACE"])
dataset = Path(os.environ["EVOLVE_SETUP_DATASET"]).resolve()
manifest_path = Path(os.environ["EVOLVE_SETUP_MANIFEST"])
benchmark = os.environ["EVOLVE_SETUP_BENCHMARK"]
method = os.environ["EVOLVE_SETUP_METHOD"]
target = os.environ["EVOLVE_SETUP_TARGET"]
name = os.environ["EVOLVE_SETUP_NAME"]
expected_counts = {
    "train": int(os.environ["EVOLVE_SETUP_TRAIN_COUNT"]),
    "gate": int(os.environ["EVOLVE_SETUP_GATE_COUNT"]),
    "sealed": int(os.environ["EVOLVE_SETUP_SEALED_COUNT"]),
}
seed = int(os.environ["EVOLVE_SETUP_SEED"])
n_concurrent = int(os.environ["EVOLVE_SETUP_N_CONCURRENT"])

source = json.loads(manifest_path.read_text())
raw_tasks = source.get("tasks", source)
if not isinstance(raw_tasks, dict):
    raise SystemExit(f"manifest has no task mapping: {manifest_path}")
tasks = {
    split: [str(name) for name in raw_tasks.get(split, [])]
    for split in ("train", "gate", "sealed")
}
observed_counts = {split: len(names) for split, names in tasks.items()}
if observed_counts != expected_counts:
    raise SystemExit(
        f"manifest count mismatch: expected={expected_counts} observed={observed_counts}"
    )
all_names = tasks["train"] + tasks["gate"] + tasks["sealed"]
if len(set(all_names)) != len(all_names):
    raise SystemExit("manifest train/gate/sealed task names are not disjoint")
dataset_names = sorted(
    path.name
    for path in dataset.iterdir()
    if path.is_dir() and (path / "task.toml").is_file()
)
if sorted(all_names) != dataset_names:
    missing = sorted(set(all_names) - set(dataset_names))[:5]
    extra = sorted(set(dataset_names) - set(all_names))[:5]
    raise SystemExit(f"dataset/manifest mismatch: missing={missing} extra={extra}")

total = len(all_names)
ratios = {split: expected_counts[split] / total for split in expected_counts}
normalized_manifest = {
    "version": 1,
    "dataset": str(dataset),
    "resolved": True,
    "seed": seed,
    "ratios": ratios,
    "sampling": "static",
    "gate_tasks_per_round": 0,
    "counts": expected_counts,
    "tasks": tasks,
}
normalized_manifest["digests"] = {
    split: hashlib.sha256(
        json.dumps(sorted(names), separators=(",", ":")).encode()
    ).hexdigest()
    for split, names in tasks.items()
}

config_path = workspace / "evolve.yaml"
config = yaml.safe_load(config_path.read_text())
experiment = config["experiment"]
experiment.pop("budget_usd", None)
experiment.update(
    {
        "id": name,
        "max_generations": 10,
        "children_per_gen": 1,
        "mode": "driver",
        "seed": 0,
    }
)

operators = config["operators"]
operators["timeout_s"] = 600
operators["select"]["timeout_s"] = 600
operators["rollout"]["timeout_s"] = 43200
trace = operators["trace_analyzer"]
trace["timeout_s"] = 7200 if method == "ahe" else 600
if method == "ahe":
    trace["max_tasks"] = expected_counts["train"]
    trace["max_concurrent"] = n_concurrent
meta = operators["meta_agent"]
meta.update(
    {
        "runner": "harbor",
        "expose_gate_data": False,
        "agent": "codex",
        "model": "gpt-5.4",
        "environment": "docker",
        "image": "evolve-meta-agent-app:ubuntu-latest",
        "max_retries": 1,
        "timeout_s": 7200,
    }
)
meta["agent_kwargs"] = {"reasoning_effort": "xhigh"}
operators["gate"]["timeout_s"] = 43200
operators["record"]["timeout_s"] = 600

evaluator = config["evaluator"]
evaluator.pop("task_scope", None)
evaluator.update(
    {
        "engine": "harbor",
        "model": "openai/gpt-5.4-2026-03-05",
        "dataset": str(dataset),
        "evaluation_split": "train",
        "sampling": "static",
        "tasks_per_round": expected_counts["train"],
        "split": {**ratios, "seed": seed},
        "k": 1,
        "n_concurrent": n_concurrent,
        "agent_setup_timeout_multiplier": 1,
        "agent_timeout_multiplier": 2,
        "max_retries": 1,
        "benchmark_timeout_is_zero": True,
        "partial_floor": 0.8,
        "anchor": {"final": True, "every_rounds": 0},
    }
)
evaluator["agent_env"] = {
    "MINISWE_STEP_LIMIT": "100",
    "MINISWE_REASONING_EFFORT": "high",
    "MINISWE_COST_LIMIT": "3.0",
    "MINISWE_ENV_TIMEOUT": "30",
    "MINISWE_MAX_OUTPUT_LIMIT": "10000",
}
if target == "codex":
    config["target"] = {"seed": "builtin-codex"}
    meta["prompt_path"] = "target/prompt.md"
    meta["skills_dir"] = "target/skills"
    meta.pop("memory_dir", None)
    meta.pop("tools_dir", None)

    evaluator["agent"] = "target.agent:HarborAgent"
    evaluator["model"] = "gpt-5.4"
    evaluator.pop("candidate_runtime", None)
    evaluator["agent_env"] = {}
config_path.write_text(yaml.safe_dump(config, sort_keys=False))

evaluator_dir = workspace / "evaluator"
(evaluator_dir / "splits.json").write_text(
    json.dumps(normalized_manifest, indent=2, sort_keys=True) + "\n"
)
tasks_dir = evaluator_dir / "tasks"
tasks_dir.mkdir(exist_ok=True)
for split in ("train", "sealed"):
    (tasks_dir / f"{split}.txt").write_text(
        "".join(f"{task_name}\n" for task_name in tasks[split])
    )

agent_env_path = evaluator_dir / "agent.env"
agent_env_path.write_text(
    "".join(f"{key}={value}\n" for key, value in sorted(evaluator["agent_env"].items()))
)

agent_kwargs_path = evaluator_dir / "agent.kwargs"
if target == "codex":
    agent_kwargs_path.write_text("reasoning_effort=high\n")
elif agent_kwargs_path.exists():
    agent_kwargs_path.unlink()

eval_env_path = evaluator_dir / "eval.env"
eval_env = {}
for line in eval_env_path.read_text().splitlines():
    key, separator, value = line.partition("=")
    if separator:
        eval_env[key] = value
eval_env.update(
    {
        "EVOLVE_HARBOR_N_CONCURRENT": str(n_concurrent),
        "EVOLVE_HARBOR_EXPECTED_TRIALS": str(expected_counts["train"]),
        "EVOLVE_HARBOR_N": str(n_concurrent),
        "EVOLVE_HARBOR_MODEL": "openai/gpt-5.4-2026-03-05",
        "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER": "1",
        "EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER": "2",
        "EVOLVE_HARBOR_MAX_RETRIES": "1",
        "EVOLVE_HARBOR_ANCHOR_TASK_FILE": "evaluator/tasks/sealed.txt",
    }
)
if target == "codex":
    eval_env["EVOLVE_HARBOR_CODEX_SUBSCRIPTION"] = "1"
    eval_env["EVOLVE_HARBOR_MODEL"] = "gpt-5.4"
else:
    eval_env.pop("EVOLVE_HARBOR_CODEX_SUBSCRIPTION", None)
eval_env["EVOLVE_HARBOR_AGENT"] = evaluator["agent"]
eval_env_path.write_text(
    "".join(f"{key}={value}\n" for key, value in sorted(eval_env.items()))
)

simulator_path = evaluator_dir / "simulator.env"
if benchmark == "tau3":
    simulator_path.write_text(
        "TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05\n"
        "TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05\n"
        "TAU2_USER_REASONING_EFFORT=low\n"
    )
elif simulator_path.exists():
    simulator_path.unlink()
PY

git -C "$workspace" add evolve.yaml evaluator
git -C "$workspace" \
  -c user.name="Evolve Experiment Setup" \
  -c user.email="evolve@example.invalid" \
  commit --amend --no-edit
git -C "$workspace" tag -f gen/0
"$evolve_cli" verify "$workspace"
printf 'prepared=%s\n' "$workspace"
