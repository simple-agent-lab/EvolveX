import importlib.util
import json
import random
from pathlib import Path

from evolve.composition.catalog import resolve_operator, validate_operator_config
from evolve.frozen.interfaces import OperatorContext, RolloutResult

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(tmp_path: Path, config=None):
    run_dir = tmp_path / "runs/gen-1"
    return OperatorContext(
        workspace=tmp_path,
        checkout=tmp_path,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config=config or {},
        rng=random.Random(0),
    )


def test_gepa_validation_replays_exact_parent_minibatch_and_accepts_improvement(tmp_path: Path, monkeypatch) -> None:
    module = _module("gepa_validate_under_test", ROOT / "library/validate/minibatch_improvement.py")
    ctx = _ctx(tmp_path, {"criterion": "strict", "n_concurrent": 2})
    parent_cases = [
        {"task_name": "task-a", "outcome": "failed", "reward": 0},
        {"task_name": "task-b", "outcome": "passed", "reward": 1},
    ]
    parent_path = ctx.run_dir / "rollout/cases.json"
    parent_path.parent.mkdir(parents=True)
    parent_path.write_text(json.dumps(parent_cases))

    class FakeRollout:
        def rollout(self, _checkout, child_ctx):
            assert child_ctx.config["task_names"] == ["task-a", "task-b"]
            assert child_ctx.config["budget_tasks"] == 2
            root = child_ctx.run_dir / "rollout"
            root.mkdir(parents=True)
            root.joinpath("cases.json").write_text(
                json.dumps(
                    [
                        {"task_name": "task-a", "outcome": "passed", "reward": 1},
                        {"task_name": "task-b", "outcome": "passed", "reward": 1},
                    ]
                )
            )
            root.joinpath("harbor.log").write_text("ok\n")
            return RolloutResult(summary={"infra_errors": 0}, artifacts=["rollout/cases.json"])

    monkeypatch.setattr(module, "HarborRollout", FakeRollout)
    result = module.MinibatchImprovementValidate().validate(tmp_path, ctx)

    assert result.accept is True
    comparison = json.loads((ctx.run_dir / "validate/comparison.json").read_text())
    assert comparison["parent_total"] == 1
    assert comparison["child_total"] == 2
    assert comparison["delta"] == 1


def test_gepa_validation_preserves_harbor_retry_fallback_when_omitted(tmp_path: Path, monkeypatch) -> None:
    module = _module("gepa_validate_retry_under_test", ROOT / "library/validate/minibatch_improvement.py")
    harbor = _module("harbor_retry_under_test", ROOT / "library/_shared/harbor.py")
    normalized = validate_operator_config(
        resolve_operator("validate", "minibatch_improvement"), {"criterion": "strict"}
    )
    ctx = _ctx(tmp_path, normalized)
    parent_path = ctx.run_dir / "rollout/cases.json"
    parent_path.parent.mkdir(parents=True)
    parent_path.write_text(json.dumps([{"task_name": "task-a", "outcome": "failed", "reward": 0}]))
    effective_retries: list[int] = []

    class FakeRollout:
        def rollout(self, _checkout, child_ctx):
            effective_retries.append(
                harbor._configured_max_retries(child_ctx.config, {"EVOLVE_HARBOR_MAX_RETRIES": "4"})
            )
            root = child_ctx.run_dir / "rollout"
            root.mkdir(parents=True)
            root.joinpath("cases.json").write_text(
                json.dumps([{"task_name": "task-a", "outcome": "passed", "reward": 1}])
            )
            root.joinpath("harbor.log").write_text("ok\n")
            return RolloutResult(summary={"infra_errors": 0}, artifacts=["rollout/cases.json"])

    monkeypatch.setattr(module, "HarborRollout", FakeRollout)

    module.MinibatchImprovementValidate().validate(tmp_path, ctx)

    assert effective_retries == [4]


