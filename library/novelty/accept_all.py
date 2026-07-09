"""Baseline novelty operator: accept every mutation (no dedup).

The off-by-default choice — a mutation is never rejected for similarity. Swap
in `diff_similarity` when you want near-duplicate mutations pruned before eval.
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult, OperatorContext


class AcceptAllNovelty(NoveltyOperator):
    def assess(self, checkout: Path, ctx: OperatorContext) -> NoveltyResult:
        return NoveltyResult(novelty=1.0, accept=True)


if __name__ == "__main__":
    sdk.main(AcceptAllNovelty)
