"""Deterministic knowledge-backed Harbor agent (no LLM, no Docker).

Candidate files are read through EVOLVE_CANDIDATE_SOURCE, the exact candidate
snapshot the evaluation engine mounts; __file__ is only a fallback for direct
runs outside the mechanism.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from harbor.agents.base import BaseAgent

QUESTION = re.compile(r"Compute (.+?) and write")


class HarborAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "knowledge-agent"

    def version(self) -> str | None:
        return "0"

    async def setup(self, environment) -> None:
        return None

    def _candidate_root(self) -> Path:
        source = self._extra_env.get("EVOLVE_CANDIDATE_SOURCE") or os.environ.get(
            "EVOLVE_CANDIDATE_SOURCE"
        )
        return Path(source) if source else Path(__file__).resolve().parent

    async def run(self, instruction, environment, context) -> None:
        facts = json.loads((self._candidate_root() / "knowledge.json").read_text())
        match = QUESTION.search(instruction)
        answer = facts.get(match.group(1).strip(), "unknown") if match else "unknown"
        await environment.exec(command=f"printf %s {shlex.quote(str(answer))} > answer.txt")
