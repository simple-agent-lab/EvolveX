from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def _projects(jobs_dir: Path) -> list[str]:
    projects: set[str] = set()
    for config_path in jobs_dir.rglob("config.json"):
        try:
            config = json.loads(config_path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(config, dict):
            continue
        trial_name = config.get("trial_name")
        if isinstance(trial_name, str) and trial_name:
            projects.add(re.sub(r"[^a-z0-9_-]", "-", f"{trial_name}__env".lower()))
    return sorted(projects)


def cleanup(jobs_dir: Path) -> int:
    returncode = 0
    for project in _projects(jobs_dir):
        query = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if query.returncode != 0:
            returncode = query.returncode
            continue
        container_ids = [line.strip() for line in query.stdout.splitlines() if line.strip()]
        if container_ids:
            removed = subprocess.run(["docker", "rm", "-f", *container_ids], check=False)
            returncode = removed.returncode or returncode
    return returncode


if __name__ == "__main__":
    raise SystemExit(cleanup(Path(sys.argv[1])))
