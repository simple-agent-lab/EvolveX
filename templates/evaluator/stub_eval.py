#!/usr/bin/env python3
"""Deterministic stub evaluator with per-task results.

Simulates a task suite (task-0 .. task-{K-1}) whose outcome is a function of the
candidate: every task passes by default (so a fresh candidate scores 1.0), but a
candidate may fail specific tasks by declaring `# FAIL task-N` lines in
target/agent.py. A candidate edit that changes those lines flips which tasks pass —
which is what makes `predicted_fixes -> verified_fixes` a real signal under the
stub. Writes score (pass rate), status, task_vector.json, and metrics.json;
exits 0 (complete) when every task passes, else 2 (partial).
"""

import hashlib
import json
import sys
from pathlib import Path

K = 8


def _attempts() -> int:
    for line in Path("evaluator/eval.env").read_text().splitlines():
        if line.startswith("EVOLVE_HARBOR_ATTEMPTS="):
            return max(1, int(line.split("=", 1)[1]))
    return 1


def _task_count(attempts: int) -> int:
    for line in Path("evaluator/eval.env").read_text().splitlines():
        if line.startswith("EVOLVE_HARBOR_EXPECTED_TRIALS="):
            expected = int(line.split("=", 1)[1])
            return max(1, expected // attempts)
    return K


def main() -> int:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/gen-0/eval")
    run_dir.mkdir(parents=True, exist_ok=True)

    agent = Path("target/agent.py")
    text = agent.read_text() if agent.exists() else ""
    failed: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# FAIL "):
            failed.update(stripped[len("# FAIL ") :].split())

    attempts = _attempts()
    task_count = _task_count(attempts)
    task_results = {f"task-{i}": (f"task-{i}" not in failed) for i in range(task_count)}
    task_vector = {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {"trial": trial, "status": "complete", "reward": 1.0 if passed else 0.0}
                    for trial in range(attempts)
                ]
            }
            for task_id, passed in task_results.items()
        },
    }
    passed = sum(task_results.values())
    score = passed / task_count

    artifacts = run_dir / "artifacts"
    artifacts.mkdir(exist_ok=True)
    artifact_trials = []
    for task_id, passed_task in task_results.items():
        for trial in range(attempts):
            trace = artifacts / f"{task_id}-trial-{trial}.trace"
            trace.write_text(
                "stub evaluation trace\n"
                f"task={task_id}\n"
                f"trial={trial}\n"
                f"outcome={'pass' if passed_task else 'fail'}\n"
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
    (run_dir / "status").write_text(("complete" if passed == task_count else "partial") + "\n")
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector) + "\n")
    (run_dir / "evaluation_artifacts.json").write_text(
        json.dumps({"jobs_dir": str(artifacts.resolve()), "trials": artifact_trials}, sort_keys=True) + "\n"
    )
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": {"pass_rate": score}}) + "\n")
    return 0 if passed == task_count else 2


if __name__ == "__main__":
    sys.exit(main())
