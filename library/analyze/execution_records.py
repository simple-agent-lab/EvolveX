"""Expose complete per-case execution and verifier records."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase


class ExecutionRecords(AnalyzeBase):
    variant = "execution_records"


if __name__ == "__main__":
    sdk.main(ExecutionRecords)
