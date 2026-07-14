import json
import sys
from pathlib import Path

import pytest


def test_operator_abcs_have_one_kind_specific_abstract_method():
    from evolve.frozen import interfaces

    expected = {
        interfaces.SelectOperator: {"pick"},
        interfaces.RolloutOperator: {"rollout"},
        interfaces.MutateOperator: {"mutate"},
        interfaces.GateOperator: {"decide"},
        interfaces.RecordOperator: {"annotate"},
    }
    for cls, methods in expected.items():
        assert cls.__abstractmethods__ == methods


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
        (workspace / ".evolve-protocol-version").write_text("2\n")
    monkeypatch.setenv("EVOLVE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EVOLVE_CHECKOUT", str(checkout))
    monkeypatch.setenv("EVOLVE_RUN_DIR", str(run_dir))
    monkeypatch.setenv("EVOLVE_GENID", genid)
    monkeypatch.setenv("EVOLVE_PARENT", parent)
    monkeypatch.setattr(sys, "argv", ["operator.py", "--config", json.dumps(config or {})])
