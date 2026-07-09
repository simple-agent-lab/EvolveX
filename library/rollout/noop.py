"""No-op rollout emits an empty rollout summary without running tasks.

It is the baseline recipe for pipelines that skip rollout before meta_agent.
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult


class NoopRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        return RolloutResult(summary={"variant": "noop", "tasks_run": 0}, artifacts=[])


if __name__ == "__main__":
    sdk.main(NoopRollout)
