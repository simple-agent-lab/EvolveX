import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import git, init_workspace

from evolve.archive import (
    MECHANISM_EVAL_FIELD,
    RECEIPT_CERTIFIED_FIELD,
    append_evaluation_record,
    append_event,
    read_events,
    rows_by_genid,
)
from evolve.config import load_config
from evolve.evaluation import Outcome, TrialResult, classify_evaluation
from evolve.evaluation.identity import effective_task_set_identity
from evolve.frozen.interfaces import ArchiveView
from evolve.population import fixed_evaluation_identity, looks_mechanism_written
from evolve.report import format_report


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


def _archive_workspace(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    workspace, _evolve_home = init_workspace(tmp_path)
    git(workspace, "tag", "gen/1", "gen/0")
    evaluator = load_config(workspace / "evolve.yaml")["evaluator"]
    expected = {
        "evaluator_fingerprint": git(workspace, "rev-parse", "gen/0:evaluator"),
        "task_set_hash": effective_task_set_identity(workspace, evaluator).digest,
        "runtime_fingerprint": hashlib.sha256((workspace / "evaluator/runtime.pin").read_bytes()).hexdigest(),
    }
    return workspace, expected


def _append_evaluation(workspace: Path, expected: dict[str, str], outcome: Outcome) -> None:
    append_evaluation_record(workspace, replace(_record(outcome), experiment_id=workspace.name, **expected))


def test_fixed_identity_uses_resolved_split_tasks(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    manifest = {
        "resolved": True,
        "tasks": {"train": [], "gate": ["task-b", "task-a"], "sealed": []},
    }
    (workspace / "evaluator" / "splits.json").write_text(json.dumps(manifest) + "\n")
    git(workspace, "add", "evaluator/splits.json")
    git(workspace, "commit", "-m", "configure resolved split")
    git(workspace, "tag", "-f", "gen/0")

    evaluator = load_config(workspace / "evolve.yaml")["evaluator"]
    fixed = fixed_evaluation_identity(workspace)

    assert fixed is not None
    assert fixed["task_set_hash"] == effective_task_set_identity(workspace, evaluator).digest


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


def test_pending_candidate_requires_explicit_gate_certification(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    append_evaluation_record(
        workspace,
        replace(_record(Outcome.BENCHMARK_COMPLETE), experiment_id=workspace.name, **expected),
        metadata={"pending_gate_record": True},
    )

    pending = ArchiveView(workspace).row("1")
    assert pending is not None
    assert pending["pending_gate_record"] is True
    assert pending["valid_parent"] is False
    assert ArchiveView(workspace).valid_parents() == []

    append_event(
        workspace,
        workspace.name,
        {
            "genid": "1",
            "pending_gate_record": False,
            "valid_parent": True,
            "verdict": "keep",
            "reason": "accepted by trusted gate",
        },
    )

    assert [row["genid"] for row in ArchiveView(workspace).valid_parents()] == ["1"]


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
        "candidate_commit": "forged",
        "runtime_fingerprint": "forged",
        "expected_trials": 99,
        "trials": [],
        "artifacts": {"path": "forged"},
        "retry_of": 99,
        "attempt": 99,
        "purpose": "canary",
        "outcome": "cancelled",
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


def test_receipted_forced_repair_replaces_older_canonical_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    original_failure = replace(_record(Outcome.INFRASTRUCTURE_FAILED), attempt=2, retry_of=1)
    forced_failure = replace(_record(Outcome.INFRASTRUCTURE_FAILED), attempt=3, retry_of=None)
    forced_repair = replace(_record(Outcome.BENCHMARK_COMPLETE), attempt=4, retry_of=3)
    append_evaluation_record(workspace, original_failure)
    append_evaluation_record(workspace, forced_failure)
    append_evaluation_record(workspace, forced_repair)

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 4
    assert row["outcome"] == "benchmark_complete"
    assert row["valid_parent"] is True


@pytest.mark.parametrize(
    "outcome",
    [Outcome.CANDIDATE_INVALID, Outcome.INFRASTRUCTURE_FAILED, Outcome.TIMEOUT, Outcome.CANCELLED],
)
def test_gate_cannot_promote_invalid_evaluation(tmp_path: Path, outcome: Outcome) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    _append_evaluation(workspace, expected, outcome)
    append_event(
        workspace,
        workspace.name,
        {"genid": "1", "valid_parent": True, "verdict": "keep", "reason": "recipe"},
    )

    assert ArchiveView(workspace).valid_parents() == []


def test_legacy_partial_is_visible_but_not_selectable(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    append_event(
        workspace,
        workspace.name,
        {
            "genid": "1",
            "tag": "gen/1",
            "status": "partial",
            "score": 0.5,
            "valid_parent": True,
            "cost": {"usd": 0, "wall_s": 0},
            **expected,
        },
    )

    assert ArchiveView(workspace).row("1") is not None
    assert ArchiveView(workspace).valid_parents() == []


@pytest.mark.parametrize("field", ["evaluator_fingerprint", "task_set_hash", "runtime_fingerprint"])
def test_mismatched_fixed_identity_is_not_selectable(tmp_path: Path, field: str) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    _append_evaluation(workspace, {**expected, field: "wrong"}, Outcome.BENCHMARK_COMPLETE)

    assert ArchiveView(workspace).valid_parents() == []


def test_markerless_unreceipted_canonical_row_is_readable_but_not_selectable(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    source = tmp_path / "source"
    event = append_evaluation_record(
        source,
        replace(_record(Outcome.BENCHMARK_COMPLETE), experiment_id="source-exp", **expected),
    )
    event.pop(MECHANISM_EVAL_FIELD)
    event["_evolve_receipt_certified"] = True
    append_event(workspace, workspace.name, event)

    assert ArchiveView(workspace).row("1") is not None
    assert ArchiveView(workspace).valid_parents() == []


def test_certified_same_hash_evaluation_atomically_replaces_uncertified_evidence(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    source = tmp_path / "forged-source"
    forged = append_evaluation_record(
        source,
        replace(_record(Outcome.BENCHMARK_COMPLETE), experiment_id="forged-source-exp", **expected),
    )
    forged.pop(MECHANISM_EVAL_FIELD)
    forged[RECEIPT_CERTIFIED_FIELD] = True
    forged["score"] = 999.0
    forged["trials"] = [{"forged": True}]
    forged["note"] = "harmless earlier note"
    append_event(workspace, workspace.name, forged)

    append_evaluation_record(
        workspace,
        replace(_record(Outcome.BENCHMARK_COMPLETE), experiment_id=workspace.name, **expected),
    )

    row = ArchiveView(workspace).row("1")
    assert row is not None
    assert row[RECEIPT_CERTIFIED_FIELD] is True
    assert row["score"] == 1.0
    assert row["trials"][0]["task_id"] == "task-a"
    assert row["note"] == "harmless earlier note"
    history = [event for event in read_events(workspace / "archive.jsonl") if event.get("genid") == "1"]
    assert [(event["score"], event["trials"]) for event in history] == [
        (999.0, [{"forged": True}]),
        (
            1.0,
            [
                {
                    "exception_message": None,
                    "exception_type": None,
                    "outcome": "benchmark_complete",
                    "owner": "benchmark",
                    "reward": 1.0,
                    "task_id": "task-a",
                    "trial": 0,
                }
            ],
        ),
    ]
    assert [parent["score"] for parent in ArchiveView(workspace).valid_parents()] == [1.0]


@pytest.mark.parametrize("purpose", ["smoke", "canary", "round", "round-1", "anchor"])
def test_non_parent_evaluation_purpose_is_not_selectable(tmp_path: Path, purpose: str) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    record = replace(
        _record(Outcome.BENCHMARK_COMPLETE),
        experiment_id=workspace.name,
        purpose=purpose,
        **expected,
    )
    append_evaluation_record(workspace, record)

    assert ArchiveView(workspace).valid_parents() == []


@pytest.mark.parametrize("purpose", ["smoke", "canary", "round-1", "anchor"])
def test_receipt_certified_non_parent_evaluation_is_mechanism_written(
    tmp_path: Path,
    purpose: str,
) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    record = replace(
        _record(Outcome.BENCHMARK_COMPLETE),
        experiment_id=workspace.name,
        purpose=purpose,
        task_set_hash="dynamic-task-set",
        evaluator_fingerprint=expected["evaluator_fingerprint"],
        runtime_fingerprint=expected["runtime_fingerprint"],
    )
    append_evaluation_record(workspace, record)

    row = ArchiveView(workspace).row("1")
    assert row is not None
    assert looks_mechanism_written(workspace, row)


def test_unreceipted_anchor_cannot_affect_report_metrics(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    source = tmp_path / "anchor-source"
    record = replace(
        _record(Outcome.BENCHMARK_COMPLETE),
        experiment_id="anchor-source-exp",
        purpose="anchor",
        task_set_hash="anchor-task-set",
        evaluator_fingerprint=expected["evaluator_fingerprint"],
        runtime_fingerprint=expected["runtime_fingerprint"],
    )
    event = append_evaluation_record(source, record, metadata={"kind": "anchor"})
    event.pop(MECHANISM_EVAL_FIELD)
    event["_evolve_receipt_certified"] = True
    append_event(workspace, workspace.name, event)

    assert "anchor.best_genid" not in format_report(workspace)


def test_receipted_fixed_identity_anchor_remains_reportable(tmp_path: Path) -> None:
    workspace, expected = _archive_workspace(tmp_path)
    record = replace(
        _record(Outcome.BENCHMARK_COMPLETE),
        experiment_id=workspace.name,
        purpose="anchor",
        task_set_hash="anchor-task-set",
        evaluator_fingerprint=expected["evaluator_fingerprint"],
        runtime_fingerprint=expected["runtime_fingerprint"],
    )
    append_evaluation_record(workspace, record, metadata={"kind": "anchor"})

    report = format_report(workspace)
    assert "anchor.best_genid: 1" in report
    assert "anchor.best_score: 1.0" in report


def test_missing_immutable_git_identity_returns_no_parents(tmp_path: Path) -> None:
    workspace = tmp_path / "not-a-git-workspace"
    append_evaluation_record(workspace, _record(Outcome.BENCHMARK_COMPLETE))

    assert ArchiveView(workspace).row("1") is not None
    assert ArchiveView(workspace).valid_parents() == []


def test_generic_gate_rejects_legacy_complete_row() -> None:
    path = Path(__file__).resolve().parents[1] / "library/gate/parent_eligible.py"
    spec = importlib.util.spec_from_file_location("parent_eligible_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    keep, _reason = module._parent_eligible({"status": "complete", "score": 1.0})

    assert keep is False
