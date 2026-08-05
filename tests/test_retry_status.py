from __future__ import annotations

from pathlib import Path

from conftest import init_workspace

import evolve.driver as driver
from evolve.archive import append_event
from evolve.report import format_status


def test_force_retry_reaches_evaluator_after_terminal_failure(tmp_path: Path, monkeypatch) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    append_event(
        workspace,
        workspace.name,
        {
            "genid": "1",
            "parent": "0",
            "tag": "gen/1",
            "mutated": [],
            "surface_violations": [],
        },
    )
    append_event(
        workspace,
        workspace.name,
        {
            "genid": "1",
            "status": "operator_failed",
            "failure_stage": "meta_agent",
            "reason": "operator meta_agent failed",
        },
    )
    calls: list[str] = []
    sentinel = object()

    def stamp(*_args, **_kwargs):
        calls.append("evaluation")
        return sentinel

    monkeypatch.setattr(driver, "_stamp_evaluation", stamp)

    assert driver.eval_child(workspace, "1") is None
    assert driver.eval_child(workspace, "1", force=True) is sentinel
    assert calls == ["evaluation"]


def test_status_exposes_latest_failure_stage(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    append_event(
        workspace,
        workspace.name,
        {
            "genid": "1",
            "parent": "0",
            "tag": "gen/1",
            "status": "operator_failed",
            "failure_stage": "rollout",
            "reason": "operator rollout failed",
        },
    )

    status = format_status(workspace)

    assert "latest.genid: 1" in status
    assert "latest.status: operator_failed" in status
    assert "latest.failure_stage: rollout" in status
