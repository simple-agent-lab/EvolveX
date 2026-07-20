import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import write_locked_miniswe_seed

from evolve import uv_runtime as uv_runtime_module
from evolve.evaluation import Outcome
from evolve.uv_runtime import candidate_runtime_config, prepare_candidate_runtime


def _fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "fake-uv"
    calls = tmp_path / "uv-calls.jsonl"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

calls = Path(os.environ["UV_CALLS"])
previous = calls.read_text().splitlines() if calls.exists() else []
with calls.open("a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args == ["--version"]:
    print("uv 0.test")
    raise SystemExit(0)
if args[:2] == ["lock", "--check"]:
    raise SystemExit(int(os.environ.get("UV_LOCK_RC", "0")))
if "sync" in args and "--offline" in args:
    raise SystemExit(int(os.environ.get("UV_OFFLINE_RC", "1")))
if "sync" in args:
    online_before = sum("sync" in json.loads(line) and "--offline" not in json.loads(line) for line in previous)
    results = [int(value) for value in os.environ.get("UV_ONLINE_RESULTS", "0").split(",")]
    result = results[min(online_before, len(results) - 1)]
    if result:
        print(os.environ.get("UV_ERROR", "sync failed"), file=sys.stderr)
    raise SystemExit(result)
raise SystemExit(2)
"""
    )
    executable.chmod(0o755)
    return executable, calls


def _runtime_fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object], dict[str, str], Path]:
    checkout = tmp_path / "checkout"
    project = checkout / "target"
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='candidate'\nversion='0'\n")
    (project / "uv.lock").write_text("version = 1\n")
    run_dir = tmp_path / "run"
    runtime_root = tmp_path / "runtime"
    executable, calls = _fake_uv(tmp_path)
    evaluator: dict[str, object] = {"candidate_runtime": {"variant": "uv", "project": "target"}}
    env = {
        **os.environ,
        "EVOLVE_UV_BINARY": str(executable),
        "UV_CALLS": str(calls),
    }
    return checkout, run_dir, runtime_root, evaluator, env, calls


def _prepare(tmp_path: Path, **env_overrides: str):
    checkout, run_dir, runtime_root, evaluator, env, calls = _runtime_fixture(tmp_path)
    env.update(env_overrides)
    result = prepare_candidate_runtime(
        checkout,
        run_dir,
        runtime_root,
        candidate_commit="abc123",
        evaluator=evaluator,
        env=env,
    )
    return result, run_dir, calls


def test_uv_runtime_prepares_cache_and_emits_offline_contract(tmp_path: Path) -> None:
    result, run_dir, _ = _prepare(tmp_path, UV_OFFLINE_RC="1", UV_ONLINE_RESULTS="0")

    assert result.ready
    assert dict(result.environment) == {
        "UV_CACHE_DIR": "/opt/evolve/uv/cache",
        "UV_LINK_MODE": "copy",
        "UV_OFFLINE": "1",
        "UV_PYTHON_INSTALL_DIR": "/opt/evolve/uv/python",
    }
    assert [mount.target for mount in result.mounts] == [
        "/opt/evolve/uv/cache",
        "/opt/evolve/uv/python",
    ]
    receipt = json.loads((run_dir / "candidate-runtime.json").read_text())
    assert receipt["variant"] == "uv"
    assert receipt["project"] == "target"
    assert receipt["candidate_commit"] == "abc123"
    assert receipt["outcome"] == "ready"
    assert receipt["attempts"] == 1
    assert not (run_dir / ".candidate-runtime-venv").exists()


def test_uv_runtime_warm_probe_avoids_online_sync(tmp_path: Path) -> None:
    result, _, calls = _prepare(tmp_path, UV_OFFLINE_RC="0", UV_ONLINE_RESULTS="1")

    assert result.ready
    invocations = [json.loads(line) for line in calls.read_text().splitlines()]
    assert not any("sync" in call and "--offline" not in call for call in invocations)


@pytest.mark.parametrize("missing", ["pyproject.toml", "uv.lock"])
def test_uv_runtime_rejects_missing_candidate_files_without_uv(tmp_path: Path, missing: str) -> None:
    checkout, run_dir, runtime_root, evaluator, env, calls = _runtime_fixture(tmp_path)
    (checkout / "target" / missing).unlink()

    result = prepare_candidate_runtime(
        checkout, run_dir, runtime_root, "abc123", evaluator, env=env
    )

    assert result.outcome is Outcome.CANDIDATE_INVALID
    assert not calls.exists()


def test_uv_runtime_rejects_invalid_lock_without_retry(tmp_path: Path) -> None:
    result, _, calls = _prepare(tmp_path, UV_LOCK_RC="1")

    assert result.outcome is Outcome.CANDIDATE_INVALID
    invocations = [json.loads(line) for line in calls.read_text().splitlines()]
    assert sum(call[:2] == ["lock", "--check"] for call in invocations) == 1
    assert not any("sync" in call for call in invocations)


def test_uv_runtime_retries_online_sync_twice_and_redacts_failure(tmp_path: Path) -> None:
    secret = "https://user:password@proxy.example/simple"
    result, run_dir, calls = _prepare(
        tmp_path,
        UV_OFFLINE_RC="1",
        UV_ONLINE_RESULTS="1,1",
        UV_ERROR=f"download failed via {secret}",
    )

    assert result.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert result.reason is not None and "user:password" not in result.reason
    invocations = [json.loads(line) for line in calls.read_text().splitlines()]
    assert sum("sync" in call and "--offline" not in call for call in invocations) == 2
    receipt_text = (run_dir / "candidate-runtime.json").read_text()
    assert "user:password" not in receipt_text
    assert "proxy.example" in receipt_text
    assert json.loads(receipt_text)["attempts"] == 2
    assert not (run_dir / ".candidate-runtime-venv").exists()


def test_uv_runtime_turns_uv_launch_error_into_redacted_infrastructure_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir, runtime_root, evaluator, env, _ = _runtime_fixture(tmp_path)
    secret = "Bearer very-secret-token"

    def fail_run(*args, **kwargs):
        raise OSError(f"launcher failed with {secret}")

    monkeypatch.setattr(uv_runtime_module, "run_owned", fail_run)
    result = prepare_candidate_runtime(
        checkout, run_dir, runtime_root, "abc123", evaluator, env=env
    )

    assert result.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert result.receipt_path == run_dir / "candidate-runtime.json"
    receipt = result.receipt_path.read_text()
    assert "very-secret-token" not in receipt
    assert "Bearer ***" in receipt


def test_uv_runtime_missing_uv_is_receipted_as_infrastructure_failure(
    tmp_path: Path,
) -> None:
    checkout, run_dir, runtime_root, evaluator, env, _ = _runtime_fixture(tmp_path)
    env["EVOLVE_UV_BINARY"] = str(tmp_path / "missing-uv")

    result = prepare_candidate_runtime(
        checkout, run_dir, runtime_root, "abc123", evaluator, env=env
    )

    assert result.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert result.receipt_path == run_dir / "candidate-runtime.json"
    receipt = json.loads(result.receipt_path.read_text())
    assert receipt["outcome"] == "infrastructure_failed"
    assert receipt["attempts"] == 0


@pytest.mark.parametrize(
    "message, secret",
    [
        ("https://token-only@proxy.example/simple", "token-only"),
        ("https://proxy.example/simple?token=query-secret", "query-secret"),
        ("Authorization: Bearer bearer-secret", "bearer-secret"),
    ],
)
def test_uv_runtime_receipt_redacts_common_credential_forms(
    tmp_path: Path, message: str, secret: str
) -> None:
    result, run_dir, _ = _prepare(
        tmp_path, UV_OFFLINE_RC="1", UV_ONLINE_RESULTS="1,1", UV_ERROR=message
    )

    assert result.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert secret not in (run_dir / "candidate-runtime.json").read_text()


def test_uv_runtime_config_resolves_project_inside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "target").mkdir(parents=True)

    config = candidate_runtime_config(
        checkout,
        {"candidate_runtime": {"variant": "uv", "project": "target"}},
    )

    assert config is not None
    assert config.variant == "uv"
    assert config.project == (checkout / "target").resolve()
    assert config.project_relative == "target"


@pytest.mark.parametrize(
    "value, message",
    [
        ("target", "candidate_runtime must be a mapping"),
        ({"variant": "pip", "project": "target"}, "unsupported candidate runtime variant"),
        ({"variant": "uv", "project": "../outside"}, "candidate runtime project escapes checkout"),
        ({"variant": "uv", "project": "/tmp/outside"}, "candidate runtime project must be relative"),
    ],
)
def test_uv_runtime_config_rejects_invalid_or_escaping_paths(
    tmp_path: Path, value: object, message: str
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    with pytest.raises(ValueError, match=message):
        candidate_runtime_config(checkout, {"candidate_runtime": value})


def test_missing_runtime_config_disables_preparation(tmp_path: Path) -> None:
    assert candidate_runtime_config(tmp_path, {}) is None


def test_frozen_project_can_rematerialize_offline_from_warm_cache(tmp_path: Path) -> None:
    project = write_locked_miniswe_seed(tmp_path / "project")
    cache = tmp_path / "uv-cache"
    env = {**os.environ, "UV_CACHE_DIR": str(cache)}
    command = [
        "uv",
        "sync",
        "--project",
        str(project),
        "--frozen",
        "--no-install-project",
        "--python",
        sys.executable,
    ]

    warm = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
    assert warm.returncode == 0, warm.stderr
    shutil.rmtree(project / ".venv")
    offline = subprocess.run([*command, "--offline"], env=env, text=True, capture_output=True, check=False)

    assert offline.returncode == 0, offline.stderr
    assert (project / ".venv" / "bin" / "python").is_file()
