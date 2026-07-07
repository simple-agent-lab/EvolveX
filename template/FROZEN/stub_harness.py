#!/usr/bin/env python3
"""FROZEN — M0 stub harness.

Fake scores, honest ruler: the score is derived deterministically from a hash
of candidate/ content (+ harness version salt), so the same candidate always
gets the same score and different mutations get different scores. That keeps
every M0 pipeline property (cross-gen comparability, best-ever re-eval, stamp
integrity) meaningful before harbor lands at M1.
"""
import argparse
import hashlib
import json
import math
import os


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--harness-version", default="stub-v1")
    a = ap.parse_args()

    seed = tree_hash(a.candidate) + a.harness_version
    import random

    rng = random.Random(seed)
    p_pass = 0.30 + 0.45 * rng.random()  # candidate-dependent "ability"
    bits = [1 if rng.random() < p_pass else 0 for _ in range(a.n_tasks)]
    score = sum(bits) / a.n_tasks
    half = 1.96 * math.sqrt(max(score * (1 - score), 1e-9) / a.n_tasks)

    result = {
        "score": round(score, 4),
        "score_ci": [round(max(0.0, score - half), 4), round(min(1.0, score + half), 4)],
        "task_vector": "".join(str(b) for b in bits),
        "n_tasks": a.n_tasks,
        "harness_version": a.harness_version,
        "metrics": {"pass_rate": round(score, 4), "stub": True},
    }
    os.makedirs(os.path.join(a.out, "artifacts"), exist_ok=True)
    with open(os.path.join(a.out, "result.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(a.out, "score"), "w") as f:
        f.write(f"{result['score']}\n")


if __name__ == "__main__":
    main()
