"""Expose detailed failed execution records to the meta-agent."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase


class FailedTraces(AnalyzeBase):
    variant = "failed_traces"


if __name__ == "__main__":
    sdk.main(FailedTraces)
