"""Dispatch a meta-agent strategy prompt to its configured runner."""

from __future__ import annotations

from pathlib import Path

from evolve.agent import AgentCommandError, AgentRunResult
from evolve.frozen.interfaces import OperatorContext
from library.meta_agent.runners import harbor, local
from library.meta_agent.runners.editable_bundle import (
    EditableBundle,
    cleanup_editable_bundle,
    install_returned_bundle,
    prepare_editable_bundle,
)

RUNNERS = ("local", "harbor")

__all__ = [
    "EditableBundle",
    "cleanup_editable_bundle",
    "install_returned_bundle",
    "prepare_editable_bundle",
    "run_agent",
    "runner_name",
]


def runner_name(ctx: OperatorContext) -> str:
    return str(ctx.config.get("runner") or "local")


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    name = runner_name(ctx)
    if name == "local":
        return local.run_agent(checkout, prompt, ctx)
    if name == "harbor":
        return harbor.run_agent(checkout, prompt, ctx)
    raise AgentCommandError(
        f"unknown meta-agent runner: {name}; available: {', '.join(RUNNERS)}",
        returncode=2,
    )
