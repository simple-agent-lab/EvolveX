"""Greedy parent selection chooses the highest-scoring valid parent.

It is the default exploitative baseline recipe for score-driven evolution.
"""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


class GreedySelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = max(parents, key=lambda row: float(row.get("score", float("-inf"))))
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(GreedySelect)
