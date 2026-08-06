from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .execution_runtime import RuntimeCheck
from .runtime import run_owned

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def contract_path(workspace: Path) -> Path:
    return workspace / "evaluator" / "doctor.json"


def has_contract(workspace: Path) -> bool:
    return contract_path(workspace).is_file()


def probe_evaluator_contract(workspace: Path, config: dict[str, object]) -> list[RuntimeCheck]:
    path = contract_path(workspace)
    if not path.is_file():
        return []
    try:
        contract = json.loads(path.read_text())
        _validate_contract(contract)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [RuntimeCheck("evaluator_contract", "fail", str(error), "fix evaluator/doctor.json")]

    checks = [RuntimeCheck("evaluator_contract", "pass", "evaluator/doctor.json schema is valid")]
    checks.append(_backend_check(config, contract))
    checks.extend(_task_checks(workspace, contract))
    checks.extend(_runtime_checks(workspace, config, contract))
    return checks


def _validate_contract(contract: object) -> None:
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("evaluator doctor contract must be a schema_version 1 object")
    backend = contract.get("backend")
    if backend not in {"local", "docker"}:
        raise ValueError("evaluator doctor backend must be local or docker")
    runtime = contract.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("evaluator doctor runtime must be an object")
    prepare = runtime.get("prepare")
    if not isinstance(prepare, str) or not prepare:
        raise ValueError("evaluator doctor runtime.prepare must be a non-empty relative path")
    _relative(prepare, "runtime.prepare")
    required_environment = runtime.get("required_environment", {})
    if not isinstance(required_environment, dict) or any(
        not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None or kind not in {"nonempty", "executable"}
        for name, kind in required_environment.items()
    ):
        raise ValueError("evaluator doctor required_environment entries must be nonempty or executable")
    smoke = contract.get("smoke")
    if smoke is not None:
        if not isinstance(smoke, dict):
            raise ValueError("evaluator doctor smoke must be an object")
        command = smoke.get("command")
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(item, str) or not item for item in command)
        ):
            raise ValueError("evaluator doctor smoke.command must be a list of non-empty strings")
    tasks = contract.get("tasks", {})
    if not isinstance(tasks, dict):
        raise ValueError("evaluator doctor tasks must be an object")
    required = tasks.get("required_files", [])
    digests = tasks.get("sha256", {})
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError("evaluator doctor tasks.required_files must be a list of relative paths")
    if not isinstance(digests, dict) or any(
        not isinstance(name, str) or not isinstance(digest, str) or not digest.startswith("sha256:")
        for name, digest in digests.items()
    ):
        raise ValueError("evaluator doctor tasks.sha256 must map relative paths to sha256 digests")
    for item in [*required, *digests]:
        _relative(str(item), "task asset")


def _relative(value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"evaluator doctor {label} must stay under its declared root: {value}")
    return path


def _backend_check(config: dict[str, object], contract: dict[str, Any]) -> RuntimeCheck:
    runtime = config.get("execution_runtime")
    configured = runtime.get("backend", "docker") if isinstance(runtime, dict) else "docker"
    evaluator = config.get("evaluator")
    environment = evaluator.get("environment") if isinstance(evaluator, dict) else None
    expected = contract["backend"]
    local_bound = isinstance(environment, str) and "localenvironment" in environment.lower()
    healthy = configured == expected and (expected != "local" or local_bound)
    detail = f"execution_runtime={configured}; evaluator.environment={environment or 'docker'}"
    return RuntimeCheck(
        "evaluator_backend_binding",
        "pass" if healthy else "fail",
        detail,
        None if healthy else "bind a local contract to execution_runtime.backend=local and Harbor LocalEnvironment",
    )


