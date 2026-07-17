"""Run an isolated Harbor editing agent and return its target artifact."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from evolve.patching import load_surface_policy, patch_parent_ref
from library.meta_agent.runners.editable_bundle import (
    EditableBundle,
    cleanup_editable_bundle,
    install_returned_bundle,
    prepare_editable_bundle,
)

_ARTIFACT_SOURCE = "/app/candidate"
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password))\b"
    r"([\"']?)(\s*[:=]\s*)([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_PROXY_ENV = (
    ("EVOLVE_HARBOR_HTTP_PROXY", "http_proxy", "HTTP_PROXY"),
    ("EVOLVE_HARBOR_HTTPS_PROXY", "https_proxy", "HTTPS_PROXY"),
    ("EVOLVE_HARBOR_NO_PROXY", "no_proxy", "NO_PROXY"),
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]", text)


def _nonnegative_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _append_agent_env(command: list[str], config: dict[str, Any]) -> None:
    values: dict[str, str] = {}
    for override, lower, upper in _PROXY_ENV:
        value = os.environ.get(override) or os.environ.get(lower) or os.environ.get(upper)
        if value:
            values[lower] = value
            values[upper] = value
    configured = config.get("agent_env")
    if isinstance(configured, dict):
        values.update({str(key): str(value) for key, value in configured.items()})
    force_auth = os.environ.get("CODEX_FORCE_AUTH_JSON")
    if force_auth and "CODEX_FORCE_AUTH_JSON" not in values:
        values["CODEX_FORCE_AUTH_JSON"] = force_auth
    for key, value in values.items():
        command.extend(["--ae", f"{key}={value}"])


def _build_command(
    harbor: str,
    bundle: EditableBundle,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
) -> list[str]:
    agent = str(config.get("agent") or "codex")
    command = [
        harbor,
        "exec",
        "--path",
        str(bundle.task_root.resolve()),
        "--no-scan",
        "--instruction-path",
        str(prompt_path.resolve()),
        "--workdir",
        "/app",
        "--artifact",
        _ARTIFACT_SOURCE,
        "--tasks-dir",
        str(tasks_dir.resolve()),
        "--agent",
        agent,
        "--jobs-dir",
        str(jobs_root.resolve()),
        "--job-name",
        job_name,
        "--n-concurrent",
        "1",
        "--n-attempts",
        "1",
        "--max-retries",
        str(_nonnegative_int(config.get("max_retries"), 0)),
    ]
    environment = config.get("environment")
    if environment:
        command.extend(["--env", str(environment)])
    image = config.get("image")
    if image:
        command.extend(["--image", str(image)])
    model = config.get("model")
    if model:
        command.extend(["--model", str(model)])
    kwargs = config.get("agent_kwargs")
    if isinstance(kwargs, dict):
        for key, value in kwargs.items():
            command.extend(["--ak", f"{key}={value}"])
    _append_agent_env(command, config)
    if os.environ.get("EVOLVE_LIVE_OUTPUT") != "1":
        command.append("--quiet")
    return command


def _run_timeout() -> float | None:
    try:
        outer = float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S", ""))
    except ValueError:
        return None
    return max(0.1, outer - min(5.0, max(0.5, outer * 0.05)))


def _harbor_env(config: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    pythonpath = config.get("agent_pythonpath")
    roots = [pythonpath] if isinstance(pythonpath, str) else pythonpath
    if isinstance(roots, list) and roots:
        prefix = os.pathsep.join(str(Path(str(root)).expanduser().resolve()) for root in roots)
        env["PYTHONPATH"] = prefix + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _run_harbor(command: list[str], checkout: Path, log_path: Path, config: dict[str, Any]) -> tuple[int, float]:
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=checkout,
        env=_harbor_env(config),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=1,
    )
    chunks: list[str] = []

    def consume_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            chunks.append(line)
            if os.environ.get("EVOLVE_LIVE_OUTPUT") == "1":
                print(_redact(line), end="", flush=True)

    reader = threading.Thread(target=consume_output, daemon=True)
    reader.start()
    try:
        process.wait(timeout=_run_timeout())
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            process.wait()
        chunks.append("\nharbor meta-agent timed out\n")
    reader.join()
    wall_s = round(time.monotonic() - start, 6)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(_redact(f"wall_s={wall_s}\n{''.join(chunks)}"))
    return (process.returncode if process.returncode is not None else 1), wall_s


def _trial_result(job_dir: Path) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(job_dir.glob("*/result.json")):
        payload = _read_json(path)
        if isinstance(payload, dict) and payload.get("trial_name"):
            matches.append((path.parent, payload))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one Harbor meta-agent trial, found {len(matches)} in {job_dir}")
    return matches[0]


def _artifact_candidate(trial_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    manifest_path = trial_dir / "artifacts" / "manifest.json"
    payload = _read_json(manifest_path)
    if not isinstance(payload, list):
        raise RuntimeError(f"missing Harbor artifact manifest: {manifest_path}")
    entries = [entry for entry in payload if isinstance(entry, dict)]
    entry = next((item for item in entries if item.get("source") == _ARTIFACT_SOURCE), None)
    if entry is None or entry.get("status") != "ok":
        raise RuntimeError("Harbor did not collect a successful /app/candidate artifact")
    destination = entry.get("destination")
    if not isinstance(destination, str) or not destination:
        raise RuntimeError("Harbor candidate artifact has no destination")
    artifact = (trial_dir / destination).resolve()
    trial_root = trial_dir.resolve()
    if trial_root not in artifact.parents or not artifact.is_dir():
        raise RuntimeError("Harbor candidate artifact escaped the trial or is not a directory")
    return artifact, entries


def _agent_output(trial_dir: Path) -> str:
    payload = _read_json(trial_dir / "agent" / "trajectory.json")
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list):
        return ""
    messages = [
        str(step.get("message"))
        for step in steps
        if isinstance(step, dict) and step.get("source") == "agent" and step.get("message")
    ]
    return messages[-1] if messages else ""


def _usage(payload: dict[str, Any], wall_s: float) -> dict[str, Any]:
    result = payload.get("agent_result")
    result = result if isinstance(result, dict) else {}
    return {
        "usd": result.get("cost_usd") if isinstance(result.get("cost_usd"), (int, float)) else 0,
        "wall_s": wall_s,
        "input_tokens": result.get("n_input_tokens"),
        "cache_tokens": result.get("n_cache_tokens"),
        "output_tokens": result.get("n_output_tokens"),
    }


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    """Run an isolated Harbor editing agent and install its candidate bundle."""
    parent_ref = patch_parent_ref(checkout, ctx)
    surface = load_surface_policy(checkout)
    harbor_root = ctx.run_dir / "meta_agent" / "harbor"
    prompt_path = harbor_root / "prompt.md"
    jobs_root = Path(str(ctx.config.get("jobs_dir") or harbor_root / "jobs")).expanduser()
    tasks_dir = harbor_root / "tasks"
    job_name = "meta-agent-gen-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", ctx.genid)
    usage: dict[str, Any] = {"usd": 0, "wall_s": 0}
    output = ""
    returncode = 1
    bundle: EditableBundle | None = None
    try:
        bundle = prepare_editable_bundle(checkout, ctx.config.get("editable_roots", ["target"]), surface)
        if (jobs_root / job_name).exists():
            raise RuntimeError(f"Harbor meta-agent job already exists: {jobs_root / job_name}")
        harbor = shutil.which("harbor")
        if harbor is None:
            raise RuntimeError("Harbor meta-agent runner requires the harbor CLI on PATH")
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            prompt.rstrip() + "\n\n# Harbor Runner Contract\n\n"
            "The editable candidate is at `/app/candidate`. Edit only paths allowed by the supplied "
            "surface rules. The complete `/app/candidate` directory is returned as the candidate artifact.\n"
        )
        command = _build_command(harbor, bundle, prompt_path, jobs_root, tasks_dir, job_name, ctx.config)
        _write_json(harbor_root / "command.json", [_redact(arg) for arg in command])
        returncode, wall_s = _run_harbor(command, checkout, harbor_root / "harbor.log", ctx.config)
        usage["wall_s"] = wall_s
        trial_dir, trial = _trial_result(jobs_root / job_name)
        usage = _usage(trial, wall_s)
        _write_json(
            harbor_root / "trial.json",
            {
                "trial_name": trial.get("trial_name"),
                "agent_info": trial.get("agent_info"),
                "agent_result": trial.get("agent_result"),
                "exception_info": trial.get("exception_info"),
                "verifier_result": trial.get("verifier_result"),
                "result_path": str(trial_dir / "result.json"),
            },
        )
        if returncode != 0:
            raise RuntimeError(f"harbor exec exited {returncode}; see {harbor_root / 'harbor.log'}")
        if trial.get("exception_info") not in (None, {}):
            raise RuntimeError(f"Harbor meta-agent trial failed: {_redact(str(trial.get('exception_info')))}")
        artifact, manifest = _artifact_candidate(trial_dir)
        _write_json(harbor_root / "artifact-manifest.json", manifest)
        output = _agent_output(trial_dir)
        install_returned_bundle(checkout, artifact, bundle, parent_ref, surface)
        return AgentRunResult(
            stdout=output,
            stderr="",
            output=output,
            returncode=0,
            wall_s=float(usage.get("wall_s") or 0),
            usage=usage,
        )
    except Exception as exc:
        raise AgentCommandError(
            f"{exc.__class__.__name__}: {_redact(str(exc))}",
            output=output,
            usage=usage,
            returncode=returncode,
        ) from exc
    finally:
        if bundle is not None:
            cleanup_editable_bundle(bundle)
