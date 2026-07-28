import json
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, smoke_agent_command

from evolve import archive as archive_module
from evolve import driver
from evolve.archive import (
    MECHANISM_EVAL_FIELD,
    RECEIPT_CERTIFIED_FIELD,
    RECORD_ATTEMPT_FIELD,
    STAMPED_FIELDS,
    archive_path,
    eval_receipt_path,
    mirror_path,
    read_events,
)
from evolve.branching import BranchIntent, create_branch_intent
from evolve.config import experiment_id
from evolve.driver import RunOptions, commit_child, doctor, fork_child, run
from evolve.git import direct_parent_commit, generation_tags, git, tag_exists


@pytest.fixture(autouse=True)
def smoke_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())


def completed_state_snapshot(workspace: Path) -> tuple[object, ...]:
    tags = {tag: git(workspace, "rev-parse", f"{tag}^{{commit}}").stdout.strip() for tag in generation_tags(workspace)}
    local_archive = archive_path(workspace)
    mirrored_archive = mirror_path(experiment_id(workspace))
    evidence = {
        str(path): tuple(path.read_text().splitlines()) if path.exists() else ()
        for path in (
            local_archive,
            mirrored_archive,
            eval_receipt_path(local_archive),
            eval_receipt_path(mirrored_archive),
        )
    }
    referenced_files: dict[str, bytes] = {}

    def snapshot_references(value: object) -> None:
        if isinstance(value, dict):
            path = value.get("path")
            if isinstance(path, str):
                referenced = workspace / path
                if referenced.is_file():
                    referenced_files[path] = referenced.read_bytes()
            for nested in value.values():
                snapshot_references(nested)
        elif isinstance(value, list):
            for nested in value:
                snapshot_references(nested)

    snapshot_references(read_events(local_archive))
    return tags, evidence, referenced_files


def assert_completed_state_preserved(
    workspace: Path,
    before: tuple[object, ...],
) -> None:
    before_tags, before_evidence, before_files = before
    after_tags, after_evidence, _ = completed_state_snapshot(workspace)
    assert isinstance(before_tags, dict)
    assert isinstance(after_tags, dict)
    assert all(after_tags.get(tag) == commit for tag, commit in before_tags.items())
    assert isinstance(before_evidence, dict)
    assert isinstance(after_evidence, dict)
    for path, lines in before_evidence.items():
        assert all(after_evidence[path].count(line) >= lines.count(line) for line in lines)
    assert isinstance(before_files, dict)
    assert all((workspace / path).read_bytes() == contents for path, contents in before_files.items())


def tagged_child_based_on_moved_parent(workspace: Path, tmp_path: Path) -> None:
    moved_parent = tmp_path / "moved-parent"
    fork_child(workspace, "0", moved_parent)
    parent_target = moved_parent / "target" / "agent.py"
    parent_target.write_text(parent_target.read_text() + "\n# uncertified moved parent\n")
    git(moved_parent, "add", "target/agent.py")
    git(moved_parent, "commit", "-m", "uncertified moved parent")
    moved_parent_commit = git(moved_parent, "rev-parse", "HEAD").stdout.strip()
    driver.remove_worktree(workspace, moved_parent)
    git(workspace, "tag", "-f", "gen/0", moved_parent_commit)

    child = tmp_path / "moved-parent-child"
    driver.add_worktree(workspace, child, "gen/0")
    child_target = child / "target" / "agent.py"
    child_target.write_text(child_target.read_text() + "\n# child of moved parent\n")
    git(child, "add", "target/agent.py")
    git(child, "commit", "-m", "child of moved parent")
    git(child, "tag", "gen/1")
    driver.remove_worktree(workspace, child)


