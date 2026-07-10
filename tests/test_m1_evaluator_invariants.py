import hashlib
import json
import stat
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, run_evolve, smoke_agent_command

from evolve.archive import MECHANISM_EVAL_FIELD, append_event
from evolve.evaluator import _evaluation_artifact_reference, _read_task_vector
from evolve.task_vectors import TaskVectorError


def make_eval_script(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_evaluator_path_commit_is_invalid_and_eval_does_not_stamp_score(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    child = tmp_path / "child"
    forked = run_evolve("fork", str(workspace), "0", str(child), env={"EVOLVE_HOME": str(evolve_home)})
    assert forked.returncode == 0, forked.stderr
    make_eval_script(
        child / "evaluator" / "eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '999.0\\n' > \"$EVOLVE_RUN_DIR/score\"\n"
        "printf 'complete\\n' > \"$EVOLVE_RUN_DIR/status\"\n"
        "exit 0\n",
    )

    committed = run_evolve(
        "commit",
        str(workspace),
        str(child),
        "--parent",
        "0",
        "--genid",
        "1",
        env={"EVOLVE_HOME": str(evolve_home)},
    )
    assert committed.returncode == 0, committed.stderr
    row = rows_by_genid(workspace)["1"]
    assert row["status"] == "invalid_proposal"
    assert row["valid_parent"] is False
    assert row["score"] is None
    assert row["surface_violations"] == ["evaluator/eval.sh"]

    before = (workspace / "archive.jsonl").read_text().splitlines()
    evaluated = run_evolve(
        "eval",
        str(workspace),
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert evaluated.returncode == 0, evaluated.stderr
    assert (workspace / "archive.jsonl").read_text().splitlines() == before
    assert rows_by_genid(workspace)["1"]["score"] is None


def test_infra_failed_eval_is_scoreless_invalid_parent_and_retryable(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": None, "EVOLVE_HOME": str(evolve_home), "EVOLVE_AGENT_COMMAND": smoke_agent_command()},
    )
    assert first.returncode == 0, first.stderr

    failed = rows_by_genid(workspace)["1"]
    assert failed["status"] == "infra_failed"
    assert failed["score"] is None
    assert failed["valid_parent"] is False

    retried = run_evolve(
        "eval",
        str(workspace),
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert retried.returncode == 0, retried.stderr
    repaired = rows_by_genid(workspace)["1"]
    assert repaired["status"] == "complete"
    assert repaired["score"] == 1.0
    assert repaired["valid_parent"] is True


def test_mechanism_eval_can_replace_initial_scaffold_score(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path, experiment="manual-attempt")
    initial = rows_by_genid(workspace)["0"]

    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "score": 0.75,
            "reason": "manual archive write",
            "note": "manual attempt",
        },
    )
    assert rows_by_genid(workspace)["0"]["score"] == 1.0

    workspace, _evolve_home = init_workspace(tmp_path, experiment="mechanism-attempt")
    initial = rows_by_genid(workspace)["0"]
    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "score": None,
            "status": "infra_failed",
            "valid_parent": False,
            "verdict": "discard",
            "reason": "mechanism evaluation stamp",
            "note": "mechanism evaluation recorded before gate/record",
            "cost": {"usd": 0, "wall_s": 1.0},
            MECHANISM_EVAL_FIELD: True,
        },
    )
    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "score": 0.25,
            "task_vector": {"baseline": False},
            "reason": "mechanism evaluation stamp",
            "note": "real baseline eval",
            "cost": {"usd": 0, "wall_s": 1.2},
            MECHANISM_EVAL_FIELD: True,
        },
    )

    row = rows_by_genid(workspace)["0"]
    assert row["score"] == 0.25
    assert row["task_vector"] == {"baseline": False}
    assert row["note"] == "real baseline eval"


def test_eval_force_re_evaluates_completed_generation_zero(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "eval",
        str(workspace),
        "0",
        "--force",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    assert (workspace / "runs" / "gen-0" / "eval" / "score").exists()
    last_event = json.loads((workspace / "archive.jsonl").read_text().splitlines()[-1])
    assert last_event["genid"] == "0"
    assert last_event[MECHANISM_EVAL_FIELD] is True


def test_evaluator_validates_task_vectors_and_compacts_artifact_references(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs" / "gen-1" / "eval"
    run_dir.mkdir(parents=True)
    vector_path = run_dir / "task_vector.json"
    vector_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks": {"case-a": {"trials": [{"trial": 0, "status": "complete", "reward": 1.0}]}},
            }
        )
    )
    artifacts_path = run_dir / "evaluation_artifacts.json"
    artifacts_path.write_text('{"jobs_dir":"/retained/jobs","trials":[]}\n')

    assert _read_task_vector(run_dir) == json.loads(vector_path.read_text())
    assert _evaluation_artifact_reference(workspace, run_dir) == {
        "path": "runs/gen-1/eval/evaluation_artifacts.json",
        "sha256": hashlib.sha256(artifacts_path.read_bytes()).hexdigest(),
    }

    vector_path.write_text('{"schema_version": 99, "tasks": {}}\n')
    with pytest.raises(TaskVectorError, match="unsupported task vector schema"):
        _read_task_vector(run_dir)


def test_hand_edited_artifact_hash_cannot_replace_mechanism_stamp(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    initial = rows_by_genid(workspace)["0"]
    expected = {"path": "runs/gen-0/eval/evaluation_artifacts.json", "sha256": "authentic"}
    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "evaluation_artifacts": expected,
            "reason": "mechanism evaluation stamp",
            "note": "real baseline eval",
            "cost": {"usd": 0, "wall_s": 1.0},
            MECHANISM_EVAL_FIELD: True,
        },
    )
    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "evaluation_artifacts": {**expected, "sha256": "forged"},
            "reason": "hand-edited artifact hash",
            "note": "manual attempt",
        },
    )

    assert rows_by_genid(workspace)["0"]["evaluation_artifacts"] == expected
