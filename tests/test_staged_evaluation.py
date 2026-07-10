from pathlib import Path

from conftest import append_archive_event, git_show, init_workspace, rows_by_genid, smoke_env

from evolve.archive import read_events
from evolve.driver import RunOptions, eval_child
from evolve.driver import run as driver_run
from evolve.evaluator import EvaluationResult
from evolve.population import valid_parent_rows


def result(score: float, *, status: str = "complete") -> EvaluationResult:
    return EvaluationResult(
        score=score,
        status=status,
        task_set_hash="tasks",
        evaluator_tree="tree",
        wall_s=0.01,
        task_vector={"task-0": score > 0},
    )


def _rewrite(workspace: Path, relative_path: str, content: str) -> None:
    (workspace / relative_path).write_text(content)


def _configure_stage(workspace: Path) -> None:
    config = (workspace / "evolve.yaml").read_text()
    config = config.replace("  sampling: static\n", "  sampling: static\n  stage: {tasks: 4, proceed_if: positive}\n")
    _rewrite(workspace, "evolve.yaml", config)


def _seed_candidate_event(workspace: Path, evolve_home: Path) -> None:
    append_archive_event(
        workspace,
        evolve_home,
        {
            "genid": "1",
            "parent": "0",
            "tag": "gen/1",
            "mutated": ["target/agent.py"],
            "surface_violations": [],
        },
    )


def test_zero_stage_score_is_recorded_without_full_evaluation(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    _configure_stage(workspace)
    _seed_candidate_event(workspace, evolve_home)
    calls: list[tuple[str, int | None]] = []

    def fake_evaluate(workspace, tag, genid, *, round_number=None, run_name="eval", task_limit=None, eval_kind="research"):
        calls.append((run_name, task_limit))
        return result(0.0)

    monkeypatch.setattr("evolve.driver.evaluate", fake_evaluate)

    eval_child(workspace, "1")

    row = rows_by_genid(workspace)["1"]
    assert calls == [("eval-stage", 4)]
    assert row["score"] == 0.0
    assert row["stage_score"] == 0.0
    assert row["run_full_eval"] is False
    assert row["valid_parent"] is True


def test_positive_stage_score_runs_full_evaluation(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    _configure_stage(workspace)
    _seed_candidate_event(workspace, evolve_home)
    calls: list[tuple[str, int | None]] = []

    def fake_evaluate(workspace, tag, genid, *, round_number=None, run_name="eval", task_limit=None, eval_kind="research"):
        calls.append((run_name, task_limit))
        return result(0.25 if run_name == "eval-stage" else 0.75)

    monkeypatch.setattr("evolve.driver.evaluate", fake_evaluate)

    eval_child(workspace, "1")

    row = rows_by_genid(workspace)["1"]
    assert calls == [("eval-stage", 4), ("eval", None)]
    assert row["score"] == 0.75
    assert row["stage_score"] == 0.25
    assert row["run_full_eval"] is True


def test_run_zero_generations_replaces_initial_scaffold_with_genesis_evaluation(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    config = (workspace / "evolve.yaml").read_text().replace(
        "  anchor: {final: true, every_rounds: 0}\n",
        "  anchor: {final: false, every_rounds: 0}\n",
    )
    _rewrite(workspace, "evolve.yaml", config)
    calls: list[tuple[str, str]] = []

    def fake_evaluate(workspace, tag, genid, *, round_number=None, run_name="eval", task_limit=None, eval_kind="research"):
        calls.append((run_name, eval_kind))
        return result(0.5, status="partial")

    monkeypatch.setattr("evolve.driver.evaluate", fake_evaluate)

    driver_run(RunOptions(workspace=workspace, max_generations=0))

    row = rows_by_genid(workspace)["0"]
    events = [event for event in read_events(workspace / "archive.jsonl") if event.get("genid") == "0"]
    assert calls == [("eval-genesis", "genesis")]
    assert row["score"] == 0.5
    assert row["status"] == "partial"
    assert events[-1]["kind"] == "genesis_eval"
    assert events[-1]["pending_gate_record"] is False


def test_final_anchor_runs_after_children_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def fake_evaluate(workspace, tag, genid, *, round_number=None, run_name="eval", task_limit=None, eval_kind="research"):
        calls.append((genid, run_name, eval_kind))
        return result(1.0)

    monkeypatch.setattr("evolve.driver.evaluate", fake_evaluate)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_env(evolve_home)["EVOLVE_AGENT_COMMAND"])

    driver_run(RunOptions(workspace=workspace, max_generations=2))
    driver_run(RunOptions(workspace=workspace, max_generations=2))

    events = read_events(workspace / "archive.jsonl")
    anchor_events = [event for event in events if event.get("kind") == "anchor"]
    assert [call for call in calls if call[2] == "anchor"] == [("2", "eval-anchor", "anchor")]
    assert calls[-1] == ("2", "eval-anchor", "anchor")
    assert len(anchor_events) == 1
    assert events[-1]["kind"] == "anchor"
    assert "gen 2" in git_show(workspace, "gen/2:target/agent.py").decode()


def test_infra_failed_final_anchor_stays_auxiliary_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def fake_evaluate(workspace, tag, genid, *, round_number=None, run_name="eval", task_limit=None, eval_kind="research"):
        calls.append((genid, run_name, eval_kind))
        if eval_kind == "anchor":
            return EvaluationResult(
                score=None,
                status="infra_failed",
                task_set_hash="tasks",
                evaluator_tree="tree",
                wall_s=0.01,
                task_vector=None,
            )
        return result(1.0)

    monkeypatch.setattr("evolve.driver.evaluate", fake_evaluate)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_env(evolve_home)["EVOLVE_AGENT_COMMAND"])

    driver_run(RunOptions(workspace=workspace, max_generations=2))
    driver_run(RunOptions(workspace=workspace, max_generations=2))

    row = rows_by_genid(workspace)["2"]
    assert row["score"] == 1.0
    assert row["status"] == "complete"
    assert row["valid_parent"] is True
    assert row["verdict"] == "keep"
    assert row["reason"] == "score 1.0 >= parent 1.0"
    assert row["note"] != "final anchor evaluation"
    assert any(str(candidate["genid"]) == "2" for candidate in valid_parent_rows(workspace))
    assert any(
        entry.get("kind") == "anchor"
        and entry.get("status") == "infra_failed"
        and entry.get("score") is None
        and entry.get("verdict") == "discard"
        for entry in row.get("evals", [])
    )

    events = read_events(workspace / "archive.jsonl")
    anchor_events = [event for event in events if event.get("kind") == "anchor"]
    assert [call for call in calls if call[2] == "anchor"] == [("2", "eval-anchor", "anchor")]
    assert len(anchor_events) == 1
    assert anchor_events[0]["status"] == "infra_failed"
    assert anchor_events[0]["score"] is None
