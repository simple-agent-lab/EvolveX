"""Score-weighted parent selection samples valid parents in proportion to nonnegative score.

It is a fitness-proportionate, roulette-wheel selection recipe from evolutionary algorithms.
"""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


class ScoreWeightedSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        weights = [max(float(row.get("score", 0.0)), 0.0) for row in parents]
        chosen = ctx.rng.choice(parents) if sum(weights) <= 0 else ctx.rng.choices(parents, weights=weights, k=1)[0]
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(ScoreWeightedSelect)
