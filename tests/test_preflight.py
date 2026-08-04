import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import allow_local_runtime, git, init_recipe_with_local_inputs

from evolve import preflight as preflight_module
from evolve.candidate.smoke import SmokeResult
from evolve.preflight import (
    PreflightCheckStatus,
    PreflightFailureCategory,
    PreflightMode,
    PreflightResultV1,
    PreflightStatus,
    run_preflight,
)


def runtime_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "OPENAI_API_KEY": "test-key-not-a-secret",
        "OPENAI_BASE_URL": "https://model.example/v1",
    }


def snapshot(root: Path) -> tuple[tuple[str, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        (path.relative_to(root).as_posix(), path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def retag_gen0(workspace: Path, message: str) -> None:
    git(workspace, "add", "-A")
    git(workspace, "commit", "-m", message)
    git(workspace, "tag", "-f", "gen/0")


def passed_smoke(attempt: Path) -> SmokeResult:
    attempt.mkdir(parents=True)
    stdout = attempt / "stdout.log"
    stderr = attempt / "stderr.log"
    stdout.write_text("model response received\n")
    stderr.write_text("")
    (attempt / "result.json").write_text('{"schema_version": 1, "status": "passed"}\n')
    return SmokeResult("passed", attempt, "a" * 40, 0, stdout, stderr)


def test_ordinary_preflight_is_typed_atomic_and_non_mutating(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before_tree = git(strict_workspace, "write-tree")
    before_cache = snapshot(strict_workspace / "runs/runtime")
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.status is PreflightStatus.PASSED
    assert result.mode is PreflightMode.ORDINARY
    assert result.receipt_path is not None
    payload = json.loads(result.receipt_path.read_text())
    assert payload["profile_name"] == "harbor-bytedance-v1"
    assert payload["status"] == "passed"
    assert "receipt_path" not in payload
    assert git(strict_workspace, "write-tree") == before_tree
    assert snapshot(strict_workspace / "runs/runtime") == before_cache
    assert not result.receipt_path.with_suffix(".json.tmp").exists()


def test_default_receipts_use_monotonic_attempt_directories(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow_local_runtime(monkeypatch)

    first = run_preflight(strict_workspace, environment=runtime_environment())
    second = run_preflight(strict_workspace, environment=runtime_environment())

    assert first.receipt_path is not None
    assert second.receipt_path is not None
    assert first.receipt_path.parent.name == "attempt-1"
    assert second.receipt_path.parent.name == "attempt-2"


def test_smoke_runs_ordinary_checks_then_one_model_agent_request(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []
    allow_local_runtime(monkeypatch)
    smoke = passed_smoke(strict_workspace / "runs" / "smoke" / "attempt-99")

    def fake_smoke(*args, **kwargs):
        del args
        calls.append((kwargs["mode"].value, dict(kwargs["environment"])))
        return smoke

    monkeypatch.setattr(preflight_module, "run_candidate_smoke", fake_smoke, raising=False)

    result = run_preflight(
        strict_workspace,
        mode=PreflightMode.SMOKE,
        environment=runtime_environment(),
    )

    assert calls == [("model", runtime_environment())]
    assert result.checks[0].name == "configuration"
    assert result.checks[-1].name == "model_agent_request"
    assert result.checks[-1].artifact is not None
    assert result.checks[-1].artifact.path == "runs/smoke/attempt-99/result.json"
    assert result.status is PreflightStatus.PASSED


def test_smoke_preserves_structured_network_failure_category(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow_local_runtime(monkeypatch)
    smoke = passed_smoke(strict_workspace / "runs" / "smoke" / "attempt-98")
    (smoke.attempt_dir / "result.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "failed",
                "failure_category": "network_unavailable",
            }
        )
        + "\n"
    )
    failed = SmokeResult(
        "failed",
        smoke.attempt_dir,
        smoke.snapshot_tree,
        1,
        smoke.stdout_path,
        smoke.stderr_path,
    )
    monkeypatch.setattr(preflight_module, "run_candidate_smoke", lambda *args, **kwargs: failed)

    result = run_preflight(
        strict_workspace,
        mode=PreflightMode.SMOKE,
        environment=runtime_environment(),
    )

    assert result.status is PreflightStatus.FAILED
    assert result.failure_category is PreflightFailureCategory.NETWORK_UNAVAILABLE
    assert result.checks[-1].artifact is not None


def test_configuration_failure_writes_typed_receipt(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (strict_workspace / "evolve.yaml").write_text("experiment: [invalid\n")
    retag_gen0(strict_workspace, "invalidate configuration")
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.status is PreflightStatus.FAILED
    assert result.failure_category is PreflightFailureCategory.CONFIGURATION_INVALID
    assert result.checks[-1].name == "configuration"
    assert result.checks[-1].status is PreflightCheckStatus.FAILED
    assert result.receipt_path is not None and result.receipt_path.is_file()


def test_invalid_profile_fails_before_contract(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (strict_workspace / "evaluator/runtime-profile.json").write_text("{}\n")
    retag_gen0(strict_workspace, "invalidate runtime profile")
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.failure_category is PreflightFailureCategory.RUNTIME_PROFILE_INVALID
    assert [check.name for check in result.checks] == ["configuration", "runtime_profile"]


def test_runtime_pin_mismatch_is_runtime_unavailable(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (strict_workspace / "evaluator/runtime.pin").write_text("sha256:different\n")
    retag_gen0(strict_workspace, "invalidate runtime pin")
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.failure_category is PreflightFailureCategory.RUNTIME_UNAVAILABLE
    assert result.checks[-1].name == "runtime_digest"


def test_missing_dependency_tool_is_classified(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight_module, "_tool_available", lambda name, env: name != "docker")
    monkeypatch.setattr(preflight_module, "_image_available", lambda digest, env: True)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.failure_category is PreflightFailureCategory.DEPENDENCY_TOOL_UNAVAILABLE
    assert "docker" in (result.failure_message or "")


def test_unavailable_image_does_not_pull(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight_module, "_tool_available", lambda name, env: True)
    monkeypatch.setattr(preflight_module, "_image_available", lambda digest, env: False)

    result = run_preflight(strict_workspace, environment=runtime_environment())

    assert result.failure_category is PreflightFailureCategory.CONTAINER_IMAGE_UNAVAILABLE
    assert result.checks[-1].name == "container_image"


def test_invalid_uv_lock_is_classified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, "ahe")
    (workspace / "target/uv.lock").write_text("not valid TOML = [\n")
    retag_gen0(workspace, "invalidate candidate lock")
    allow_local_runtime(monkeypatch)

    result = run_preflight(workspace, environment=runtime_environment())

    assert result.failure_category is PreflightFailureCategory.DEPENDENCY_LOCK_INVALID
    assert result.checks[-1].name == "dependency_lock"


def test_uv_lock_validation_is_explicitly_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "target"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'target'\nversion = '0'\n")
    (project / "uv.lock").write_text("version = 1\nrevision = 1\n")
    commands: list[list[str]] = []
    timeouts: list[object] = []

    monkeypatch.setattr(preflight_module, "uv_executable", lambda environment: "uv")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        timeouts.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(preflight_module.subprocess, "run", run)

    assert preflight_module._lock_valid(project, runtime_environment())
    assert commands == [
        ["uv", "lock", "--offline", "--check", "--project", str(project)]
    ]
    assert timeouts == [30]


def test_local_capability_timeout_is_a_failed_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight_module.shutil, "which", lambda name, path: "/usr/bin/docker")
    monkeypatch.setattr(
        preflight_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd=args[0], timeout=30)
        ),
    )

    assert not preflight_module._image_available("sha256:runtime", runtime_environment())


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_BASE_URL"])
def test_missing_credentials_are_classified(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    environment = runtime_environment()
    environment.pop(missing)
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=environment)

    assert result.failure_category is PreflightFailureCategory.CREDENTIAL_MISSING
    assert missing in (result.failure_message or "")


def test_forbidden_credential_is_classified_without_value(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = runtime_environment()
    environment["CODEX_FORCE_AUTH_JSON"] = "forbidden-literal"
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=environment)

    assert result.failure_category is PreflightFailureCategory.CREDENTIAL_FORBIDDEN
    assert "forbidden-literal" not in json.dumps(result.to_dict())


@pytest.mark.parametrize(
    "endpoint",
    ["not-a-url", "https://other.example/v1"],
)
def test_invalid_or_mismatched_endpoint_is_classified_and_redacted(
    strict_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    environment = runtime_environment()
    environment["OPENAI_BASE_URL"] = endpoint
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=environment)

    assert result.failure_category is PreflightFailureCategory.ENDPOINT_INVALID
    assert endpoint not in json.dumps(result.to_dict())


@pytest.mark.parametrize(
    "category",
    [
        PreflightFailureCategory.NETWORK_UNAVAILABLE,
        PreflightFailureCategory.MODEL_SMOKE_FAILED,
    ],
)
def test_future_smoke_failure_categories_use_the_predefined_receipt(
    tmp_path: Path, category: PreflightFailureCategory
) -> None:
    receipt = tmp_path / "preflight.json"
    result = PreflightResultV1.failed(
        mode=PreflightMode.SMOKE,
        profile_name="harbor-bytedance-v1",
        profile_digest="a" * 64,
        runtime_digest="sha256:runtime",
        model_route_digest="b" * 64,
        checks=(),
        category=category,
        message="bounded failure",
        receipt_path=receipt,
    )

    assert result.write() == receipt
    assert json.loads(receipt.read_text())["failure_category"] == category.value


def test_receipt_never_persists_secret_endpoint_or_proxy_literals(
    strict_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = runtime_environment()
    environment.update(
        {
            "OPENAI_API_KEY": "canary-sensitive-key",
            "HTTPS_PROXY": "http://proxy-user:proxy-password@proxy.example:8118",
            "NO_PROXY": "pypi.org",
        }
    )
    allow_local_runtime(monkeypatch)

    result = run_preflight(strict_workspace, environment=environment)

    assert result.receipt_path is not None
    serialized = result.receipt_path.read_text()
    for literal in (
        environment["OPENAI_API_KEY"],
        environment["OPENAI_BASE_URL"],
        environment["HTTPS_PROXY"],
        "model.example",
        "proxy-password",
    ):
        assert literal not in serialized
