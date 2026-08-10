"""No-op rollout emits an empty rollout summary without running tasks.

It is the baseline recipe for pipelines that skip rollout before mutate.
"""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class NoopRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        return RolloutResult(summary={"variant": "noop", "tasks_run": 0}, artifacts=[])


if __name__ == "__main__":
    sdk.main(NoopRollout, validate_config=validate_config)
