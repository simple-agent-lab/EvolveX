import json
import sys
from pathlib import Path

import pytest

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


def test_operator_abcs_have_one_kind_specific_abstract_method():
    from evolve.frozen import interfaces

    expected = {
        interfaces.SelectOperator: {"pick"},
        interfaces.RolloutOperator: {"rollout"},
        interfaces.MetaAgentOperator: {"run"},
        interfaces.ValidateOperator: {"validate"},
        interfaces.GateOperator: {"decide"},
        interfaces.RecordOperator: {"annotate"},
    }
    for cls, methods in expected.items():
        assert cls.__abstractmethods__ == methods


def test_operator_registry_uses_meta_agent_not_mutate():
    from evolve.frozen import interfaces

    kinds = {spec.kind for spec in interfaces.OPERATORS}
    assert "meta_agent" in kinds
    assert "mutate" not in kinds
    assert hasattr(interfaces, "MetaAgentOperator")
    assert hasattr(interfaces, "MetaAgentResult")
    assert not hasattr(interfaces, "MutateOperator")
    assert not hasattr(interfaces, "MutateResult")


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


def test_sdk_main_runs_meta_agent_operator_and_writes_meta_agent_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evolve.frozen import interfaces, sdk

    class TinyMetaAgent(interfaces.MetaAgentOperator):
        def run(self, checkout, observation, ctx):
            assert checkout == tmp_path / "checkout"
            assert observation == '{"failed": ["task-1"]}\n'
            assert ctx.parent == "0"
            return interfaces.MetaAgentResult(
                changed=["target/agent.py"],
                notes=["edited target"],
                usage={"usd": 1.25},
            )

    _set_sdk_env(monkeypatch, tmp_path, parent="0")
    rollout_dir = tmp_path / "run" / "rollout"
    rollout_dir.mkdir(parents=True)
    (rollout_dir / "summary.json").write_text('{"failed": ["task-1"]}\n')

    sdk.main(TinyMetaAgent)

    meta_agent_dir = tmp_path / "run" / "meta_agent"
    assert json.loads((meta_agent_dir / "changed.json").read_text()) == ["target/agent.py"]
    assert json.loads((meta_agent_dir / "predicted_fixes.json").read_text()) == ["target/agent.py"]
    assert json.loads((meta_agent_dir / "usage.json").read_text()) == {"usd": 1.25}
    assert (meta_agent_dir / "rationale.md").read_text() == "edited target\n"


def test_sdk_main_runs_validate_operator_and_writes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
