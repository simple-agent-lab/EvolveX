"""Run an isolated Harbor editing agent and return its target artifact."""

from __future__ import annotations

import hashlib
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
from evolve.git import git, head_commit, working_tree_changed_paths
from evolve.host_runtime import uv_run
from evolve.patching import SurfacePolicy, load_surface_policy, patch_parent_ref
from evolve.surface import check_paths

_HARBOR_WORKDIR = "/app"
_ARTIFACT_SOURCE = "/app/task/workspace"
_EVAL_RECEIPT = ".evolve-eval-receipts.jsonl"
_FILE_TASK_AGENT = "evolve_harbor_agent:FileTaskMiniSweAgent"
_SAFE_INLINE_INSTRUCTION_BYTES = 96 * 1024
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


class _WorkspaceBundle:
    __slots__ = ("staging", "task_root", "workspace", "roots", "before")

    def __init__(
        self,
        staging: Path,
        task_root: Path,
        workspace: Path,
        roots: tuple[str, ...],
        before: dict[str, tuple[str, str]],
    ) -> None:
        self.staging = staging
        self.task_root = task_root
        self.workspace = workspace
        self.roots = roots
        self.before = before


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
        if check_paths([raw], surface.include, surface.exclude):
            raise ValueError(f"editable root is not covered by mutable surface: {raw}")
        roots.append(raw)
    return tuple(roots)


def _copy_tree(source: Path, destination: Path, *, ignore=None) -> None:
    if not source.exists():
        return
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True, ignore=ignore)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


def _runs_ignore(runs_root: Path):
    resolved_root = runs_root.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory).resolve()
        ignored: set[str] = set()
        if current == resolved_root:
            ignored.add("worktrees")
        try:
            relative = current.relative_to(resolved_root)
        except ValueError:
            return ignored
        if len(relative.parts) >= 3 and relative.parts[-2:] == ("meta_agent", "harbor"):
            ignored.update({"jobs", "tasks"})
        return ignored.intersection(names)

    return ignore


def _manifest_ignored(relative: Path) -> bool:
    if not relative.parts:
        return False
    return relative.parts[0] in {".git", "runs"} or relative.as_posix() in {
        "archive.jsonl",
        _EVAL_RECEIPT,
    }


def _tree_manifest(root: Path) -> dict[str, tuple[str, str]]:
    manifest: dict[str, tuple[str, str]] = {}
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        relative_dir = current.relative_to(root)
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            path = current / name
            relative = relative_dir / name
            if _manifest_ignored(relative):
                continue
            if path.is_symlink():
                manifest[relative.as_posix()] = ("symlink", os.readlink(path))
            else:
                manifest[relative.as_posix()] = ("directory", "")
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            path = current / name
            relative = relative_dir / name
            if _manifest_ignored(relative):
                continue
            key = relative.as_posix()
            if path.is_symlink():
                manifest[key] = ("symlink", os.readlink(path))
            elif path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest[key] = ("file", digest)
            else:
                manifest[key] = ("special", "")
    return manifest


def _prepare_bundle(
    checkout: Path,
    ctx: OperatorContext,
    value: object,
    surface: SurfacePolicy,
) -> _WorkspaceBundle:
    roots = _editable_roots(value, surface)
    for root in roots:
        _validate_tree(checkout / root)
    staging = Path(tempfile.mkdtemp(prefix="evolve-harbor-", dir=checkout.parent))
    task_root = staging / "task"
    workspace = task_root / "workspace"
    try:
        task_root.mkdir(parents=True)
        git(checkout, "clone", "--quiet", "--no-hardlinks", str(checkout), str(workspace))
        git(workspace, "checkout", "--quiet", "--detach", head_commit(checkout))

        for path in workspace.iterdir():
            if path.name != ".git":
                _remove(path)
        for source in checkout.iterdir():
            if source.name not in {".git", "runs", "archive.jsonl", _EVAL_RECEIPT}:
                _copy_tree(source, workspace / source.name)

        archive = ctx.workspace / "archive.jsonl"
        if archive.is_file():
            _copy_tree(archive, workspace / "archive.jsonl")
        receipt = ctx.workspace / _EVAL_RECEIPT
        if receipt.is_file():
            _copy_tree(receipt, workspace / _EVAL_RECEIPT)
        runs = ctx.workspace / "runs"
        if runs.is_dir():
            _copy_tree(runs, workspace / "runs", ignore=_runs_ignore(runs))
        if ctx.run_dir.is_dir():
            _copy_tree(
                ctx.run_dir,
                workspace / "runs" / f"gen-{ctx.genid}",
                ignore=_runs_ignore(ctx.run_dir.parent),
            )
        return _WorkspaceBundle(staging, task_root, workspace, roots, _tree_manifest(workspace))
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
    bundle: _WorkspaceBundle,
    parent_ref: str,
    surface: SurfacePolicy,
) -> list[str]:
    if not returned.is_dir() or returned.is_symlink():
        raise RuntimeError("returned workspace must be a real directory")
    after = _tree_manifest(returned)
    changed_workspace = sorted(
        path for path in set(bundle.before) | set(after) if bundle.before.get(path) != after.get(path)
    )
    violations = check_paths(changed_workspace, surface.include, surface.exclude)
    if violations:
        raise RuntimeError("returned workspace mutated paths outside surface: " + ", ".join(violations))

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
            raise RuntimeError("returned workspace mutated paths outside surface: " + ", ".join(violations))
        diff = git(checkout, "diff", "--check", parent_ref, "--", *bundle.roots, check=False)
        if diff.returncode:
            raise RuntimeError(f"returned workspace failed git diff --check: {(diff.stderr or diff.stdout).strip()}")
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


