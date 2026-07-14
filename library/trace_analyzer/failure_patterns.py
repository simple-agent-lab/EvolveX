"""Summarize verifier-grounded failure clusters and passing behavior."""

from evolve.frozen import sdk
from evolve.trace_analysis import TraceAnalyzerBase


class FailurePatterns(TraceAnalyzerBase):
    variant = "failure_patterns"


if __name__ == "__main__":
    sdk.main(FailurePatterns)