def test_gepa_validation_excludes_infra_scores_and_rejects_incomplete_comparison(tmp_path: Path, monkeypatch) -> None:
    module = _module("gepa_validate_infra_under_test", ROOT / "library/validate/minibatch_improvement.py")
    ctx = _ctx(tmp_path, {"criterion": "strict", "n_concurrent": 2})
    parent_cases = [
        {"task_name": "task-a", "outcome": "infra_error", "reward": None},
        {"task_name": "task-b", "outcome": "passed", "reward": 1},
    ]
    parent_path = ctx.run_dir / "rollout/cases.json"
    parent_path.parent.mkdir(parents=True)
    parent_path.write_text(json.dumps(parent_cases))

    class FakeRollout:
        def rollout(self, _checkout, child_ctx):
            assert child_ctx.config["task_names"] == ["task-a", "task-b"]
            assert child_ctx.config["budget_tasks"] == 2
            root = child_ctx.run_dir / "rollout"
            root.mkdir(parents=True)
            root.joinpath("cases.json").write_text(
                json.dumps(
                    [
                        {"task_name": "task-a", "outcome": "passed", "reward": 1},
                        {"task_name": "task-b", "outcome": "incomplete", "reward": None},
                    ]
                )
            )
            root.joinpath("harbor.log").write_text("one missing result\n")
            return RolloutResult(summary={"infra_errors": 1}, artifacts=["rollout/cases.json"])

    monkeypatch.setattr(module, "HarborRollout", FakeRollout)
    result = module.MinibatchImprovementValidate().validate(tmp_path, ctx)

    comparison = json.loads((ctx.run_dir / "validate/comparison.json").read_text())
    assert result.accept is False
    assert comparison["parent_total"] == comparison["child_total"] == 1
    assert comparison["parent_scores"] == {"task-b": 1.0}
    assert comparison["child_scores"] == {"task-a": 1.0}
    assert comparison["comparison_complete"] is False
    assert comparison["parent_infra_cases"] == ["task-a"]
    assert comparison["child_infra_cases"] == ["task-b"]
    assert "incomplete" in result.reason


def test_gepa_validation_cannot_accept_apparent_improvement_with_parent_infra(tmp_path: Path, monkeypatch) -> None:
    module = _module("gepa_validate_parent_infra_under_test", ROOT / "library/validate/minibatch_improvement.py")
    ctx = _ctx(tmp_path, {"criterion": "strict", "n_concurrent": 2})
    parent_path = ctx.run_dir / "rollout/cases.json"
    parent_path.parent.mkdir(parents=True)
    parent_path.write_text(
        json.dumps(
            [
                {"task_name": "task-a", "outcome": "infra_error", "reward": None},
                {"task_name": "task-b", "outcome": "failed", "reward": 0},
            ]
        )
    )

    class FakeRollout:
        def rollout(self, _checkout, child_ctx):
            root = child_ctx.run_dir / "rollout"
            root.mkdir(parents=True)
            root.joinpath("cases.json").write_text(
                json.dumps(
                    [
                        {"task_name": "task-a", "outcome": "passed", "reward": 1},
                        {"task_name": "task-b", "outcome": "passed", "reward": 1},
                    ]
                )
            )
            root.joinpath("harbor.log").write_text("ok\n")
            return RolloutResult(summary={"infra_errors": 0}, artifacts=["rollout/cases.json"])

    monkeypatch.setattr(module, "HarborRollout", FakeRollout)
    result = module.MinibatchImprovementValidate().validate(tmp_path, ctx)

    comparison = json.loads((ctx.run_dir / "validate/comparison.json").read_text())
    assert comparison["delta"] == 2
    assert comparison["comparison_complete"] is False
    assert comparison["accepted"] is False
    assert result.accept is False


def test_gepa_record_points_to_evidence_and_comparison(tmp_path: Path) -> None:
    module = _module("gepa_record_under_test", ROOT / "library/record/gepa.py")
    ctx = _ctx(tmp_path)
    proposal = ctx.run_dir / "mutate/proposal.json"
    proposal.parent.mkdir(parents=True)
    proposal.write_text(json.dumps({"components": ["prompt"], "paths": ["target/prompt.md"]}))
    comparison = ctx.run_dir / "validate/comparison.json"
    comparison.parent.mkdir(parents=True)
    comparison.write_text(
        json.dumps({"criterion": "strict", "parent_total": 1, "child_total": 2, "delta": 1, "accepted": True})
    )
    dataset = ctx.run_dir / "analyze/evidence/reflective_dataset.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text("{}\n")

    result = module.GepaRecord().annotate({"genid": "1", "parent": "0", "score": 0.5}, ctx)

    assert result.fields["gepa"]["components"] == ["prompt"]
    assert result.fields["gepa"]["train_delta"] == 1
    experience = json.loads((ctx.run_dir / "record/gepa-experience.json").read_text())
    assert experience["artifacts"]["reflective_dataset"].endswith("reflective_dataset.json")
