import hashlib
import json
import stat
from pathlib import Path

import pytest
from conftest import git, init_workspace, rows_by_genid, run_evolve, smoke_agent_command

from evolve.archive import MECHANISM_EVAL_FIELD, append_event, verify_integrity
from evolve.driver import RunOptions
from evolve.driver import run as driver_run
from evolve.evaluation import Outcome, evaluation_status
from evolve.evaluator import (
    _effective_task_set_identity,
    _evaluation_artifact_reference,
    _read_task_vector,
    _run_eval_script,
    evaluate,
)
from evolve.frozen.interfaces import ArchiveView
from evolve.population import looks_mechanism_written, valid_parent_rows
from evolve.task_vectors import TaskVectorError


def make_eval_script(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def configure_outcome_evaluator(workspace: Path, *, timeout_rule: str | None = None) -> None:
    make_eval_script(
        workspace / "evaluator/eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        'outcome="${TEST_EVAL_OUTCOME:-benchmark_complete}"\n'
        'reward="1.0"; owner="benchmark"\n'
        'case "$outcome" in\n'
        '  candidate_invalid) reward="null"; owner="candidate" ;;\n'
        '  infrastructure_failed) reward="null"; owner="infrastructure" ;;\n'
        '  timeout) reward="0.0"; owner="benchmark_agent" ;;\n'
        '  cancelled) reward="null"; owner="evaluator" ;;\n'
        "esac\n"
        "printf '{\"schema_version\":1,\"tasks\":{\"case-a\":{\"trials\":[{\"trial\":0,\"status\":\"%s\",\"reward\":%s,\"owner\":\"%s\"}]}}}\\n' "
        '"$outcome" "$reward" "$owner" > "$EVOLVE_RUN_DIR/task_vector.json"\n',
    )
    config = workspace / "evolve.yaml"
    text = config.read_text().replace("tasks_per_round: 16", "tasks_per_round: 1")
    if timeout_rule is not None:
        text = text.replace("  tasks_per_round: 1\n", f"  tasks_per_round: 1\n  benchmark_timeout_is_zero: {timeout_rule}\n")
    config.write_text(text)
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "configure canonical outcome evaluator")
    git(workspace, "tag", "-f", "gen/0")


def prepare_lifecycle_generation(workspace: Path) -> None:
    configure_outcome_evaluator(workspace)
    driver_run(RunOptions(workspace, max_generations=0))
    git(workspace, "tag", "gen/1", "gen/0")
    append_event(workspace, workspace.name, {
        "genid": "1", "parent": "0", "tag": "gen/1",
        "mutated": [], "surface_violations": [],
    })


