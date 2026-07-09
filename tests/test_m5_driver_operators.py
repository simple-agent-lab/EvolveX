import json
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, run_evolve


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
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    run_dir = workspace / "runs" / "gen-1"
    assert "written-by: operators/meta_agent.py" in (run_dir / "meta_agent" / "rationale.md").read_text()
    assert json.loads((run_dir / "gate.json").read_text())["verdict"] == "keep"
    assert (run_dir / "feedback" / "index.md").exists()
    row = rows_by_genid(workspace)["1"]
    assert row["reason"] == "score 1.0 >= parent 1.0"
    assert row["note"] == "variant: fixed"


def test_run_records_operator_failed_when_meta_agent_operator_crashes(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite(workspace, "operators/meta_agent.py", "raise SystemExit(1)\n")
    _commit_and_retag_gen0(workspace, "operators/meta_agent.py")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "operator_failed"
    assert row["valid_parent"] is False
    assert row["verdict"] == "discard"
    assert row["reason"] == "operator meta_agent failed"
