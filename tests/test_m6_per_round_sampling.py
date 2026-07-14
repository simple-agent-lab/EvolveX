import json
import stat
from pathlib import Path

import pytest
from conftest import git, init_workspace, rows_by_genid, run_evolve, smoke_agent_command

from evolve.config import evaluator_sampling
from evolve.driver import eval_child
from evolve.evaluator import evaluate


def _replace(workspace: Path, relative_path: str, old: str, new: str) -> None:
    path = workspace / relative_path
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_per_round_sampling_is_rejected_clearly(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    _replace(workspace, "evolve.yaml", "  partial_floor: 0.8\n", "  partial_floor: 0.8\n  sampling: per_round\n")
    git(workspace, "add", "evolve.yaml")
    git(workspace, "commit", "-m", "configure unsupported sampling")
    git(workspace, "tag", "-f", "gen/0")

    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        evaluator_sampling(workspace)
    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        eval_child(workspace, "0", force=True)
    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        evaluate(workspace, "gen/0", "0", purpose="genesis")


def test_static_sampling_can_select_generation_one_for_generation_two(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    script = workspace / "evaluator/eval.sh"
    script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "mkdir -p \"$EVOLVE_RUN_DIR\"\n"
        "reward=0.0\n"
        "if [ \"$EVOLVE_GENID\" = 1 ]; then reward=1.0; fi\n"
        "printf '{\"schema_version\":1,\"tasks\":{\"static-task\":{\"trials\":[{\"trial\":0,\"status\":\"benchmark_complete\",\"reward\":%s}]}}}\\n' \"$reward\" > \"$EVOLVE_RUN_DIR/task_vector.json\"\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _replace(workspace, "evolve.yaml", "  tasks_per_round: 16\n", "  tasks_per_round: 1\n")
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "configure static evaluator")
    git(workspace, "tag", "-f", "gen/0")

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVOLVE_HOME": str(evolve_home), "EVOLVE_AGENT_COMMAND": smoke_agent_command()},
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    assert rows["1"]["score"] == 1.0
    assert rows["2"]["parent"] == "1"
    assert rows["1"]["task_set_hash"] == rows["2"]["task_set_hash"]
    assert not any(
        event.get("kind") == "reeval"
        for event in map(json.loads, (workspace / "archive.jsonl").read_text().splitlines())
    )
