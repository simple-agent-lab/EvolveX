"""Skeleton trace analyzer operator for custom evidence-selection strategies."""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import AnalyzeOperator, AnalyzeResult, OperatorContext
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class CustomAnalyze(AnalyzeOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> AnalyzeResult:
        raise NotImplementedError


if __name__ == "__main__":
    sdk.main(CustomAnalyze, validate_config=validate_config)