def _instruction_transport(agent: str, prompt_path: Path) -> dict[str, object]:
    size = prompt_path.stat().st_size
    safe = agent == _FILE_TASK_AGENT
    mode = "mounted-file" if safe else "inline-argument"
    if size > _SAFE_INLINE_INSTRUCTION_BYTES and not safe:
        raise RuntimeError(
            f"harbor_instruction_transport_unsafe: agent={agent} bytes={size} limit={_SAFE_INLINE_INSTRUCTION_BYTES}"
        )
    return {"bytes": size, "mode": mode, "safe": safe}


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
    bundle: _WorkspaceBundle,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
) -> list[str]:
    command = _base_command(harbor, bundle.task_root, prompt_path, jobs_root, tasks_dir, job_name, config)
    workdir_index = command.index("--workdir")
    command[workdir_index + 1] = _HARBOR_WORKDIR
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
        raise RuntimeError(f"Harbor did not collect a successful {_ARTIFACT_SOURCE} artifact")
    destination = entry.get("destination")
    if not isinstance(destination, str) or not destination:
        raise RuntimeError("Harbor workspace artifact has no destination")
    artifact = (trial_dir / destination).resolve()
    trial_root = trial_dir.resolve()
    if trial_root not in artifact.parents or not artifact.is_dir():
        raise RuntimeError("Harbor workspace artifact escaped the trial or is not a directory")
    return artifact, entries


def _agent_output(trial_dir: Path) -> str:
    payload = _read_json(trial_dir / "agent" / "trajectory.json")
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if isinstance(steps, list):
        messages = [
            str(step.get("message"))
            for step in steps
            if isinstance(step, dict) and step.get("source") == "agent" and step.get("message")
        ]
        if messages:
            return messages[-1]

    payload = _read_json(trial_dir / "agent" / "mini-swe-agent.trajectory.json")
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return ""
    responses = [
        str(message.get("content"))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "assistant" and message.get("content")
    ]
    return responses[-1] if responses else ""


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
        _write_json(
            output_dir / "instruction-transport.json",
            _instruction_transport(str(ctx.config.get("agent") or "codex"), prompt_path),
        )
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
    bundle: _WorkspaceBundle | None = None
    try:
        if "agent_pythonpath" in ctx.config:
            raise ValueError(
                "agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock"
            )
        bundle = _prepare_bundle(checkout, ctx, ctx.config.get("editable_roots", ["target"]), surface)
        if (jobs_root / job_name).exists():
            raise RuntimeError(f"Harbor meta-agent job already exists: {jobs_root / job_name}")
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            prompt.rstrip() + "\n\n# Harbor Runner Contract\n\n"
            f"The disposable experiment workspace is at `{_ARTIFACT_SOURCE}`. It contains the selected parent, "
            "Git history, configuration, archive, and run evidence. Work in that directory normally. Edit "
            "only paths allowed by the supplied surface rules. Runtime evidence edits are discarded; only "
            "configured editable roots are imported after the complete workspace artifact passes the surface gate. "
            "Before finishing, remove generated virtual environments and caches inside editable roots (for example "
            "target/.venv, __pycache__, and .pytest_cache); returned editable roots must contain no symlinks.\n"
        )
        _write_json(
            harbor_root / "instruction-transport.json",
            _instruction_transport(str(ctx.config.get("agent") or "codex"), prompt_path),
        )
        command = _build_command(harbor, bundle, prompt_path, jobs_root, tasks_dir, job_name, ctx.config)
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
        _write_json(
            harbor_root / "error.json",
            {
                "message": _redact(str(exc)),
                "returncode": returncode,
                "type": exc.__class__.__name__,
            },
        )
        raise AgentCommandError(
            f"{exc.__class__.__name__}: {_redact(str(exc))}",
            output=output,
            usage=usage,
            returncode=returncode,
        ) from exc
    finally:
        if bundle is not None:
            shutil.rmtree(bundle.staging, ignore_errors=True)
