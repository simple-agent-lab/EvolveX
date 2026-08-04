from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation import Outcome
from .host_runtime import clean_python_env, uv_executable
from .runtime import run_owned
from .runtime_profiles import load_resolved_runtime_profile

CONTAINER_UV_CACHE = "/opt/evolve/uv/cache"
CONTAINER_UV_PYTHON = "/opt/evolve/uv/python"
RECEIPT_NAME = "candidate-runtime.json"
FRAMEWORK_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"


@dataclass(frozen=True)
class UvRuntimeConfig:
    variant: str
    project: Path
    project_relative: str
    python: str


def _digest_project(project: Path) -> str:
    digest = hashlib.sha256()
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        path = project / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def candidate_dependency_digest(checkout: Path, evaluator: dict[str, Any]) -> str | None:
    config = candidate_runtime_config(checkout, evaluator)
    return _digest_project(config.project) if config is not None else None


_SECRET_ENV_NAME = re.compile(r"(?i)(?:secret|token|password|passwd|api[_-]?key|credential|authorization|proxy)")


def _redact(message: str, environment: Mapping[str, str] | None = None) -> str:
    redacted = message
    for name, value in (environment or {}).items():
        if _SECRET_ENV_NAME.search(name) and len(value) >= 4:
            redacted = redacted.replace(value, "***")
    redacted = re.sub(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@", r"\1***:***@", redacted)
    redacted = re.sub(r"(?i)(https?://)[^\s/@]+@", r"\1***@", redacted)
    redacted = re.sub(
        r"(?i)([?&](?:access_token|api_key|key|password|token)=)[^\s&#]+",
        r"\1***",
        redacted,
    )
    redacted = re.sub(r"(?i)(\bBearer\s+)[^\s]+", r"\1***", redacted)
    return redacted[:2000]


@dataclass(frozen=True)
class RuntimeMount:
    source: Path
    target: str
    read_only: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "bind",
            "source": str(self.source),
            "target": self.target,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class CandidateRuntimeResult:
    variant: str | None
    project: str | None
    environment: tuple[tuple[str, str], ...] = ()
    mounts: tuple[RuntimeMount, ...] = ()
    outcome: Outcome | None = None
    reason: str | None = None
    receipt_path: Path | None = None

    @property
    def ready(self) -> bool:
        return self.outcome is None

    def environment_json(self) -> str:
        return json.dumps(dict(self.environment), sort_keys=True, separators=(",", ":"))

    def mounts_json(self) -> str:
        return json.dumps(
            [mount.to_dict() for mount in self.mounts],
            sort_keys=True,
            separators=(",", ":"),
        )


def candidate_runtime_config(checkout: Path, evaluator: dict[str, Any]) -> UvRuntimeConfig | None:
    profile_path = checkout / "evaluator" / "runtime-profile.json"
    if profile_path.is_file():
        if "candidate_runtime" in evaluator:
            raise ValueError(
                "cannot combine a resolved runtime profile with evaluator.candidate_runtime"
            )
        try:
            resolved_profile = load_resolved_runtime_profile(json.loads(profile_path.read_text()))
        except json.JSONDecodeError as error:
            raise ValueError("evaluator/runtime-profile.json is invalid JSON") from error
        policy = resolved_profile.profile.candidate_runtime
        if policy is None:
            return None
        value: object = {
            "variant": policy.variant,
            "project": policy.project,
            "python": policy.python,
        }
    else:
        value = evaluator.get("candidate_runtime")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("evaluator.candidate_runtime must be a mapping")
    if value.get("variant") != "uv":
        raise ValueError(f"unsupported candidate runtime variant: {value.get('variant')!r}")
    raw_project = value.get("project")
    if not isinstance(raw_project, str) or not raw_project.strip():
        raise ValueError("evaluator.candidate_runtime.project must be a relative path")
    relative = Path(raw_project)
    if relative.is_absolute():
        raise ValueError("candidate runtime project must be relative")
    root = checkout.resolve()
    project = (root / relative).resolve()
    try:
        project.relative_to(root)
    except ValueError:
        raise ValueError("candidate runtime project escapes checkout") from None
    python = value.get("python", FRAMEWORK_PYTHON)
    if not isinstance(python, str) or not re.fullmatch(r"\d+\.\d+", python):
        raise ValueError("evaluator.candidate_runtime.python must be a Python major.minor version")
    return UvRuntimeConfig("uv", project, project.relative_to(root).as_posix(), python)


def _uv_version(uv: str, checkout: Path, env: dict[str, str]) -> str | None:
    completed = run_owned([uv, "--version"], cwd=checkout, env=env)
    if completed.returncode:
        return None
    return completed.stdout.strip() or None


def _normalize_managed_python_links(python_dir: Path) -> None:
    """Keep uv-managed aliases valid when their directory is bind-mounted."""
    for link in python_dir.iterdir():
        if not link.is_symlink():
            continue
        target = link.readlink()
        if not target.is_absolute():
            continue
        try:
            relative = target.relative_to(python_dir)
        except ValueError:
            continue
        temporary = link.with_name(f".{link.name}.relative")
        temporary.symlink_to(relative)
        temporary.replace(link)


def _write_receipt(
    run_dir: Path,
    config: UvRuntimeConfig,
    *,
    candidate_commit: str,
    contract_id: str | None,
    dependency_digest: str,
    uv_version: str | None,
    cache_warm: bool,
    attempts: int,
    outcome: str,
    duration_s: float,
    reason: str | None,
) -> Path:
    receipt = run_dir / RECEIPT_NAME
    temporary = receipt.with_suffix(".json.tmp")
    values = {
        "schema_version": 2 if contract_id is not None else 1,
        "contract_id": contract_id,
        "variant": config.variant,
        "project": config.project_relative,
        "candidate_commit": candidate_commit,
        "candidate_dependency_digest": dependency_digest,
        "uv_version": uv_version,
        "cache_warm": cache_warm,
        "attempts": attempts,
        "outcome": outcome,
        "duration_s": round(duration_s, 6),
        "reason": _redact(reason) if reason else None,
    }
    if contract_id is None:
        values.pop("contract_id")
    temporary.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    temporary.replace(receipt)
    return receipt


def _finish_runtime(
    run_dir: Path,
    config: UvRuntimeConfig,
    *,
    candidate_commit: str,
    contract_id: str | None,
    dependency_digest: str,
    started: float,
    outcome: Outcome,
    reason: str,
    attempts: int,
    cache_warm: bool,
    uv_version: str | None,
    secret_environment: Mapping[str, str] | None = None,
) -> CandidateRuntimeResult:
    redacted = _redact(reason, secret_environment)
    receipt = _write_receipt(
        run_dir,
        config,
        candidate_commit=candidate_commit,
        contract_id=contract_id,
        dependency_digest=dependency_digest,
        uv_version=uv_version,
        cache_warm=cache_warm,
        attempts=attempts,
        outcome=outcome.value,
        duration_s=time.monotonic() - started,
        reason=redacted,
    )
    return CandidateRuntimeResult(
        config.variant,
        config.project_relative,
        outcome=outcome,
        reason=redacted,
        receipt_path=receipt,
    )


def _finish_ready_runtime(
    run_dir: Path,
    config: UvRuntimeConfig,
    cache: Path,
    python_dir: Path,
    *,
    candidate_commit: str,
    contract_id: str | None,
    dependency_digest: str,
    started: float,
    attempts: int,
    cache_warm: bool,
    uv_version: str | None,
) -> CandidateRuntimeResult:
    receipt = _write_receipt(
        run_dir,
        config,
        candidate_commit=candidate_commit,
        contract_id=contract_id,
        dependency_digest=dependency_digest,
        uv_version=uv_version,
        cache_warm=cache_warm,
        attempts=attempts,
        outcome="ready",
        duration_s=time.monotonic() - started,
        reason=None,
    )
    return CandidateRuntimeResult(
        config.variant,
        config.project_relative,
        environment=(
            ("UV_CACHE_DIR", CONTAINER_UV_CACHE),
            ("UV_LINK_MODE", "copy"),
            ("UV_OFFLINE", "1"),
            ("UV_PYTHON", config.python),
            ("UV_PYTHON_INSTALL_DIR", CONTAINER_UV_PYTHON),
        ),
        mounts=(
            RuntimeMount(cache, CONTAINER_UV_CACHE),
            RuntimeMount(python_dir, CONTAINER_UV_PYTHON),
        ),
        receipt_path=receipt,
    )


def prepare_candidate_runtime(
    checkout: Path,
    run_dir: Path,
    runtime_root: Path,
    candidate_commit: str,
    evaluator: dict[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    contract_id: str | None = None,
) -> CandidateRuntimeResult:
    config = candidate_runtime_config(checkout, evaluator)
    if config is None:
        return CandidateRuntimeResult(None, None)

    values = clean_python_env(env)
    if values.get("EVAL_STUB") == "1":
        return CandidateRuntimeResult(None, None)

    started = time.monotonic()
    run_dir.mkdir(parents=True, exist_ok=True)
    project = config.project
    dependency_digest = candidate_dependency_digest(checkout, evaluator)
    assert dependency_digest is not None
    missing = [name for name in ("pyproject.toml", "uv.lock") if not (project / name).is_file()]
    if missing:
        return _finish_runtime(
            run_dir,
            config,
            candidate_commit=candidate_commit,
            contract_id=contract_id,
            dependency_digest=dependency_digest,
            started=started,
            outcome=Outcome.CANDIDATE_INVALID,
            reason=f"candidate uv project missing {', '.join(missing)}",
            attempts=0,
            cache_warm=False,
            uv_version=None,
        )

    cache = Path(values.get("EVOLVE_UV_CACHE_DIR") or runtime_root / "uv-cache").resolve()
    python_dir = Path(values.get("EVOLVE_UV_PYTHON_INSTALL_DIR") or runtime_root / "uv-python").resolve()
    temporary_environment = run_dir / ".candidate-runtime-venv"
    command_env = {
        **values,
        "UV_CACHE_DIR": str(cache),
        "UV_PYTHON": config.python,
        "UV_PYTHON_INSTALL_DIR": str(python_dir),
        "UV_PROJECT_ENVIRONMENT": str(temporary_environment),
    }
    try:
        uv = uv_executable(values)
        cache.mkdir(parents=True, exist_ok=True)
        python_dir.mkdir(parents=True, exist_ok=True)
        installed_python = run_owned(
            [uv, "python", "install", config.python],
            cwd=checkout,
            env=command_env,
        )
        if installed_python.returncode:
            return _finish_runtime(
                run_dir,
                config,
                candidate_commit=candidate_commit,
                contract_id=contract_id,
                dependency_digest=dependency_digest,
                started=started,
                outcome=Outcome.INFRASTRUCTURE_FAILED,
                reason=installed_python.stderr or installed_python.stdout or "uv managed Python preparation failed",
                attempts=0,
                cache_warm=False,
                uv_version=None,
                secret_environment=command_env,
            )
        _normalize_managed_python_links(python_dir)
        checked = run_owned(
            [uv, "lock", "--check", "--project", str(project)],
            cwd=checkout,
            env=command_env,
        )
        version = _uv_version(uv, checkout, command_env)
        if checked.returncode:
            return _finish_runtime(
                run_dir,
                config,
                candidate_commit=candidate_commit,
                contract_id=contract_id,
                dependency_digest=dependency_digest,
                started=started,
                outcome=Outcome.CANDIDATE_INVALID,
                reason=checked.stderr or checked.stdout or "uv lock --check failed",
                attempts=0,
                cache_warm=False,
                uv_version=version,
                secret_environment=command_env,
            )

        sync = [
            uv,
            "sync",
            "--project",
            str(project),
            "--frozen",
            "--no-install-local",
        ]
        offline = run_owned([*sync, "--offline"], cwd=checkout, env=command_env)
        cache_warm = offline.returncode == 0
        attempts = 1
        if not cache_warm:
            for attempt in (1, 2):
                attempts = attempt
                shutil.rmtree(temporary_environment, ignore_errors=True)
                online = run_owned(sync, cwd=checkout, env=command_env)
                if online.returncode == 0:
                    break
            else:
                return _finish_runtime(
                    run_dir,
                    config,
                    candidate_commit=candidate_commit,
                    contract_id=contract_id,
                    dependency_digest=dependency_digest,
                    started=started,
                    outcome=Outcome.INFRASTRUCTURE_FAILED,
                    reason=online.stderr or online.stdout or "uv dependency preparation failed",
                    attempts=2,
                    cache_warm=False,
                    uv_version=version,
                    secret_environment=command_env,
                )

        local_sync = [
            uv,
            "sync",
            "--project",
            str(project),
            "--frozen",
        ]
        shutil.rmtree(temporary_environment, ignore_errors=True)
        local = run_owned([*local_sync, "--offline"], cwd=checkout, env=command_env)
        if local.returncode:
            shutil.rmtree(temporary_environment, ignore_errors=True)
            local = run_owned(local_sync, cwd=checkout, env=command_env)
        if local.returncode:
            return _finish_runtime(
                run_dir,
                config,
                candidate_commit=candidate_commit,
                contract_id=contract_id,
                dependency_digest=dependency_digest,
                started=started,
                outcome=Outcome.CANDIDATE_INVALID,
                reason=local.stderr or local.stdout or "candidate local project build failed",
                attempts=attempts,
                cache_warm=cache_warm,
                uv_version=version,
                secret_environment=command_env,
            )

        return _finish_ready_runtime(
            run_dir,
            config,
            cache,
            python_dir,
            candidate_commit=candidate_commit,
            contract_id=contract_id,
            dependency_digest=dependency_digest,
            started=started,
            attempts=attempts,
            cache_warm=cache_warm,
            uv_version=version,
        )
    except Exception as error:
        return _finish_runtime(
            run_dir,
            config,
            candidate_commit=candidate_commit,
            contract_id=contract_id,
            dependency_digest=dependency_digest,
            started=started,
            outcome=Outcome.INFRASTRUCTURE_FAILED,
            reason=str(error) or type(error).__name__,
            attempts=0,
            cache_warm=False,
            uv_version=None,
            secret_environment=command_env,
        )
    finally:
        shutil.rmtree(temporary_environment, ignore_errors=True)
