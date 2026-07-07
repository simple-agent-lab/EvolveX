#!/usr/bin/env python3
"""rollout — dev-lane sampling for mutation feedback (advisory, never canonical).

Default: failure-focused — surface the parent's failed tasks as clusters for
the mutator to aim at. M0 derives them from the parent's stamped task_vector;
M1 runs real harbor rollouts on the dev split (budget-capped).

Variants: random-subset / staged / full / racing.
Contract: writes runs/gen-<id>/dev/feedback.json, prints JSON {"ok": true, ...}.
Trajectories written here are the future training-data source (distill, M5).
"""
import argparse
import json
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, required=True)
    ap.add_argument("--parent", type=int, required=True)
    a = ap.parse_args()

    failed = []
    parent_stamp = os.path.join(WS, "runs", f"gen-{a.parent}", "stamp.json")
    if os.path.exists(parent_stamp):
        vec = json.load(open(parent_stamp)).get("task_vector", "")
        failed = [i for i, b in enumerate(vec) if b == "0"]

    dev_dir = os.path.join(WS, "runs", f"gen-{a.gen}", "dev")
    os.makedirs(dev_dir, exist_ok=True)
    feedback = {
        "lane": "dev",
        "strategy": "failure-focused",
        "failed_tasks": failed,
        "clusters": [{"kind": "stub-cluster", "tasks": failed}] if failed else [],
        "note": "M0 stub: derived from parent task_vector; M1 runs real dev rollouts on harbor",
    }
    with open(os.path.join(dev_dir, "feedback.json"), "w") as f:
        json.dump(feedback, f, indent=1)

    print(json.dumps({"ok": True, "lane": "dev", "failed_tasks": len(failed),
                      "feedback": f"runs/gen-{a.gen}/dev/feedback.json"}))


if __name__ == "__main__":
    main()
