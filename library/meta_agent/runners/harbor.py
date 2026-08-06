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
from collections.abc import Mapping
from pathlib import Path
from typing import Any, SupportsFloat, SupportsIndex, cast
from urllib.parse import urlsplit

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.config import load_config
from evolve.execution_runtime import execution_runtime_config, resolve_execution_runtime
from evolve.frozen.interfaces import OperatorContext
from evolve.git import git, head_commit, working_tree_changed_paths
from evolve.host_runtime import uv_run
from evolve.meta_agent_budget import (
    HARBOR_FILE_TASK_AGENT,
    harbor_agent_supports_per_attempt_timeout,
    harbor_meta_agent_budget,
    uses_harbor_per_attempt_timeout,
)
from evolve.patching import SurfacePolicy, load_surface_policy, patch_parent_ref
from evolve.surface import check_paths
from library.meta_agent.support.artifacts import ensure_artifact_layout

_HARBOR_WORKDIR = "/app"
_ARTIFACT_SOURCE = "/app/task/workspace"
_READONLY_ARTIFACT_SOURCE = "/logs/artifacts"
_READONLY_REPORT = "ahe-debugger-response.md"
_EVAL_RECEIPT = ".evolve-eval-receipts.jsonl"
_FILE_TASK_AGENT = HARBOR_FILE_TASK_AGENT
_SAFE_INLINE_INSTRUCTION_BYTES = 96 * 1024
_RETRY_EXCLUDE_EXCEPTIONS = (
    "VerifierTimeoutError",
    "RewardFileNotFoundError",
    "RewardFileEmptyError",
    "VerifierOutputParseError",
    "ApiUsageLimitError",
)
_VISIBLE_RUN_INPUTS = ("rollout", "trace_analyzer", "feedback")
_HIDDEN_WORKSPACE_ROOTS = {".git", ".venv", "runs", "artifacts", "archive.jsonl", _EVAL_RECEIPT, "evaluator"}
_TASK_IDENTIFIER_CHARACTERS = rb"A-Za-z0-9_.-"
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:api[_-]?key|access[_-]?token|auth(?:orization)?|secret|password))\b"
    r"([\"']?)(\s*[:=]\s*)([^\s,;}]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_ENV_NAME = re.compile(r"(?i)(?:proxy|api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)")
_CREDENTIAL_ENV = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE")
_PROXY_ENV = (
    ("EVOLVE_HARBOR_HTTP_PROXY", "http_proxy", "HTTP_PROXY"),
    ("EVOLVE_HARBOR_HTTPS_PROXY", "https_proxy", "HTTPS_PROXY"),
)
_BYPASS_ENV = ("no_proxy", "NO_PROXY")


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
        includes = surface.include or ["target/**"]
        root_is_mutable = not check_paths([raw], surface.include, surface.exclude)
        contains_mutable_path = any(pattern.startswith(raw + "/") for pattern in includes)
        if not root_is_mutable and not contains_mutable_path:
            raise ValueError(f"editable root contains no mutable surface paths: {raw}")
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


def _ignored_checkout_paths(checkout: Path) -> set[str]:
    result = git(
        checkout,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "-z",
    )
    return {path.rstrip("/") for path in result.stdout.split("\0") if path}


def _checkout_copy_ignore(checkout: Path, ignored: set[str]):
    root = checkout.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        relative = Path(directory).resolve().relative_to(root)
        return {name for name in names if (relative / name).as_posix() in ignored}

    return ignore


