"""Skeleton novelty operator template for custom candidate-dedup recipes."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult


class SkeletonNovelty(NoveltyOperator):
    def assess(self, checkout, ctx):
        # Fill in a similarity/novelty policy; this permissive default accepts
        # every candidate edit until customized.
        return NoveltyResult(novelty=1.0, accept=True)


if __name__ == "__main__":
    sdk.main(SkeletonNovelty)
