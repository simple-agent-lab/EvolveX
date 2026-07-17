"""Parent-eligible gate may only reject canonical eligible evaluations."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row


def _parent_eligible(child: Row) -> tuple[bool, str]:
    outcome = child.get("outcome")
    keep = outcome == "benchmark_complete" and child.get("selection_eligible") is True
    if keep:
        return True, "canonical evaluation is parent-eligible"
    return False, "canonical evaluation is not parent-eligible: %s" % outcome


class ParentEligibleGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        keep, reason = _parent_eligible(child)
        return GateResult(decision="accept" if keep else "reject", reason=reason)


if __name__ == "__main__":
    sdk.main(ParentEligibleGate)