def _copy_checkout_inputs(checkout: Path, workspace: Path, excluded_roots: set[str]) -> None:
    ignored = _ignored_checkout_paths(checkout)
    ignore = _checkout_copy_ignore(checkout, ignored)
    for source in checkout.iterdir():
        relative = source.relative_to(checkout).as_posix()
        if source.name not in excluded_roots and relative not in ignored:
            _copy_tree(source, workspace / source.name, ignore=ignore)


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
    return relative.parts[0] in {".git", ".venv", "runs", "artifacts"} or relative.as_posix() in {
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


def _git_ignored(checkout: Path, relative: Path, *, directory: bool = False) -> bool:
    candidates = [relative.as_posix()]
    if directory:
        candidates.append(relative.as_posix() + "/")
    return any(
        git(checkout, "check-ignore", "--quiet", "--", candidate, check=False).returncode == 0
        for candidate in candidates
    )


def _nonignored_manifest_changes(
    checkout: Path,
    paths: list[str],
    before: dict[str, tuple[str, str]],
    after: dict[str, tuple[str, str]],
) -> list[str]:
    ignored_directories: list[str] = []
    visible: list[str] = []
    for path in sorted(paths, key=lambda item: (len(Path(item).parts), item)):
        if any(path == root or path.startswith(root + "/") for root in ignored_directories):
            continue
        kind = (after.get(path) or before.get(path) or ("", ""))[0]
        if _git_ignored(checkout, Path(path), directory=kind == "directory"):
            if kind == "directory":
                ignored_directories.append(path)
            continue
        visible.append(path)
    return sorted(visible)


def _initialize_sanitized_git(workspace: Path) -> None:
    git(workspace, "init", "--quiet")
    git(workspace, "config", "user.name", "EvolveX Meta-Agent")
    git(workspace, "config", "user.email", "meta-agent@evolvex.invalid")
    # This repository is copied into the Harbor task immediately after the
    # baseline commit.  Git may otherwise detach automatic maintenance on
    # platforms such as macOS, racing that copy as maintenance.lock appears
    # and disappears underneath shutil/tar.
    git(workspace, "config", "maintenance.auto", "false")
    git(workspace, "config", "gc.auto", "0")
    git(workspace, "add", "--all")
    git(workspace, "commit", "--quiet", "--no-gpg-sign", "-m", "sanitized meta-agent baseline")


def _copy_visible_generation_inputs(source: Path, destination: Path) -> None:
    for name in _VISIBLE_RUN_INPUTS:
        subtree = source / name
        if subtree.exists():
            copied = destination / name
            _copy_tree(subtree, copied)
            # Certified replay snapshots are intentionally frozen in the
            # experiment workspace. Docker Compose's artifact copier preserves
            # those directory modes, then cannot create their descendants in
            # the host destination. The meta-agent bundle is disposable and
            # changes under runs/ are never imported, so keep the files intact
            # while allowing the bundle itself to round-trip as an artifact.
            for current, _, _ in os.walk(copied, followlinks=False):
                directory = Path(current)
                directory.chmod(stat.S_IMODE(directory.stat().st_mode) | stat.S_IWUSR)


def _copy_visible_run_inputs(ctx: OperatorContext, workspace: Path) -> None:
    runs = ctx.workspace / "runs"
    copied_sources: set[Path] = set()
    if runs.is_dir():
        for generation in sorted(runs.glob("gen-*")):
            if generation.is_dir() and not generation.is_symlink():
                _copy_visible_generation_inputs(
                    generation,
                    workspace / "runs" / generation.name,
                )
                copied_sources.add(generation.resolve())
    if ctx.run_dir.resolve() not in copied_sources:
        _copy_visible_generation_inputs(
            ctx.run_dir,
            workspace / "runs" / f"gen-{ctx.genid}",
        )


def _private_task_names(workspace: Path) -> tuple[str, ...]:
    path = workspace / "evaluator" / "splits.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, dict):
        return ()
    names: set[str] = set()
    for split in ("gate", "sealed"):
        values = tasks.get(split)
        if isinstance(values, list):
            names.update(name for name in values if isinstance(name, str) and name)
    return tuple(sorted(names))


def _contains_private_task_name(
    path: Path,
    pattern: re.Pattern[bytes],
    overlap: int,
) -> bool:
    tail = b""
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                content = tail + chunk
                match = pattern.search(content)
                if match is not None and match.end() < len(content):
                    return True
                tail = content[-overlap:]
    except OSError:
        return False
    return pattern.search(tail) is not None


def _assert_private_tasks_absent(workspace: Path, prompt: str, private_names: tuple[str, ...]) -> None:
    if not private_names:
        return
    encoded_names = tuple(name.encode() for name in private_names)
    pattern = re.compile(
        rb"(?<!["
        + _TASK_IDENTIFIER_CHARACTERS
        + rb"])(?:"
        + rb"|".join(re.escape(name) for name in encoded_names)
        + rb")(?!["
        + _TASK_IDENTIFIER_CHARACTERS
        + rb"])"
    )
    if pattern.search(prompt.encode()):
        raise RuntimeError("Harbor meta-agent prompt contains a private gate/sealed task identifier")
    overlap = max(len(name) for name in encoded_names) + 1
    for path in workspace.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(workspace).parts:
            continue
        if _contains_private_task_name(path, pattern, overlap):
            raise RuntimeError("Harbor meta-agent workspace contains a private gate/sealed task identifier")


def _expose_gate_data(config: dict[str, Any]) -> bool:
    value = config.get("expose_gate_data", False)
    if not isinstance(value, bool):
        raise ValueError("expose_gate_data must be true or false")
    return value


def _copy_full_workspace_inputs(checkout: Path, ctx: OperatorContext, workspace: Path) -> None:
    for path in workspace.iterdir():
        if path.name != ".git":
            _remove(path)
    _copy_checkout_inputs(
        checkout,
        workspace,
        {".git", "runs", "archive.jsonl", _EVAL_RECEIPT},
    )
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


def _copy_artifact_inputs(ctx: OperatorContext, workspace: Path) -> None:
    ensure_artifact_layout(ctx.workspace, ctx.genid)
    artifacts = ctx.workspace / "artifacts"
    if artifacts.exists():
        _validate_tree(artifacts)
        _copy_tree(artifacts, workspace / "artifacts")
    (workspace / "artifacts" / "user").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "generations" / ctx.genid).mkdir(parents=True, exist_ok=True)


