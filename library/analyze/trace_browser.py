"""Give the mutate operator metrics plus a filesystem interface to raw traces."""

from evolve.frozen import sdk
from evolve.trace_analysis import AnalyzeBase
from library.analyze._config import TRACE_CONFIG as CONFIG


class TraceBrowser(AnalyzeBase):
    operator = "trace_browser"


if __name__ == "__main__":
    sdk.main(TraceBrowser, config_schema=CONFIG)
