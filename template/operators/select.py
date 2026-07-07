#!/usr/bin/env python3
"""select — pick a parent from the archive.

Default: parent-balancing (design v0.4 §06-B1, DGM-style):
    p(i) ∝ score_norm(i) × 1 / (1 + offspring(i)) ** alpha
over valid_parent nodes; offspring counts derived from ledger parent pointers
at call time. Keeps high scorers favored without letting one champion's
descendants flood the population.

Variants (M3+): random / greedy / tournament / map-elites / novelty.
"""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import OperatorError, env_seed, operator_main, read_archive  # noqa: E402
from FROZEN.contracts.protocol import SelectOutput  # noqa: E402


@operator_main("select")
def main(args):
    nodes = read_archive()
    if not nodes:
        raise OperatorError("empty archive — bootstrap gen 0 first")

    valid = [n for n in nodes if n.get("valid_parent")] or nodes

    offspring = {}
    for n in nodes:
        if n.get("parent") is not None:
            offspring[n["parent"]] = offspring.get(n["parent"], 0) + 1

    scores = [n["score"] for n in valid]
    lo, hi = min(scores), max(scores)
    alpha = float(os.environ.get("EVOLVE_SELECT_ALPHA", "1.0"))

    def weight(n):
        norm = 0.1 + ((n["score"] - lo) / (hi - lo) if hi > lo else 1.0)
        return norm / (1 + offspring.get(n["genid"], 0)) ** alpha

    rng = random.Random(env_seed(salt=str(len(nodes))))
    pick = rng.choices(valid, weights=[weight(n) for n in valid], k=1)[0]
    return SelectOutput(parent=pick["genid"],
                        extras={"strategy": "parent-balancing", "alpha": alpha})


if __name__ == "__main__":
    main()
