import importlib.util
import json
import random
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("ahe_gate_test", ROOT / "library/gate/ahe_artifact_valid.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ahe_gate_accepts_lower_score_with_valid_manifest(tmp_path: Path) -> None:
    ctx = OperatorContext(tmp_path, tmp_path, tmp_path / "run", "2", "1", None, 1, {}, random.Random(0))
    path = ctx.run_dir / "meta_agent" / "change_manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"iteration": 2, "changes": [{"id": "chg-1"}]}))
    child = {"outcome": "benchmark_complete", "selection_eligible": True, "score": 0.1}
    assert _module().AheArtifactValidGate().decide(child, {"score": 0.9}, ctx).decision == "accept"


def test_ahe_gate_accepts_canonical_child_without_valid_manifest(tmp_path: Path) -> None:
    ctx = OperatorContext(tmp_path, tmp_path, tmp_path / "run", "2", "1", None, 1, {}, random.Random(0))
    child = {"outcome": "benchmark_complete", "selection_eligible": True}
    gate = _module().AheArtifactValidGate()
    assert gate.decide(child, None, ctx).decision == "accept"
    path = ctx.run_dir / "meta_agent" / "change_manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"iteration": 9, "changes": [{"id": "chg-1"}]}))
    assert gate.decide(child, None, ctx).decision == "accept"


def test_ahe_gate_rejects_incomplete_canonical_evaluation(tmp_path: Path) -> None:
    ctx = OperatorContext(tmp_path, tmp_path, tmp_path / "run", "2", "1", None, 1, {}, random.Random(0))
    gate = _module().AheArtifactValidGate()
    assert gate.decide({"outcome": "benchmark_failed", "selection_eligible": True}, None, ctx).decision == "reject"
    assert gate.decide({"outcome": "benchmark_complete", "selection_eligible": False}, None, ctx).decision == "reject"
