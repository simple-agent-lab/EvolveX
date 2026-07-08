#!/usr/bin/env python3
"""select — pick a parent from the archive.

Variants (config.json "select"):
  parent-balancing (default) — p(i) ∝ score_norm(i) / (1+offspring(i))^alpha
        (design §06-B1, DGM-style: favor high scorers without letting one
        champion's descendants flood the population)
  random     — uniform over valid parents (HyperAgents / open-ended)
  greedy     — always the best valid parent (autoresearch hillclimb chain)
  tournament — sample T=3, take the best (AHE-style elitist pressure)
"""
import os
import random

from FROZEN.contracts.oplib import OperatorError, config, env_seed, operator_main, read_archive  # noqa: E402
from FROZEN.contracts.protocol import SelectOutput  # noqa: E402


@operator_main("select")
def main(args):
    nodes = read_archive()
    if not nodes:
        raise OperatorError("empty archive — bootstrap gen 0 first")
    valid = [n for n in nodes if n.get("valid_parent")] or nodes
    variant = config().get("select", "parent-balancing")
    rng = random.Random(env_seed(salt=str(len(nodes))))

    if variant == "random":
        pick = rng.choice(valid)
    elif variant == "greedy":
        pick = max(valid, key=lambda n: (n["score"], n["genid"]))
    elif variant == "tournament":
        arena = [rng.choice(valid) for _ in range(min(3, len(valid)))]
        pick = max(arena, key=lambda n: (n["score"], n["genid"]))
    else:  # parent-balancing
        variant = "parent-balancing"
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

        pick = rng.choices(valid, weights=[weight(n) for n in valid], k=1)[0]

    return SelectOutput(parent=pick["genid"], extras={"strategy": variant})


if __name__ == "__main__":
    main()
