"""HyperAgents score-proportional, child-penalized parent selection."""

import math

from evolve.frozen import sdk
from evolve.frozen.interfaces import SelectOperator, SelectResult


def selection_weights(parents, rows):
    candidates = {str(row["genid"]): row for row in parents}
    if not candidates:
        return []
    child_counts = {genid: 0 for genid in candidates}
    for row in rows:
        parent = str(row.get("parent"))
        if parent in child_counts:
            child_counts[parent] += 1
    scores = [float(row["score"]) for row in candidates.values()]
    top = sorted(scores, reverse=True)[:3]
    midpoint = sum(top) / len(top)
    weighted = []
    for genid, row in candidates.items():
        score = float(row["score"])
        score_weight = 1 / (1 + math.exp(-10 * (score - midpoint)))
        child_penalty = math.exp(-((child_counts[genid] / 8) ** 3))
        weighted.append((genid, score_weight * child_penalty))
    return weighted


class ScoreChildProportionalSelect(SelectOperator):
    def pick(self, archive, ctx) -> SelectResult:
        weighted = selection_weights(archive.valid_parents(), archive.rows())
        if not weighted:
            raise RuntimeError("score_child_prop found no valid scored parents")
        genids = [genid for genid, _weight in weighted]
        weights = [weight for _genid, weight in weighted]
        if sum(weights) <= 0:
            weights = [1.0] * len(weights)
        return SelectResult(parents=ctx.rng.choices(genids, weights=weights, k=max(1, ctx.fan_out)))


if __name__ == "__main__":
    sdk.main(ScoreChildProportionalSelect)
