"""Hill-climb gate compares a child score with the matched parent score.

By default it allows non-decreasing scores. Set ``strict: true`` to require an
actual improvement.
"""

from evolve.frozen import sdk
from evolve.frozen.config import Config, boolean
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row

CONFIG = Config({"strict": boolean(default=False, description="Require a strict score improvement.")})


def _hillclimb_gate(child: Row, parent: Row | None, *, strict: bool = False) -> tuple[bool, str]:
    task_hash = child.get("task_set_hash")
    score = float(child.get("score") or 0.0)
    if parent is None or parent.get("score") is None:
        return False, "parent has no score for same task hash %s" % task_hash
    parent_score = float(parent["score"])
    suffix = " on same task hash %s" % task_hash if parent.get("_matched_from_evals") else ""
    keep = score > parent_score if strict else score >= parent_score
    comparator = ">" if strict else ">="
    if keep:
        return True, "score %s %s parent %s%s" % (score, comparator, parent_score, suffix)
    rejected_comparator = "<=" if strict else "<"
    return False, "score %s %s parent %s%s" % (score, rejected_comparator, parent_score, suffix)


class HillclimbGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        strict = ctx.config.get("strict", False)
        if not isinstance(strict, bool):
            raise ValueError("hillclimb strict must be a boolean")
        keep, reason = _hillclimb_gate(child, parent, strict=strict)
        return GateResult(decision="accept" if keep else "reject", reason=reason)


if __name__ == "__main__":
    sdk.main(HillclimbGate, config_schema=CONFIG)
