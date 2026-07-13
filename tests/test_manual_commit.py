from pathlib import Path

from conftest import git, init_miniswe_workspace, init_workspace, rows_by_genid, run_evolve


def test_manual_commit_rejects_surface_violation_without_child_commit_or_tag(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    child = tmp_path / "child"

    fork = run_evolve("fork", str(workspace), "0", str(child), env={"EVOLVE_HOME": str(evolve_home)})
    assert fork.returncode == 0, fork.stderr
    parent_commit = git(workspace, "rev-parse", "gen/0")

    (child / "README.md").write_text("out of surface\n")

    result = run_evolve(
        "commit",
        str(workspace),
        str(child),
        "--parent",
        "0",
        "--genid",
        "1",
        env={"EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "invalid_proposal"
    assert row["valid_parent"] is False
    assert row["mutated"] == ["README.md"]
    assert row["surface_violations"] == ["README.md"]
    assert git(workspace, "tag", "--list", "gen/1") == ""
    assert git(child, "rev-parse", "HEAD") == parent_commit


def test_manual_commit_rejects_project_change_without_lock_update(tmp_path: Path) -> None:
    workspace, evolve_home = init_miniswe_workspace(tmp_path)
    child = tmp_path / "child"
    fork = run_evolve("fork", str(workspace), "0", str(child), env={"EVOLVE_HOME": str(evolve_home)})
    assert fork.returncode == 0, fork.stderr
    project = child / "target" / "pyproject.toml"
    project.write_text(project.read_text() + "\n# dependency metadata changed\n")

    result = run_evolve(
        "commit",
        str(workspace),
        str(child),
        "--parent",
        "0",
        "--genid",
        "1",
        env={"EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "invalid_proposal"
    assert row["reason"] == "candidate dependency invalid: project_changed_without_lock"
    assert git(workspace, "tag", "--list", "gen/1") == ""
