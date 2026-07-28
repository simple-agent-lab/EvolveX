import os
from pathlib import Path

import pytest
from conftest import init_workspace

from evolve.driver import RunOptions, doctor, run, workspace_run_lock
from evolve.git import add_worktree


def test_driver_rejects_a_second_run_for_the_same_workspace(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)

    with workspace_run_lock(workspace):
        with pytest.raises(RuntimeError, match="another evolve run already owns workspace"):
            run(RunOptions(workspace=workspace, max_generations=0))


def test_stale_driver_lock_file_does_not_block_a_new_run(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    lock_path = workspace / "runs" / ".driver.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999\n")

    with workspace_run_lock(workspace):
        assert lock_path.read_text() == f"{os.getpid()}\n"


def test_doctor_refuses_lock_contention_without_removing_active_worktree(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    active = workspace / "runs" / "worktrees" / "active"
    add_worktree(workspace, active, "gen/0")
    sentinel = active / "active-sentinel"
    sentinel.write_text("owned by the active run\n")

    with workspace_run_lock(workspace):
        with pytest.raises(RuntimeError, match="another evolve run already owns workspace"):
            doctor(workspace)
        assert sentinel.read_text() == "owned by the active run\n"

    assert doctor(workspace) == ["removed stale worktree active"]
    assert not active.exists()
