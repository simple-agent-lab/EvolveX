"""Run an isolated Harbor editing agent and return its target artifact."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from evolve.git import git, working_tree_changed_paths
from evolve.host_runtime import uv_run
from evolve.patching import SurfacePolicy, load_surface_policy, patch_parent_ref
from evolve.surface import check_paths

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


class _EditableBundle:
    __slots__ = ("staging", "task_root", "roots")

    def __init__(self, staging: Path, task_root: Path, roots: tuple[str, ...]) -> None:
        self.staging = staging
        self.task_root = task_root
        self.roots = roots


def _validate_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"editable root must be a real directory: {root}")
    for path in [root, *root.rglob("*")]:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"Harbor meta-agent does not accept symlinks: {path}")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise RuntimeError(f"Harbor meta-agent does not accept special files: {path}")


def _editable_roots(value: object, surface: SurfacePolicy) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("editable_roots must contain at least one root")
    roots: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or not raw or Path(raw).name != raw or raw in (".", ".."):
            raise ValueError(f"editable root must be one top-level relative directory: {raw!r}")
        if raw in roots:
            raise ValueError(f"duplicate editable root: {raw}")
        includes = surface.include or ["target/**"]
        root_is_mutable = not check_paths([raw], surface.include, surface.exclude)
        contains_mutable_path = any(pattern.startswith(raw + "/") for pattern in includes)
        if not root_is_mutable and not contains_mutable_path:
            raise ValueError(f"editable root contains no mutable surface paths: {raw}")
        roots.append(raw)
    return tuple(roots)


def _prepare_bundle(checkout: Path, value: object, surface: SurfacePolicy) -> _EditableBundle:
    roots = _editable_roots(value, surface)
    staging = Path(tempfile.mkdtemp(prefix=".evolve-harbor-", dir=checkout))
    task_root = staging / "task"
    candidate = task_root / "candidate"
    try:
        candidate.mkdir(parents=True)
        for root in roots:
            source = checkout / root
            _validate_tree(source)
            shutil.copytree(source, candidate / root)
        return _EditableBundle(staging, task_root, roots)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _install_bundle(
    checkout: Path,
    returned: Path,
    bundle: _EditableBundle,
    parent_ref: str,
    surface: SurfacePolicy,
) -> list[str]:
    if not returned.is_dir() or returned.is_symlink():
        raise RuntimeError("returned candidate must be a real directory")
    actual = {path.name for path in returned.iterdir()}
    expected = set(bundle.roots)
    if actual != expected:
        raise RuntimeError(
            "returned candidate roots differ: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )

    transaction = bundle.staging / "install"
    replacements = transaction / "replacements"
    backups = transaction / "backups"
    replacements.mkdir(parents=True)
    backups.mkdir()
    moved: list[str] = []
    installed: list[str] = []
    try:
        for root in bundle.roots:
            _validate_tree(returned / root)
            shutil.copytree(returned / root, replacements / root)
        for root in bundle.roots:
            (checkout / root).rename(backups / root)
            moved.append(root)
            (replacements / root).rename(checkout / root)
            installed.append(root)

        changed = [
            path
            for path in working_tree_changed_paths(checkout, parent_ref)
            if any(path == root or path.startswith(root + "/") for root in bundle.roots)
        ]
        violations = check_paths(changed, surface.include, surface.exclude)
        if violations:
            raise RuntimeError("returned candidate mutated paths outside surface: " + ", ".join(violations))
        diff = git(checkout, "diff", "--check", parent_ref, "--", *bundle.roots, check=False)
        if diff.returncode:
            raise RuntimeError(f"returned candidate failed git diff --check: {(diff.stderr or diff.stdout).strip()}")
        shutil.rmtree(transaction)
        return changed
    except Exception:
        for root in reversed(installed):
            _remove(checkout / root)
        for root in reversed(moved):
            _remove(checkout / root)
            (backups / root).rename(checkout / root)
        shutil.rmtree(transaction, ignore_errors=True)
        raise


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
    for key, value in _agent_env(config).items():
        command.extend(["--ae", f"{key}={value}"])


def _agent_env(config: dict[str, Any]) -> dict[str, str]:
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
    return values


def _uv_cache_dir(workspace: Path) -> Path:
    configured = os.environ.get("EVOLVE_UV_CACHE_DIR")
    cache = Path(configured).expanduser() if configured else workspace / "runs" / "runtime" / "uv-cache"
    if not cache.is_absolute():
        cache = workspace / cache
    cache = cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _miniswe_config_command(
    harbor: list[str],
    source: Path,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
    *,
    candidate_source: Path,
    artifact: str | None,
    uv_cache_dir: Path,
) -> list[str]:
    agent_env = _agent_env(config)
    agent_env.setdefault("EVOLVE_CANDIDATE_SOURCE", str(candidate_source.resolve()))
    agent: dict[str, Any] = {
        "name": str(config.get("agent")),
        "env": agent_env,
    }
    model = config.get("model")
    if model:
        agent["model_name"] = str(model)
    kwargs = config.get("agent_kwargs")
    if isinstance(kwargs, dict) and kwargs:
        agent["kwargs"] = {str(key): value for key, value in kwargs.items()}

    compile_environment: dict[str, Any] = {"paths": [str(source.resolve())]}
    image = config.get("image")
    if image:
        compile_environment["image"] = str(image)
    workdir = str(config.get("workdir") or "/app")
    if workdir != "/app":
        compile_environment["workdir"] = workdir
    compile_config: dict[str, Any] = {
        "task_name_prefix": job_name,
        "output_dir": str(tasks_dir.resolve()),
        "instructions": [{"text": prompt_path.read_text()}],
        "artifacts": [artifact] if artifact else [],
        "environments": [compile_environment],
        "verifiers": ([{"auto_verifier": {"required_artifacts": [artifact]}}] if artifact else []),
    }
    environment: dict[str, Any] = {
        "type": str(config.get("environment") or "docker"),
        "mounts": [
            {
                "type": "bind",
                "source": str(uv_cache_dir.resolve()),
                "target": "/installed-agent/uv-cache",
            }
        ],
    }
    job_config: dict[str, Any] = {
        "job_name": job_name,
        "jobs_dir": str(jobs_root.resolve()),
        "n_concurrent_trials": 1,
        "quiet": os.environ.get("EVOLVE_LIVE_OUTPUT") != "1",
        "retry": {"max_retries": _nonnegative_int(config.get("max_retries"), 0)},
        "environment": environment,
        "agents": [agent],
    }
    exec_config = {"map": {"compile": compile_config, "job": job_config}}
    config_path = prompt_path.parent / "exec-config.json"
    _write_json(config_path, exec_config)
    return [*harbor, "exec", "--config", str(config_path.resolve())]


def _base_command(
    harbor: list[str],
    task_root: Path,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
) -> list[str]:
    agent = str(config.get("agent") or "codex")
    command = [
        *harbor,
        "exec",
        "--path",
        str(task_root.resolve()),
        "--no-scan",
        "--instruction-path",
        str(prompt_path.resolve()),
        "--workdir",
        "/app",
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


def _build_command(
    harbor: list[str],
    bundle: _EditableBundle,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
    uv_cache_dir: Path | None = None,
) -> list[str]:
    agent = str(config.get("agent") or "codex")
    if agent.endswith(":MiniSweSourceAgent"):
        if "target" not in bundle.roots:
            raise ValueError("MiniSweSourceAgent requires target in editable_roots")
        return _miniswe_config_command(
            harbor,
            bundle.task_root / "candidate",
            prompt_path,
            jobs_root,
            tasks_dir,
            job_name,
            config,
            candidate_source=bundle.task_root / "candidate" / "target",
            artifact=_ARTIFACT_SOURCE,
            uv_cache_dir=uv_cache_dir or _uv_cache_dir(bundle.task_root),
        )
    command = _base_command(
        harbor,
        bundle.task_root / "candidate",
        prompt_path,
        jobs_root,
        tasks_dir,
        job_name,
        config,
    )
    tasks_index = command.index("--tasks-dir")
    command[tasks_index:tasks_index] = ["--artifact", _ARTIFACT_SOURCE]
    return command


def _run_timeout() -> float | None:
    try:
        outer = float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S", ""))
    except ValueError:
        return None
    return max(0.1, outer - min(5.0, max(0.5, outer * 0.05)))


def _run_harbor(
    command: list[str],
    checkout: Path,
    log_path: Path,
    env: dict[str, str],
    *,
    timeout_s: float | None = None,
) -> tuple[int, float]:
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=checkout,
        env=env,
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
        process.wait(timeout=timeout_s if timeout_s is not None else _run_timeout())
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


def _miniswe_exit_status(trial_dir: Path) -> str | None:
    payload = _read_json(trial_dir / "agent" / "mini-swe-agent.trajectory.json")
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "exit":
            continue
        extra = message.get("extra")
        if isinstance(extra, dict) and isinstance(extra.get("exit_status"), str):
            return extra["exit_status"]
        content = message.get("content")
        return str(content) if content else None
    return None


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


def run_readonly_agent(
    checkout: Path,
    prompt: str,
    ctx: OperatorContext,
    *,
    output_dir: Path,
    job_name: str,
    timeout_s: float,
) -> AgentRunResult:
    """Run one evidence-only Harbor agent and return its final response."""
    usage: dict[str, Any] = {"usd": 0, "wall_s": 0}
    output = ""
    returncode = 1
    try:
        if "agent_pythonpath" in ctx.config:
            raise ValueError(
                "agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock"
            )
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        task_root = output_dir / "task"
        prompt_path = output_dir / "prompt.md"
        jobs_root = output_dir / "jobs"
        tasks_dir = output_dir / "tasks"
        task_root.mkdir(parents=True, exist_ok=False)
        prompt_path.write_text(prompt.rstrip() + "\n")
        agent = str(ctx.config.get("agent") or "codex")
        if agent.endswith(":MiniSweSourceAgent"):
            command = _miniswe_config_command(
                harbor,
                task_root,
                prompt_path,
                jobs_root,
                tasks_dir,
                job_name,
                ctx.config,
                candidate_source=checkout / "target",
                artifact=None,
                uv_cache_dir=_uv_cache_dir(ctx.workspace),
            )
        else:
            command = _base_command(harbor, task_root, prompt_path, jobs_root, tasks_dir, job_name, ctx.config)
        _write_json(output_dir / "command.json", [_redact(arg) for arg in command])
        returncode, wall_s = _run_harbor(
            command,
            checkout,
            output_dir / "harbor.log",
            harbor_env,
            timeout_s=timeout_s,
        )
        usage["wall_s"] = wall_s
        trial_dir, trial = _trial_result(jobs_root / job_name)
        usage = _usage(trial, wall_s)
        _write_json(output_dir / "trial.json", trial)
        output = _agent_output(trial_dir).strip()
        if returncode != 0:
            raise RuntimeError(f"harbor exec exited {returncode}")
        if trial.get("exception_info") not in (None, {}):
            raise RuntimeError(f"Harbor read-only trial failed: {_redact(str(trial.get('exception_info')))}")
        if not output:
            raise RuntimeError("Harbor read-only trial returned no agent response")
        return AgentRunResult(
            stdout=output,
            stderr="",
            output=output,
            returncode=0,
            wall_s=wall_s,
            usage=usage,
        )
    except Exception as exc:
        raise AgentCommandError(
            f"{exc.__class__.__name__}: {_redact(str(exc))}",
            output=output,
            usage=usage,
            returncode=returncode,
        ) from exc


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
    bundle: _EditableBundle | None = None
    try:
        if "agent_pythonpath" in ctx.config:
            raise ValueError(
                "agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock"
            )
        bundle = _prepare_bundle(checkout, ctx.config.get("editable_roots", ["target"]), surface)
        if (jobs_root / job_name).exists():
            raise RuntimeError(f"Harbor meta-agent job already exists: {jobs_root / job_name}")
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            prompt.rstrip() + "\n\n# Harbor Runner Contract\n\n"
            "The editable candidate is at `/app/candidate`. Edit only paths allowed by the supplied "
            "surface rules. The complete `/app/candidate` directory is returned as the candidate artifact.\n"
        )
        command = _build_command(
            harbor,
            bundle,
            prompt_path,
            jobs_root,
            tasks_dir,
            job_name,
            ctx.config,
            _uv_cache_dir(ctx.workspace),
        )
        _write_json(harbor_root / "command.json", [_redact(arg) for arg in command])
        returncode, wall_s = _run_harbor(command, checkout, harbor_root / "harbor.log", harbor_env)
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
        if str(ctx.config.get("agent") or "").endswith(":MiniSweSourceAgent"):
            exit_status = _miniswe_exit_status(trial_dir)
            if exit_status != "Submitted":
                raise RuntimeError(
                    "Harbor MiniSwe meta-agent did not submit successfully: "
                    f"exit_status={_redact(str(exit_status or 'missing'))}"
                )
        artifact, manifest = _artifact_candidate(trial_dir)
        _write_json(harbor_root / "artifact-manifest.json", manifest)
        output = _agent_output(trial_dir)
        _install_bundle(checkout, artifact, bundle, parent_ref, surface)
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
            shutil.rmtree(bundle.staging, ignore_errors=True)
