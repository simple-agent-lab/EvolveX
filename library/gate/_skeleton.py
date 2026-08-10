"""Skeleton gate operator template for custom child-acceptance recipes."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import GateOperator, GateResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class SkeletonGate(GateOperator):
    def decide(self, child, parent, ctx):
        # Fill in acceptance policy; this minimal default rejects until customized.
        return GateResult(decision="reject", reason="fill in gate decision policy")


if __name__ == "__main__":
    sdk.main(SkeletonGate, validate_config=validate_config)
