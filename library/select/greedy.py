"""Greedy parent selection chooses the highest-scoring valid parent.

It is the default exploitative baseline recipe for score-driven evolution.
"""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"seed"})
    seed = config.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    return {"seed": seed}


class GreedySelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = max(parents, key=lambda row: float(row.get("score", float("-inf"))))
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(GreedySelect, validate_config=validate_config)
