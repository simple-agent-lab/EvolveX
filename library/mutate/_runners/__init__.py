"""Dispatch a meta-agent strategy prompt to its configured runner."""

from __future__ import annotations

from pathlib import Path

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from library.mutate._runners import harbor, local
from library.mutate._support.artifacts import ensure_artifact_layout

RUNNERS = ("local", "harbor")

__all__ = ["run_agent", "run_readonly_agent", "runner_name"]


def runner_name(ctx: OperatorContext) -> str:
    return str(ctx.config.get("runner") or "local")


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    ensure_artifact_layout(ctx.workspace, ctx.genid)
    name = runner_name(ctx)
    if name == "local":
        return local.run_agent(checkout, prompt, ctx)
    if name == "harbor":
        return harbor.run_agent(checkout, prompt, ctx)
    raise AgentCommandError(
        f"unknown meta-agent runner: {name}; available: {', '.join(RUNNERS)}",
        returncode=2,
    )


def run_readonly_agent(
    checkout: Path,
    prompt: str,
    ctx: OperatorContext,
    *,
    output_dir: Path,
    job_name: str,
    timeout_s: float,
    input_files: dict[str, str] | None = None,
) -> AgentRunResult:
    return harbor.run_readonly_agent(
        checkout,
        prompt,
        ctx,
        output_dir=output_dir,
        job_name=job_name,
        timeout_s=timeout_s,
        input_files=input_files,
    )
