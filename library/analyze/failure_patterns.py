"""Summarize verifier-grounded failure clusters and passing behavior."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase
from library.analyze._config import TRACE_CONFIG as CONFIG


class FailurePatterns(AnalyzeBase):
    operator = "failure_patterns"


if __name__ == "__main__":
    sdk.main(FailurePatterns, config_schema=CONFIG)
