from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .config import load_config
from .evaluator_doctor import has_contract, probe_evaluator_contract
from .execution_runtime import (
    ExecutionRuntimeProbeReport,
    RuntimeCheck,
    execution_runtime_config,
    probe_execution_runtime,
    resolve_execution_runtime,
)
from .execution_runtime.models import ExecutionBackend
from .population import fixed_evaluation_identity
from .runtime import run_owned

DoctorProfile = Literal["local", "experiment"]


@dataclass(frozen=True)
class DoctorReport:
    schema_version: int
    profile: DoctorProfile
    root: str
    checks: tuple[RuntimeCheck, ...]
    execution_runtime: dict[str, object]
    report_path: Path

    @property
    def healthy(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "root": self.root,
            "checks": [asdict(check) for check in self.checks],
            "execution_runtime": self.execution_runtime,
            "healthy": self.healthy,
        }


def _codex_checks(root: Path, *, required: bool, probe_model: bool) -> list[RuntimeCheck]:
    executable = shutil.which("codex")
    if not executable:
        status = "fail" if required else "warn"
        return [RuntimeCheck("codex_cli", status, "codex is not installed", "install Codex CLI")]
    checks = [RuntimeCheck("codex_cli", "pass", executable)]
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    auth_path = Path(os.environ.get("CODEX_AUTH_JSON_PATH") or codex_home / "auth.json")
    checks.append(
        RuntimeCheck(
            "codex_auth",
            "pass" if auth_path.is_file() else ("fail" if required else "warn"),
            "Codex login state is available" if auth_path.is_file() else "Codex auth.json is unavailable",
            None if auth_path.is_file() else "run `codex login`",
        )
    )
    if probe_model and auth_path.is_file():
        result = run_owned(
            [executable, "exec", "--skip-git-repo-check", "--json", "--", "Reply with EVOLVE_DOCTOR_OK."],
            cwd=root,
            env=dict(os.environ),
            timeout_s=120,
        )
        checks.append(
            RuntimeCheck(
                "codex_model",
                "pass" if result.returncode == 0 else "fail",
                "model probe completed"
                if result.returncode == 0
                else (result.stderr or result.stdout or "Codex model probe failed").strip()[-1000:],
                None if result.returncode == 0 else "verify the Codex login, model access, and network",
            )
        )
    elif required:
        checks.append(RuntimeCheck("codex_model", "warn", "model access was not probed; pass --probe-model"))
    return checks


def _plugin_checks(root: Path) -> list[RuntimeCheck]:
    manifests = sorted(
        manifest
        for base in (root, root / "target")
        for plugins in (base / "plugins", base / ".codex" / "plugins")
        for manifest in plugins.glob("*/.codex-plugin/plugin.json")
    )
    if not manifests:
        return [RuntimeCheck("plugin_layout", "warn", "no local Codex plugin was found")]
    checks: list[RuntimeCheck] = []
    for manifest in manifests:
        try:
            payload = json.loads(manifest.read_text())
            valid = isinstance(payload, dict) and isinstance(payload.get("name"), str) and bool(payload["name"])
        except (OSError, UnicodeError, json.JSONDecodeError):
            valid = False
        checks.append(
            RuntimeCheck(
                "plugin_layout",
                "pass" if valid else "fail",
                str(manifest.relative_to(root)),
                None if valid else "fix the Codex plugin manifest",
            )
        )
        hooks = manifest.parent.parent / "hooks" / "hooks.json"
        if hooks.exists():
            try:
                hooks_payload = json.loads(hooks.read_text())
                hooks_valid = isinstance(hooks_payload, dict) and isinstance(hooks_payload.get("hooks"), dict)
            except (OSError, UnicodeError, json.JSONDecodeError):
                hooks_valid = False
            checks.append(
                RuntimeCheck(
                    "plugin_hooks",
                    "pass" if hooks_valid else "fail",
                    str(hooks.relative_to(root)),
                    None if hooks_valid else "fix hooks/hooks.json",
                )
            )
    return checks