def _prepare_bundle(
    checkout: Path,
    ctx: OperatorContext,
    value: object,
    surface: SurfacePolicy,
    *,
    prompt: str = "",
) -> _WorkspaceBundle:
    roots = _editable_roots(value, surface)
    for root in roots:
        _validate_tree(checkout / root)
    staging = Path(tempfile.mkdtemp(prefix="evolve-harbor-", dir=checkout.parent))
    task_root = staging / "task"
    workspace = task_root / "workspace"
    try:
        task_root.mkdir(parents=True)
        if _expose_gate_data(ctx.config):
            git(checkout, "clone", "--quiet", "--no-hardlinks", str(checkout), str(workspace))
            git(workspace, "checkout", "--quiet", "--detach", head_commit(checkout))
            _copy_full_workspace_inputs(checkout, ctx, workspace)
        else:
            workspace.mkdir()
            _copy_checkout_inputs(checkout, workspace, _HIDDEN_WORKSPACE_ROOTS)
            _copy_visible_run_inputs(ctx, workspace)
        _copy_artifact_inputs(ctx, workspace)
        if not _expose_gate_data(ctx.config):
            _assert_private_tasks_absent(workspace, prompt, _private_task_names(ctx.workspace))
            _initialize_sanitized_git(workspace)
        return _WorkspaceBundle(staging, task_root, workspace, roots, _tree_manifest(workspace))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _copy_returned_tree(checkout: Path, source: Path, destination: Path, relative: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError(f"returned candidate root must be a real directory: {source}")
    destination.mkdir()
    for child in source.iterdir():
        child_relative = relative / child.name
        mode = child.lstat().st_mode
        if _git_ignored(checkout, child_relative, directory=stat.S_ISDIR(mode)):
            continue
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"Harbor meta-agent does not accept symlinks: {child}")
        if stat.S_ISDIR(mode):
            _copy_returned_tree(checkout, child, destination / child.name, child_relative)
        elif stat.S_ISREG(mode):
            shutil.copy2(child, destination / child.name)
        else:
            raise RuntimeError(f"Harbor meta-agent does not accept special files: {child}")


