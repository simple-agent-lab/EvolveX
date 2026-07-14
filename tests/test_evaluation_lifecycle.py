import stat
from pathlib import Path

import pytest
from conftest import git, init_workspace, smoke_agent_command

from evolve.archive import MECHANISM_EVAL_FIELD, read_events, rows_by_genid
from evolve.driver import EvaluationPaused, RunOptions, run
from evolve.frozen.interfaces import ArchiveView


def _lifecycle_workspace(tmp_path: Path, outcomes: dict[str, list[str]]) -> Path:
    workspace, _evolve_home = init_workspace(tmp_path)
    script = workspace / "evaluator/eval.sh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        f"outcomes = {outcomes!r}\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR'])\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "purpose = os.environ['EVOLVE_EVAL_KIND']\n"
        "attempt = int(run_dir.name.removeprefix('attempt-'))\n"
        "sequence = outcomes.get(purpose, outcomes.get('candidate', ['benchmark_complete']))\n"
        "outcome = sequence[min(attempt - 1, len(sequence) - 1)]\n"
        "owner = 'candidate' if outcome == 'candidate_invalid' else 'benchmark_agent'\n"
        "reward = 1.0 if outcome == 'benchmark_complete' else (0.0 if outcome == 'timeout' else None)\n"
        "vector = {'schema_version': 1, 'tasks': {'case-a': {'trials': [{\n"
        "    'trial': 0, 'status': outcome, 'reward': reward, 'owner': owner,\n"
        "}]}}}\n"
        "(run_dir / 'task_vector.json').write_text(json.dumps(vector) + '\\n')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    config = workspace / "evolve.yaml"
    config.write_text(config.read_text().replace("tasks_per_round: 16", "tasks_per_round: 1"))
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "configure lifecycle evaluator")
    git(workspace, "tag", "-f", "gen/0")
    return workspace


def _evaluation_events(workspace: Path, genid: str) -> list[dict[str, object]]:
    return [
        event
        for event in read_events(workspace / "archive.jsonl")
        if str(event.get("genid")) == genid and event.get(MECHANISM_EVAL_FIELD) is True
    ]


def test_failed_real_genesis_is_not_selectable(tmp_path: Path) -> None:
    workspace = _lifecycle_workspace(tmp_path, {"genesis": ["candidate_invalid"]})

    with pytest.raises(RuntimeError, match="genesis candidate_invalid"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    row = ArchiveView(workspace).row("0")
    assert row is not None and row["score"] is None
    assert row["status"] == "candidate_invalid"
    assert ArchiveView(workspace).valid_parents() == []
    assert not git(workspace, "tag", "--list", "gen/1")


def test_genesis_infrastructure_retries_same_commit_once(tmp_path: Path) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {"genesis": ["infrastructure_failed", "benchmark_complete"]},
    )

    run(RunOptions(workspace, max_generations=0, children_per_gen=1))

    attempts = _evaluation_events(workspace, "0")
    assert [event["attempt"] for event in attempts] == [1, 2]
    assert attempts[0]["candidate_commit"] == attempts[1]["candidate_commit"]
    assert attempts[1]["retry_of"] == 1
    assert rows_by_genid(workspace)["0"]["attempt"] == 2
    assert rows_by_genid(workspace)["0"]["status"] == "complete"


def test_two_genesis_infrastructure_failures_pause_before_evolution(tmp_path: Path) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {"genesis": ["infrastructure_failed", "infrastructure_failed"]},
    )

    with pytest.raises(EvaluationPaused, match="gen/0 infrastructure failed twice"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    row = rows_by_genid(workspace)["0"]
    assert row["attempt"] == 2
    assert row["retry_of"] == 1
    assert row["status"] == "infrastructure_failed"
    assert [event["attempt"] for event in _evaluation_events(workspace, "0")] == [1, 2]
    assert not git(workspace, "tag", "--list", "gen/1")

    with pytest.raises(EvaluationPaused, match="gen/0 infrastructure failed twice"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))
    assert [event["attempt"] for event in _evaluation_events(workspace, "0")] == [1, 2]


