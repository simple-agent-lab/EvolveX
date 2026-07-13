import json
import stat
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid, run_evolve, smoke_agent_command


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    path = workspace / relative_path
    path.write_text(content)
    if relative_path.endswith(".sh") or relative_path.startswith("operators/"):
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _replace(workspace: Path, relative_path: str, old: str, new: str) -> None:
    path = workspace / relative_path
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def _commit_and_retag_gen0(workspace: Path, *paths: str) -> None:
    git(workspace, "add", *paths)
    git(workspace, "commit", "-m", "configure per-round sampling")
    git(workspace, "tag", "-f", "gen/0")


def _per_round_eval_script() -> str:
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '1.0\\n' > \"$EVOLVE_RUN_DIR/score\"\n"
        "printf 'complete\\n' > \"$EVOLVE_RUN_DIR/status\"\n"
        "printf '{\"schema_version\":1,\"tasks\":{\"round-task\":{\"trials\":[{\"trial\":0,\"status\":\"benchmark_complete\",\"reward\":1.0}]}}}\\n' > \"$EVOLVE_RUN_DIR/task_vector.json\"\n"
        'printf \'round-%s\\n\' "${EVOLVE_ROUND:-missing}" > "$EVOLVE_RUN_DIR/task_set_hash"\n'
        "exit 0\n"
    )


def _enable_per_round_stub(workspace: Path) -> None:
    _enable_per_round_script(workspace, _per_round_eval_script())


def _enable_per_round_script(workspace: Path, script: str) -> None:
    evaluator_tail = "  partial_floor: 0.8\n"
    _replace(workspace, "evolve.yaml", evaluator_tail, evaluator_tail + "  sampling: per_round\n")
    _replace(workspace, "evolve.yaml", "  tasks_per_round: 16\n", "  tasks_per_round: 1\n")
    _rewrite(workspace, "evaluator/eval.sh", script)
    _commit_and_retag_gen0(workspace, "evolve.yaml", "evaluator/eval.sh")


def _events(workspace: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (workspace / "archive.jsonl").read_text().splitlines() if line.strip()]


def test_per_round_sampling_re_evaluates_parent_before_same_hash_gate(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    _enable_per_round_stub(workspace)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVOLVE_HOME": str(evolve_home), "EVOLVE_AGENT_COMMAND": smoke_agent_command()},
    )

    assert result.returncode == 0, result.stderr
    events = _events(workspace)
    rows = rows_by_genid(workspace)
    round2_parent = rows["2"]["parent"]
    round2_parent_reevals = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("genid") == round2_parent
        and event.get("kind") == "reeval"
        and event.get("task_set_hash") == "round-2"
    ]
    assert len(round2_parent_reevals) == 1
    assert round2_parent_reevals[0][1]["purpose"] == "round-2"
    assert round2_parent_reevals[0][1]["selection_eligible"] is False
    assert round2_parent_reevals[0][1]["valid_parent"] is False
    child2_eval_index = next(
        index
        for index, event in enumerate(events)
        if event.get("genid") == "2" and event.get("task_set_hash") == "round-2"
    )
    assert round2_parent_reevals[0][0] < child2_eval_index
    assert rows["2"]["task_set_hash"] == "round-2"
    assert "same task hash round-2" in json.loads((workspace / "runs" / "gen-2" / "gate.json").read_text())["reason"]
    assert any(event.get("kind") == "reeval" for event in rows["0"]["evals"])
    assert list((workspace / "runs/evaluations/round-1").glob("gen-*/candidate-*/attempt-1"))
    assert list((workspace / "runs/evaluations/round-2").glob("gen-*/candidate-*/attempt-1"))
