"""Skeleton rollout operator template for custom task-rollout recipes."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import RolloutOperator, RolloutResult


class SkeletonRollout(RolloutOperator):
    def rollout(self, checkout, ctx):
        # Fill in task execution; this minimal default reports that no tasks ran.
        return RolloutResult(summary={"variant": "skeleton", "tasks_run": 0}, artifacts=[])


if __name__ == "__main__":
    sdk.main(SkeletonRollout)
