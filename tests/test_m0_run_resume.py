from pathlib import Path

from conftest import git, init_workspace, run_evolve

from evolve.archive import merged_rows as mechanism_merged_rows


def assert_complete_lineage(
    workspace: Path,
    max_gen: int,
    *,
    require_valid_parents: bool = True,
) -> list[dict[str, object]]:
    rows = mechanism_merged_rows(workspace / "archive.jsonl")
    assert [row["genid"] for row in rows] == [str(gen) for gen in range(max_gen + 1)]
    assert all(row["status"] == "complete" for row in rows)
    if require_valid_parents:
        assert all(row["valid_parent"] is True for row in rows)
    for gen in range(max_gen + 1):
        assert git(workspace, "tag", "--list", f"gen/{gen}") == f"gen/{gen}"
        assert git(workspace, "rev-parse", f"gen/{gen}^{{commit}}")
    return rows


def test_stub_run_produces_lineage_and_mirror(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = assert_complete_lineage(workspace, 1)
    assert all(row["mutated"] == ["target/agent.py"] for row in rows[1:])
    assert git(workspace, "status", "--short").splitlines() == []
    assert git(workspace, "ls-files", "archive.jsonl") == ""

    mirror = evolve_home / "mirrors" / "experiment" / "archive.jsonl"
    mirror_rows = mechanism_merged_rows(mirror)
    assert [row["genid"] for row in mirror_rows] == ["0", "1"]
    assert mirror.read_text() == (workspace / "archive.jsonl").read_text()