def test_archive_view_reads_markerless_legacy_evaluation_without_rewrite(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    archive = workspace / "archive.jsonl"
    archive.write_text(
        json.dumps(
            {
                "genid": "1",
                "parent": "0",
                "tag": "gen/1",
                "score": 0.0,
                "status": "complete",
                "task_set_hash": "legacy-task-set",
                "task_vector": None,
                "evaluator_tree": "legacy-evaluator",
                "valid_parent": True,
                "verdict": "keep",
                "reason": "mechanism evaluation stamp",
                "pending_gate_record": True,
                "note": "mechanism evaluation recorded before gate/record",
                "cost": {"usd": 0, "wall_s": 1.0},
            }
        )
        + "\n"
    )
    before = archive.read_bytes()

    row = ArchiveView(workspace).row("1")

    assert row is not None
    assert row["status"] == "complete"
    assert row["score"] == 0.0
    assert row["valid_parent"] is True
    assert archive.read_bytes() == before


def test_eval_script_receives_persistent_workspace_uv_cache(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    (checkout / "evaluator").mkdir(parents=True)
    make_eval_script(
        checkout / "evaluator" / "eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        'printf "%s\\n" "$EVOLVE_UV_CACHE_DIR" > cache-path\n'
        'printf "complete\\n" > "$EVOLVE_RUN_DIR/status"\n'
        'printf "1.0\\n" > "$EVOLVE_RUN_DIR/score"\n',
    )
    run_dir = workspace / "runs" / "gen-1" / "eval"
    run_dir.mkdir(parents=True)

    result = _run_eval_script(checkout, run_dir, "1", None, None, "research")

    assert result.returncode == 0
    expected = workspace / "runs" / "runtime" / "uv-cache"
    assert (checkout / "cache-path").read_text() == f"{expected}\n"
    assert expected.is_dir()


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


def test_infrastructure_failed_eval_is_scoreless_invalid_parent(tmp_path: Path) -> None:
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
    assert failed["status"] == "infrastructure_failed"
    assert failed["score"] is None
    assert failed["valid_parent"] is False


@pytest.mark.parametrize(
    ("timeout_rule", "expected"),
    [(None, Outcome.TIMEOUT), ("false", Outcome.TIMEOUT), ("true", Outcome.BENCHMARK_COMPLETE)],
)
def test_timeout_zero_scoring_requires_literal_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout_rule: str | None, expected: Outcome,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    configure_outcome_evaluator(workspace, timeout_rule=timeout_rule)
    monkeypatch.setenv("TEST_EVAL_OUTCOME", "timeout")

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")

    assert record.outcome is expected


def test_timeout_zero_rejects_non_boolean_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    configure_outcome_evaluator(workspace, timeout_rule='"false"')
    monkeypatch.setenv("TEST_EVAL_OUTCOME", "timeout")

    with pytest.raises(ValueError, match="benchmark_timeout_is_zero must be a boolean"):
        evaluate(workspace, "gen/0", "0", purpose="genesis")


@pytest.mark.parametrize("outcome", ["candidate_invalid", "timeout", "cancelled"])
def test_canonical_terminal_outcomes_are_not_reevaluated_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    prepare_lifecycle_generation(workspace)
    monkeypatch.setenv("TEST_EVAL_OUTCOME", outcome)

    driver_run(RunOptions(workspace, max_generations=1))
    row = rows_by_genid(workspace)["1"]
    attempts = list((workspace / "runs/evaluations/candidate/gen-1").glob("candidate-*/attempt-*"))
    before = (workspace / "archive.jsonl").read_bytes()
    monkeypatch.setenv("TEST_EVAL_OUTCOME", "benchmark_complete")
    driver_run(RunOptions(workspace, max_generations=1))

    assert row["outcome"] == outcome
    assert row["selection_eligible"] is False
    assert looks_mechanism_written(workspace, row)
    assert all(candidate["genid"] != "1" for candidate in valid_parent_rows(workspace))
    assert len(attempts) == 1
    assert (workspace / "archive.jsonl").read_bytes() == before


def test_canonical_infrastructure_failure_retries_and_success_replaces_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    prepare_lifecycle_generation(workspace)
    monkeypatch.setenv("TEST_EVAL_OUTCOME", "infrastructure_failed")
    driver_run(RunOptions(workspace, max_generations=1))

    failed = rows_by_genid(workspace)["1"]
    assert failed["outcome"] == "infrastructure_failed"
    assert failed["selection_eligible"] is False
    monkeypatch.setenv("TEST_EVAL_OUTCOME", "benchmark_complete")
    driver_run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    attempts = list((workspace / "runs/evaluations/candidate/gen-1").glob("candidate-*/attempt-*"))
    assert len(attempts) == 2
    assert row["attempt"] == 2
    assert row["outcome"] == "benchmark_complete"
    assert evaluation_status(row) == "complete"
    assert row["selection_eligible"] is True


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
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    assert (
        workspace
        / "runs/evaluations/candidate/gen-0"
        / f"candidate-{commit}"
        / "attempt-1/score"
    ).exists()
    last_event = json.loads((workspace / "archive.jsonl").read_text().splitlines()[-1])
    assert last_event["genid"] == "0"
    assert last_event[MECHANISM_EVAL_FIELD] is True


def test_ordinary_evaluation_is_marked_and_receipted(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in (workspace / "archive.jsonl").read_text().splitlines()]
    evaluation = next(
        event
        for event in events
        if event.get("genid") == "1" and event.get("pending_gate_record") is True
    )
    assert evaluation[MECHANISM_EVAL_FIELD] is True
    assert verify_integrity(workspace) == []


def test_evaluator_validates_task_vectors_and_compacts_artifact_references(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs" / "gen-1" / "eval"
    run_dir.mkdir(parents=True)
    vector_path = run_dir / "task_vector.json"
    vector_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks": {"case-a": {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": 1.0}]}},
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


