"""Accept canonically evaluated, parent-eligible AHE children."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult, OperatorContext, Row
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class AheArtifactValidGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        if child.get("outcome") != "benchmark_complete" or child.get("selection_eligible") is not True:
            return GateResult(decision="reject", reason="canonical evaluation is not parent-eligible")
        return GateResult(
            decision="accept",
            reason="canonical evaluation is complete and parent-eligible",
        )


if __name__ == "__main__":
    sdk.main(AheArtifactValidGate, validate_config=validate_config)
