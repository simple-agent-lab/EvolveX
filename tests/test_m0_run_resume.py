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


def test_stub_run_produces_five_generation_lineage_and_mirror(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "5",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = assert_complete_lineage(workspace, 5)
    assert all(row["mutated"] == ["target/agent.py"] for row in rows[1:])
    assert git(workspace, "status", "--short").splitlines() == []
    assert git(workspace, "ls-files", "archive.jsonl") == ""

    mirror = evolve_home / "mirrors" / "experiment" / "archive.jsonl"
    mirror_rows = mechanism_merged_rows(mirror)
    assert [row["genid"] for row in mirror_rows] == [str(gen) for gen in range(6)]
    assert mirror.read_text() == (workspace / "archive.jsonl").read_text()


def test_resume_continues_from_last_complete_generation_without_duplicates(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr
    before = (workspace / "archive.jsonl").read_text().splitlines()

    second = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "5",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert second.returncode == 0, second.stderr
    rows = assert_complete_lineage(workspace, 5)
    assert [row["genid"] for row in rows].count("1") == 1
    assert [row["genid"] for row in rows].count("2") == 1
    after = (workspace / "archive.jsonl").read_text().splitlines()
    assert after[: len(before)] == before
