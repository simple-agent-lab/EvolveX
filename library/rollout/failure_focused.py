"""Failure-focused rollout reads evaluator split metadata for targeted training/evaluation.

It is the fault-directed recipe for spending rollout effort on known difficult slices.
"""

# ruff: noqa: E402

import json
import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, RolloutOperator, RolloutResult


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
    sdk.main(FailureFocusedRollout)
