import json
import os
import subprocess
import sys
from pathlib import Path

from evolve.archive import merged_rows as mechanism_merged_rows


def run_evolve(
    *args: str,
    env: dict[str, str | None] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if value is None:
                merged_env.pop(key, None)
            else:
                merged_env[key] = value
    return subprocess.run(
        [sys.executable, "-m", "evolve", *args],
        text=True,
        capture_output=True,
        env=merged_env,
        cwd=cwd,
        check=False,
    )


def git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def init_workspace(tmp_path: Path, experiment: str = "experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def rows_by_genid(workspace: Path) -> dict[str, dict[str, object]]:
    return {str(row["genid"]): row for row in mechanism_merged_rows(workspace / "archive.jsonl")}


def git_show(workspace: Path, spec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(workspace), "show", spec],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


def append_archive_event(workspace: Path, evolve_home: Path, event: dict[str, object]) -> None:
    line = json.dumps(event, sort_keys=True) + "\n"
    with (workspace / "archive.jsonl").open("a") as archive:
        archive.write(line)
    mirror = evolve_home / "mirrors" / workspace.name / "archive.jsonl"
    with mirror.open("a") as archive:
        archive.write(line)
