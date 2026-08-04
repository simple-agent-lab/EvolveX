import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "library" / "novelty" / "diff_similarity.py"
    spec = importlib.util.spec_from_file_location("diff_similarity_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diff_similarity_surfaces_git_failures(tmp_path: Path) -> None:
    module = _module()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    with pytest.raises(RuntimeError, match="git diff missing-ref failed with exit code"):
        module._git(tmp_path, "diff", "missing-ref")
