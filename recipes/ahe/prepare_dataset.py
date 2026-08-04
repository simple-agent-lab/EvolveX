"""Use the shared, content-pinned AHE Terminal-Bench 2.0 subset."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).parents[1] / "ahe_codex" / "prepare_dataset.py"), run_name="__main__")
