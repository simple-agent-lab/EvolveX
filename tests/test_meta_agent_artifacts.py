import random
import subprocess
from pathlib import Path

import pytest

from evolve.agent import AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from library.meta_agent import runners
from library.meta_agent.support.artifacts import (
    artifact_generation_relative,
    render_artifact_guidance,
)


def _ctx(workspace: Path, *, genid: str = "2", parent: str | None = "1") -> OperatorContext:
    return OperatorContext(
        workspace=workspace,
        checkout=workspace / "checkout",
        run_dir=workspace / "runs" / f"gen-{genid}",
        genid=genid,
        parent=parent,
        round=None,
        fan_out=1,
        config={},
        rng=random.Random(0),
    )


def test_artifact_guidance_identifies_selected_parent_handoff_without_inlining(tmp_path: Path) -> None:
    handoff = tmp_path / "artifacts" / "generations" / "1" / "handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("PRIVATE HANDOFF BODY")

    guidance = render_artifact_guidance(_ctx(tmp_path), Path("/app/task/workspace"))

    assert "`/app/task/workspace/artifacts/generations/2`" in guidance
    assert "selected parent's handoff" in guidance
    assert "`/app/task/workspace/artifacts/generations/1/handoff.md`" in guidance
    assert "free-form `handoff.md`" in guidance
    assert "optional" in guidance
    assert "PRIVATE HANDOFF BODY" not in guidance


def test_artifact_guidance_is_best_effort_when_parent_handoff_is_missing(tmp_path: Path) -> None:
    guidance = render_artifact_guidance(_ctx(tmp_path), tmp_path)

    assert "No selected-parent handoff is available" in guidance
    assert "continue using the other evidence" in guidance


def test_runner_creates_layout_for_existing_local_workspace(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    ctx.config["runner"] = "local"

    def fake_run_agent(checkout: Path, prompt: str, actual_ctx: OperatorContext) -> AgentRunResult:
        assert checkout == ctx.checkout and prompt == "prompt" and actual_ctx == ctx
        return AgentRunResult("", "", "", 0, 0, {"usd": 0})

    monkeypatch.setattr(runners.local, "run_agent", fake_run_agent)

    runners.run_agent(ctx.checkout, "prompt", ctx)

    assert (tmp_path / "artifacts" / "user").is_dir()
    assert (tmp_path / "artifacts" / "generations" / "2").is_dir()


def test_runner_locally_ignores_artifacts_in_existing_git_workspace(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    ctx = _ctx(tmp_path)
    ctx.config["runner"] = "local"
    monkeypatch.setattr(
        runners.local,
        "run_agent",
        lambda *_args: AgentRunResult("", "", "", 0, 0, {"usd": 0}),
    )

    runners.run_agent(ctx.checkout, "prompt", ctx)

    assert subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "-q", "artifacts/example.txt"],
        check=False,
    ).returncode == 0
    assert not (tmp_path / ".gitignore").exists()


@pytest.mark.parametrize("genid", ["", ".", "..", "1/child", "1\\child"])
def test_generation_artifact_path_rejects_unsafe_genid(genid: str) -> None:
    with pytest.raises(ValueError, match="generation id"):
        artifact_generation_relative(genid)
