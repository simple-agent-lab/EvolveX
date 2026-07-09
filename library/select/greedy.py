"""Greedy parent selection chooses the highest-scoring valid parent.

It is the default exploitative baseline recipe for score-driven evolution.
"""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


def _generation_key(row: dict[str, object]) -> int:
    genid = str(row.get("genid", ""))
    head = genid.split("-", 1)[0]
    return int(head) if head.isdigit() else -1


def _per_round_sampling(workspace) -> bool:
    config = workspace / "evolve.yaml"
    lines = config.read_text().splitlines() if config.exists() else []
    in_evaluator = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("evaluator:"):
            in_evaluator = True
            continue
        if in_evaluator and line and not line.startswith(" "):
            return False
        if in_evaluator and stripped == "sampling: per_round":
            return True
    return False


class GreedySelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        mixed_hashes = _per_round_sampling(ctx.workspace) and len({row.get("task_set_hash") for row in parents}) > 1
        if mixed_hashes:
            chosen = max(parents, key=_generation_key)
        else:
            chosen = max(parents, key=lambda row: float(row.get("score", float("-inf"))))
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(GreedySelect)