def _copy_regular_tree(source: Path, destination: Path) -> None:
    """Copy only regular files/directories, treating a deleted namespace as empty."""
    if source.is_symlink():
        raise RuntimeError(f"Harbor meta-agent does not accept symlinks: {source}")
    if not source.exists():
        destination.mkdir(parents=True)
        return
    if not source.is_dir():
        raise RuntimeError(f"returned artifact namespace must be a real directory: {source}")
    destination.mkdir(parents=True)
    for child in source.iterdir():
        mode = child.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"Harbor meta-agent does not accept symlinks: {child}")
        if stat.S_ISDIR(mode):
            _copy_regular_tree(child, destination / child.name)
        elif stat.S_ISREG(mode):
            shutil.copy2(child, destination / child.name)
        else:
            raise RuntimeError(f"Harbor meta-agent does not accept special files: {child}")


def _install_bundle(
    checkout: Path,
    returned: Path,
    bundle: _WorkspaceBundle,
    parent_ref: str,
    surface: SurfacePolicy,
    *,
    artifact_workspace: Path | None = None,
    genid: str | None = None,
) -> list[str]:
    if not returned.is_dir() or returned.is_symlink():
        raise RuntimeError("returned workspace must be a real directory")
    returned_artifacts = returned / "artifacts"
    if returned_artifacts.exists() or returned_artifacts.is_symlink():
        _validate_tree(returned_artifacts)
    after = _tree_manifest(returned)
    changed_workspace = [path for path in set(bundle.before) | set(after) if bundle.before.get(path) != after.get(path)]
    changed_workspace = _nonignored_manifest_changes(checkout, changed_workspace, bundle.before, after)
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
    artifact_destination: Path | None = None
    artifact_backup = backups / "artifact-generation"
    artifact_installed = False
    artifact_moved = False
    try:
        for root in bundle.roots:
            _copy_returned_tree(checkout, returned / root, replacements / root, Path(root))
        if artifact_workspace is not None and genid is not None:
            if not genid or genid in {".", ".."} or "/" in genid or "\\" in genid:
                raise ValueError(f"invalid generation id for artifact path: {genid!r}")
            artifact_relative = Path("artifacts") / "generations" / genid
            artifact_destination = artifact_workspace / artifact_relative
            _copy_regular_tree(returned / artifact_relative, replacements / "artifact-generation")
        for root in bundle.roots:
            (checkout / root).rename(backups / root)
            moved.append(root)
            (replacements / root).rename(checkout / root)
            installed.append(root)
        if artifact_destination is not None:
            artifact_destination.parent.mkdir(parents=True, exist_ok=True)
            if artifact_destination.exists():
                artifact_destination.rename(artifact_backup)
                artifact_moved = True
            (replacements / "artifact-generation").rename(artifact_destination)
            artifact_installed = True

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
        if artifact_installed and artifact_destination is not None:
            _remove(artifact_destination)
        if artifact_moved and artifact_destination is not None:
            artifact_backup.rename(artifact_destination)
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
    path.chmod(0o600)


def _instruction_transport(agent: str, prompt_path: Path) -> dict[str, object]:
    size = prompt_path.stat().st_size
    config_file = agent.endswith(":MiniSweSourceAgent")
    safe = agent == _FILE_TASK_AGENT or config_file
    mode = "config-file" if config_file else "mounted-file" if safe else "inline-argument"
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


def _redact(text: str, environment: Mapping[str, str] | None = None) -> str:
    configured = os.environ if environment is None else environment
    values = {value for name, value in configured.items() if _SENSITIVE_ENV_NAME.search(name) and len(value) >= 8}
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]", text)


