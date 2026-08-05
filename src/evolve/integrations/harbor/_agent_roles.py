"""Exact identities for Evolve-owned MiniSWE Harbor adapter roles."""

from __future__ import annotations

INSTALLED_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent"
LEGACY_INSTALLED_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent"
CANDIDATE_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent"
LEGACY_CANDIDATE_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent"

_INSTALLED_MINISWE_AGENTS = frozenset({INSTALLED_MINISWE_AGENT, LEGACY_INSTALLED_MINISWE_AGENT})
_CANDIDATE_MINISWE_AGENTS = frozenset({CANDIDATE_MINISWE_AGENT, LEGACY_CANDIDATE_MINISWE_AGENT})
_MINISWE_SUBMISSION_AGENTS = frozenset({"mini-swe-agent", *_INSTALLED_MINISWE_AGENTS})


def is_installed_miniswe_agent(value: object) -> bool:
    return str(value or "") in _INSTALLED_MINISWE_AGENTS


def is_candidate_miniswe_agent(value: object) -> bool:
    return str(value or "") in _CANDIDATE_MINISWE_AGENTS


def uses_miniswe_submission(value: object) -> bool:
    return str(value or "") in _MINISWE_SUBMISSION_AGENTS
