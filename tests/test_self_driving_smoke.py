from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest
from assert_self_driving_smoke import assert_self_driving_smoke
from conftest import git

from evolve.archive import MECHANISM_EVAL_FIELD, append_event, archive_path, read_events

SMOKE_AGENT = Path(__file__).parent / "fixtures" / "smoke_agent.py"


def test_smoke_agent_creates_missing_target_deterministically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVOLVE_GENID", "7")

    runpy.run_path(str(SMOKE_AGENT), run_name="__main__")
    first = (tmp_path / "target" / "agent.py").read_text()
    runpy.run_path(str(SMOKE_AGENT), run_name="__main__")

    assert first == "# smoke-mutate gen 7\n"
    assert (tmp_path / "target" / "agent.py").read_text() == first


def _smoke_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "smoke-workspace"
    workspace.mkdir()
    git(workspace, "init", "-q")
    git(workspace, "config", "user.name", "Smoke Test")
    git(workspace, "config", "user.email", "smoke@example.invalid")
    (workspace / ".gitignore").write_text("archive.jsonl\n.evolve-eval-receipts.jsonl\nruns/\n")
    target = workspace / "target" / "agent.py"
    target.parent.mkdir()
    target.write_text("VALUE = 0\n")
    git(workspace, "add", ".")
    git(workspace, "commit", "-qm", "genesis")
    commits = [git(workspace, "rev-parse", "HEAD")]
    git(workspace, "tag", "gen/0")

    target.write_text("VALUE = 0\n# smoke-mutate gen 1\n")
    git(workspace, "add", "target/agent.py")
    git(workspace, "commit", "-qm", "generation 1")
    commits.append(git(workspace, "rev-parse", "HEAD"))
    git(workspace, "tag", "gen/1")

    for generation, commit in enumerate(commits):
        genid = str(generation)
        append_event(
            workspace,
            workspace.name,
            {
                "event_type": "evaluation",
                "experiment_id": workspace.name,
                "genid": genid,
                "generation": genid,
                "candidate_commit": commit,
                "purpose": "genesis" if generation == 0 else "candidate",
                "attempt": 1,
                "evaluator_fingerprint": "smoke-evaluator",
                "task_set_hash": "smoke-tasks",
                "runtime_fingerprint": "smoke-runtime",
                "expected_trials": 1,
                "outcome": "benchmark_complete",
                "trials": [],
                "score": 1.0,
                "cost_usd": 0.0,
                "wall_s": 0.0,
                "artifacts": {},
                "tag": f"gen/{genid}",
                "status": "complete",
                "selection_eligible": True,
                "pending_gate_record": False,
                "valid_parent": True,
                "verdict": "keep",
                "mutated": [] if generation == 0 else ["target/agent.py"],
                "reason": "smoke complete",
                "cost": {"usd": 0.0, "wall_s": 0.0},
                MECHANISM_EVAL_FIELD: True,
            },
        )
    return workspace


def test_self_driving_smoke_accepts_complete_bound_lineage(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)

    assert_self_driving_smoke(workspace, 1)


def test_self_driving_smoke_rejects_raw_operator_failure(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)
    events = read_events(archive_path(workspace))
    events.append({"genid": "1", "status": "operator_failed"})
    archive_path(workspace).write_text("".join(f"{json.dumps(event)}\n" for event in events))

    with pytest.raises(AssertionError, match="operator_failed events recorded for generations: 1"):
        assert_self_driving_smoke(workspace, 1)


def test_self_driving_smoke_rejects_missing_tag(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)
    git(workspace, "tag", "-d", "gen/1")

    with pytest.raises(AssertionError, match="gen/1: tag does not resolve to candidate_commit"):
        assert_self_driving_smoke(workspace, 1)


def test_self_driving_smoke_rejects_tag_commit_mismatch(tmp_path: Path) -> None:
    workspace = _smoke_workspace(tmp_path)
    git(workspace, "tag", "-f", "gen/1", "gen/0")

    with pytest.raises(AssertionError, match="gen/1: tag does not resolve to candidate_commit"):
        assert_self_driving_smoke(workspace, 1)
