import hashlib
import importlib.util
import json
import random
import shutil
import sys
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ctx(workspace: Path, run_dir: Path) -> OperatorContext:
    return OperatorContext(
        workspace=workspace,
        checkout=workspace,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={},
        rng=random.Random(0),
    )


def _vector() -> dict[str, object]:
    return {
        "schema_version": 1,
        "tasks": {"task-1": {"trials": [{"trial": 0, "status": "benchmark_complete", "reward": 1.0}]}},
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generation": "1",
        "parent": "0",
        "decision": "revise",
        "changes": [
            {
                "id": "change-1",
                "type": "improvement",
                "files": ["target/agent.py"],
                "failure_evidence": [{"task_id": "task-1", "report": "rollout/analysis/detail/task-1.md"}],
                "root_cause": "The tool call is malformed.",
                "targeted_fix": "Normalize tool arguments.",
                "predicted_fixes": ["task-2", "task-1", "task-1"],
                "risk_tasks": ["task-3", "task-3"],
                "component_level": "tool",
            }
        ],
        "validation": {"status": "passed", "commands": ["pytest -q"]},
    }


def _prepared_run(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs" / "gen-1"
    report = run_dir / "rollout" / "analysis" / "detail" / "task-1.md"
    report.parent.mkdir(parents=True)
    report.write_text("LARGE_REPORT_TEXT\n" * 10_000)
    artifact = run_dir / "eval" / "evaluation_artifacts.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"trials": []}\n')
    manifest = _manifest()
    manifest_path = run_dir / "meta_agent" / "change_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest) + "\n")
    child = {
        "status": "complete",
        "outcome": "benchmark_complete",
        "selection_eligible": True,
        "score": 0.1,
        "task_vector": _vector(),
        "mutated": ["target/agent.py"],
        "artifacts": {
            "path": artifact.relative_to(workspace).as_posix(),
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
    }
    return workspace, run_dir, child


def test_gate_accepts_structurally_valid_child_without_parent_score_comparison(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    gate = _module(ROOT / "library" / "gate" / "ahe_artifact_valid.py", "ahe_artifact_valid")

    result = gate.AheArtifactValidGate().decide(child, {"score": 0.9}, _ctx(workspace, run_dir))

    assert result.decision == "accept"


def test_gate_rejects_display_complete_child_without_canonical_eligibility(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    child.pop("outcome")
    child.pop("selection_eligible")
    gate = _module(ROOT / "library" / "gate" / "ahe_artifact_valid.py", "ahe_artifact_valid_legacy")

    result = gate.AheArtifactValidGate().decide(child, {"score": 0.9}, _ctx(workspace, run_dir))

    assert result.decision == "reject"
    assert "evaluation" in result.reason


def test_gate_rejects_corrupt_evaluation_artifact_hash_before_manifest(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    gate = _module(ROOT / "library" / "gate" / "ahe_artifact_valid.py", "ahe_artifact_valid_corrupt")
    child["artifacts"] = {"path": "runs/gen-1/eval/evaluation_artifacts.json", "sha256": "0" * 64}

    result = gate.AheArtifactValidGate().decide(child, {"score": 0.9}, _ctx(workspace, run_dir))

    assert result.decision == "reject"
    assert "artifacts" in result.reason


def test_gate_rejects_missing_change_manifest(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    (run_dir / "meta_agent" / "change_manifest.json").unlink()
    gate = _module(ROOT / "library" / "gate" / "ahe_artifact_valid.py", "ahe_artifact_valid_missing")

    result = gate.AheArtifactValidGate().decide(child, {"score": 0.9}, _ctx(workspace, run_dir))

    assert result.decision == "reject"
    assert "change_manifest" in result.reason


def test_gate_imports_ahe_support_from_an_installed_workspace(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    operators = workspace / "operators"
    support = workspace / "library"
    operators.mkdir()
    support.mkdir()
    shutil.copy(ROOT / "library" / "gate" / "ahe_artifact_valid.py", operators / "gate.py")
    shutil.copy(ROOT / "library" / "ahe_support.py", support / "ahe_support.py")
    sys.modules.pop("ahe_support", None)
    gate = _module(operators / "gate.py", "installed_ahe_artifact_valid")

    result = gate.AheArtifactValidGate().decide(child, {"score": 0.9}, _ctx(workspace, run_dir))

    assert result.decision == "accept"
    assert Path(sys.modules["ahe_support"].__file__).resolve() == (support / "ahe_support.py").resolve()


def test_record_uses_compact_manifest_references_and_summaries(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    (run_dir / "gate.json").write_text(json.dumps({"valid_parent": True, "verdict": "keep", "reason": "structurally valid"}) + "\n")
    (run_dir / "rollout" / "analysis" / "selection.json").write_text('{"tasks": {}}\n')
    (run_dir / "rollout" / "analysis" / "failures.json").write_text('{"failures": []}\n')
    (run_dir / "rollout" / "analysis" / "overview.md").write_text("LARGE_OVERVIEW_TEXT\n" * 10_000)
    (run_dir / "rollout" / "attribution.json").write_text(
        json.dumps({"changes": [{"verdict": "HARMFUL"}, {"verdict": "HARMFUL"}, {"verdict": "EFFECTIVE"}]}) + "\n"
    )
    record = _module(ROOT / "library" / "record" / "ahe_manifest.py", "ahe_manifest")

    fields = record.AheManifestRecord().annotate(child, _ctx(workspace, run_dir)).fields

    manifest_path = run_dir / "meta_agent" / "change_manifest.json"
    assert fields == {
        "valid_parent": True,
        "verdict": "keep",
        "reason": "structurally valid",
        "ahe_manifest_path": "runs/gen-1/meta_agent/change_manifest.json",
        "ahe_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "ahe_decision": "revise",
        "predicted_fixes": ["task-1", "task-2"],
        "risk_tasks": ["task-3"],
        "ahe_attribution": {"EFFECTIVE": 1, "HARMFUL": 2},
        "ahe_analysis_paths": [
            "runs/gen-1/rollout/analysis/detail/task-1.md",
            "runs/gen-1/rollout/analysis/failures.json",
            "runs/gen-1/rollout/analysis/overview.md",
            "runs/gen-1/rollout/analysis/selection.json",
        ],
    }
    serialized = json.dumps(fields)
    assert "LARGE_REPORT_TEXT" not in serialized
    assert "LARGE_OVERVIEW_TEXT" not in serialized
    assert "root_cause" not in serialized


def test_record_imports_ahe_support_from_an_installed_workspace(tmp_path: Path) -> None:
    workspace, run_dir, child = _prepared_run(tmp_path)
    (run_dir / "gate.json").write_text(json.dumps({"valid_parent": True, "verdict": "keep", "reason": "structurally valid"}) + "\n")
    operators = workspace / "operators"
    support = workspace / "library"
    operators.mkdir()
    support.mkdir()
    shutil.copy(ROOT / "library" / "record" / "ahe_manifest.py", operators / "record.py")
    shutil.copy(ROOT / "library" / "ahe_support.py", support / "ahe_support.py")
    sys.modules.pop("ahe_support", None)
    record = _module(operators / "record.py", "installed_ahe_manifest")

    fields = record.AheManifestRecord().annotate(child, _ctx(workspace, run_dir)).fields

    assert fields["ahe_manifest_path"] == "runs/gen-1/meta_agent/change_manifest.json"
    assert Path(sys.modules["ahe_support"].__file__).resolve() == (support / "ahe_support.py").resolve()
