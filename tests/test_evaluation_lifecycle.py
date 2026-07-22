import stat
from pathlib import Path

import pytest
from conftest import git, init_workspace, smoke_agent_command

from evolve.archive import MECHANISM_EVAL_FIELD, read_events, rows_by_genid
from evolve.driver import RunOptions, run


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


def test_candidate_infrastructure_failure_is_recorded_once_without_batch_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    assert attempts[1]["source_attempts"] == [2]
    assert attempts[1]["repaired_tasks"] == ["case-a"]
    assert attempts[1]["trials"][0]["source_attempt"] == 2
    assert attempts[1]["trials"][0]["repaired_from_attempt"] == 1
    repaired_trial = attempts[1]["task_vector"]["tasks"]["case-a"]["trials"][0]
    assert repaired_trial["source_attempt"] == 2
    assert repaired_trial["repaired_from_attempt"] == 1
    repair_dir = Path(workspace / attempts[1]["artifacts"]["path"]).parent
    assert (repair_dir / "repair-task-names.txt").read_text() == "case-a\n"
    assert (repair_dir / "composite_evaluation_artifacts.json").exists()
    assert rows_by_genid(workspace)["1"]["attempt"] == 2
    assert rows_by_genid(workspace)["1"]["status"] == "complete"
