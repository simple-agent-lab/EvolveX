"""Give the meta-agent metrics plus a filesystem interface to raw traces."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase


class TraceBrowser(AnalyzeBase):
    variant = "trace_browser"


if __name__ == "__main__":
    sdk.main(TraceBrowser)
