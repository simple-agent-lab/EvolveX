from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, run_evolve, smoke_agent_command

from evolve import driver
from evolve.archive import archive_path
from evolve.branching import BranchIntent, branch_intent_path, create_branch_intent, load_branch_intent
from evolve.driver import RunOptions, commit_child, fork_child, run
from evolve.git import git_stdout


@pytest.fixture(autouse=True)
def smoke_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())


def test_run_branches_next_generation_from_certified_prior_parent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    branched = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "3",
        "--from-generation",
        "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert branched.returncode == 0, branched.stderr
    assert rows_by_genid(workspace)["3"]["parent"] == "0"
    assert rows_by_genid(workspace)["2"]["parent"] == "0"
    assert load_branch_intent(workspace) is None
    assert "[evolve] branch intent created: gen/0 -> generation 3" in branched.stdout
    assert "[evolve] branch intent consumed: generation 3" in branched.stdout


def test_branch_refuses_non_certified_parent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        "--from-generation",
        "99",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 1
    assert "unknown parent: 99" in result.stderr


def persisted_intent(workspace: Path, source: str, target: int, genids: tuple[str, ...]) -> BranchIntent:
    return create_branch_intent(
        workspace,
        BranchIntent(
            source_generation=source,
            source_tag=f"gen/{source}",
            source_commit=git_stdout(workspace, "rev-parse", f"gen/{source}^{{commit}}"),
            target_generation=target,
            target_genids=genids,
            created_at="2026-07-28T00:00:00+00:00",
        ),
    )


def test_existing_branch_intent_resumes_without_repeating_cli_flag(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr
    persisted_intent(workspace, "0", 3, ("3",))

    resumed = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "3",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert resumed.returncode == 0, resumed.stderr
    assert rows_by_genid(workspace)["3"]["parent"] == "0"
    assert load_branch_intent(workspace) is None
    assert "[evolve] branch intent resumed: gen/0 -> generation 3" in resumed.stdout
    assert "[evolve] branch intent consumed: generation 3" in resumed.stdout


def test_conflicting_branch_request_preserves_existing_intent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr
    persisted_intent(workspace, "0", 3, ("3",))
    before = branch_intent_path(workspace).read_bytes()

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "3",
        "--from-generation",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 1
    assert "conflicting branch intent" in result.stderr
    assert branch_intent_path(workspace).read_bytes() == before


def test_branch_requires_max_generations_to_reach_target(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        "--from-generation",
        "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 1
    assert "--max-generations must be at least 3" in result.stderr
    assert load_branch_intent(workspace) is None


def test_multi_child_branch_forces_every_target_child(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        "--children-per-gen",
        "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "2",
        "--children-per-gen",
        "2",
        "--from-generation",
        "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    assert rows["2-0"]["parent"] == "0"
    assert rows["2-1"]["parent"] == "0"
    assert load_branch_intent(workspace) is None
    assert "[evolve] branch intent created: gen/0 -> generation 2" in result.stdout
    assert "[evolve] branch intent consumed: generation 2" in result.stdout


def test_multi_child_branch_intent_survives_partial_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1, children_per_gen=2))
    source_commit = git_stdout(workspace, "rev-parse", "gen/0^{commit}")
    create_branch_intent(
        workspace,
        BranchIntent(
            source_generation="0",
            source_tag="gen/0",
            source_commit=source_commit,
            target_generation=2,
            target_genids=("2-0", "2-1"),
            created_at="2026-07-28T00:00:00+00:00",
        ),
    )
    real_run_child = driver._run_child

    def interrupt_second(*args, **kwargs):
        genid = args[2]
        if genid == "2-1":
            raise KeyboardInterrupt("between branch children")
        return real_run_child(*args, **kwargs)

    monkeypatch.setattr(driver, "_run_child", interrupt_second)
    with pytest.raises(KeyboardInterrupt, match="between branch children"):
        run(RunOptions(workspace, max_generations=2, children_per_gen=2))
    assert rows_by_genid(workspace)["2-0"]["parent"] == "0"
    assert load_branch_intent(workspace) is not None

    monkeypatch.setattr(driver, "_run_child", real_run_child)
    run(RunOptions(workspace, max_generations=2, children_per_gen=2))

    assert rows_by_genid(workspace)["2-1"]["parent"] == "0"
    assert load_branch_intent(workspace) is None


def test_new_branch_refuses_existing_unfinished_tagged_generation(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    child = tmp_path / "unfinished-child"
    fork_child(workspace, "1", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# unevaluated\n")
    commit_child(workspace, child, "1", "2")

    with pytest.raises(RuntimeError, match="generations need recovery: gen/2"):
        run(
            RunOptions(
                workspace,
                max_generations=3,
                from_generation="0",
            )
        )


def test_branch_rejects_source_tag_that_contradicts_certified_commit(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    certified_commit = str(rows_by_genid(workspace)["0"]["candidate_commit"])
    assert git_stdout(workspace, "rev-parse", "gen/0^{commit}") == certified_commit
    driver.git(workspace, "tag", "-f", "gen/0", "gen/1")

    with pytest.raises(RuntimeError, match="Git/archive contradiction for parent gen/0"):
        run(RunOptions(workspace, max_generations=2, from_generation="0"))

    assert load_branch_intent(workspace) is None


def test_completed_intent_refuses_target_with_contradictory_parent(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=2))
    intent = persisted_intent(workspace, "1", 2, ("2",))
    archive_before = archive_path(workspace).read_bytes()

    with pytest.raises(RuntimeError, match="branch intent target parent mismatch for gen/2"):
        run(RunOptions(workspace, max_generations=2))

    assert load_branch_intent(workspace) == intent
    assert archive_path(workspace).read_bytes() == archive_before


def test_matching_branch_request_resumes_after_tag_before_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    real_eval_child = driver.eval_child

    def interrupt_after_tag(*args, **kwargs):
        raise KeyboardInterrupt("after target tag")

    monkeypatch.setattr(driver, "eval_child", interrupt_after_tag)
    with pytest.raises(KeyboardInterrupt, match="after target tag"):
        run(RunOptions(workspace, max_generations=2, from_generation="0"))
    intent = load_branch_intent(workspace)
    assert intent is not None
    assert intent.target_genids == ("2",)
    assert git_stdout(workspace, "rev-parse", "gen/2^{commit}")

    monkeypatch.setattr(driver, "eval_child", real_eval_child)
    run(RunOptions(workspace, max_generations=2, from_generation="0"))

    assert rows_by_genid(workspace)["2"]["parent"] == "0"
    assert load_branch_intent(workspace) is None


def test_active_intent_rejects_mismatched_source_tag(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    source_commit = git_stdout(workspace, "rev-parse", "gen/0^{commit}")
    intent = BranchIntent(
        source_generation="0",
        source_tag="gen/not-0",
        source_commit=source_commit,
        target_generation=2,
        target_genids=("2",),
        created_at="2026-07-28T00:00:00+00:00",
    )
    create_branch_intent(workspace, intent)

    with pytest.raises(RuntimeError, match="branch intent source tag mismatch"):
        run(RunOptions(workspace, max_generations=2))

    assert load_branch_intent(workspace) == intent
