"""Run a configured local command as the editing-agent backend."""

from __future__ import annotations

from pathlib import Path

from evolve.agent import AgentRunResult, run_mutate
from evolve.frozen.interfaces import OperatorContext


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    """Run the trusted local-command backend in the candidate checkout."""
    return run_mutate(workspace=checkout, prompt=prompt, config=ctx.config)
