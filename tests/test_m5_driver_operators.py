import json
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, run_evolve, smoke_env

from evolve.driver import RunOptions
from evolve.driver import run as driver_run

_REJECTING_VALIDATE = """
import os
import sys
sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]
from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class RejectingValidate(ValidateOperator):
    def validate(self, checkout, ctx):
        return ValidateResult(accept=False, reason="broken imports", artifacts=[])


if __name__ == "__main__":
    sdk.main(RejectingValidate)
"""


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    path = workspace / relative_path
    path.write_text(content)


def _commit_and_retag_gen0(workspace: Path, *paths: str) -> None:
    git(workspace, "add", *paths)
    git(workspace, "commit", "-m", "adjust gen 0 scaffolding")
    git(workspace, "tag", "-f", "gen/0")


def test_run_uses_operator_subprocesses_for_loop_steps(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    run_dir = workspace / "runs" / "gen-1"
    assert "written-by: operators/meta_agent.py" in (run_dir / "meta_agent" / "rationale.md").read_text()
    assert json.loads((run_dir / "gate.json").read_text())["verdict"] == "keep"
    row = rows_by_genid(workspace)["1"]
    assert row["reason"] == "score 1.0 >= parent 1.0"
    assert row["note"] == "variant: agent_command"


def test_run_records_operator_failed_when_meta_agent_operator_crashes(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", "raise SystemExit(1)\n")
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env=smoke_env(evolve_home),
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "operator_failed"
    assert row["valid_parent"] is False
    assert row["verdict"] == "discard"
    assert row["reason"] == "operator meta_agent failed"


def test_validate_rejection_happens_before_candidate_commit(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/validate.py", _REJECTING_VALIDATE)
    config = (workspace / "evolve.yaml").read_text().replace("  gate: {}\n", "  validate: {}\n  gate: {}\n")
    assert "  validate: {}\n" in config
    _rewrite(workspace, "evolve.yaml", config)
    _commit_and_retag_gen0(workspace, "operators/validate.py", "evolve.yaml")
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_env(evolve_home)["EVOLVE_AGENT_COMMAND"])

    driver_run(RunOptions(workspace=workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "rejected_validation"
    assert row["reason"] == "candidate validation rejected: broken imports"
    assert not git(workspace, "tag", "--list", "gen/1")
    assert json.loads((workspace / "runs/gen-1/validate/result.json").read_text())["accept"] is False
