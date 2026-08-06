"""Compatibility entry point for the shared Terminal-Bench 2.0 preparer."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).parents[2] / "datasets" / "terminal_bench_2" / "prepare_dataset.py"), run_name="__main__")
