"""Failure-focused rollout reads evaluator split metadata for targeted training/evaluation.

It is the fault-directed recipe for spending rollout effort on known difficult slices.
"""

import json
from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult
from library._shared.config import config_object, positive_int, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, {"budget_tasks"})
    return {"budget_tasks": positive_int(config, "budget_tasks", 32)}


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
    sdk.main(FailureFocusedRollout, validate_config=validate_config)
