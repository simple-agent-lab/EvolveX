"""Skeleton select operator template for custom parent-selection recipes."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import SelectOperator, SelectResult


def _generation_key(row):
    genid = str(row.get("genid", ""))
    head = genid.split("-", 1)[0]
    return int(head) if head.isdigit() else -1


class SkeletonSelect(SelectOperator):
    def pick(self, archive, ctx):
        # Fill in your selection policy; this minimal default picks the newest valid parent.
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid parents")
        chosen = max(parents, key=_generation_key)
        return SelectResult(parents=[str(chosen["genid"])])


if __name__ == "__main__":
    sdk.main(SkeletonSelect)
