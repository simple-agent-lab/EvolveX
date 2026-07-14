"""Skeleton trace analyzer operator for custom evidence-selection strategies."""

from pathlib import Path

from evolve.frozen import sdk
from evolve.frozen.interfaces import OperatorContext, TraceAnalyzerOperator, TraceAnalyzerResult


class CustomTraceAnalyzer(TraceAnalyzerOperator):
    def analyze(self, checkout: Path, ctx: OperatorContext) -> TraceAnalyzerResult:
        raise NotImplementedError


if __name__ == "__main__":
    sdk.main(CustomTraceAnalyzer)