def test_evaluate_uses_exact_commit_attempt_and_ignores_compatibility_score(
    tmp_path: Path,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    script = workspace / "evaluator/eval.sh"
    make_eval_script(
        script,
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '999.0\\n' > \"$EVOLVE_RUN_DIR/score\"\n"
        "printf 'complete\\n' > \"$EVOLVE_RUN_DIR/status\"\n"
        "printf '{\"schema_version\":1,\"tasks\":{\"case-a\":{\"trials\":[{\"trial\":0,\"status\":\"benchmark_complete\",\"reward\":0.0}]}}}\\n' > \"$EVOLVE_RUN_DIR/task_vector.json\"\n"
        "printf '{\"usd\":2.5}\\n' > \"$EVOLVE_RUN_DIR/cost.json\"\n",
    )
    config = workspace / "evolve.yaml"
    config.write_text(config.read_text().replace("tasks_per_round: 16", "tasks_per_round: 1"))
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "test exact evaluator evidence")
    git(workspace, "tag", "-f", "gen/0")

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")
    candidate_commit = git(workspace, "rev-parse", "gen/0^{commit}")
    attempt = (
        workspace
        / "runs/evaluations/genesis/gen-0"
        / f"candidate-{candidate_commit}"
        / "attempt-1"
    )

    assert record.candidate_commit == candidate_commit
    assert record.outcome is Outcome.BENCHMARK_COMPLETE
    assert record.score == 0.0
    assert record.cost_usd == 2.5
    assert record.evaluator_fingerprint == git(workspace, "rev-parse", "gen/0:evaluator")
    assert record.runtime_fingerprint == hashlib.sha256(b"sha256:test-runtime\n").hexdigest()
    assert (attempt / "task_vector.json").is_file()
    assert (attempt / "stdout.log").is_file()
    assert (attempt / "stderr.log").is_file()
    second = evaluate(workspace, "gen/0", "0", purpose="genesis")
    assert second.attempt == 2
    assert (attempt.parent / "attempt-2/task_vector.json").is_file()
    with pytest.raises(FileExistsError, match="attempt already exists"):
        evaluate(workspace, "gen/0", "0", purpose="genesis", attempt=1)


