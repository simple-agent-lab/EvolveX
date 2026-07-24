import hashlib
import importlib.util
import json
import random
from pathlib import Path

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _replay_module():
    path = ROOT / "library" / "rollout" / "evaluation_replay.py"
    spec = importlib.util.spec_from_file_location("evaluation_replay_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Archive:
    def __init__(self, rows: dict[str, dict]) -> None:
        self._rows = rows

    def row(self, genid: str) -> dict | None:
        return self._rows.get(genid)


def _context(workspace: Path, *, parent: str | None) -> OperatorContext:
    checkout = workspace / "checkout"
    checkout.mkdir(parents=True, exist_ok=True)
    return OperatorContext(
        workspace=workspace,
        checkout=checkout,
        run_dir=workspace / "runs" / "gen-5",
        genid="5",
        parent=parent,
        round=None,
        fan_out=1,
        config={"field_limit": 1200, "pass_threshold": 1.0},
        rng=random.Random(0),
    )


def _artifact(workspace: Path, *, generation: str = "3") -> tuple[Path, dict[str, str]]:
    attempt = workspace / "runs" / "evaluations" / "candidate" / f"gen-{generation}" / "attempt-1"
    jobs = attempt / "jobs"
    jobs.mkdir(parents=True)
    artifact = attempt / "evaluation_artifacts.json"
    artifact.write_text(json.dumps({"jobs_dir": str(jobs), "trials": []}))
    return jobs, {
        "path": artifact.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }


def test_replay_uses_selected_parent_certified_evaluation(tmp_path: Path, monkeypatch) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    jobs, reference = _artifact(workspace)
    rows = {
        "3": {"genid": "3", "artifacts": reference, "score": 1.0},
        "4": {"genid": "4", "artifacts": {"path": "wrong", "sha256": "wrong"}, "score": 0.0},
    }
    observed: dict[str, object] = {}

    def collect(selected_jobs: Path, **options):
        observed.update({"jobs": selected_jobs, **options})
        return [{"task_name": "task-a", "trial_name": "task-a__trial-0", "reward": 1.0, "outcome": "passed"}]

    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive(rows))
    monkeypatch.setattr(module, "_load_collect_cases", lambda _checkout: collect)
    ctx = _context(workspace, parent="3")

    result = module.EvaluationReplayRollout().rollout(ctx.checkout, ctx)

    cases = json.loads((ctx.run_dir / "rollout" / "cases.json").read_text())
    assert [case["task_name"] for case in cases] == ["task-a"]
    assert observed == {"jobs": jobs, "field_limit": 1200, "pass_threshold": 1.0}
    assert result.summary["source_parent"] == "3"
    assert result.summary["tasks_observed"] == 1
    assert result.summary["trials_observed"] == 1
    assert result.summary["mean_observed_reward"] == 1.0


