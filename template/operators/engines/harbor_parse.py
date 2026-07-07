#!/usr/bin/env python3
"""engine adapter — normalize a harbor job result into the Harness contract shape
(result.json: score / score_ci / task_vector / task_ids / lane / harness_version).

Code-complete against harbor's documented result layout
(runs/<job>/result.json -> evals[key].pass_at_k / per-task verifier rewards);
the exact field mapping gets finalized against a live harbor install at M1.
"""
import argparse
import json
import math
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--splits", required=True)
    ap.add_argument("--lane", required=True)
    ap.add_argument("--harness-version", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    raw_path = os.path.join(a.job_dir, "result.json")
    if not os.path.exists(raw_path):
        print(f"harbor_parse: no result.json under {a.job_dir}", file=sys.stderr)
        return 1
    raw = json.load(open(raw_path))
    splits = json.load(open(a.splits))
    task_ids = splits["sealed_test"] if a.lane == "sealed" else splits[a.lane]

    # M1 finalizes this mapping against live harbor output; documented assumption:
    # raw["tasks"] is {task_name: {"passed": bool, ...}} ordered by the dataset
    # registry, and splits.json ids index into that ordering.
    tasks = raw.get("tasks") or {}
    names = sorted(tasks.keys())
    bits = []
    for t in task_ids:
        if t >= len(names):
            print(f"harbor_parse: split task id {t} outside dataset ({len(names)} tasks)",
                  file=sys.stderr)
            return 1
        bits.append(1 if tasks[names[t]].get("passed") else 0)

    score = sum(bits) / len(bits)
    half = 1.96 * math.sqrt(max(score * (1 - score), 1e-9) / len(bits))
    result = {
        "score": round(score, 4),
        "score_ci": [round(max(0.0, score - half), 4), round(min(1.0, score + half), 4)],
        "task_vector": "".join(str(b) for b in bits),
        "task_ids": task_ids,
        "lane": a.lane,
        "n_tasks": len(bits),
        "harness_version": a.harness_version,
        "metrics": {"pass_rate": round(score, 4), "engine": "harbor"},
    }
    os.makedirs(os.path.join(a.out, "artifacts"), exist_ok=True)
    with open(os.path.join(a.out, "result.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(a.out, "score"), "w") as f:
        f.write(f"{result['score']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