@pytest.mark.parametrize("outcome", ["candidate_invalid", "timeout", "cancelled"])
def test_genesis_retry_terminal_is_canonical_and_persistent(tmp_path: Path, outcome: str) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {"genesis": ["infrastructure_failed", outcome]},
    )

    with pytest.raises(RuntimeError, match=f"genesis {outcome}"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    row = rows_by_genid(workspace)["0"]
    assert row["attempt"] == 2
    assert row["retry_of"] == 1
    assert row["status"] == outcome
    with pytest.raises(RuntimeError, match=f"genesis {outcome}"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))
    assert [event["attempt"] for event in _evaluation_events(workspace, "0")] == [1, 2]
    assert not git(workspace, "tag", "--list", "gen/1")


def test_later_candidate_infrastructure_retries_same_commit_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {
            "genesis": ["benchmark_complete"],
            "candidate": ["infrastructure_failed", "benchmark_complete"],
        },
    )
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    attempts = _evaluation_events(workspace, "1")
    assert [event["attempt"] for event in attempts] == [1, 2]
    assert attempts[0]["candidate_commit"] == attempts[1]["candidate_commit"]
    assert attempts[1]["retry_of"] == 1
    assert rows_by_genid(workspace)["1"]["attempt"] == 2
    assert rows_by_genid(workspace)["1"]["status"] == "complete"


def test_two_later_infrastructure_failures_pause_without_advancing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {
            "genesis": ["benchmark_complete"],
            "candidate": ["infrastructure_failed", "infrastructure_failed"],
        },
    )
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    with pytest.raises(EvaluationPaused, match="gen/1 infrastructure failed twice"):
        run(RunOptions(workspace, max_generations=2, children_per_gen=1))

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 2
    assert row["retry_of"] == 1
    assert row["status"] == "infrastructure_failed"
    assert [event["attempt"] for event in _evaluation_events(workspace, "1")] == [1, 2]
    assert git(workspace, "tag", "--list", "gen/1") == "gen/1"
    assert not git(workspace, "tag", "--list", "gen/2")
    assert [row["genid"] for row in ArchiveView(workspace).valid_parents()] == ["0"]

    with pytest.raises(EvaluationPaused, match="gen/1 infrastructure failed twice"):
        run(RunOptions(workspace, max_generations=2, children_per_gen=1))
    assert [event["attempt"] for event in _evaluation_events(workspace, "1")] == [1, 2]


@pytest.mark.parametrize("outcome", ["candidate_invalid", "timeout", "cancelled"])
def test_later_retry_terminal_is_canonical_and_does_not_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {
            "genesis": ["benchmark_complete"],
            "candidate": ["infrastructure_failed", outcome],
        },
    )
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 2
    assert row["retry_of"] == 1
    assert row["status"] == outcome
    assert not (workspace / "runs/gen-1/gate.json").exists()
    run(RunOptions(workspace, max_generations=1, children_per_gen=1))
    assert [event["attempt"] for event in _evaluation_events(workspace, "1")] == [1, 2]
    assert [row["genid"] for row in ArchiveView(workspace).valid_parents()] == ["0"]


@pytest.mark.parametrize("outcome", ["candidate_invalid", "timeout", "cancelled"])
def test_later_terminal_candidate_does_not_retry_or_run_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {"genesis": ["benchmark_complete"], "candidate": [outcome]},
    )
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    assert [event["attempt"] for event in _evaluation_events(workspace, "1")] == [1]
    assert rows_by_genid(workspace)["1"]["status"] == outcome
    assert [row["genid"] for row in ArchiveView(workspace).valid_parents()] == ["0"]
    assert not (workspace / "runs/gen-1/gate.json").exists()
