import json
import sys
from pathlib import Path

import pytest

from evolve.frozen import sdk
from evolve.frozen.interfaces import (
    PayloadValidationError,
    ValidateOperator,
    ValidateResult,
    validate_gate_file_payload,
    validate_novelty_payload,
)
from evolve.operators import run_operator


def test_operator_abcs_have_one_kind_specific_abstract_method():
    from evolve.frozen import interfaces

    expected = {
        interfaces.SelectOperator: {"pick"},
        interfaces.RolloutOperator: {"rollout"},
        interfaces.AnalyzeOperator: {"analyze"},
        interfaces.MutateOperator: {"mutate"},
        interfaces.ValidateOperator: {"validate"},
        interfaces.GateOperator: {"decide"},
        interfaces.RecordOperator: {"annotate"},
    }
    for cls, methods in expected.items():
        assert cls.__abstractmethods__ == methods


def test_operator_registry_uses_only_canonical_stage_names() -> None:
    from evolve.frozen import interfaces

    assert tuple(spec.kind for spec in interfaces.OPERATORS) == (
        "select",
        "rollout",
        "analyze",
        "mutate",
        "validate",
        "novelty",
        "gate",
        "record",
        "reflect",
    )
    assert hasattr(interfaces, "AnalyzeOperator")
    assert hasattr(interfaces, "MutateOperator")
    assert not hasattr(interfaces, "TraceAnalyzerOperator")
    assert not hasattr(interfaces, "MetaAgentOperator")


@pytest.mark.parametrize(
    ("valid_parent", "verdict"),
    [(True, "discard"), (False, "keep")],
)
def test_gate_file_rejects_contradictory_parent_decision(valid_parent: bool, verdict: str) -> None:
    with pytest.raises(PayloadValidationError, match="must agree"):
        validate_gate_file_payload({"valid_parent": valid_parent, "verdict": verdict, "reason": "contradictory"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_operator_payloads_reject_non_finite_numbers(value: float) -> None:
    from evolve.frozen import interfaces

    with pytest.raises(PayloadValidationError, match="finite number"):
        validate_novelty_payload({"novelty": value, "accept": True})
    with pytest.raises(PayloadValidationError, match="finite number"):
        interfaces.validate_mutate_usage_payload({"usd": value})


def test_sdk_main_runs_select_operator_and_writes_parents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from evolve.frozen import interfaces, sdk

    class TinySelect(interfaces.SelectOperator):
        def pick(self, archive, ctx):
            assert archive.rows() == []
            assert ctx.workspace == tmp_path / "ws"
            assert ctx.checkout == tmp_path / "checkout"
            assert ctx.run_dir == tmp_path / "run"
            assert ctx.genid == "5"
            assert ctx.parent is None
            assert ctx.fan_out == 3
            assert ctx.config == {"seed": 123, "fan_out": 3}
            return interfaces.SelectResult(parents=["0"])

    _set_sdk_env(monkeypatch, tmp_path, genid="5", config={"seed": 123, "fan_out": 3})

    sdk.main(TinySelect)

    assert json.loads((tmp_path / "run" / "parents.json").read_text()) == {"parents": ["0"]}


def test_sdk_rng_is_reproducible_for_same_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sdk_env(monkeypatch, tmp_path, genid="5", parent="2", config={"seed": 123})
    first_rng = sdk._context({"seed": 123}).rng
    second_rng = sdk._context({"seed": 123}).rng

    assert [first_rng.random() for _ in range(3)] == [second_rng.random() for _ in range(3)]


def test_sdk_rng_varies_by_generation_and_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sdk_env(monkeypatch, tmp_path, genid="5", parent="2", config={"seed": 123})
    original = sdk._context({"seed": 123}).rng.random()
    monkeypatch.setenv("EVOLVE_GENID", "6")
    by_generation = sdk._context({"seed": 123}).rng.random()
    monkeypatch.setenv("EVOLVE_GENID", "5")
    monkeypatch.setenv("EVOLVE_PARENT", "3")
    by_parent = sdk._context({"seed": 123}).rng.random()

    assert len({original, by_generation, by_parent}) == 3


def test_sdk_rng_accepts_string_generation_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_sdk_env(monkeypatch, tmp_path, genid="candidate-a", parent="root", config={"seed": 0})

    assert isinstance(sdk._context({"seed": 0}).rng.random(), float)


def test_sdk_main_runs_analyze_operator_and_writes_analyze_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evolve.frozen import interfaces, sdk

    class TinyAnalyze(interfaces.AnalyzeOperator):
        def analyze(self, checkout: Path, ctx):
            assert checkout == tmp_path / "checkout"
            return interfaces.AnalyzeResult(summary={"failed": ["task-1"]}, artifacts=["evidence/task-1.log"])

    _set_sdk_env(monkeypatch, tmp_path)

    sdk.main(TinyAnalyze)

    analyze_dir = tmp_path / "run" / "analyze"
    assert json.loads((analyze_dir / "summary.json").read_text()) == {"failed": ["task-1"]}
    assert json.loads((analyze_dir / "artifacts.json").read_text()) == ["evidence/task-1.log"]


def test_sdk_main_runs_mutate_operator_and_writes_mutate_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evolve.frozen import interfaces, sdk

    class TinyMutate(interfaces.MutateOperator):
        def mutate(self, checkout, observation, ctx):
            assert checkout == tmp_path / "checkout"
            assert observation == '{"failed": ["task-1"]}\n'
            assert ctx.parent == "0"
            return interfaces.MutateResult(
                changed=["target/agent.py"],
                notes=["edited target"],
                usage={"usd": 1.25},
            )

    _set_sdk_env(monkeypatch, tmp_path, parent="0")
    rollout_dir = tmp_path / "run" / "rollout"
    rollout_dir.mkdir(parents=True)
    (rollout_dir / "summary.json").write_text('{"failed": ["task-1"]}\n')

    sdk.main(TinyMutate)

    mutate_dir = tmp_path / "run" / "mutate"
    assert json.loads((mutate_dir / "changed.json").read_text()) == ["target/agent.py"]
    assert not (mutate_dir / "predicted_fixes.json").exists()
    assert json.loads((mutate_dir / "usage.json").read_text()) == {"usd": 1.25}
    assert (mutate_dir / "rationale.md").read_text() == "edited target\n"


def test_sdk_main_runs_validate_operator_and_writes_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    _set_sdk_env(monkeypatch, tmp_path)

    class TinyValidate(ValidateOperator):
        def validate(self, checkout: Path, ctx) -> ValidateResult:
            return ValidateResult(accept=True, reason="imports pass", artifacts=["validate/imports.log"])

    sdk.main(TinyValidate)

    assert json.loads((run_dir / "validate" / "result.json").read_text()) == {
        "accept": True,
        "artifacts": ["validate/imports.log"],
        "reason": "imports pass",
    }


def test_historical_prediction_fields_remain_readable_as_unknown_archive_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evolve.frozen.interfaces import ArchiveView

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "home"))
    (workspace / "evolve.yaml").write_text("experiment:\n  id: historical\n")
    (workspace / "archive.jsonl").write_text(
        '{"genid":"old","predicted_fixes":["task-1"],"verified_fixes":["task-1"]}\n'
    )

    row = ArchiveView(workspace).row("old")

    assert row is not None
    assert row["predicted_fixes"] == ["task-1"]
    assert row["verified_fixes"] == ["task-1"]


