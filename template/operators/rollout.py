#!/usr/bin/env python3
"""rollout — dev-lane sampling for mutation feedback (advisory, never canonical).

Runs the engine on the DEV split against the parent's checkout (the working
tree at this point in the loop) and emits failure-focused feedback for the
mutator plus per-task trajectory stubs — distill's (M5) raw material.
The gate split belongs to FROZEN/eval.sh; the sealed split to humans.

Variants: random-subset / staged / full / racing (budget-capped).
"""
import os
import subprocess
import sys

from FROZEN.contracts.oplib import OperatorError, operator_main, read_json, run_dir, write_json, ws_path  # noqa: E402
from FROZEN.contracts.protocol import RolloutOutput  # noqa: E402


@operator_main("rollout")
def main(args):
    dev_dir = run_dir(args.gen) / "dev"
    dev_dir.mkdir(parents=True, exist_ok=True)

    if os.environ.get("HARNESS_STUB", "0") == "1":
        cmd = [sys.executable, str(ws_path("FROZEN", "stub_harness.py")),
               "--candidate", str(ws_path("candidate")),
               "--out", str(dev_dir),
               "--splits", str(ws_path("FROZEN", "splits.json")),
               "--lane", "dev", "--trajectories"]
    else:
        cmd = ["bash", str(ws_path("operators", "engines", "harbor.sh")),
               str(args.gen), "dev", str(dev_dir)]
    p = subprocess.run(cmd, cwd=ws_path(), capture_output=True, text=True)
    if p.returncode != 0:
        raise OperatorError(f"dev engine failed (exit {p.returncode}): {p.stderr.strip()[:200]}")

    result = read_json(dev_dir / "result.json", {})
    task_ids = result.get("task_ids", [])
    vec = result.get("task_vector", "")
    failed = [t for t, b in zip(task_ids, vec) if b == "0"]

    feedback = {
        "lane": "dev",
        "strategy": "failure-focused",
        "dev_score": result.get("score"),
        "task_ids": task_ids,
        "task_vector": vec,
        "failed_tasks": failed,
        "clusters": [{"kind": "failure-cluster", "tasks": failed}] if failed else [],
    }
    write_json(dev_dir / "feedback.json", feedback)
    return RolloutOutput(ok=True, lane="dev",
                         extras={"dev_score": result.get("score"),
                                 "failed_tasks": len(failed),
                                 "feedback": f"runs/gen-{args.gen}/dev/feedback.json"})


if __name__ == "__main__":
    main()
