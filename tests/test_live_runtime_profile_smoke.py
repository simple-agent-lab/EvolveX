import os
from pathlib import Path

import pytest
from conftest import git

from evolve.preflight import PreflightMode, PreflightStatus, run_preflight
from evolve.workspace import InitOptions, init_workspace

UBUNTU_DIGEST = "sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"


def write_model_smoke_dataset(root: Path) -> Path:
    root.mkdir()
    for index in range(10):
        task = root / f"model-smoke-{index}"
        (task / "environment").mkdir(parents=True)
        (task / "tests").mkdir()
        (task / "task.toml").write_text(
            'version = "1.0"\n\n'
            "[metadata]\n\n"
            "[verifier]\ntimeout_sec = 60.0\n\n"
            "[agent]\ntimeout_sec = 180.0\n\n"
            "[environment]\nbuild_timeout_sec = 300.0\n"
        )
        (task / "instruction.md").write_text("Runtime profile smoke.\n")
        (task / "environment" / "Dockerfile").write_text(
            f"FROM ubuntu:24.04@{UBUNTU_DIGEST}\nWORKDIR /app\n"
        )
        verifier = task / "tests" / "test.sh"
        verifier.write_text("#!/bin/sh\nset -eu\nprintf '1\\n' > /logs/verifier/reward.txt\n")
        verifier.chmod(0o755)
    return root


def build_live_smoke_workspace(tmp_path: Path, recipe: str) -> Path:
    for name in ("OPENAI_API_KEY", "EVOLVE_RUNTIME_DIGEST"):
        if not os.environ.get(name):
            raise AssertionError(f"live profile smoke requires {name}")
    dataset = write_model_smoke_dataset(tmp_path / f"{recipe}-dataset")
    workspace = tmp_path / f"{recipe}-workspace"
    init_workspace(InitOptions(workspace=workspace, recipe=recipe, dataset=str(dataset)))
    return workspace


@pytest.mark.live_model
@pytest.mark.skipif(
    os.environ.get("EVOLVE_LIVE_RUNTIME_SMOKE") != "1",
    reason="live model smoke is opt-in",
)
@pytest.mark.parametrize("recipe", ["aevolve", "ahe"])
def test_live_profile_smoke_is_non_mutating(tmp_path: Path, recipe: str) -> None:
    assert "CODEX_AUTH_JSON_PATH" not in os.environ
    assert "CODEX_FORCE_AUTH_JSON" not in os.environ
    workspace = build_live_smoke_workspace(tmp_path, recipe)
    before = git(workspace, "write-tree")

    result = run_preflight(workspace, mode=PreflightMode.SMOKE)

    assert result.status is PreflightStatus.PASSED
    assert git(workspace, "write-tree") == before
    assert result.receipt_path is not None
    serialized = result.receipt_path.read_text()
    assert os.environ["OPENAI_API_KEY"] not in serialized
    if endpoint := os.environ.get("OPENAI_BASE_URL"):
        assert endpoint not in serialized
