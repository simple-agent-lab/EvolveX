"""Skeleton fixed candidate-validation operator."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class SkeletonValidate(ValidateOperator):
    def validate(self, checkout, ctx) -> ValidateResult:
        return ValidateResult(accept=True, reason="replace with candidate checks", artifacts=[])


if __name__ == "__main__":
    sdk.main(SkeletonValidate, validate_config=validate_config)
