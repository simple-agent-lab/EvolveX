from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, run_evolve


def _rewrite_operator(workspace: Path, kind: str, source: str) -> None:
    path = workspace / "operators" / f"{kind}.py"
    path.write_text(source)
    git(workspace, "add", str(path.relative_to(workspace)))
    git(workspace, "commit", "-m", f"make {kind} output malformed")
    git(workspace, "tag", "-f", "gen/0")


def _run_one_generation(workspace: Path, evolve_home: Path) -> None:
    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr


def _assert_failed_row(workspace: Path, kind: str, file_name: str, field: str) -> None:
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "operator_failed"
    assert row["reason"] == f"operator {kind} failed"
    assert file_name in str(row["note"])
    assert field in str(row["note"])


def test_malformed_select_output_records_operator_failed_with_file_and_field(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _rewrite_operator(
        workspace,
        "select",
        "import json, os\n"
        "from pathlib import Path\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR'])\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "(run_dir / 'parents.json').write_text(json.dumps({'not_parents': ['0']}))\n",
    )

    _run_one_generation(workspace, evolve_home)

    _assert_failed_row(workspace, "select", "parents.json", "parents")
