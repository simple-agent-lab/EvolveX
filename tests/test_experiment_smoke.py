from __future__ import annotations

import json
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, smoke_agent_command

from evolve.experiment_smoke import run_experiment_smoke


def test_experiment_smoke_runs_in_isolated_clone_and_produces_real_child(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    split = {
        "version": 2,
        "resolved": True,
        "identity_status": "verified",
        "dataset_identity": {
            "source": "local",
            "digest": "d" * 64,
            "resolved_reference": "sha256:" + "d" * 64,
        },
        "tasks": {"train": [], "gate": ["task-a"], "sealed": []},
        "task_digests": {"task-a": "a" * 64},
    }
    (workspace / "evaluator" / "splits.json").write_text(json.dumps(split) + "\n")
    git(workspace, "add", "evaluator/splits.json")
    git(workspace, "commit", "-m", "freeze smoke task")
    git(workspace, "tag", "-f", "gen/0")
    source_rows = rows_by_genid(workspace)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    result = run_experiment_smoke(workspace, task="task-a")

    assert result.status == "passed", result.error
    assert result.workspace.is_relative_to(workspace / "runs" / "experiment-smoke")
    assert rows_by_genid(workspace) == source_rows
    child = rows_by_genid(result.workspace)["1"]
    assert child["outcome"] == "benchmark_complete"
    assert child["selection_eligible"] is True
    assert result.result_path.is_file()
