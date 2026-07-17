import json
import re
import shlex
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import git, run_evolve

from evolve import candidate_runtime as candidate_runtime_module
from evolve.candidate_runtime import run_candidate_smoke
from evolve.config import default_config
from evolve.workspace import InitOptions, init_workspace

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def smoke_checkout(
    tmp_path: Path,
    *,
    stdout: str = "",
    stderr: str = "",
    rc: int = 0,
    create_script: bool = True,
) -> Path:
    checkout = tmp_path / "checkout"
    (checkout / "target").mkdir(parents=True)
    (checkout / "target" / "candidate.txt").write_text("candidate\n")
    (checkout / ".gitignore").write_text("runs/\n")
    (checkout / "evolve.yaml").write_text("surface:\n  include: [target/**]\n  exclude: []\n")
    if create_script:
        _write_executable(
            checkout / "evaluator" / "smoke.sh",
            "#!/bin/sh\n"
            "set -eu\n"
            f"printf '%s' {shlex.quote(stdout)}\n"
            f"printf '%s' {shlex.quote(stderr)} >&2\n"
            f"exit {rc}\n",
        )
    git(checkout, "init", "-q")
    git(checkout, "config", "user.name", "test")
    git(checkout, "config", "user.email", "test@example.invalid")
    git(checkout, "add", ".")
    git(checkout, "commit", "-qm", "parent")
    return checkout


def test_smoke_exposes_missing_module_from_snapshot(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, stderr="ModuleNotFoundError: No module named 'fastapi'\n", rc=2)

    result = run_candidate_smoke(checkout, workspace=checkout)

    assert result.status == "failed"
    assert "No module named 'fastapi'" in result.stderr_path.read_text()


def test_smoke_runs_through_owned_process_helper(tmp_path: Path, monkeypatch) -> None:
    checkout = smoke_checkout(tmp_path)
    calls: list[tuple[list[str], dict[str, str]]] = []
    ticks = iter((10.0, 12.0))
    monkeypatch.setattr(candidate_runtime_module.time, "monotonic", lambda: next(ticks))

    def fake_run_owned(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_s: float | None = None,
    ) -> SimpleNamespace:
        calls.append((command, env))
        return SimpleNamespace(returncode=0, stdout="owned\n", stderr="", wall_s=0.01, timed_out=False)

    monkeypatch.setattr(candidate_runtime_module, "run_owned", fake_run_owned, raising=False)

    result = run_candidate_smoke(checkout, workspace=checkout)

    assert result.status == "passed"
    assert result.stdout_path.read_text() == "owned\n"
    assert json.loads((result.attempt_dir / "result.json").read_text())["duration_s"] == 2.0
    assert len(calls) == 1
    assert calls[0][1]["EVOLVE_ATTEMPT_ID"] == candidate_runtime_module.owned_attempt_id(
        checkout,
        result.attempt_dir,
    )


def test_smoke_redacts_proxy_credential_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@example.invalid:8080")
    checkout = smoke_checkout(tmp_path, stderr="http://user:secret@example.invalid:8080 fastapi\n", rc=2)

    text = run_candidate_smoke(checkout, workspace=checkout).stderr_path.read_text()

    assert "secret" not in text
    assert "fastapi" in text


def test_smoke_without_evaluator_script_is_unsupported(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, create_script=False)

    assert run_candidate_smoke(checkout, workspace=checkout).status == "unsupported"


def test_smoke_executes_uncommitted_snapshot_in_detached_checkout(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path)
    _write_executable(
        checkout / "evaluator" / "smoke.sh",
        "#!/bin/sh\nset -eu\nprintf '%s\\n' \"$PWD\"\ncat target/candidate.txt\n",
    )
    git(checkout, "add", "evaluator/smoke.sh")
    git(checkout, "commit", "--amend", "--no-edit", "-q")
    (checkout / "target" / "candidate.txt").write_text("uncommitted candidate\n")

    result = run_candidate_smoke(checkout, workspace=checkout)

    lines = result.stdout_path.read_text().splitlines()
    assert result.status == "passed"
    assert lines[0] != str(checkout)
    assert lines[1] == "uncommitted candidate"
    assert result.snapshot_tree == git(checkout, "rev-parse", f"{result.snapshot_tree}^{{tree}}")


def test_smoke_redacts_secret_environment_values_but_preserves_traceback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sensitive-value")
    checkout = smoke_checkout(
        tmp_path,
        stderr="token setup failed for sk-sensitive-value\nTraceback: useful frame 17\n",
        rc=1,
    )

    text = run_candidate_smoke(checkout, workspace=checkout).stderr_path.read_text()

    assert "sk-sensitive-value" not in text
    assert "token setup failed for [REDACTED]" in text
    assert "Traceback: useful frame 17" in text


def test_smoke_redacts_common_secret_forms_without_rewriting_diagnostics(tmp_path: Path) -> None:
    checkout = smoke_checkout(
        tmp_path,
        stderr="request failed for sk-standalone-secret token=standalone-token-value\nImportError: useful module\n",
        rc=1,
    )

    text = run_candidate_smoke(checkout, workspace=checkout).stderr_path.read_text()

    assert "sk-standalone-secret" not in text
    assert "standalone-token-value" not in text
    assert "request failed for [REDACTED] token=[REDACTED]" in text
    assert "ImportError: useful module" in text


def test_candidate_smoke_cli_returns_three_when_unsupported(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, create_script=False)

    result = run_evolve(
        "candidate-smoke",
        "--full",
        "--checkout",
        str(checkout),
        env={"EVOLVE_WORKSPACE": str(checkout)},
    )

    assert result.returncode == 3
    assert "candidate-smoke: unsupported" in result.stdout


def test_init_generates_executable_smoke_only_for_harbor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "evolve-home"))
    harbor = tmp_path / "harbor"
    init_workspace(InitOptions(workspace=harbor, recipe="hill_climb-smoke"))

    smoke = harbor / "evaluator" / "smoke.sh"
    assert smoke.read_text() == (
        "#!/bin/sh\n"
        "set -eu\n"
        ': "${EVOLVE_RUN_DIR:?EVOLVE_RUN_DIR is required}"\n'
        "export EVOLVE_CANDIDATE_SMOKE_MODE=full\n"
        "exec ./evaluator/eval.sh\n"
    )
    assert smoke.stat().st_mode & stat.S_IXUSR

    from evolve import workspace as workspace_module

    local_config = default_config("hill_climb-smoke", "local")
    assert isinstance(local_config["evaluator"], dict)
    local_config["evaluator"]["engine"] = "local"
    local_config["evaluator"].pop("agent", None)
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: local_config)
    local = tmp_path / "local"
    with pytest.raises(ValueError, match="unsupported evaluator.engine: local"):
        init_workspace(InitOptions(workspace=local, recipe="hill_climb-smoke"))

    assert not (local / "evaluator" / "smoke.sh").exists()
