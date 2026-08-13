"""Failure-focused rollout reads evaluator split metadata for targeted training/evaluation.

It is the fault-directed recipe for spending rollout effort on known difficult slices.
"""

import json
from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.config import Config, integer
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult

CONFIG = Config({"budget_tasks": integer(default=32, minimum=1)})


class FailureFocusedRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        summary = {"variant": "failure_focused", "tasks_run": 0}
        splits = checkout / "evaluator" / "splits.json"
        if splits.exists():
            data = json.loads(splits.read_text())
            if "train" in data:
                summary["train_split"] = data["train"]
            if "seed" in data:
                summary["seed"] = data["seed"]
        return RolloutResult(summary=summary, artifacts=[])


if __name__ == "__main__":
    sdk.main(FailureFocusedRollout, config_schema=CONFIG)
