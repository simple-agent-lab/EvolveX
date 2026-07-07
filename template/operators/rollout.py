#!/usr/bin/env python3
"""rollout — dev-lane sampling for mutation feedback (advisory, never canonical).

Default: failure-focused — surface the parent's failed tasks as clusters for
the mutator to aim at. M0 derives them from the parent's stamped task_vector;
M1 runs real harbor rollouts on the dev split (budget-capped). Trajectories
written here are the future training-data source (distill, M5).

Variants: random-subset / staged / full / racing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import operator_main, read_json, run_dir, write_json, ws_path  # noqa: E402
from FROZEN.contracts.protocol import RolloutOutput  # noqa: E402


@operator_main("rollout")
def main(args):
    parent_stamp = read_json(ws_path("runs", f"gen-{args.parent}", "stamp.json"), {})
    vec = parent_stamp.get("task_vector", "")
    failed = [i for i, b in enumerate(vec) if b == "0"]

    feedback = {
        "lane": "dev",
        "strategy": "failure-focused",
        "failed_tasks": failed,
        "clusters": [{"kind": "stub-cluster", "tasks": failed}] if failed else [],
        "note": "M0 stub: derived from parent task_vector; M1 runs real dev rollouts on harbor",
    }
    write_json(run_dir(args.gen) / "dev" / "feedback.json", feedback)
    return RolloutOutput(ok=True, lane="dev",
                         extras={"failed_tasks": len(failed),
                                 "feedback": f"runs/gen-{args.gen}/dev/feedback.json"})


if __name__ == "__main__":
    main()
