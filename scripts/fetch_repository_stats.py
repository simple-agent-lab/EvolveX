#!/usr/bin/env python3
"""Fetch authenticated GitHub repository statistics for the documentation build."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPOSITORY = "simple-agent-lab/RSIHub"
DEFAULT_OUTPUT = Path("docs/assets/repository-stats.json")


def _count(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"GitHub response has invalid {key}")
    return value


def fetch_repository_stats(repository: str, token: str | None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "RSIHub-docs-build",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub response is not an object")
    return {
        "schema_version": 1,
        "repository": repository,
        "stars": _count(payload, "stargazers_count"),
        "forks": _count(payload, "forks_count"),
        "fetched_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def write_repository_stats(output: Path, stats: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)


def has_usable_fallback(output: Path) -> bool:
    try:
        payload = json.loads(output.read_text())
        return (
            isinstance(payload, dict)
            and payload.get("schema_version") == 1
            and isinstance(payload.get("repository"), str)
            and _count(payload, "stars") >= 0
            and _count(payload, "forks") >= 0
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    output = Path(os.environ.get("RSIHUB_REPOSITORY_STATS_PATH", DEFAULT_OUTPUT))
    try:
        stats = fetch_repository_stats(repository, os.environ.get("GITHUB_TOKEN"))
        write_repository_stats(output, stats)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        if has_usable_fallback(output):
            print(f"warning: keeping existing repository statistics after refresh failed: {exc}", file=sys.stderr)
            return 0
        else:
            print(f"failed to refresh repository statistics: {exc}", file=sys.stderr)
            return 1
    print(f"wrote repository statistics to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
