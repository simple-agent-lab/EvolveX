from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from .archive import rows_by_genid
from .driver import RunOptions, run
from .git import git, git_stdout, tag_exists


@dataclass(frozen=True)
class ExperimentSmokeResult:
    status: str
    workspace: Path
    task: str
    result_path: Path
    error: str | None = None


def _selected_task(workspace: Path, requested: str | None) -> tuple[str, str]:
    split_path = workspace / "evaluator" / "splits.json"
    payload = json.loads(split_path.read_text())
    if not isinstance(payload, dict) or payload.get("resolved") is not True:
        raise ValueError("experiment smoke requires a resolved local dataset")
    tasks = payload.get("tasks")
    digests = payload.get("task_digests")
    if not isinstance(tasks, dict) or not isinstance(digests, dict):
        raise ValueError("experiment smoke requires frozen task content digests")
    available = sorted(
        {name for values in tasks.values() if isinstance(values, list) for name in values if isinstance(name, str)}
    )
    if not available:
        raise ValueError("experiment smoke found no dataset tasks")
    selected = requested or available[0]
    if selected not in available or not isinstance(digests.get(selected), str):
        raise ValueError(f"experiment smoke task is unavailable: {selected}")
    return selected, str(digests[selected])


def _next_workspace(workspace: Path) -> Path:
    root = workspace / "runs" / "experiment-smoke"
    root.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while (destination := root / f"attempt-{attempt}" / "workspace").exists():
        attempt += 1
    destination.parent.mkdir()
    return destination


def _rewrite_eval_env(path: Path) -> None:
    replacements = {
        "EVOLVE_HARBOR_N_CONCURRENT": "1",
        "EVOLVE_HARBOR_ATTEMPTS": "1",
        "EVOLVE_HARBOR_EXPECTED_TRIALS": "1",
        "EVOLVE_HARBOR_N": "1",
    }
    lines: list[str] = []
    seen: set[str] = set()
    for line in path.read_text().splitlines():
        name, separator, _ = line.partition("=")
        if separator and name in replacements:
            lines.append(f"{name}={replacements[name]}")
            seen.add(name)
        else:
            lines.append(line)
    lines.extend(f"{name}={value}" for name, value in replacements.items() if name not in seen)
    path.write_text("\n".join(lines) + "\n")


def _prepare_smoke_workspace(source: Path, destination: Path, task: str, digest: str) -> None:
    git(source, "clone", "--quiet", "--no-hardlinks", str(source), str(destination))
    git(destination, "config", "user.name", "Evolve Experiment Smoke")
    git(destination, "config", "user.email", "smoke@evolve.invalid")
    for tag in git_stdout(destination, "tag", "--list").splitlines():
        git(destination, "tag", "--delete", tag, check=False)
    for path in (destination / "archive.jsonl", destination / ".evolve-eval-receipts.jsonl"):
        path.unlink(missing_ok=True)
    shutil.rmtree(destination / "runs", ignore_errors=True)

    config_path = destination / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError("experiment smoke workspace has invalid evolve.yaml")
    experiment = config.setdefault("experiment", {})
    evaluator = config.setdefault("evaluator", {})
    if not isinstance(experiment, dict) or not isinstance(evaluator, dict):
        raise ValueError("experiment smoke workspace has invalid configuration sections")
    experiment["id"] = f"{source.name}-smoke-{int(time.time())}"
    experiment["max_generations"] = 1
    experiment["children_per_gen"] = 1
    evaluator["task_names"] = [task]
    evaluator["tasks_per_round"] = 1
    evaluator["k"] = 1
    evaluator["n_concurrent"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    split_path = destination / "evaluator" / "splits.json"
    split = json.loads(split_path.read_text())
    split["tasks"] = {"train": [task], "gate": [task], "sealed": []}
    split["task_digests"] = {task: digest}
    split["gate_tasks_per_round"] = 1
    split_path.write_text(json.dumps(split, indent=2, sort_keys=True) + "\n")
    _rewrite_eval_env(destination / "evaluator" / "eval.env")

    (destination / "archive.jsonl").write_text(
        json.dumps(
            {
                "cost": {"usd": 0, "wall_s": 0},
                "genid": "0",
                "mutated": [],
                "note": "initial scaffold",
                "parent": None,
                "reason": "generation zero requires real evaluation",
                "score": None,
                "status": "pending",
                "surface_violations": [],
                "tag": "gen/0",
                "valid_parent": False,
                "verdict": "pending",
            },
            sort_keys=True,
        )
        + "\n"
    )
    git(destination, "add", "--all")
    git(destination, "commit", "--quiet", "--no-gpg-sign", "-m", "Prepare isolated experiment smoke")
    git(destination, "tag", "gen/0")


def run_experiment_smoke(workspace: Path, *, task: str | None = None) -> ExperimentSmokeResult:
    source = workspace.resolve()
    selected, digest = _selected_task(source, task)
    destination = _next_workspace(source)
    result_path = destination.parent / "result.json"
    try:
        _prepare_smoke_workspace(source, destination, selected, digest)
        run(RunOptions(workspace=destination, max_generations=1, children_per_gen=1))
        row = rows_by_genid(destination).get("1", {})
        complete = row.get("outcome") == "benchmark_complete" and row.get("selection_eligible") is True
        tag_bound = tag_exists(destination, "gen/1") and git_stdout(
            destination, "rev-parse", "gen/1^{commit}"
        ) == row.get("candidate_commit")
        if not complete or not tag_bound:
            raise RuntimeError("full-loop smoke did not produce a complete commit-bound gen/1")
        payload = {"status": "passed", "task": selected, "workspace": str(destination)}
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return ExperimentSmokeResult("passed", destination, selected, result_path)
    except Exception as error:
        payload = {"status": "failed", "task": selected, "workspace": str(destination), "error": str(error)}
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return ExperimentSmokeResult("failed", destination, selected, result_path, str(error))
