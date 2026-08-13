"""Shared declarative config for trace-analysis operators."""

from evolve.frozen.config import Config, integer

TRACE_CONFIG = Config(
    {
        "history_cycles": integer(default=2, minimum=1),
        "max_observations": integer(default=30, minimum=1),
        "max_chars": integer(default=30_000, minimum=1),
    }
)
