from pathlib import Path

import pytest
from conftest import git, init_workspace

from evolve.config import evaluator_sampling
from evolve.driver import eval_child
from evolve.evaluation.execution import evaluate


def _replace(workspace: Path, relative_path: str, old: str, new: str) -> None:
    path = workspace / relative_path
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_per_round_sampling_is_rejected_clearly(tmp_path: Path) -> None:
    workspace, _evolve_home = init_workspace(tmp_path)
    _replace(workspace, "evolve.yaml", "  partial_floor: 0.9\n", "  partial_floor: 0.9\n  sampling: per_round\n")
    git(workspace, "add", "evolve.yaml")
    git(workspace, "commit", "-m", "configure unsupported sampling")
    git(workspace, "tag", "-f", "gen/0")

    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        evaluator_sampling(workspace)
    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        eval_child(workspace, "0", force=True)
    with pytest.raises(ValueError, match="evaluator.sampling.*static"):
        evaluate(workspace, "gen/0", "0", purpose="genesis")
