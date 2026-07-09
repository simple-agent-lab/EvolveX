"""Skeleton gate operator template for custom child-acceptance recipes."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult


class SkeletonGate(GateOperator):
    def decide(self, child, parent, ctx):
        # Fill in acceptance policy; this minimal default rejects until customized.
        return GateResult(decision="reject", reason="fill in gate decision policy")


if __name__ == "__main__":
    sdk.main(SkeletonGate)