def _task_checks(workspace: Path, contract: dict[str, Any]) -> list[RuntimeCheck]:
    tasks = contract.get("tasks", {})
    required = [str(item) for item in tasks.get("required_files", [])]
    expected = {str(name): str(value) for name, value in tasks.get("sha256", {}).items()}
    try:
        split = json.loads((workspace / "evaluator" / "splits.json").read_text())
        dataset = Path(str(split["dataset"])).expanduser().resolve()
        names = sorted({str(name) for values in split["tasks"].values() for name in values})
        roots = _task_roots(dataset, names)
    except (OSError, KeyError, TypeError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [RuntimeCheck("evaluator_task_assets", "fail", str(error), "initialize a fresh frozen dataset")]
    failures: list[str] = []
    for name, root in roots.items():
        for relative in required:
            if not (root / relative).is_file():
                failures.append(f"{name}/{relative} is missing")
        for relative, digest in expected.items():
            path = root / relative
            if not path.is_file():
                failures.append(f"{name}/{relative} is missing")
            elif _sha256(path) != digest:
                failures.append(f"{name}/{relative} is stale")
    detail = f"{len(roots)} frozen tasks match the evaluator contract" if not failures else "; ".join(failures[:8])
    return [
        RuntimeCheck(
            "evaluator_task_assets",
            "pass" if not failures else "fail",
            detail,
            None if not failures else "rebuild the dataset and initialize a new workspace",
        )
    ]


def _task_roots(dataset: Path, names: list[str]) -> dict[str, Path]:
    if not dataset.is_dir():
        raise ValueError(f"frozen evaluator dataset does not exist: {dataset}")
    if (dataset / "task.toml").is_file():
        roots = {dataset.name: dataset}
    else:
        roots = {name: dataset / name for name in names}
    missing = [name for name, root in roots.items() if not (root / "task.toml").is_file()]
    if missing:
        raise ValueError(f"frozen evaluator tasks are missing: {', '.join(missing)}")
    return roots


def _runtime_checks(workspace: Path, config: dict[str, object], contract: dict[str, Any]) -> list[RuntimeCheck]:
    runtime = contract["runtime"]
    prepare = workspace / _relative(str(runtime["prepare"]), "runtime.prepare")
    if not prepare.is_file():
        return [RuntimeCheck("evaluator_runtime_prepare", "fail", f"missing runtime hook: {prepare}")]
    evaluator = config.get("evaluator")
    environment_name = evaluator.get("environment") if isinstance(evaluator, dict) else ""
    report_dir = workspace / "runs" / "doctor"
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="evaluator-", dir=report_dir) as temporary:
        root = Path(temporary)
        env_file = root / "runtime.env"
        environment = {
            **os.environ,
            "EVOLVE_DOCTOR_TEMP": str(root),
            "EVOLVE_EXECUTION_BACKEND": str(contract["backend"]),
            "EVOLVE_HARBOR_ENVIRONMENT": str(environment_name or ""),
            "EVOLVE_WORKSPACE": str(workspace),
        }
        result = run_owned(
            ["sh", str(prepare), str(root), str(env_file)],
            cwd=workspace,
            env=environment,
            timeout_s=float(runtime.get("timeout_s", 180)),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "runtime preparation failed").strip()[-1200:]
            return [RuntimeCheck("evaluator_runtime_prepare", "fail", detail, "fix the frozen local runtime hook")]
        try:
            values = _read_env(env_file)
        except (OSError, UnicodeError, ValueError) as error:
            return [RuntimeCheck("evaluator_runtime_environment", "fail", str(error))]
        checks = [RuntimeCheck("evaluator_runtime_prepare", "pass", "frozen runtime hook completed")]
        missing = _invalid_environment(values, runtime.get("required_environment", {}))
        checks.append(
            RuntimeCheck(
                "evaluator_runtime_environment",
                "pass" if not missing else "fail",
                "required runtime values are available" if not missing else "; ".join(missing),
                None if not missing else "repair or rebuild the pinned local evaluator runtime",
            )
        )
        smoke = contract.get("smoke")
        if not missing and isinstance(smoke, dict):
            checks.append(_smoke_check(workspace, root, environment | values, smoke))
        return checks


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line:
            continue
        name, separator, value = line.partition("=")
        if not separator or _ENV_NAME.fullmatch(name) is None or "\0" in value:
            raise ValueError("runtime hook wrote an invalid environment file")
        values[name] = value
    return values


def _invalid_environment(values: dict[str, str], required: object) -> list[str]:
    assert isinstance(required, dict)
    failures: list[str] = []
    for name, kind in required.items():
        value = values.get(str(name), "")
        if not value:
            failures.append(f"{name} is missing")
        elif kind == "executable" and (not Path(value).is_file() or not os.access(value, os.X_OK)):
            failures.append(f"{name} is not an executable file")
    return failures


def _smoke_check(workspace: Path, temporary: Path, environment: dict[str, str], smoke: dict[str, Any]) -> RuntimeCheck:
    result = run_owned(
        [str(item) for item in smoke["command"]],
        cwd=workspace,
        env=environment,
        timeout_s=float(smoke.get("timeout_s", 120)),
    )
    detail = "model-free evaluator smoke passed"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "evaluator smoke failed").strip()[-1200:]
    return RuntimeCheck(
        "evaluator_runtime_smoke",
        "pass" if result.returncode == 0 else "fail",
        detail,
        None if result.returncode == 0 else f"inspect the frozen runtime and smoke output under {temporary.parent}",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
