"""Baseline novelty operator: accept every candidate edit (no dedup).

The off-by-default choice — a candidate edit is never rejected for similarity.
Swap in `diff_similarity` when you want near-duplicate edits pruned before eval.
"""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class AcceptAllNovelty(NoveltyOperator):
    def assess(self, checkout: Path, ctx: OperatorContext) -> NoveltyResult:
        return NoveltyResult(novelty=1.0, accept=True)


if __name__ == "__main__":
    sdk.main(AcceptAllNovelty, validate_config=validate_config)
