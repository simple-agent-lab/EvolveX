"""Dispatch a meta-agent strategy prompt to its configured runner."""

from __future__ import annotations

from pathlib import Path

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from library.meta_agent.runners import agent_command, harbor

RUNNERS = ("agent_command", "harbor")


def runner_name(ctx: OperatorContext) -> str:
    return str(ctx.config.get("runner") or "agent_command")


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    name = runner_name(ctx)
    if name == "agent_command":
        return agent_command.run_agent(checkout, prompt, ctx)
    if name == "harbor":
        return harbor.run_agent(checkout, prompt, ctx)
    raise AgentCommandError(
        f"unknown meta-agent runner: {name}; available: {', '.join(RUNNERS)}",
        returncode=2,
    )