def recovery_evidence_snapshot(workspace: Path) -> tuple[object, ...]:
    row = rows_by_genid(workspace)["0"]
    artifact = row.get("artifacts")
    artifact_path = artifact.get("path") if isinstance(artifact, dict) else None
    artifact_bytes = (workspace / artifact_path).read_bytes() if isinstance(artifact_path, str) else None
    return (
        (workspace / "archive.jsonl").read_bytes(),
        (workspace / ".evolve-eval-receipts.jsonl").read_bytes(),
        git(workspace, "rev-parse", "gen/0^{commit}").stdout.strip(),
        git(workspace, "rev-parse", "gen/1^{commit}").stdout.strip(),
        artifact_path,
        artifact_bytes,
    )


def test_missing_lineage_refuses_child_based_on_moved_parent_tag(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    tagged_child_based_on_moved_parent(workspace, tmp_path)
    evidence_before = recovery_evidence_snapshot(workspace)

    with pytest.raises(RuntimeError, match="Git/archive contradiction for parent gen/0"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert recovery_evidence_snapshot(workspace) == evidence_before


def test_recorded_lineage_refuses_child_based_on_moved_parent_tag(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    tagged_child_based_on_moved_parent(workspace, tmp_path)
    driver.append_event(
        workspace,
        experiment_id(workspace),
        {
            "genid": "1",
            "parent": "0",
            "tag": "gen/1",
            "mutated": ["target/agent.py"],
            "surface_violations": [],
        },
    )
    evidence_before = recovery_evidence_snapshot(workspace)

    with pytest.raises(RuntimeError, match="Git/archive contradiction for parent gen/0"):
        driver._tagged_parent(
            workspace,
            experiment_id(workspace),
            "1",
            rows_by_genid(workspace)["1"],
        )

    assert recovery_evidence_snapshot(workspace) == evidence_before


def test_tagged_candidate_recovers_missing_lineage_without_reselecting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# interrupted candidate\n")
    completed_before = completed_state_snapshot(workspace)

    real_append = driver.append_event

    def fail_lineage(*args, **kwargs):
        raise KeyboardInterrupt("after tag")

    monkeypatch.setattr(driver, "append_event", fail_lineage)
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    assert tag_exists(workspace, "gen/1")
    assert "1" not in rows_by_genid(workspace)
    assert "tagged candidate needs lineage recovery: 1" in doctor(workspace)

    monkeypatch.setattr(
        driver,
        "_select_generation_parents",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selection reran")),
    )
    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["parent"] == "0"
    assert row["mutated"] == ["target/agent.py"]
    assert row["status"] == "complete"
    assert_completed_state_preserved(workspace, completed_before)


def test_untagged_generation_discards_stale_operator_output_before_rerun(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    stale = workspace / "runs" / "gen-1" / "stale-sentinel"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("interrupted\n")
    completed_before = completed_state_snapshot(workspace)

    run(RunOptions(workspace, max_generations=1))

    assert rows_by_genid(workspace)["1"]["status"] == "complete"
    assert not stale.exists()
    assert "[evolve] discarded stale operator output for gen/1" in capsys.readouterr().out
    assert_completed_state_preserved(workspace, completed_before)


def test_tagged_candidate_starts_new_evaluation_attempt_after_partial_attempt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# candidate\n")
    commit_child(workspace, child, "0", "1")
    commit = git(workspace, "rev-parse", "gen/1^{commit}").stdout.strip()
    partial = workspace / "runs" / "evaluations" / "candidate" / "gen-1" / f"candidate-{commit}" / "attempt-1"
    partial.mkdir(parents=True)
    (partial / "partial-sentinel").write_text("interrupted\n")
    completed_before = completed_state_snapshot(workspace)

    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 2
    assert (partial / "partial-sentinel").read_text() == "interrupted\n"
    assert "[evolve] gen/1 evaluation: attempting evaluation recovery" in capsys.readouterr().out
    assert_completed_state_preserved(workspace, completed_before)


def test_unreceipted_evaluation_is_ignored_and_retried_as_a_fresh_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# candidate with interrupted receipt\n")
    commit_child(workspace, child, "0", "1")

    real_append_receipt = archive_module._append_eval_receipt
    monkeypatch.setattr(
        archive_module,
        "_append_eval_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt("before evaluation receipt")),
    )
    with pytest.raises(KeyboardInterrupt, match="before evaluation receipt"):
        driver.eval_child(workspace, "1")
    monkeypatch.setattr(archive_module, "_append_eval_receipt", real_append_receipt)

    interrupted_before = completed_state_snapshot(workspace)
    receipts_before = set(eval_receipt_path(archive_path(workspace)).read_text().splitlines())
    unreceipted = [
        event
        for event in read_events(archive_path(workspace))
        if str(event.get("genid")) == "1" and event.get(MECHANISM_EVAL_FIELD) is True
    ]
    assert [event["attempt"] for event in unreceipted] == [1]

    run(RunOptions(workspace, max_generations=1))

    evaluations = [
        event
        for event in read_events(archive_path(workspace))
        if str(event.get("genid")) == "1" and event.get(MECHANISM_EVAL_FIELD) is True
    ]
    row = rows_by_genid(workspace)["1"]
    assert [event["attempt"] for event in evaluations] == [1, 2]
    assert evaluations[1]["retry_of"] is None
    assert row["attempt"] == 2
    assert row[RECEIPT_CERTIFIED_FIELD] is True
    assert row["pending_gate_record"] is False
    receipts_after = set(eval_receipt_path(archive_path(workspace)).read_text().splitlines())
    assert receipts_before <= receipts_after
    assert archive_module._eval_receipt(evaluations[0]) not in receipts_after
    assert archive_module._eval_receipt(evaluations[1]) in receipts_after
    assert "[evolve] gen/1 evaluation: attempting evaluation recovery" in capsys.readouterr().out
    assert_completed_state_preserved(workspace, interrupted_before)


def _remove_gate_event(path: Path, genid: str) -> None:
    events = read_events(path)
    candidates = [
        index
        for index, event in enumerate(events)
        if str(event.get("genid")) == genid
        and STAMPED_FIELDS.isdisjoint(event)
        and {"valid_parent", "verdict", "reason"} <= set(event)
    ]
    assert len(candidates) == 1
    del events[candidates[0]]
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events))


def test_completed_evaluation_resumes_only_pending_gate_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    _remove_gate_event(workspace / "archive.jsonl", "1")
    _remove_gate_event(evolve_home / "mirrors" / workspace.name / "archive.jsonl", "1")
    assert rows_by_genid(workspace)["1"]["pending_gate_record"] is True
    completed_before = completed_state_snapshot(workspace)
    monkeypatch.setattr(
        driver,
        "eval_child",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("evaluation reran")),
    )
    monkeypatch.setattr(
        driver,
        "_select_generation_parents",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selection reran")),
    )

    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["pending_gate_record"] is False
    assert row["status"] == "complete"
    assert "[evolve] gen/1 gate/record: resuming" in capsys.readouterr().out
    assert_completed_state_preserved(workspace, completed_before)


def test_gate_success_keeps_transaction_pending_until_record_is_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# gate-record crash candidate\n")
    commit_child(workspace, child, "0", "1")
    driver.eval_child(workspace, "1")
    completed_before = completed_state_snapshot(workspace)
    real_terminal_record = driver._run_terminal_record
    monkeypatch.setattr(
        driver,
        "_run_terminal_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt("before record is durable")),
    )

    with pytest.raises(KeyboardInterrupt, match="before record is durable"):
        run(RunOptions(workspace, max_generations=1))

    assert rows_by_genid(workspace)["1"]["pending_gate_record"] is True
    assert "1" in driver._evaluation_pending_gate_record_genids(workspace)
    assert_completed_state_preserved(workspace, completed_before)

    monkeypatch.setattr(driver, "_run_terminal_record", real_terminal_record)
    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    events = read_events(archive_path(workspace))
    assert row["pending_gate_record"] is False
    assert row["status"] == "complete"
    assert any(str(event.get("genid")) == "1" and event.get(RECORD_ATTEMPT_FIELD) is True for event in events)
    assert capsys.readouterr().out.count("[evolve] gen/1 gate/record: resuming") == 2
    assert_completed_state_preserved(workspace, completed_before)


def test_doctor_reports_active_branch_intent(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    intent = BranchIntent(
        source_generation="0",
        source_tag="gen/0",
        source_commit=git(workspace, "rev-parse", "gen/0^{commit}").stdout.strip(),
        target_generation=1,
        target_genids=("1",),
        created_at="2026-07-28T00:00:00+00:00",
    )
    create_branch_intent(workspace, intent)

    assert "active branch intent: gen/0 -> generation 1" in doctor(workspace)


def test_tagged_candidate_refuses_archive_git_parent_contradiction(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    child = tmp_path / "child-2"
    fork_child(workspace, "1", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# child two\n")
    commit_child(workspace, child, "1", "2")
    archive_before = (workspace / "archive.jsonl").read_bytes()
    receipts_before = (workspace / ".evolve-eval-receipts.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="lineage contradiction for gen/2"):
        driver._tagged_parent(
            workspace,
            experiment_id(workspace),
            "2",
            {"parent": "0"},
        )

    assert (workspace / "archive.jsonl").read_bytes() == archive_before
    assert (workspace / ".evolve-eval-receipts.jsonl").read_bytes() == receipts_before


def test_tagged_candidate_refuses_missing_certified_git_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# interrupted candidate\n")
    real_append = driver.append_event
    monkeypatch.setattr(
        driver,
        "append_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt("after tag")),
    )
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    git(workspace, "tag", "-d", "gen/0")
    archive_before = (workspace / "archive.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="expected one certified Git parent, found none"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert (workspace / "archive.jsonl").read_bytes() == archive_before


def test_tagged_candidate_refuses_ambiguous_certified_git_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    genesis_evaluation = next(
        event
        for event in driver.read_events(driver.archive_path(workspace))
        if str(event.get("genid")) == "0" and event.get("event_type") == "evaluation"
    )
    genesis_evaluation.pop("kind", None)
    driver.append_event(
        workspace,
        experiment_id(workspace),
        {**genesis_evaluation, "genid": "9", "tag": "gen/9"},
    )
    git(workspace, "tag", "gen/9", "gen/0")
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# interrupted candidate\n")
    real_append = driver.append_event
    monkeypatch.setattr(
        driver,
        "append_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt("after tag")),
    )
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    archive_before = (workspace / "archive.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match=r"expected one certified Git parent, found gen/0, gen/9"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert (workspace / "archive.jsonl").read_bytes() == archive_before


def test_direct_parent_commit_refuses_merge_commit(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    tree = git(workspace, "rev-parse", "gen/1^{tree}").stdout.strip()
    first_parent = git(workspace, "rev-parse", "gen/0^{commit}").stdout.strip()
    second_parent = git(workspace, "rev-parse", "gen/1^{commit}").stdout.strip()
    merge = git(
        workspace,
        "commit-tree",
        tree,
        "-p",
        first_parent,
        "-p",
        second_parent,
        "-m",
        "synthetic merge",
    ).stdout.strip()

    with pytest.raises(RuntimeError, match="must have exactly one Git parent, found 2"):
        direct_parent_commit(workspace, merge)


def test_tagged_candidate_refuses_recovery_with_no_changes(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "empty-child"
    fork_child(workspace, "0", child)
    git(child, "commit", "--allow-empty", "-m", "empty candidate")
    git(child, "tag", "gen/1")
    archive_before = (workspace / "archive.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="candidate has no changes"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert (workspace / "archive.jsonl").read_bytes() == archive_before


def test_tagged_candidate_refuses_recovery_outside_mutable_surface(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "invalid-child"
    fork_child(workspace, "0", child)
    config = child / "evolve.yaml"
    config.write_text(config.read_text() + "\n# invalid candidate change\n")
    git(child, "add", "evolve.yaml")
    git(child, "commit", "-m", "invalid candidate")
    git(child, "tag", "gen/1")
    archive_before = (workspace / "archive.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="changed paths outside mutable surface: evolve.yaml"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert (workspace / "archive.jsonl").read_bytes() == archive_before
