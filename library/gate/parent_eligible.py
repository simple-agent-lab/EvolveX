"""Parent-eligible gate accepts children with evaluation status complete or partial."""

# ruff: noqa: E402

import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row


def _parent_eligible(child: Row) -> tuple[bool, str]:
    status = child.get("status")
    keep = status in {"complete", "partial"}
    if keep:
        return True, "status %s is parent-eligible" % status
    return False, "status %s is not parent-eligible" % status


class ParentEligibleGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        keep, reason = _parent_eligible(child)
        return GateResult(decision="accept" if keep else "reject", reason=reason)


if __name__ == "__main__":
    sdk.main(ParentEligibleGate)
