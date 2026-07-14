"""Expose detailed failed execution records to the meta-agent."""

from evolve.frozen import sdk
from evolve.trace_analysis import TraceAnalyzerBase


class FailedTraces(TraceAnalyzerBase):
    variant = "failed_traces"


if __name__ == "__main__":
    sdk.main(FailedTraces)