def test_evaluator_tree_mismatch_does_not_consume_attempt_identity(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    make_eval_script(workspace / "evaluator/eval.sh", "#!/bin/sh\nexit 0\n")
    git(workspace, "add", "evaluator/eval.sh")
    git(workspace, "commit", "-m", "mutate evaluator")
    git(workspace, "tag", "gen/1")

    with pytest.raises(RuntimeError, match="differs from gen/0"):
        evaluate(workspace, "gen/1", "1")

    assert not (workspace / "runs/evaluations/candidate/gen-1").exists()


def test_reward_bearing_candidate_failure_is_classified_after_ingestion(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    make_eval_script(
        workspace / "evaluator/eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '{\"schema_version\":1,\"tasks\":{\"case-a\":{\"trials\":[{\"trial\":0,\"status\":\"candidate_invalid\",\"reward\":0.0,\"owner\":\"candidate\",\"exception_type\":\"RuntimeError\"}]}}}\\n' > \"$EVOLVE_RUN_DIR/task_vector.json\"\n"
        "exit 3\n",
    )
    config = workspace / "evolve.yaml"
    config.write_text(config.read_text().replace("tasks_per_round: 16", "tasks_per_round: 1"))
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "emit diagnostic candidate reward")
    git(workspace, "tag", "-f", "gen/0")

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.trials[0].reward == 0.0
    assert record.score is None


def test_candidate_wide_structured_setup_failure_beats_nonzero_exit(
    tmp_path: Path,
) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    make_eval_script(
        workspace / "evaluator/eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf 'candidate_invalid\\n' > \"$EVOLVE_RUN_DIR/setup_outcome\"\n"
        "printf 'candidate dependency setup failed\\n' > \"$EVOLVE_RUN_DIR/setup_reason\"\n"
        "exit 3\n",
    )
    git(workspace, "add", "evaluator/eval.sh")
    git(workspace, "commit", "-m", "test structured setup failure")
    git(workspace, "tag", "-f", "gen/0")

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")

    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.reason == "candidate dependency setup failed"
    assert record.trials == ()
    assert record.score is None


def test_force_re_evaluation_appends_complete_record_evidence(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    script = workspace / "evaluator/eval.sh"
    make_eval_script(
        script,
        "#!/bin/sh\n"
        "set -eu\n"
        'mkdir -p "$EVOLVE_RUN_DIR"\n'
        "printf '{\"schema_version\":1,\"tasks\":{\"case-a\":{\"trials\":[{\"trial\":0,\"status\":\"benchmark_complete\",\"reward\":1.0}]}}}\\n' > \"$EVOLVE_RUN_DIR/task_vector.json\"\n"
        "printf '{\"usd\":2.5}\\n' > \"$EVOLVE_RUN_DIR/cost.json\"\n"
        "printf '{\"trials\":[]}\\n' > \"$EVOLVE_RUN_DIR/evaluation_artifacts.json\"\n",
    )
    config = workspace / "evolve.yaml"
    config.write_text(config.read_text().replace("tasks_per_round: 16", "tasks_per_round: 1"))
    git(workspace, "add", "evaluator/eval.sh", "evolve.yaml")
    git(workspace, "commit", "-m", "emit complete record evidence")
    git(workspace, "tag", "-f", "gen/0")

    for _ in range(2):
        result = run_evolve(
            "eval", str(workspace), "0", "--force",
            env={"EVOLVE_HOME": str(evolve_home)},
        )
        assert result.returncode == 0, result.stderr

    events = [event for event in map(json.loads, (workspace / "archive.jsonl").read_text().splitlines())
              if event.get("event_type") == "evaluation"]
    assert [event["attempt"] for event in events] == [1, 2]
    event = events[-1]
    assert event["cost"] == {"usd": 2.5, "wall_s": event["wall_s"]}
    assert event["artifacts"]["path"].endswith("attempt-2/evaluation_artifacts.json")
    for field in (
        "candidate_commit", "runtime_fingerprint", "purpose", "expected_trials",
        "outcome", "selection_eligible", "trials",
    ):
        assert field in event
    assert event["selection_eligible"] is True
    assert event["valid_parent"] is True


def test_effective_task_set_identity_uses_configured_names_dataset_and_attempts(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    tasks = checkout / "evaluator" / "tasks"
    tasks.mkdir(parents=True)
    (checkout / "evaluator" / "splits.json").write_text('{"unchanged": true}\n')
    (tasks / "smoke.txt").write_text("task-a\ntask-b\n")
    (tasks / "train.txt").write_text("task-a\ntask-b\ntask-c\n")

    smoke = _effective_task_set_identity(
        checkout,
        {"dataset": "suite@1", "k": 2, "task_file": "evaluator/tasks/smoke.txt"},
        None,
    )
    train = _effective_task_set_identity(
        checkout,
        {"dataset": "suite@1", "k": 2, "task_file": "evaluator/tasks/train.txt"},
        None,
    )
    different_k = _effective_task_set_identity(
        checkout,
        {"dataset": "suite@1", "k": 1, "task_file": "evaluator/tasks/smoke.txt"},
        None,
    )

    assert smoke.members == ("task-a", "task-b")
    assert train.members == ("task-a", "task-b", "task-c")
    assert len({smoke.digest, train.digest, different_k.digest}) == 3


def test_effective_task_set_identity_accepts_explicit_configured_task_names(tmp_path: Path) -> None:
    identity = _effective_task_set_identity(
        tmp_path,
        {"dataset": "stub", "k": 2, "task_names": ["task-b", "task-a"]},
        None,
    )

    assert identity.members == ("task-a", "task-b")


def test_hand_edited_artifact_hash_cannot_replace_mechanism_stamp(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    initial = rows_by_genid(workspace)["0"]
    expected = {"path": "runs/gen-0/eval/evaluation_artifacts.json", "sha256": "authentic"}
    append_event(
        workspace,
        workspace.name,
        {
            **initial,
            "artifacts": expected,
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
            "artifacts": {**expected, "sha256": "forged"},
            "reason": "hand-edited artifact hash",
            "note": "manual attempt",
        },
    )

    assert rows_by_genid(workspace)["0"]["artifacts"] == expected
