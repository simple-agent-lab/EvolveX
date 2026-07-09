"""Skeleton mutate variant showing artifact-writing operator shape."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult


class SkeletonMutate(MutateOperator):
    def mutate(self, checkout, observation, ctx):
        # Fill in checkout edits; this minimal default makes no changes.
        changed: list[str] = []
        notes: list[str] = ["fill in mutation logic before relying on this variant"]
        return MutateResult(changed=changed, notes=notes, usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(SkeletonMutate)
