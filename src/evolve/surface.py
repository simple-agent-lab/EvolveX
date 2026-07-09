from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from .config import surface_lists

IMPLICIT_EXCLUDES = ("evaluator/**", "archive.jsonl", ".evolve/**", "evolve")


def check_paths(
    paths: list[str],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[str]:
    includes = include or ["target/**"]
    excludes = [*(exclude or []), *IMPLICIT_EXCLUDES]
    violations: list[str] = []
    for path in paths:
        if any(_matches(path, pattern) for pattern in excludes):
            violations.append(path)
            continue
        if not any(_matches(path, pattern) for pattern in includes):
            violations.append(path)
    return violations


def surface_patterns(workspace: Path) -> tuple[list[str], list[str]]:
    return surface_lists(workspace)


def _matches(path: str, pattern: str) -> bool:
    if fnmatch(path, pattern):
        return True
    if pattern.endswith("/**"):
        return path == pattern[:-3].rstrip("/")
    return False
