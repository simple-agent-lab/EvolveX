#!/usr/bin/env python3
"""select — pick a parent from the archive.

Default: parent-balancing (design v0.4 §06-B1, DGM-style):
    p(i) ∝ score_norm(i) × 1 / (1 + offspring(i)) ** alpha
over valid_parent nodes. Offspring counts are derived from ledger parent
pointers at call time (nothing extra to store). Keeps high scorers favored
without letting one champion's descendants flood the population.

Variants (M3+): random / greedy / tournament / map-elites / novelty.
Contract: prints JSON {"parent": <genid present in archive>} to stdout.
Env: EVOLVE_SELECT_ALPHA (default 1.0), EVOLVE_SEED (reproducible tests).
"""
import json
import os
import random
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    path = os.path.join(WS, "archive.jsonl")
    if not os.path.exists(path):
        print(json.dumps({"parent": None, "error": "empty archive — bootstrap gen 0 first"}))
        return 1
    nodes = [json.loads(l) for l in open(path) if l.strip()]
    if not nodes:
        print(json.dumps({"parent": None, "error": "empty archive — bootstrap gen 0 first"}))
        return 1

    valid = [n for n in nodes if n.get("valid_parent")] or nodes

    offspring: dict = {}
    for n in nodes:
        p = n.get("parent")
        if p is not None:
            offspring[p] = offspring.get(p, 0) + 1

    scores = [n["score"] for n in valid]
    lo, hi = min(scores), max(scores)
    alpha = float(os.environ.get("EVOLVE_SELECT_ALPHA", "1.0"))

    def weight(n: dict) -> float:
        norm = 0.1 + ((n["score"] - lo) / (hi - lo) if hi > lo else 1.0)
        return norm / (1 + offspring.get(n["genid"], 0)) ** alpha

    seed = os.environ.get("EVOLVE_SEED")
    rng = random.Random(f"{seed}:{len(nodes)}") if seed else random.Random()
    pick = rng.choices(valid, weights=[weight(n) for n in valid], k=1)[0]

    print(json.dumps({"parent": pick["genid"], "strategy": "parent-balancing", "alpha": alpha}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
