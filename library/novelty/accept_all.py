"""Baseline novelty operator: accept every candidate edit (no dedup).

The off-by-default choice — a candidate edit is never rejected for similarity.
Swap in `diff_similarity` when you want near-duplicate edits pruned before eval.
"""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext

CONFIG = Config({})


class AcceptAllNovelty(NoveltyOperator):
    def assess(self, checkout: Path, ctx: OperatorContext) -> NoveltyResult:
        return NoveltyResult(novelty=1.0, accept=True)


if __name__ == "__main__":
    sdk.main(AcceptAllNovelty, config_schema=CONFIG)
