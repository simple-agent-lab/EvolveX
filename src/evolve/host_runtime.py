from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

_PYTHON_ENVIRONMENT_OVERRIDES = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")


def clean_python_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy an environment without interpreter path or activation overrides."""
    env = dict(os.environ if source is None else source)
    for name in _PYTHON_ENVIRONMENT_OVERRIDES:
        env.pop(name, None)
    return env


def uv_executable(env: Mapping[str, str] | None = None) -> str:
    """Resolve uv from the explicit EvolveX override or the supplied PATH."""
    values = os.environ if env is None else env
    configured = values.get("EVOLVE_UV_BINARY")
    candidate = configured or shutil.which("uv", path=values.get("PATH"))
    if not candidate or not Path(candidate).expanduser().is_file():
        raise RuntimeError("uv is required; install uv or set EVOLVE_UV_BINARY")
    return str(Path(candidate).expanduser().resolve())


def uv_run(
    workspace: Path,
    *command: str,
    env: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Build a locked uv invocation for a generated workspace."""
    clean = clean_python_env(env)
    root = workspace.resolve()
    for name in ("pyproject.toml", "uv.lock"):
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"workspace uv project is missing {path}")
    return [
        uv_executable(clean),
        "run",
        "--project",
        str(root),
        "--frozen",
        "--python",
        sys.executable,
        *command,
    ], clean
