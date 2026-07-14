"""Give the mutator metrics plus a filesystem interface to raw traces."""

from evolve.frozen import sdk
from evolve.trace_analysis import TraceAnalyzerBase


class TraceBrowser(TraceAnalyzerBase):
    variant = "trace_browser"


if __name__ == "__main__":
    sdk.main(TraceBrowser)
