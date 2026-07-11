from __future__ import annotations

from importlib.resources.abc import Traversable
from pathlib import Path


def root_python_helpers(root: Path | Traversable):
    for source in sorted(root.iterdir(), key=lambda entry: entry.name):
        if source.name.startswith((".", "_")) or not source.name.endswith(".py") or not source.is_file():
            continue
        if isinstance(source, Path) and source.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {source}")
        try:
            yield source.name, source.read_text()
        except UnicodeDecodeError:
            continue
