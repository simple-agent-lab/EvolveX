"""Skeleton novelty operator template for custom candidate-dedup recipes."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import NoveltyOperator, NoveltyResult


class SkeletonNovelty(NoveltyOperator):
    def assess(self, checkout, ctx):
        # Fill in a similarity/novelty policy; this permissive default accepts
        # every candidate edit until customized.
        return NoveltyResult(novelty=1.0, accept=True)


if __name__ == "__main__":
    sdk.main(SkeletonNovelty)