def _experiment_checks(root: Path, config: dict[str, object]) -> list[RuntimeCheck]:
    checks: list[RuntimeCheck] = []
    identity = fixed_evaluation_identity(root)
    checks.append(
        RuntimeCheck(
            "evaluation_identity",
            "pass" if identity is not None else "fail",
            "fixed evaluator/task/runtime identity is available"
            if identity is not None
            else "fixed evaluation identity is unavailable",
            None if identity is not None else "initialize a new workspace with a resolved v2 split manifest",
        )
    )
    split_path = root / "evaluator" / "splits.json"
    try:
        split = json.loads(split_path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError):
        split = None
    digests = split.get("task_digests") if isinstance(split, dict) else None
    checks.append(
        RuntimeCheck(
            "dataset_manifest",
            "pass" if isinstance(digests, dict) and bool(digests) else "fail",
            "task content digests are frozen" if isinstance(digests, dict) and digests else "task digests are missing",
            None if isinstance(digests, dict) and digests else "materialize the dataset and initialize a new workspace",
        )
    )
    runtime_pin = root / "evaluator" / "runtime.pin"
    checks.append(
        RuntimeCheck(
            "runtime_pin",
            "pass" if runtime_pin.is_file() and bool(runtime_pin.read_text().strip()) else "fail",
            "runtime.pin is present" if runtime_pin.is_file() else "runtime.pin is missing",
        )
    )
    return checks


def _backend(config: dict[str, object]) -> ExecutionBackend:
    evaluator = config.get("evaluator")
    environment = evaluator.get("environment") if isinstance(evaluator, dict) else None
    value = str(environment or "docker").lower()
    return "local" if "localenvironment" in value or value == "evolve-local" else "docker"


def _codex_required(config: dict[str, object]) -> bool:
    return "codex" in json.dumps(config, sort_keys=True).lower()


def run_doctor(
    root: Path,
    *,
    profile: DoctorProfile,
    probe_model: bool = False,
) -> DoctorReport:
    root = root.expanduser().resolve()
    checks: list[RuntimeCheck] = []
    if not root.is_dir():
        raise ValueError(f"doctor root does not exist: {root}")
    config_path = root / "evolve.yaml"
    config = load_config(config_path) if config_path.is_file() else {}
    if profile == "experiment" and not config:
        raise ValueError("experiment doctor requires an initialized EvolveX workspace")

    report_dir = root / "runs" / "doctor"
    report_dir.mkdir(parents=True, exist_ok=True)

    backend = "local" if profile == "local" else _backend(config)
    runtime_values = config.get("execution_runtime") if profile == "experiment" else {"minimum_free_gib": 1}
    runtime_config = execution_runtime_config(runtime_values, default_backend=backend)
    runtime = resolve_execution_runtime(runtime_config)
    runtime_report: ExecutionRuntimeProbeReport = probe_execution_runtime(runtime, workspace=root)
    checks.extend(runtime_report.checks)
    checks.extend(_codex_checks(root, required=profile == "local" or _codex_required(config), probe_model=probe_model))
    checks.extend(_plugin_checks(root))
    if profile == "experiment":
        checks.extend(_experiment_checks(root, config))
        checks.extend(probe_evaluator_contract(root, config))

    report_path = report_dir / f"{profile}-latest.json"
    report = DoctorReport(
        schema_version=1,
        profile=profile,
        root=str(root),
        checks=tuple(checks),
        execution_runtime=runtime_report.to_dict(),
        report_path=report_path,
    )
    temporary = report_path.with_name(f".{report_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
    temporary.replace(report_path)
    return report


def ensure_evaluator_ready(root: Path) -> DoctorReport | None:
    """Fail before rollout when an opt-in frozen evaluator contract is unhealthy."""
    root = root.expanduser().resolve()
    if not has_contract(root):
        return None
    report = run_doctor(root, profile="experiment")
    failures = [check for check in report.checks if check.status == "fail"]
    if failures:
        summary = "; ".join(f"{check.name}: {check.detail}" for check in failures[:5])
        raise RuntimeError(f"evaluator doctor failed before rollout: {summary}; report: {report.report_path}")
    return report
