from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from evolve import driver, orchestration
from evolve.driver import RunOptions
from evolve.evaluator_doctor import probe_evaluator_contract


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _workspace(tmp_path: Path, *, stale: bool = False, local_environment: bool = True) -> tuple[Path, dict]:
    workspace = tmp_path / "workspace"
    evaluator = workspace / "evaluator"
    task = tmp_path / "dataset" / "task-a"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    evaluator.mkdir(parents=True)
    (workspace / "runs").mkdir()
    (task / "task.toml").write_text('version = "1.0"\n')
    (task / "environment" / "paper.txt").write_text("paper")
    frozen = b"current evaluator"
    (task / "tests" / "evaluate.py").write_bytes(b"stale evaluator" if stale else frozen)
    (evaluator / "splits.json").write_text(
        json.dumps(
            {
                "dataset": str(task.parent),
                "tasks": {"train": ["task-a"], "gate": [], "sealed": []},
            }
        )
    )
    executable = workspace / "renderer"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    prepare = evaluator / "prepare-runtime.sh"
    prepare.write_text(f"#!/bin/sh\nset -eu\nprintf 'RENDERER={executable}\\nDIGEST=sha256:test\\n' > \"$2\"\n")
    smoke = evaluator / "smoke.py"
    smoke.write_text("import os\nassert os.environ['DIGEST'] == 'sha256:test'\n")
    (evaluator / "doctor.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": "local",
                "runtime": {
                    "prepare": "evaluator/prepare-runtime.sh",
                    "required_environment": {"RENDERER": "executable", "DIGEST": "nonempty"},
                },
                "tasks": {
                    "required_files": ["environment/paper.txt"],
                    "sha256": {"tests/evaluate.py": _sha256(frozen)},
                },
                "smoke": {"command": ["python3", "evaluator/smoke.py"]},
            }
        )
    )
    config = {
        "execution_runtime": {"backend": "local"},
        "evaluator": {"environment": "evolve.harbor_local:LocalEnvironment" if local_environment else "docker"},
    }
    return workspace, config


def test_evaluator_doctor_checks_local_runtime_tasks_and_model_free_smoke(tmp_path: Path) -> None:
    workspace, config = _workspace(tmp_path)

    checks = probe_evaluator_contract(workspace, config)

    assert {check.name: check.status for check in checks} == {
        "evaluator_contract": "pass",
        "evaluator_backend_binding": "pass",
        "evaluator_task_assets": "pass",
        "evaluator_runtime_prepare": "pass",
        "evaluator_runtime_environment": "pass",
        "evaluator_runtime_smoke": "pass",
    }


def test_evaluator_doctor_rejects_stale_dataset_asset_before_rollout(tmp_path: Path) -> None:
    workspace, config = _workspace(tmp_path, stale=True)

    checks = probe_evaluator_contract(workspace, config)

    task_check = next(check for check in checks if check.name == "evaluator_task_assets")
    assert task_check.status == "fail"
    assert "tests/evaluate.py is stale" in task_check.detail


def test_evaluator_doctor_rejects_implicit_docker_fallback(tmp_path: Path) -> None:
    workspace, config = _workspace(tmp_path, local_environment=False)

    checks = probe_evaluator_contract(workspace, config)

    backend = next(check for check in checks if check.name == "evaluator_backend_binding")
    assert backend.status == "fail"
    assert "evaluator.environment=docker" in backend.detail


def test_driver_runs_opt_in_evaluator_doctor_before_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(driver, "ensure_evaluator_ready", lambda workspace: calls.append(f"doctor:{workspace}"))
    monkeypatch.setattr(driver, "workspace_run_lock", lambda _workspace: nullcontext())
    monkeypatch.setattr(driver, "_run_locked", lambda _options, workspace: calls.append(f"run:{workspace}"))

    driver.run(RunOptions(workspace=tmp_path, max_generations=0))

    assert calls == [f"doctor:{tmp_path}", f"run:{tmp_path}"]


def test_outer_agent_eval_runs_opt_in_evaluator_doctor_before_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(orchestration, "ensure_evaluator_ready", lambda workspace: calls.append(f"doctor:{workspace}"))
    monkeypatch.setattr(orchestration, "workspace_run_lock", lambda _workspace: nullcontext())
    monkeypatch.setattr(
        orchestration, "eval_child", lambda workspace, _genid, force=False: calls.append(f"eval:{workspace}")
    )

    orchestration.eval_agent_child(tmp_path, "0")

    assert calls == [f"doctor:{tmp_path}", f"eval:{tmp_path}"]
