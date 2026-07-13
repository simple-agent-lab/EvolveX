import json
import os
import stat
import subprocess
from pathlib import Path

from conftest import run_evolve, write_locked_miniswe_seed

from evolve.candidate_runtime import run_candidate_smoke, select_smoke_mode


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _smoke_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    write_locked_miniswe_seed(checkout / "target")
    _write_executable(
        checkout / "evaluator" / "eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR" "$EVOLVE_CANDIDATE_SMOKE_JOBS_DIR"\n'
        'printf "%s\\n" "$EVOLVE_CANDIDATE_SMOKE_MODE" > "$EVOLVE_RUN_DIR/mode"\n'
        'printf "%s\\n" "$EVOLVE_UV_CACHE_DIR" > "$EVOLVE_RUN_DIR/cache"\n'
        'printf "%s\\n" "$EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER" > "$EVOLVE_RUN_DIR/setup-timeout"\n'
        'printf \'{"schema_version":1,"status":"passed","owner":"none","category":"none","harbor_returncode":0,"trial_results_seen":1}\\n\' > "$EVOLVE_RUN_DIR/harbor-result.json"\n',
    )
    return checkout


def _run_parser(tmp_path: Path, result: dict[str, object] | None, harbor_rc: int = 0) -> subprocess.CompletedProcess[str]:
    jobs = tmp_path / "jobs"
    if result is not None:
        trial = jobs / "trial"
        trial.mkdir(parents=True)
        (trial / "result.json").write_text(json.dumps(result))
    output = tmp_path / "smoke.json"
    return subprocess.run(
        [
            os.environ.get("PYTHON", "python3"),
            "templates/evaluator/parse_smoke.py",
            str(jobs),
            str(output),
            str(harbor_rc),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_smoke_parser_classifies_explicit_candidate_failure(tmp_path: Path) -> None:
    result = {
        "exception_info": {
            "exception_type": "NonZeroAgentExitCodeError",
            "exception_message": "EVOLVE_CANDIDATE_INVALID: frozen_sync_failed",
        }
    }

    completed = _run_parser(tmp_path, result, harbor_rc=1)

    assert completed.returncode == 2
    payload = json.loads((tmp_path / "smoke.json").read_text())
    assert payload["status"] == "candidate_invalid"
    assert payload["category"] == "frozen_sync_failed"
    assert "exception_message" not in payload


def test_smoke_parser_does_not_guess_from_fastapi_traceback(tmp_path: Path) -> None:
    result = {
        "exception_info": {
            "exception_type": "NonZeroAgentExitCodeError",
            "exception_message": "ModuleNotFoundError: No module named 'fastapi'",
        }
    }

    completed = _run_parser(tmp_path, result, harbor_rc=1)

    assert completed.returncode == 3
    payload = json.loads((tmp_path / "smoke.json").read_text())
    assert payload == {
        "category": "setup_failed",
        "harbor_returncode": 1,
        "owner": "infrastructure",
        "schema_version": 1,
        "status": "infrastructure_failed",
        "trial_results_seen": 1,
    }


def test_quick_smoke_is_append_only_and_does_not_invoke_evaluator(tmp_path: Path) -> None:
    checkout = _smoke_checkout(tmp_path)
    (checkout / "evaluator" / "eval.sh").unlink()
    run_dir = tmp_path / "run"

    first = run_candidate_smoke(checkout, workspace=checkout, run_dir=run_dir, mode="quick")
    second = run_candidate_smoke(checkout, workspace=checkout, run_dir=run_dir, mode="quick")

    assert first.status == second.status == "passed"
    assert first.attempt_dir.name == "attempt-1"
    assert second.attempt_dir.name == "attempt-2"
    assert (first.attempt_dir / "result.json").is_file()


def test_quick_smoke_records_missing_lock_as_candidate_invalid(tmp_path: Path) -> None:
    checkout = _smoke_checkout(tmp_path)
    (checkout / "target" / "uv.lock").unlink()

    result = run_candidate_smoke(checkout, workspace=checkout, run_dir=tmp_path / "run", mode="quick")

    assert result.status == "candidate_invalid"
    payload = json.loads((result.attempt_dir / "result.json").read_text())
    assert payload["category"] == "lock_missing"
    assert payload["owner"] == "candidate"


def test_container_and_full_smoke_reuse_cache_and_write_sanitized_records(tmp_path: Path, monkeypatch) -> None:
    checkout = _smoke_checkout(tmp_path)
    run_dir = tmp_path / "run"
    sentinel = "must-not-appear-in-artifacts"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    monkeypatch.setenv("HTTPS_PROXY", sentinel)

    container = run_candidate_smoke(checkout, workspace=checkout, run_dir=run_dir, mode="container")
    full = run_candidate_smoke(checkout, workspace=checkout, run_dir=run_dir, mode="full")

    expected_cache = checkout / "runs" / "runtime" / "uv-cache"
    assert (container.attempt_dir / "mode").read_text() == "container\n"
    assert (full.attempt_dir / "mode").read_text() == "full\n"
    assert (container.attempt_dir / "cache").read_text() == f"{expected_cache}\n"
    assert (full.attempt_dir / "cache").read_text() == f"{expected_cache}\n"
    assert (container.attempt_dir / "setup-timeout").read_text() == "6\n"
    assert (full.attempt_dir / "setup-timeout").read_text() == "6\n"
    assert sentinel not in "".join(path.read_text() for path in run_dir.rglob("*") if path.is_file())
    materializations = list((checkout / "runs" / "runtime" / "candidates").glob("*/attempts/*.json"))
    assert len(materializations) == 2
    assert len({path.parents[1] for path in materializations}) == 1


def test_select_smoke_mode_defaults_to_full_and_rejects_combinations() -> None:
    assert select_smoke_mode(quick=False, container=False, full=False) == "full"
    assert select_smoke_mode(quick=True, container=False, full=False) == "quick"

    try:
        select_smoke_mode(quick=True, container=False, full=True)
    except ValueError as exc:
        assert str(exc) == "choose only one smoke mode"
    else:
        raise AssertionError("combined smoke modes were accepted")


def test_candidate_smoke_cli_prints_only_safe_summary(tmp_path: Path, monkeypatch) -> None:
    checkout = _smoke_checkout(tmp_path)
    sentinel = "secret-value-must-not-print"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    run_dir = tmp_path / "run"

    result = run_evolve(
        "candidate-smoke",
        "--quick",
        "--checkout",
        str(checkout),
        env={"EVOLVE_WORKSPACE": str(checkout), "EVOLVE_RUN_DIR": str(run_dir)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("candidate-smoke: passed mode=quick result=")
    assert sentinel not in result.stdout + result.stderr


def test_candidate_smoke_cli_returns_two_for_candidate_dependency_failure(tmp_path: Path) -> None:
    checkout = _smoke_checkout(tmp_path)
    (checkout / "target" / "uv.lock").unlink()

    result = run_evolve(
        "candidate-smoke",
        "--quick",
        "--checkout",
        str(checkout),
        env={"EVOLVE_WORKSPACE": str(checkout), "EVOLVE_RUN_DIR": str(tmp_path / "run")},
    )

    assert result.returncode == 2
    assert "candidate-smoke: candidate_invalid mode=quick" in result.stdout
