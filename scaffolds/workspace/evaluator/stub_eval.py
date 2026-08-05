#!/usr/bin/env python3
"""Deterministic stub evaluator for local testing (EVAL_STUB=1).

Scores exactly the tasks the evaluation targets: the evaluated split's members
when evaluator/splits.json is resolved, otherwise a synthetic task-0..task-{K-1}
suite sized from evaluator/eval.env. Every task passes unless target/agent.py
declares a `# FAIL <task-name>` line; flipping those lines is how a candidate
edit changes the score, which keeps gate decisions and
`predicted_fixes -> verified_fixes` real signals under the stub. Writes score,
status, task_vector.json, evaluation_artifacts.json, and metrics.json; exits 0
when every task passes, else 2 (partial).
"""

import hashlib
import json
import os
import sys
from pathlib import Path


def _eval_env(name: str) -> str | None:
    for line in Path("evaluator/eval.env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip("'\"")
    return None


def _attempts() -> int:
    plan = _run_plan()
    if isinstance(plan.get("attempts_per_task"), int):
        return max(1, int(plan["attempts_per_task"]))
    return max(1, int(_eval_env("EVOLVE_HARBOR_ATTEMPTS") or 1))


def _task_names(run_dir: Path, kind: str | None, attempts: int) -> list[str]:
    try:
        selection = json.loads((run_dir / "task-split.json").read_text())
    except (OSError, json.JSONDecodeError):
        selection = {}
    selected = selection.get("tasks")
    if isinstance(selected, list) and selected and all(isinstance(name, str) and name for name in selected):
        return list(selected)
    plan = _run_plan()
    planned = plan.get("tasks")
    if isinstance(planned, list) and planned and all(isinstance(name, str) and name for name in planned):
        return list(planned)
    split = os.environ.get("EVOLVE_EVAL_SPLIT") or ("sealed" if kind == "anchor" else "gate")
    try:
        manifest = json.loads(Path("evaluator/splits.json").read_text())
    except (OSError, json.JSONDecodeError):
        manifest = {}
    names = list(manifest.get("tasks", {}).get(split, [])) if manifest.get("resolved") else []
    if not names:
        prefix = "sealed-task" if kind == "anchor" else "task"
        expected = int(_eval_env("EVOLVE_HARBOR_EXPECTED_TRIALS") or 0)
        count = expected // attempts if expected else int(os.environ.get("EVOLVE_TASK_LIMIT", "8"))
        names = [f"{prefix}-{i}" for i in range(max(1, count))]
    limit = os.environ.get("EVOLVE_TASK_LIMIT")
    if limit:
        names = names[: max(1, int(limit))]
    return names


def _run_plan() -> dict[str, object]:
    configured = os.environ.get("EVOLVE_RUN_PLAN")
    if not configured:
        return {}
    try:
        payload = json.loads(Path(configured).read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/gen-0/eval")
    run_dir.mkdir(parents=True, exist_ok=True)

    agent = Path("target/agent.py")
    failed: set[str] = set()
    missing: set[str] = set()
    for line in (agent.read_text() if agent.exists() else "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# FAIL "):
            failed.update(stripped[len("# FAIL ") :].split())
        if stripped.startswith("# MISSING "):
            missing.update(stripped[len("# MISSING ") :].split())

    attempts = _attempts()
    names = _task_names(run_dir, os.environ.get("EVOLVE_EVAL_KIND"), attempts)
    task_results = {name: name not in failed for name in names if name not in missing}
    task_vector = {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {"trial": trial, "status": "benchmark_complete", "reward": 1.0 if passed else 0.0}
                    for trial in range(attempts)
                ]
            }
            for task_id, passed in task_results.items()
        },
    }
    passed = sum(task_results.values())
    score = passed / len(names)

    artifacts = run_dir / "artifacts"
    artifacts.mkdir(exist_ok=True)
    artifact_trials = []
    for task_id, passed_task in task_results.items():
        for trial in range(attempts):
            artifact_name = task_id.replace("/", "__").replace("\\", "__")
            trace = artifacts / f"{artifact_name}-trial-{trial}.trace"
            trace.write_text(
                f"stub evaluation trace\ntask={task_id}\ntrial={trial}\noutcome={'pass' if passed_task else 'fail'}\n"
            )
            artifact_trials.append(
                {
                    "task_name": task_id,
                    "trial": trial,
                    "files": [
                        {
                            "path": trace.name,
                            "kind": "agent_trace",
                            "size": trace.stat().st_size,
                            "sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
                        }
                    ],
                }
            )

    (run_dir / "score").write_text(f"{score}\n")
    (run_dir / "status").write_text(("complete" if passed == len(names) else "partial") + "\n")
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector) + "\n")
    (run_dir / "evaluation_artifacts.json").write_text(
        json.dumps({"jobs_dir": str(artifacts.resolve()), "trials": artifact_trials}, sort_keys=True) + "\n"
    )
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": {"pass_rate": score}}) + "\n")
    return 0 if passed == len(names) else 2


if __name__ == "__main__":
    sys.exit(main())
