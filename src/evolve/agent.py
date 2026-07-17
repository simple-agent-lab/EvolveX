from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, SupportsFloat, SupportsIndex, cast


@dataclass(frozen=True)
class AgentRunResult:
    stdout: str
    stderr: str
    output: str
    returncode: int
    wall_s: float
    usage: dict[str, Any]


class AgentCommandError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        output: str = "",
        usage: dict[str, Any] | None = None,
        returncode: int = 1,
    ) -> None:
        super().__init__(message)
        self.output = output
        self.usage = usage or {"usd": 0}
        self.returncode = returncode if isinstance(returncode, int) and returncode else 1


def run_meta_agent(
    workspace: Path | str,
    prompt: str,
    config: dict[str, Any] | None = None,
    *,
    env_overrides: dict[str, str | None] | None = None,
) -> AgentRunResult:
    root = Path(workspace).resolve()
    config = config or {}
    command = _resolve_command(config)
    timeout = _configured_timeout(config)
    start = time.monotonic()

    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(prompt)
        handle.flush()
        os.fsync(handle.fileno())
        prompt_file = handle.name

    env: dict[str, str] = dict(os.environ)
    env["EVOLVE_PROMPT_FILE"] = prompt_file
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    stdout = ""
    stderr = ""
    try:
        if timeout is not None and timeout <= 0.01:
            raise AgentCommandError(f"meta-agent timeout after {timeout}s", usage=_usage(start))

        proc: subprocess.Popen[str] = subprocess.Popen(
            ["sh", "-c", command],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc, signal.SIGKILL)
                stdout, stderr = proc.communicate()
            raise AgentCommandError(
                f"meta-agent timeout after {timeout}s",
                output=_combined_output(stdout or "", stderr or ""),
                usage=_usage(start),
                returncode=1,
            )
    finally:
        Path(prompt_file).unlink(missing_ok=True)

    stdout = stdout or ""
    stderr = stderr or ""
    output = _combined_output(stdout, stderr)
    usage = _usage(start)
    if proc.returncode != 0:
        raise AgentCommandError(
            stderr.strip() or stdout.strip() or "meta-agent command failed",
            output=output,
            usage=usage,
            returncode=proc.returncode,
        )
    return AgentRunResult(
        stdout=stdout, stderr=stderr, output=output, returncode=0, wall_s=usage["wall_s"], usage=usage
    )


def _resolve_command(config: dict[str, Any]) -> str:
    command = config.get("command")
    if command:
        return str(command)

    operators = config.get("operators")
    if isinstance(operators, dict):
        meta_agent = operators.get("meta_agent")
        if isinstance(meta_agent, dict) and meta_agent.get("command"):
            return str(meta_agent["command"])

    env_command = os.environ.get("EVOLVE_AGENT_COMMAND")
    if env_command:
        return env_command

    raise AgentCommandError(
        "missing meta-agent command; set EVOLVE_AGENT_COMMAND or operators.meta_agent.command",
        returncode=2,
    )


def _configured_timeout(config: dict[str, Any]) -> float | None:
    timeout = _timeout_float(config.get("timeout_s"))
    inherited = _timeout_float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S"))
    if inherited is None:
        return timeout
    cap = _timeout_headroom(inherited)
    if cap is None:
        return timeout
    return cap if timeout is None else min(timeout, cap)


def _timeout_float(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(cast(str | SupportsFloat | SupportsIndex, value))
    except (TypeError, ValueError):
        return None


def _timeout_headroom(timeout: float) -> float:
    if timeout <= 0:
        return timeout
    if timeout < 1:
        return max(0.001, timeout * 0.05)
    return max(0.01, timeout - min(5.0, max(0.5, timeout * 0.05)))


def _kill_process_group(proc: subprocess.Popen[str], sig: int = signal.SIGTERM) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def _combined_output(stdout: str, stderr: str) -> str:
    if not stderr:
        return stdout
    if not stdout:
        return stderr
    return stdout + ("" if stdout.endswith("\n") else "\n") + stderr


def _usage(start: float) -> dict[str, Any]:
    return {"wall_s": round(time.monotonic() - start, 6), "usd": 0}
