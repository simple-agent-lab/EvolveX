from pathlib import Path

import pytest

from evolve import workspace as workspace_module
from evolve.evaluation import Outcome
from evolve.evaluator import evaluate
from evolve.runtime import attempt_dir
from evolve.workspace import InitOptions, init_workspace


def test_attempt_paths_never_replace_prior_evidence(tmp_path: Path) -> None:
    first = attempt_dir(
        tmp_path,
        purpose="candidate",
        generation="7",
        candidate_commit="abc",
        attempt=1,
    )
    first.mkdir(parents=True)
    (first / "marker").write_text("first")

    second = attempt_dir(
        tmp_path,
        purpose="candidate",
        generation="7",
        candidate_commit="abc",
        attempt=2,
    )

    assert first == tmp_path / "runs/evaluations/candidate/gen-7/candidate-abc/attempt-1"
    assert second != first
    assert (first / "marker").read_text() == "first"
    with pytest.raises(FileExistsError, match="attempt already exists"):
        attempt_dir(
            tmp_path,
            purpose="candidate",
            generation="7",
            candidate_commit="abc",
            attempt=1,
        )


@pytest.mark.parametrize("value", ["../escape", "a/b", "", "."])
def test_attempt_identity_rejects_unsafe_path_components(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        attempt_dir(
            tmp_path,
            purpose=value,
            generation="7",
            candidate_commit="abc",
            attempt=1,
        )


def test_harbor_init_requires_evaluator_runtime_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVOLVE_RUNTIME_DIGEST")

    with pytest.raises(ValueError, match="EVOLVE_RUNTIME_DIGEST.*evaluator capsule"):
        init_workspace(InitOptions(workspace=tmp_path / "workspace", recipe="hill_climb-smoke"))


def test_init_commits_evaluator_owned_runtime_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLVE_RUNTIME_DIGEST", "sha256:immutable-evaluator")
    workspace = tmp_path / "workspace"

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb-smoke"))

    assert (workspace / "evaluator/runtime.pin").read_text() == "sha256:immutable-evaluator\n"
    assert not (workspace / "target/runtime.pin").exists()


def test_default_expected_trials_match_generated_evaluator_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = workspace_module.default_config("hill_climb-smoke", "workspace")
    config["evaluator"].pop("tasks_per_round")
    config["evaluator"]["k"] = 2
    monkeypatch.setattr(workspace_module, "default_config", lambda _recipe, _experiment: config)
    monkeypatch.setenv("EVAL_STUB", "1")
    workspace = tmp_path / "workspace"
    workspace_module.init_workspace(workspace_module.InitOptions(workspace, "hill_climb-smoke"))

    record = evaluate(workspace, "gen/0", "0", purpose="genesis")

    assert record.outcome is Outcome.BENCHMARK_COMPLETE
    assert record.expected_trials == 4
    assert len(record.trials) == 4
