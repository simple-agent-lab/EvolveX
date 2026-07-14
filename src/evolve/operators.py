from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OperatorResult:
    name: str
    returncode: int
    stdout: str
    stderr: str
    wall_s: float


_OPERATOR_WRAPPER = """
from pathlib import Path
import sys

script = Path(sys.argv[1])
sys.argv = sys.argv[1:]
namespace = {"__name__": "__main__", "__file__": str(script), "__package__": None, "__cached__": None}
exec(compile(script.read_bytes(), str(script), "exec"), namespace)
"""


def _text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def run_operator(
    *,
    name: str,
    checkout: Path,
    workspace: Path,
    genid: str,
    parent: str | None,
    run_dir: Path,
    config_block: dict[str, Any],
    timeout_s: float,
    round_number: int | None = None,
    operator_checkout: Path | None = None,
) -> OperatorResult:
    start = time.monotonic()
    source_checkout = operator_checkout or checkout
    script = source_checkout / "operators" / f"{name}.py"
    if not script.exists():
        return OperatorResult(
            name=name,
            returncode=127,
            stdout="",
            stderr=f"missing operator script: {script}",
            wall_s=time.monotonic() - start,
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    base_env = (
        {**os.environ, "EVOLVE_HOME": str((run_dir / "operator-home").resolve())}
        if checkout.resolve() != workspace.resolve()
        else os.environ
    )
    env: dict[str, str] = {
        **base_env,
        "EVOLVE_GENID": genid,
        "EVOLVE_PARENT": parent or "",
        "EVOLVE_OPERATOR_TIMEOUT_S": str(timeout_s),
        "EVOLVE_RUN_DIR": str(run_dir.resolve()),
        "EVOLVE_WORKSPACE": str(workspace.resolve()),
        "EVOLVE_CHECKOUT": str(checkout.resolve()),
    }
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _OPERATOR_WRAPPER,
                str(script.resolve()),
                "--config",
                json.dumps(config_block),
            ],
            cwd=checkout,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        return OperatorResult(
            name=name,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            wall_s=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = _text(exc.stderr)
        if stderr:
            stderr = f"{stderr.rstrip()}\n"
        stderr += f"timeout after {timeout_s}s"
        return OperatorResult(
            name=name,
            returncode=-1,
            stdout=_text(exc.stdout),
            stderr=stderr,
            wall_s=time.monotonic() - start,
        )


def operator_timeout(operators_config: dict[str, Any], name: str) -> float:
    block = operators_config.get(name)
    if isinstance(block, dict):
        timeout_s = block.get("timeout_s")
        if isinstance(timeout_s, (int, float)) and not isinstance(timeout_s, bool):
            return float(timeout_s)
    default_timeout_s = operators_config.get("timeout_s")
    if isinstance(default_timeout_s, (int, float)) and not isinstance(default_timeout_s, bool):
        return float(default_timeout_s)
    return 600.0
