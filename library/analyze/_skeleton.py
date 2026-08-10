"""Skeleton trace analyzer operator for custom evidence-selection strategies."""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import AnalyzeOperator, AnalyzeResult, OperatorContext


class CustomAnalyze(AnalyzeOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> AnalyzeResult:
        raise NotImplementedError


if __name__ == "__main__":
    sdk.main(CustomAnalyze)
