import json
import shlex
import stat
from pathlib import Path

from conftest import git, run_evolve

from evolve.candidate_runtime import run_candidate_smoke
from evolve.config import default_config
from evolve.workspace import InitOptions, init_workspace


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


def test_smoke_attempts_are_append_only_generic_records(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, stdout="ordinary output\n")

    first = run_candidate_smoke(checkout, workspace=checkout)
    second = run_candidate_smoke(checkout, workspace=checkout)

    assert first.attempt_dir.name == "attempt-1"
    assert second.attempt_dir.name == "attempt-2"
    payload = json.loads((first.attempt_dir / "result.json").read_text())
    assert payload["status"] == "passed"
    assert payload["snapshot_tree"] == first.snapshot_tree
    assert payload["returncode"] == 0
    assert payload["stdout_path"] == str(first.stdout_path.resolve())
    assert payload["stderr_path"] == str(first.stderr_path.resolve())
    assert "owner" not in payload
    assert "category" not in payload
    assert "dependency_digest" not in payload


def test_smoke_redacts_secret_environment_values_but_preserves_traceback(
    tmp_path: Path, monkeypatch
) -> None:
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


def test_candidate_smoke_cli_requires_full_and_prints_bounded_stderr_tail(tmp_path: Path) -> None:
    stderr = "".join(f"diagnostic-{number}\n" for number in range(205))
    checkout = smoke_checkout(tmp_path, stderr=stderr, rc=7)

    result = run_evolve(
        "candidate-smoke",
        "--full",
        "--checkout",
        str(checkout),
        env={"EVOLVE_WORKSPACE": str(checkout)},
    )

    attempt = checkout / "runs" / "smoke" / "attempt-1"
    assert result.returncode == 2
    tail = result.stderr.splitlines()
    assert len(tail) == 200
    assert tail[0] == "diagnostic-5"
    assert tail[-1] == "diagnostic-204"
    assert str((attempt / "stdout.log").resolve()) in result.stdout
    assert str((attempt / "stderr.log").resolve()) in result.stdout
    assert str((attempt / "result.json").resolve()) in result.stdout

    unsupported_mode = run_evolve("candidate-smoke", "--quick", "--checkout", str(checkout))
    assert unsupported_mode.returncode != 0
    assert "No such option: --quick" in unsupported_mode.stderr

    missing_full = run_evolve("candidate-smoke", "--checkout", str(checkout))
    assert missing_full.returncode != 0


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
        'export EVOLVE_CANDIDATE_SMOKE_JOBS_DIR="$EVOLVE_RUN_DIR/jobs"\n'
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
    init_workspace(InitOptions(workspace=local, recipe="hill_climb-smoke"))

    assert not (local / "evaluator" / "smoke.sh").exists()


def test_init_protocol_documents_single_diagnostic_smoke_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "evolve-home"))
    workspace = tmp_path / "workspace"

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb-smoke"))

    protocol = (workspace / "PROTOCOL.md").read_text()
    assert protocol.count("./evolve candidate-smoke") == 1
    assert "`./evolve candidate-smoke --full`" in protocol
    assert "--quick" not in protocol
    assert "--container" not in protocol
    assert "Exit code 0 means passed, 2 means failed, and 3 means unsupported." in protocol
    assert "redacted stdout and stderr artifact paths" in protocol
    assert "Smoke diagnostics are not selection classifications" in protocol
