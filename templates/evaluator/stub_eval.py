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

import json
import sys
from pathlib import Path

K = 8


def _attempts() -> int:
    for line in Path("evaluator/eval.env").read_text().splitlines():
        if line.startswith("EVOLVE_HARBOR_ATTEMPTS="):
            return max(1, int(line.split("=", 1)[1]))
    return 1


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

    task_results = {f"task-{i}": (f"task-{i}" not in failed) for i in range(K)}
    task_vector = {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {"trial": trial, "status": "complete", "reward": 1.0 if passed else 0.0}
                    for trial in range(_attempts())
                ]
            }
            for task_id, passed in task_results.items()
        },
    }
    passed = sum(task_results.values())
    score = passed / K

    (run_dir / "score").write_text(f"{score}\n")
    (run_dir / "status").write_text(("complete" if passed == K else "partial") + "\n")
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector) + "\n")
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": {"pass_rate": score}}) + "\n")
    return 0 if passed == K else 2


if __name__ == "__main__":
    sys.exit(main())
