import json
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, smoke_agent_command

from evolve import driver
from evolve.config import experiment_id
from evolve.driver import RunOptions, commit_child, fork_child, run
from evolve.git import direct_parent_commit, git, tag_exists


@pytest.fixture(autouse=True)
def smoke_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())


def completed_generation_snapshot(workspace: Path, genid: str = "0") -> tuple[object, ...]:
    row = rows_by_genid(workspace)[genid]
    artifact = row.get("artifacts")
    artifact_path = None
    artifact_bytes = None
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
        artifact_path = artifact["path"]
        artifact_bytes = (workspace / artifact_path).read_bytes()
    receipts = workspace / ".evolve-eval-receipts.jsonl"
    archive_events = tuple(
        line
        for line in (workspace / "archive.jsonl").read_text().splitlines()
        if str(json.loads(line).get("genid")) == genid
    )
    return (
        git(workspace, "rev-parse", f"gen/{genid}^{{commit}}").stdout.strip(),
        archive_events,
        tuple(receipts.read_text().splitlines()),
        artifact_path,
        artifact_bytes,
    )


def assert_completed_generation_preserved(
    workspace: Path,
    before: tuple[object, ...],
    genid: str = "0",
) -> None:
    before_commit, before_events, before_receipts, artifact_path, before_artifact = before
    after_commit, after_events, after_receipts, _, _ = completed_generation_snapshot(workspace, genid)
    assert after_commit == before_commit
    assert isinstance(before_events, tuple)
    assert isinstance(after_events, tuple)
    assert all(after_events.count(event) >= before_events.count(event) for event in before_events)
    assert isinstance(before_receipts, tuple)
    assert isinstance(after_receipts, tuple)
    assert all(after_receipts.count(receipt) >= before_receipts.count(receipt) for receipt in before_receipts)
    if isinstance(artifact_path, str):
        assert (workspace / artifact_path).read_bytes() == before_artifact
    else:
        assert artifact_path is None
        assert before_artifact is None


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
    completed_before = completed_generation_snapshot(workspace)

    real_append = driver.append_event

    def fail_lineage(*args, **kwargs):
        raise KeyboardInterrupt("after tag")

    monkeypatch.setattr(driver, "append_event", fail_lineage)
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    assert tag_exists(workspace, "gen/1")
    assert "1" not in rows_by_genid(workspace)

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
    assert_completed_generation_preserved(workspace, completed_before)


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
