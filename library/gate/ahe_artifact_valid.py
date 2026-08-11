"""Accept canonically evaluated, parent-eligible AHE children."""

from evolve.frozen import sdk
from evolve.frozen.config import Config
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row

CONFIG = Config({})


class AheArtifactValidGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        if child.get("outcome") != "benchmark_complete" or child.get("selection_eligible") is not True:
            return GateResult(decision="reject", reason="canonical evaluation is not parent-eligible")
        return GateResult(
            decision="accept",
            reason="canonical evaluation is complete and parent-eligible",
        )


if __name__ == "__main__":
    sdk.main(AheArtifactValidGate, config_schema=CONFIG)
