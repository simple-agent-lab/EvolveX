"""Hill-climb gate accepts a child when its score is at least the matched parent score.

It is the classic local-search hill-climbing recipe for monotonic score improvement.
"""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row


def _hillclimb_gate(child: Row, parent: Row | None) -> tuple[bool, str]:
    task_hash = child.get("task_set_hash")
    score = float(child.get("score") or 0.0)
    if parent is None or parent.get("score") is None:
        return False, "parent has no score for same task hash %s" % task_hash
    parent_score = float(parent["score"])
    suffix = " on same task hash %s" % task_hash if parent.get("_matched_from_evals") else ""
    keep = score >= parent_score
    if keep:
        return True, "score %s >= parent %s%s" % (score, parent_score, suffix)
    return False, "score %s < parent %s%s" % (score, parent_score, suffix)


class HillclimbGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        keep, reason = _hillclimb_gate(child, parent)
        return GateResult(decision="accept" if keep else "reject", reason=reason)


if __name__ == "__main__":
    sdk.main(HillclimbGate)
