import os
from pathlib import Path

import pytest
from conftest import init_workspace

from evolve.driver import RunOptions, run, workspace_run_lock


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
