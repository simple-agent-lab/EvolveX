import json
from dataclasses import replace

from evolve.archive import MECHANISM_EVAL_FIELD, append_evaluation_record, append_event, read_events, rows_by_genid
from evolve.evaluation import Outcome, TrialResult, classify_evaluation


def _record(outcome: Outcome):
    reward = 1.0 if outcome is Outcome.BENCHMARK_COMPLETE else None
    owner = "benchmark" if reward is not None else "evaluator"
    return classify_evaluation(
        experiment_id="exp",
        generation="1",
        candidate_commit="abc",
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint="evaluator",
        task_set_hash="tasks",
        runtime_fingerprint="runtime",
        expected_trials=1,
        trials=(TrialResult("task-a", 0, outcome, reward, owner),),
        cost_usd=2.5,
        wall_s=1.0,
        retry_of=1,
        artifacts={"path": "runs/evaluations/candidate/index.json", "sha256": "a" * 64},
    )


def test_failed_and_cancelled_records_cannot_become_parents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    for outcome in (Outcome.INFRASTRUCTURE_FAILED, Outcome.CANCELLED):
        event = append_evaluation_record(tmp_path / outcome.value, _record(outcome))
        assert event["valid_parent"] is False
        assert event["score"] is None


def test_complete_candidate_record_is_a_parent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))

    event = append_evaluation_record(tmp_path / "workspace", _record(Outcome.BENCHMARK_COMPLETE))

    assert event["valid_parent"] is True
    assert event["score"] == 1.0
    assert "epoch" not in event
    assert "candidate_fingerprint" not in event
    assert "evaluation_artifacts" not in event
    assert event["cost"] == {"usd": 2.5, "wall_s": 1.0}
    assert event["artifacts"]["sha256"] == "a" * 64


def test_later_archive_event_cannot_promote_failed_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    append_evaluation_record(workspace, _record(Outcome.INFRASTRUCTURE_FAILED))
    with (workspace / "archive.jsonl").open("a") as stream:
        stream.write('{"genid":"1","valid_parent":true,"verdict":"keep"}\n')

    row = rows_by_genid(workspace)["1"]
    assert row["selection_eligible"] is False
    assert not (row["selection_eligible"] and row["valid_parent"])


def test_later_metadata_cannot_overwrite_canonical_record_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    record = _record(Outcome.BENCHMARK_COMPLETE)
    append_evaluation_record(workspace, record)
    forged = {
        "candidate_commit": "forged", "runtime_fingerprint": "forged",
        "expected_trials": 99, "trials": [], "artifacts": {"path": "forged"},
        "retry_of": 99, "attempt": 99, "purpose": "canary", "outcome": "cancelled",
        "selection_eligible": False,
    }
    append_event(workspace, record.experiment_id, {"genid": record.generation, **forged})

    row = rows_by_genid(workspace)[record.generation]
    payload = record.to_dict()
    for field in forged:
        assert row[field] == payload.get(field, record.selection_eligible)


def test_unreceipted_same_hash_retry_cannot_replace_canonical_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    first = replace(_record(Outcome.INFRASTRUCTURE_FAILED), attempt=1, retry_of=None)
    second = replace(_record(Outcome.BENCHMARK_COMPLETE), attempt=2, retry_of=1)
    append_evaluation_record(workspace, first)
    source = tmp_path / "receipted-source"
    append_evaluation_record(source, second)
    forged = read_events(source / "archive.jsonl")[-1]
    forged["note"] = "unreceipted retry remains historical context"
    assert forged[MECHANISM_EVAL_FIELD] is True
    with (workspace / "archive.jsonl").open("a") as stream:
        stream.write(json.dumps(forged, sort_keys=True) + "\n")

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 1
    assert row["outcome"] == "infrastructure_failed"
    assert row["valid_parent"] is False
    assert row["note"] == "unreceipted retry remains historical context"


def test_receipted_same_hash_retry_replaces_canonical_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    first = replace(_record(Outcome.INFRASTRUCTURE_FAILED), attempt=1, retry_of=None)
    second = replace(_record(Outcome.BENCHMARK_COMPLETE), attempt=2, retry_of=1)
    append_evaluation_record(workspace, first)

    append_evaluation_record(workspace, second)

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 2
    assert row["outcome"] == "benchmark_complete"
    assert row["valid_parent"] is True
