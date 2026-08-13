"""Shared declarative config for selection operators."""

from evolve.frozen.config import Config, integer

SELECT_CONFIG = Config({"seed": integer(default=0, description="Deterministic selection seed.")})