def _redaction_environment(config: dict[str, Any]) -> dict[str, str]:
    return {**os.environ, **_agent_env(config)}


def _nonnegative_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(cast(str | SupportsFloat | SupportsIndex, value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _retry_config(config: dict[str, Any]) -> dict[str, Any]:
    max_retries = _nonnegative_int(config.get("max_retries"), 0)
    retry: dict[str, Any] = {"max_retries": max_retries}
    if max_retries:
        retry["exclude_exceptions"] = list(_RETRY_EXCLUDE_EXCEPTIONS)
    return retry


def _meta_agent_process_timeout_s(config: dict[str, Any]) -> float | None:
    if not uses_harbor_per_attempt_timeout(config):
        return None
    timeout_s = _positive_float(config.get("timeout_s"))
    if timeout_s is None:
        return None
    max_retries = _nonnegative_int(config.get("max_retries"), 0)
    return harbor_meta_agent_budget(timeout_s, max_retries).harbor_process_s


def _append_agent_env(command: list[str], config: dict[str, Any]) -> None:
    for key, value in _agent_env(config).items():
        command.extend(["--ae", f"{key}={value}"])


def _agent_env(config: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    agent = str(config.get("agent") or "").strip().lower()
    for override, lower, upper in _PROXY_ENV:
        value = os.environ.get(override) or os.environ.get(lower) or os.environ.get(upper)
        if value:
            values.update({lower: value, upper: value})
    for name in _BYPASS_ENV:
        value = os.environ.get(name)
        if value:
            values[name] = value
    bypass_override = os.environ.get("EVOLVE_HARBOR_NO_PROXY")
    if bypass_override:
        values.update({name: bypass_override for name in _BYPASS_ENV})
    # Harbor's Codex agent mounts the host Codex home, including auth.json.
    # Do not let evaluator/judge endpoints exported by the driver override
    # that login. A custom Codex provider remains available through an
    # explicit meta_agent.agent_env mapping.
    if agent != "codex":
        for name in _CREDENTIAL_ENV:
            value = os.environ.get(name)
            if value:
                values[name] = value
    configured = config.get("agent_env")
    if isinstance(configured, dict):
        values.update({str(key): str(value) for key, value in configured.items()})
    for _, lower, upper in _PROXY_ENV:
        value = values.get(lower) or values.get(upper)
        if value:
            values.update({lower: value, upper: value})
    base_url = values.get("OPENAI_BASE_URL") or values.get("OPENAI_API_BASE")
    bypass_entries: list[str] = []
    for name in _BYPASS_ENV:
        for entry in values.get(name, "").split(","):
            entry = entry.strip()
            if entry and entry not in bypass_entries:
                bypass_entries.append(entry)
    if base_url:
        hostname = urlsplit(base_url).hostname
        if not hostname:
            raise ValueError("configured model base URL has no hostname")
        if hostname not in bypass_entries:
            bypass_entries.append(hostname)
    if bypass_entries:
        bypass = ",".join(bypass_entries)
        values.update({name: bypass for name in _BYPASS_ENV})
    if agent == "codex":
        # Harbor redacts literal values for environment keys containing
        # "AUTH" when it persists a job. Keep this as a resolvable template
        # so the trial receives a boolean value instead of "****".
        values["CODEX_FORCE_AUTH_JSON"] = "${CODEX_FORCE_AUTH_JSON:-1}"
    force_auth = os.environ.get("CODEX_FORCE_AUTH_JSON")
    if force_auth and "CODEX_FORCE_AUTH_JSON" not in values:
        values["CODEX_FORCE_AUTH_JSON"] = force_auth
    return values


def _harbor_process_env(
    config: dict[str, Any], values: dict[str, str], *, workspace: Path | None = None
) -> dict[str, str]:
    sanitized = dict(values)
    if str(config.get("agent") or "").strip().lower() == "codex":
        for name in _CREDENTIAL_ENV:
            sanitized.pop(name, None)
    runtime_values = load_config(workspace / "evolve.yaml")["execution_runtime"] if workspace is not None else {}
    runtime = resolve_execution_runtime(execution_runtime_config(runtime_values), sanitized)
    return runtime.process_environment(sanitized)


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
    agent_timeout_s: float | None,
) -> list[str]:
    agent_env = _agent_env(config)
    agent_env.setdefault("EVOLVE_CANDIDATE_SOURCE", str(candidate_source.resolve()))
    agent: dict[str, Any] = {
        "name": str(config.get("agent")),
        "env": agent_env,
    }
    if agent_timeout_s is not None:
        agent["override_timeout_sec"] = agent_timeout_s
    model = config.get("model")
    if model:
        agent["model_name"] = str(model)
    kwargs = config.get("agent_kwargs")
    if isinstance(kwargs, dict) and kwargs:
        agent["kwargs"] = {str(key): value for key, value in kwargs.items()}

    compile_environment: dict[str, Any] = {"paths": [str(source.resolve())]}
    image = config.get("image")
    if image:
        compile_environment["docker_image"] = str(image)
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
    environment_kwargs = config.get("environment_kwargs")
    if isinstance(environment_kwargs, dict):
        environment["kwargs"] = environment_kwargs
    job_config: dict[str, Any] = {
        "job_name": job_name,
        "jobs_dir": str(jobs_root.resolve()),
        "n_concurrent_trials": 1,
        "quiet": os.environ.get("EVOLVE_LIVE_OUTPUT") != "1",
        "retry": _retry_config(config),
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
    environment_kwargs = config.get("environment_kwargs")
    if isinstance(environment_kwargs, dict):
        for key in sorted(environment_kwargs):
            value = environment_kwargs[key]
            command.extend(["--environment-kwarg", f"{key}={json.dumps(value, separators=(',', ':'))}"])
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
    uv_cache_dir: Path | None = None,
) -> list[str]:
    agent = str(config.get("agent") or "codex")
    if harbor_agent_supports_per_attempt_timeout(agent):
        if "target" not in bundle.roots:
            raise ValueError("MiniSweSourceAgent requires target in editable_roots")
        return _miniswe_config_command(
            harbor,
            bundle.task_root,
            prompt_path,
            jobs_root,
            tasks_dir,
            job_name,
            config,
            candidate_source=bundle.workspace / "target",
            artifact=_ARTIFACT_SOURCE,
            uv_cache_dir=uv_cache_dir or _uv_cache_dir(bundle.task_root),
            agent_timeout_s=_positive_float(config.get("timeout_s")),
        )
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
    redaction_environment: Mapping[str, str] | None = None,
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
        umask=0o077,
    )
    chunks: list[str] = []

    def consume_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            chunks.append(line)
            if os.environ.get("EVOLVE_LIVE_OUTPUT") == "1":
                print(_redact(line, redaction_environment), end="", flush=True)

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
    log_path.write_text(_redact(f"wall_s={wall_s}\n{''.join(chunks)}", redaction_environment))
    log_path.chmod(0o600)
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
    for path in sorted((trial_dir / "agent").glob("*.trajectory.json")):
        if path.name == "trajectory.json":
            continue
        raw = _read_json(path)
        messages = raw.get("messages") if isinstance(raw, dict) else None
        if not isinstance(messages, list):
            continue
        preserved: list[str] = []
        for item in messages:
            extra = item.get("extra") if isinstance(item, dict) else None
            response = extra.get("response") if isinstance(extra, dict) else None
            choices = response.get("choices") if isinstance(response, dict) else None
            if not isinstance(choices, list):
                continue
            for choice in choices:
                message = choice.get("message") if isinstance(choice, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str) and content:
                    preserved.append(content)
        if preserved:
            return preserved[-1]
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


def _readonly_artifact_output(trial_dir: Path) -> str:
    payload = _read_json(trial_dir / "artifacts" / "manifest.json")
    entries = [entry for entry in payload if isinstance(entry, dict)] if isinstance(payload, list) else []
    entry = next((item for item in entries if item.get("source") == _READONLY_ARTIFACT_SOURCE), None)
    if entry is None or entry.get("status") != "ok":
        raise RuntimeError("Harbor did not collect AHE debugger artifacts")
    destination = entry.get("destination")
    if not isinstance(destination, str) or not destination:
        raise RuntimeError("Harbor AHE debugger artifact has no destination")
    artifact_dir = (trial_dir / destination).resolve()
    trial_root = trial_dir.resolve()
    if trial_root != artifact_dir and trial_root not in artifact_dir.parents:
        raise RuntimeError("Harbor AHE debugger artifact escaped the trial")
    report = artifact_dir / _READONLY_REPORT
    if not report.is_file():
        raise RuntimeError(f"missing AHE debugger report: {_READONLY_REPORT}")
    output = report.read_text().strip()
    if not output:
        raise RuntimeError(f"empty AHE debugger report: {_READONLY_REPORT}")
    return output


def _uses_miniswe_artifact(agent: object) -> bool:
    name = str(agent or "")
    return name == "mini-swe-agent" or name.endswith(":FileTaskMiniSweAgent")


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
    input_files: dict[str, str] | None = None,
) -> AgentRunResult:
    """Run one evidence-only Harbor agent and return its final response."""
    usage: dict[str, Any] = {"usd": 0, "wall_s": 0}
    output = ""
    returncode = 1
    redaction_environment: Mapping[str, str] = os.environ
    try:
        if "agent_pythonpath" in ctx.config:
            raise ValueError(
                "agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock"
            )
        redaction_environment = _redaction_environment(ctx.config)
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        harbor_env = _harbor_process_env(ctx.config, harbor_env, workspace=ctx.workspace)
        task_root = output_dir / "task"
        prompt_path = output_dir / "prompt.md"
        jobs_root = output_dir / "jobs"
        tasks_dir = output_dir / "tasks"
        task_root.mkdir(parents=True, exist_ok=False)
        (task_root / ".evolve-readonly").write_text("")
        if input_files:
            inputs = task_root / "inputs"
            inputs.mkdir()
            for name, content in input_files.items():
                if Path(name).name != name or name in {".", ".."}:
                    raise ValueError(f"read-only input name must be one relative filename: {name!r}")
                (inputs / name).write_text(content)
        prompt_path.write_text(prompt.rstrip() + "\n")
        _write_json(
            output_dir / "instruction-transport.json",
            _instruction_transport(str(ctx.config.get("agent") or "codex"), prompt_path),
        )
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
                agent_timeout_s=timeout_s,
            )
        else:
            command = _base_command(harbor, task_root, prompt_path, jobs_root, tasks_dir, job_name, ctx.config)
        _write_json(
            output_dir / "command.json",
            [_redact(arg, redaction_environment) for arg in command],
        )
        returncode, wall_s = _run_harbor(
            command,
            checkout,
            output_dir / "harbor.log",
            harbor_env,
            timeout_s=timeout_s,
            redaction_environment=redaction_environment,
        )
        usage["wall_s"] = wall_s
        trial_dir, trial = _trial_result(jobs_root / job_name)
        usage = _usage(trial, wall_s)
        _write_json(output_dir / "trial.json", trial)
        output = (
            _readonly_artifact_output(trial_dir)
            if _uses_miniswe_artifact(ctx.config.get("agent"))
            else _agent_output(trial_dir).strip()
        )
        if returncode != 0:
            raise RuntimeError(f"harbor exec exited {returncode}")
        if trial.get("exception_info") not in (None, {}):
            raise RuntimeError(
                f"Harbor read-only trial failed: {_redact(str(trial.get('exception_info')), redaction_environment)}"
            )
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
            f"{exc.__class__.__name__}: {_redact(str(exc), redaction_environment)}",
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
    redaction_environment: Mapping[str, str] = os.environ
    try:
        if "agent_pythonpath" in ctx.config:
            raise ValueError(
                "agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock"
            )
        redaction_environment = _redaction_environment(ctx.config)
        bundle = _prepare_bundle(
            checkout,
            ctx,
            ctx.config.get("editable_roots", ["target"]),
            surface,
            prompt=prompt,
        )
        if (jobs_root / job_name).exists():
            raise RuntimeError(f"Harbor meta-agent job already exists: {jobs_root / job_name}")
        harbor, harbor_env = uv_run(ctx.workspace, "harbor")
        harbor_env = _harbor_process_env(ctx.config, harbor_env, workspace=ctx.workspace)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_contract = (
            "It contains the selected parent, full Git history, configuration, archive, evaluator, and complete "
            "run evidence, including gate/sealed data."
            if _expose_gate_data(ctx.config)
            else "It contains the selected parent, a clean Git baseline, configuration, and current/prior "
            "generations' train rollout, trace-analysis, and feedback evidence. Evaluator files, task partitions, "
            "archive records, selection artifacts, and gate/sealed evaluations are intentionally unavailable."
        )
        prompt_path.write_text(
            prompt.rstrip() + "\n\n# Harbor Runner Contract\n\n"
            f"The disposable experiment workspace is at `{_ARTIFACT_SOURCE}`. {evidence_contract} "
            "Work in that directory normally. "
            "Edit only paths allowed by the supplied surface rules. Runtime evidence edits are discarded; only "
            "configured editable roots and the current generation's durable artifact directory are imported after "
            "the complete workspace artifact passes the surface gate. User and prior-generation durable artifacts "
            "are read-only from the runner's perspective. "
            "Before finishing, remove generated virtual environments and caches inside editable roots (for example "
            "target/.venv, __pycache__, and .pytest_cache); returned editable roots must contain no symlinks.\n"
        )
        _write_json(
            harbor_root / "instruction-transport.json",
            _instruction_transport(str(ctx.config.get("agent") or "codex"), prompt_path),
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
        _write_json(
            harbor_root / "command.json",
            [_redact(arg, redaction_environment) for arg in command],
        )
        returncode, wall_s = _run_harbor(
            command,
            checkout,
            harbor_root / "harbor.log",
            harbor_env,
            timeout_s=_meta_agent_process_timeout_s(ctx.config),
            redaction_environment=redaction_environment,
        )
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
            raise RuntimeError(
                f"Harbor meta-agent trial failed: {_redact(str(trial.get('exception_info')), redaction_environment)}"
            )
        if str(ctx.config.get("agent") or "").endswith(":MiniSweSourceAgent") or _uses_miniswe_artifact(
            ctx.config.get("agent")
        ):
            exit_status = _miniswe_exit_status(trial_dir)
            if exit_status != "Submitted":
                raise RuntimeError(
                    "Harbor MiniSwe meta-agent did not submit successfully: "
                    f"exit_status={_redact(str(exit_status or 'missing'), redaction_environment)}"
                )
        artifact, manifest = _artifact_candidate(trial_dir)
        _write_json(harbor_root / "artifact-manifest.json", manifest)
        output = _agent_output(trial_dir)
        _install_bundle(
            checkout,
            artifact,
            bundle,
            parent_ref,
            surface,
            artifact_workspace=ctx.workspace,
            genid=ctx.genid,
        )
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
                "message": _redact(str(exc), redaction_environment),
                "returncode": returncode,
                "type": exc.__class__.__name__,
            },
        )
        raise AgentCommandError(
            f"{exc.__class__.__name__}: {_redact(str(exc), redaction_environment)}",
            output=output,
            usage=usage,
            returncode=returncode,
        ) from exc
    finally:
        if bundle is not None:
            shutil.rmtree(bundle.staging, ignore_errors=True)
