"""Skeleton fixed candidate-validation operator."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class SkeletonValidate(ValidateOperator):
    def validate(self, checkout, ctx) -> ValidateResult:
        return ValidateResult(accept=True, reason="replace with candidate checks", artifacts=[])


if __name__ == "__main__":
    sdk.main(SkeletonValidate)
