from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import git

from evolve.review import (
    ReviewFormatError,
    ReviewReport,
    ReviewTask,
    collect_review_run,
    default_task_path,
    run_review,
)
from evolve.runtime import OwnedResult


def _report(*, category: str = "simplicity", evidence: bool = True) -> dict[str, object]:
    return {
        "schema_version": 1,
        "verdict": "needs_changes",
        "summary": "One actionable issue.",
        "findings": [
            {
                "severity": "P2",
                "category": category,
                "title": "Remove the duplicate decision path",
                "evidence": (
                    [{"path": "module.py", "line": 2, "detail": "Both branches select the same behavior."}]
                    if evidence
                    else []
                ),
                "impact": "Maintainers must reason about two sources of truth.",
                "smallest_fix": "Keep the direct branch and delete the duplicate wrapper.",
                "confidence": "high",
            }
        ],
        "questions": [],
        "strengths": ["The public name is clear."],
    }


def _git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "review-test")
    git(repo, "config", "user.email", "review@example.invalid")
    (repo / "module.py").write_text("value = 1\n")
    git(repo, "add", "module.py")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "module.py").write_text("value = 1\nother = 2\n")
    git(repo, "commit", "-am", "change")
    return repo, base, git(repo, "rev-parse", "HEAD")


def test_default_review_task_is_reusable_and_valid() -> None:
    task = ReviewTask.load(default_task_path())

    assert task.name == "framework-quality"
    assert task.max_findings == 10
    assert {"simplicity", "user-understanding", "llm-agent"} <= set(task.rubrics)


def test_review_report_validates_evidence_and_enabled_categories(tmp_path: Path) -> None:
    task = ReviewTask.load(default_task_path())
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()))

    report = ReviewReport.load(report_path, task)

    assert report.findings[0].evidence[0].line == 2
    report_path.write_text(json.dumps(_report(category="not-enabled")))
    with pytest.raises(ReviewFormatError, match="not enabled"):
        ReviewReport.load(report_path, task)
    report_path.write_text(json.dumps(_report(evidence=False)))
    with pytest.raises(ReviewFormatError, match="requires evidence"):
        ReviewReport.load(report_path, task)


def test_review_run_collects_report_result_and_atif_trajectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, head = _git_repo(tmp_path)
    task = ReviewTask.load(default_task_path())

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str], timeout_s=None) -> OwnedResult:
        del env, timeout_s
        assert cwd == repo
        jobs_dir = Path(command[command.index("--jobs-dir") + 1])
        task_dir = Path(command[command.index("--path") + 1])
        assert "--agent-include-logs" not in command
        assert "--skill" not in command
        assert command[command.index("--agent-env") + 1] == "HOME=/tmp/evolve-review-home"
        assert command[command.index("--agent-kwarg") + 1] == "reasoning_effort=medium"
        assert "schema_version=1" in (task_dir / "instruction.md").read_text()
        trial = jobs_dir / "review-framework-quality" / "task" / "trial"
        agent = trial / "agent"
        agent.mkdir(parents=True)
        (agent / "trajectory.json").write_text(
            json.dumps({"schema_version": "ATIF-v1.7", "session_id": "review-session", "steps": []})
        )
        (agent / "review-report.json").write_text(json.dumps(_report()))
        (trial / "result.json").write_text(
            json.dumps(
                {
                    "task_name": task.name,
                    "trial_name": "trial",
                    "started_at": "2026-07-22T00:00:00Z",
                    "finished_at": "2026-07-22T00:00:01.25Z",
                }
            )
        )
        return OwnedResult(0, "done\n", "", 1.25, False)

    monkeypatch.setattr("evolve.review.run_owned", fake_run)

    result = run_review(repo, task=task, base_ref=base, head_ref=head, runs_dir=tmp_path / "review-runs")

    assert result.base_commit == base
    assert result.head_commit == head
    assert result.wall_s == 1.25
    assert result.report.findings[0].category == "simplicity"
    assert result.trajectory_path.is_file()
    manifest = json.loads((result.run_dir / "run.json").read_text())
    assert manifest["task"]["name"] == "framework-quality"
    assert manifest["reasoning_effort"] == "medium"
    assert manifest["trajectory"].endswith("agent/trajectory.json")
    assert len(git(repo, "worktree", "list", "--porcelain").split("worktree ")) == 2

    recovered = collect_review_run(result.run_dir)
    assert recovered.wall_s == 1.25
    assert recovered.report == result.report

    result.trajectory_path.write_text(json.dumps({"schema_version": "ATIF-v1.7"}))
    with pytest.raises(ReviewFormatError, match="session_id"):
        collect_review_run(result.run_dir)