def test_run_operator_can_use_trusted_operator_source_with_candidate_context(tmp_path: Path) -> None:
    candidate_checkout = tmp_path / "candidate"
    operator_checkout = tmp_path / "trusted"
    workspace = tmp_path / "ws"
    run_dir = tmp_path / "run"
    (candidate_checkout / "target").mkdir(parents=True)
    (operator_checkout / "operators").mkdir(parents=True)
    workspace.mkdir()
    (operator_checkout / "operators" / "record.py").write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        "Path(os.environ['EVOLVE_RUN_DIR']).mkdir(parents=True, exist_ok=True)\n"
        "Path(os.environ['EVOLVE_RUN_DIR'], 'probe.json').write_text(json.dumps({\n"
        "    'checkout': os.environ['EVOLVE_CHECKOUT'],\n"
        "    'cwd': os.getcwd(),\n"
        "    'script': __file__,\n"
        "}))\n"
    )

    result = run_operator(
        name="record",
        checkout=candidate_checkout,
        operator_checkout=operator_checkout,
        workspace=workspace,
        genid="1",
        parent="0",
        run_dir=run_dir,
        config_block={},
        timeout_s=30,
    )

    assert result.returncode == 0, result.stderr
    probe = json.loads((run_dir / "probe.json").read_text())
    assert probe == {
        "checkout": str(candidate_checkout.resolve()),
        "cwd": str(candidate_checkout.resolve()),
        "script": str((operator_checkout / "operators" / "record.py").resolve()),
    }


def _set_sdk_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    genid: str = "1",
    parent: str = "",
    config: dict[str, object] | None = None,
    write_protocol_marker: bool = True,
) -> None:
    workspace = tmp_path / "ws"
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "run"
    workspace.mkdir()
    checkout.mkdir()
    if write_protocol_marker:
        (workspace / ".evolve-protocol-version").write_text("1\n")
    monkeypatch.setenv("EVOLVE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EVOLVE_CHECKOUT", str(checkout))
    monkeypatch.setenv("EVOLVE_RUN_DIR", str(run_dir))
    monkeypatch.setenv("EVOLVE_GENID", genid)
    monkeypatch.setenv("EVOLVE_PARENT", parent)
    monkeypatch.setattr(sys, "argv", ["operator.py", "--config", json.dumps(config or {})])
