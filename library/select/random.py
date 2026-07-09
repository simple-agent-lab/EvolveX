"""Random parent selection samples uniformly from valid parents.

It is the exploration baseline recipe for population search.
"""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, SelectOperator, SelectResult


class RandomSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = ctx.rng.choice(parents)
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(RandomSelect)
