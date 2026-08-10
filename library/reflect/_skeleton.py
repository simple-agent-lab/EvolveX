"""Skeleton reflect operator template for custom playbook policies."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ReflectOperator, ReflectResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class SkeletonReflect(ReflectOperator):
    def reflect(self, archive, ctx):
        # Fill in a playbook policy; this minimal default writes no insights.
        return ReflectResult(ops=[])


if __name__ == "__main__":
    sdk.main(SkeletonReflect, validate_config=validate_config)
