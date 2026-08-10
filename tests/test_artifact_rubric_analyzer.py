import importlib.util
import json
import random
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "analyze" / "artifact_rubric.py"
    spec = importlib.util.spec_from_file_location("evolve_test_artifact_rubric", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_rubric_analyzer_uses_artifacts_without_trajectory(tmp_path: Path) -> None:
    module = _module()
    run_dir = tmp_path / "runs" / "gen-1"
    rollout = run_dir / "rollout"
    rollout.mkdir(parents=True)
    (rollout / "cases.json").write_text(
        json.dumps(
            [
                {
                    "task_name": "paper-a",
                    "outcome": "failed",
                    "inputs": {"instruction": "Create poster A"},
                    "outputs": {"primary_artifact": "verifier/poster.svg"},
                    "artifacts": [{"kind": "svg", "path": "verifier/poster.svg"}],
                    "judgments": [{"rubric_id": "authored_visual_language", "score": 1, "hard_failure": False}],
                    "metrics": {"reward": 0.4},
                    "feedback": {"message": "Use a restrained palette."},
                    "execution": {"trajectory_available": False},
                }
            ]
        )
    )
    ctx = OperatorContext(
        workspace=tmp_path,
        checkout=tmp_path,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"components": {"skill": "target/SKILL.md"}},
        rng=random.Random(0),
    )

    result = module.ArtifactRubricAnalyzer().analyze(tmp_path, ctx)

    assert result.summary["operator"] == "artifact_rubric"
    assert result.summary["weak_rubric_counts"] == {"authored_visual_language": 1}
    dataset = json.loads((run_dir / "analyze/evidence/reflective_dataset.json").read_text())
    assert dataset["skill"][0]["Generated Artifacts"]["artifacts"][0]["kind"] == "svg"
    assert dataset["skill"][0]["Rubric Feedback"]["feedback"]["message"] == ("Use a restrained palette.")
    manifest = json.loads((run_dir / "analyze/evidence/manifest.json").read_text())
    assert manifest["analyze_operator"] == "artifact_rubric"
    assert manifest["cases"] == 1
    selected = (run_dir / "analyze/evidence/selected.md").read_text()
    assert "### paper-a" in selected
    assert "`authored_visual_language` (score 1)" in selected
    assert "Judge feedback: Use a restrained palette." in selected
    assert "`verifier/poster.svg`" in selected
