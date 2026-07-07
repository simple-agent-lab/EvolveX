#!/usr/bin/env python3
"""FROZEN — M0/M1-mechanics stub harness.

Fake scores, honest ruler: per-task pass/fail is derived deterministically
from a hash of candidate/ content + the task id (+ harness version salt), so
the same candidate always gets the same result on the same task, different
mutations move different tasks, and the three-way split behaves exactly like
a real benchmark would — before harbor lands.

Lanes (driven by FROZEN/splits.json):
  dev    — rollout's lane (advisory feedback + trajectory stubs for distill)
  gate   — canonical eval's lane (the only lane that ever gets stamped)
  sealed — human-triggered only; never selected on, never trains
"""
import argparse
import hashlib
import json
import math
import os
import random


def tree_hash(path: str) -> str:
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(root, name)
            h.update(os.path.relpath(p, path).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def task_result(candidate_hash: str, version: str, task_id: int) -> bool:
    """Deterministic per-task outcome: candidate 'ability' × task-specific roll."""
    ability = random.Random(f"{candidate_hash}:{version}:ability").random()
    p_pass = 0.30 + 0.45 * ability
    roll = random.Random(f"{candidate_hash}:{version}:task:{task_id}").random()
    return roll < p_pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--splits", required=True, help="path to FROZEN/splits.json")
    ap.add_argument("--lane", required=True, choices=("dev", "gate", "sealed"))
    ap.add_argument("--harness-version", default="stub-v1")
    ap.add_argument("--trajectories", action="store_true",
                    help="emit per-task trajectory stubs (dev lane; distill's raw material)")
    a = ap.parse_args()

    splits = json.load(open(a.splits))
    task_ids = splits["sealed_test"] if a.lane == "sealed" else splits[a.lane]

    chash = tree_hash(a.candidate)
    bits = [1 if task_result(chash, a.harness_version, t) else 0 for t in task_ids]
    score = sum(bits) / len(bits)
    half = 1.96 * math.sqrt(max(score * (1 - score), 1e-9) / len(bits))

    result = {
        "score": round(score, 4),
        "score_ci": [round(max(0.0, score - half), 4), round(min(1.0, score + half), 4)],
        "task_vector": "".join(str(b) for b in bits),
        "task_ids": task_ids,
        "lane": a.lane,
        "n_tasks": len(task_ids),
        "harness_version": a.harness_version,
        "metrics": {"pass_rate": round(score, 4), "stub": True},
    }
    os.makedirs(os.path.join(a.out, "artifacts"), exist_ok=True)
    with open(os.path.join(a.out, "result.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(a.out, "score"), "w") as f:
        f.write(f"{result['score']}\n")

    if a.trajectories:
        tdir = os.path.join(a.out, "trajs")
        os.makedirs(tdir, exist_ok=True)
        for t, b in zip(task_ids, bits):
            traj = {
                "task_id": t,
                "passed": bool(b),
                "steps": [f"stub step {i} on task {t}" for i in range(3)],
                "candidate_hash": chash[:16],
            }
            traj["trajectory_hash"] = hashlib.sha256(
                json.dumps(traj, sort_keys=True).encode()).hexdigest()[:16]
            with open(os.path.join(tdir, f"task_{t}.json"), "w") as f:
                json.dump(traj, f, indent=1)


if __name__ == "__main__":
    main()