def test_replay_merges_base_and_repair_artifacts_for_composite_evaluation(tmp_path: Path, monkeypatch) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    base_jobs, base_reference = _artifact(workspace, generation="3")
    repair_attempt = workspace / "runs" / "evaluations" / "candidate" / "gen-3" / "attempt-2"
    repair_jobs = repair_attempt / "jobs"
    repair_jobs.mkdir(parents=True)
    repair_artifact = repair_attempt / "evaluation_artifacts.json"
    repair_artifact.write_text(json.dumps({"jobs_dir": str(repair_jobs), "trials": []}))
    repair_reference = {
        "path": repair_artifact.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(repair_artifact.read_bytes()).hexdigest(),
    }
    composite = repair_attempt / "composite_evaluation_artifacts.json"
    composite.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "failed_task_repair",
                "base_artifacts": base_reference,
                "repair_artifacts": repair_reference,
                "replaced_slots": [
                    {
                        "task_id": "task-c",
                        "trial": 0,
                        "from_attempt": 1,
                        "to_attempt": 2,
                    }
                ],
            }
        )
    )
    composite_reference = {
        "path": composite.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(composite.read_bytes()).hexdigest(),
    }
    rows = {"3": {"genid": "3", "artifacts": composite_reference, "score": 2 / 3}}

    def collect(selected_jobs: Path, **_options):
        if selected_jobs == base_jobs:
            return [
                {
                    "task_name": "task-a",
                    "trial_name": "task-a__base",
                    "reward": 1.0,
                    "outcome": "passed",
                },
                {
                    "task_name": "task-b",
                    "trial_name": "task-b__base",
                    "reward": 0.0,
                    "outcome": "failed",
                },
                {
                    "task_name": "task-c",
                    "trial_name": "task-c__base",
                    "reward": None,
                    "outcome": "infra_error",
                },
            ]
        assert selected_jobs == repair_jobs
        return [
            {
                "task_name": "task-c",
                "trial_name": "task-c__repair",
                "reward": 1.0,
                "outcome": "passed",
            }
        ]

    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive(rows))
    monkeypatch.setattr(module, "_load_collect_cases", lambda _checkout: collect)
    ctx = _context(workspace, parent="3")

    result = module.EvaluationReplayRollout().rollout(ctx.checkout, ctx)

    cases = json.loads((ctx.run_dir / "rollout" / "cases.json").read_text())
    assert [(case["task_name"], case["trial_name"]) for case in cases] == [
        ("task-a", "task-a__base"),
        ("task-b", "task-b__base"),
        ("task-c", "task-c__repair"),
    ]
    assert result.summary["tasks_observed"] == 3
    assert result.summary["trials_observed"] == 3
    assert result.summary["mean_observed_reward"] == pytest.approx(2 / 3)


def test_replay_loads_collector_from_vendored_workspace_library(tmp_path: Path) -> None:
    module = _replay_module()
    checkout = tmp_path / "checkout"
    vendored = checkout / "library" / "rollout" / "harbor.py"
    vendored.parent.mkdir(parents=True)
    vendored.write_text((ROOT / "library" / "rollout" / "harbor.py").read_text())
    jobs = tmp_path / "jobs"
    trial = jobs / "trial-a"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "trial-a",
                "task_name": "task-a",
                "verifier_result": {"rewards": {"reward": 1.0}},
            }
        )
    )

    cases = module._load_collect_cases(checkout)(jobs)

    assert [(case["task_name"], case["outcome"]) for case in cases] == [("task-a", "passed")]


@pytest.mark.parametrize(
    ("parent", "row", "message"),
    [
        (None, None, "evaluation replay requires a selected parent"),
        ("3", None, "selected parent 3 is missing from archive"),
        ("3", {"genid": "3"}, "selected parent 3 has no certified evaluation artifacts"),
        (
            "3",
            {"genid": "3", "artifacts": {"path": "missing.json", "sha256": "0" * 64}},
            "artifact path is missing",
        ),
    ],
)
def test_replay_rejects_missing_parent_evidence(tmp_path: Path, monkeypatch, parent, row, message: str) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    rows = {} if row is None else {"3": row}
    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive(rows))

    with pytest.raises(SystemExit, match=message):
        module.EvaluationReplayRollout().rollout(
            _context(workspace, parent=parent).checkout, _context(workspace, parent=parent)
        )


def test_replay_rejects_artifact_digest_mismatch(tmp_path: Path, monkeypatch) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    _jobs, reference = _artifact(workspace)
    reference["sha256"] = "0" * 64
    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive({"3": {"artifacts": reference}}))
    ctx = _context(workspace, parent="3")

    with pytest.raises(SystemExit, match="artifact digest mismatch"):
        module.EvaluationReplayRollout().rollout(ctx.checkout, ctx)


def test_replay_rejects_jobs_path_without_trial_results(tmp_path: Path, monkeypatch) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    _jobs, reference = _artifact(workspace)
    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive({"3": {"artifacts": reference}}))
    monkeypatch.setattr(module, "_load_collect_cases", lambda _checkout: lambda *_args, **_kwargs: [])
    ctx = _context(workspace, parent="3")

    with pytest.raises(SystemExit, match="produced no trial results"):
        module.EvaluationReplayRollout().rollout(ctx.checkout, ctx)
