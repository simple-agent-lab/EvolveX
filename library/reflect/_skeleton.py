"""Skeleton reflect operator template for custom playbook policies."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ReflectOperator, ReflectResult


class SkeletonReflect(ReflectOperator):
    def reflect(self, archive, ctx):
        # Fill in a playbook policy; this minimal default writes no insights.
        return ReflectResult(ops=[])


if __name__ == "__main__":
    sdk.main(SkeletonReflect)
