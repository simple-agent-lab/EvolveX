"""Skeleton mutate operator showing an artifact-writing shape."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class SkeletonMutate(MutateOperator):
    def mutate(self, checkout, observation, ctx):
        # Fill in checkout edits; this minimal default makes no changes.
        changed: list[str] = []
        notes: list[str] = ["fill in mutate logic before relying on this operator"]
        return MutateResult(changed=changed, notes=notes, usage={"usd": 0})


if __name__ == "__main__":
    sdk.main(SkeletonMutate, validate_config=validate_config)
