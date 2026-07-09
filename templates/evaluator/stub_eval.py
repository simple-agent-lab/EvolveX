#!/usr/bin/env python3
"""Deterministic stub evaluator with per-task results.

Simulates a task suite (task-0 .. task-{K-1}) whose outcome is a function of the
candidate: every task passes by default (so a fresh candidate scores 1.0), but a
candidate may fail specific tasks by declaring `# FAIL task-N` lines in
target/agent.py. A mutation that changes those lines flips which tasks pass —
which is what makes `predicted_fixes -> verified_fixes` a real signal under the
stub. Writes score (pass rate), status, task_vector.json, and metrics.json;
exits 0 (complete) when every task passes, else 2 (partial).
"""

import json
import sys
from pathlib import Path

K = 8


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

    task_vector = {f"task-{i}": (f"task-{i}" not in failed) for i in range(K)}
    passed = sum(1 for ok in task_vector.values() if ok)
    score = passed / K

    (run_dir / "score").write_text(f"{score}\n")
    (run_dir / "status").write_text(("complete" if passed == K else "partial") + "\n")
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector) + "\n")
    (run_dir / "metrics.json").write_text(json.dumps({"dimensions": {"pass_rate": score}}) + "\n")
    return 0 if passed == K else 2


if __name__ == "__main__":
    sys.exit(main())
