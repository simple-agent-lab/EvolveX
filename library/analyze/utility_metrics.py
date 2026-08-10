"""Expose per-task downstream utility without emphasizing trajectories."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase


class UtilityMetrics(AnalyzeBase):
    variant = "utility_metrics"


if __name__ == "__main__":
    sdk.main(UtilityMetrics)
