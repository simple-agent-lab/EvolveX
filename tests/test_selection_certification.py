from evolve.archive import append_certificate, rows_by_genid
from evolve.evaluation import Outcome, TrialResult, certify_evaluation
from evolve.population import certified_parent_rows


def _certificate(outcome: Outcome, *, epoch: int = 0):
    reward = 1.0 if outcome is Outcome.BENCHMARK_COMPLETE else None
    owner = "benchmark" if reward is not None else "evaluator"
    trial = TrialResult("task-a", 0, outcome, reward, owner)
    return certify_evaluation(
        experiment_id="exp",
        epoch=epoch,
        generation="1",
        candidate_id="abc",
        purpose="candidate",
        attempt=1,
        evaluator_fingerprint="runtime",
        candidate_fingerprint="candidate",
        task_set_hash="tasks",
        expected_trials=1,
        trials=(trial,),
        cost_usd=0.0,
        wall_s=1.0,
    )


def test_failed_and_cancelled_certificates_cannot_become_parents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    for outcome in (Outcome.INFRASTRUCTURE_FAILED, Outcome.CANCELLED):
        workspace = tmp_path / outcome.value
        event = append_certificate(workspace, _certificate(outcome), current_epoch=0)
        assert event["valid_parent"] is False
        assert event["score"] is None


def test_old_epoch_certificate_is_not_a_current_parent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    append_certificate(workspace, _certificate(Outcome.BENCHMARK_COMPLETE, epoch=0), current_epoch=0)

    assert certified_parent_rows(workspace, epoch=0)[0]["genid"] == "1"
    assert certified_parent_rows(workspace, epoch=1) == []


def test_later_archive_event_cannot_promote_failed_certificate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    append_certificate(workspace, _certificate(Outcome.INFRASTRUCTURE_FAILED), current_epoch=0)
    archive = workspace / "archive.jsonl"
    with archive.open("a") as stream:
        stream.write('{"genid":"1","valid_parent":true,"verdict":"keep"}\n')

    row = rows_by_genid(workspace)["1"]
    assert row["valid_parent"] is False
    assert row["selection_eligible"] is False
