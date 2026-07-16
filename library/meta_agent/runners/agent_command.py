"""Run a configured host command as the editing-agent backend."""

from __future__ import annotations

from pathlib import Path

from evolve.agent import AgentRunResult, run_meta_agent
from evolve.frozen.interfaces import OperatorContext


def run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult:
    """Run the trusted command backend in the candidate checkout."""
    return run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
