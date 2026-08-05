import importlib.util
import random
from pathlib import Path

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "gate" / "hillclimb.py"
    spec = importlib.util.spec_from_file_location("hillclimb_gate_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(tmp_path: Path, strict: object) -> OperatorContext:
    return OperatorContext(
        workspace=tmp_path,
        checkout=tmp_path,
        run_dir=tmp_path / "runs" / "gen-1",
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"strict": strict},
        rng=random.Random(0),
    )


def test_hillclimb_strict_requires_actual_improvement(tmp_path: Path) -> None:
    module = _module()
    child = {"score": 0.5, "task_set_hash": "same"}
    parent = {"score": 0.5, "task_set_hash": "same"}

    strict = module.HillclimbGate().decide(child, parent, _ctx(tmp_path, True))
    non_strict = module.HillclimbGate().decide(child, parent, _ctx(tmp_path, False))

    assert strict.decision == "reject"
    assert "<=" in strict.reason
    assert non_strict.decision == "accept"
    assert ">=" in non_strict.reason


def test_hillclimb_strict_must_be_boolean(tmp_path: Path) -> None:
    module = _module()

    with pytest.raises(ValueError, match="strict must be a boolean"):
        module.HillclimbGate().decide({"score": 1}, {"score": 0}, _ctx(tmp_path, "true"))
