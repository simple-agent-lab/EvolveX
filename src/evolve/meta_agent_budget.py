"""Lifecycle budgets for a retrying Harbor meta-agent.

Harbor 0.18 bounds environment image preparation and verifier execution at
600 seconds each, and agent setup at 360 seconds.  Agent execution is bounded
separately by the configured per-attempt timeout.  Harbor does not put one
aggregate deadline around artifact/log collection or environment teardown, so
Evolve assigns each of those lifecycle phases the same conservative 600-second
allowance as Harbor's standard bounded phases.

The Harbor process budget is:

    task compilation
    + attempts * (
        environment start + agent setup + agent execution + verifier
        + artifact/log collection + teardown/finalization
      )
    + retries * failed-trial removal/recreation/backoff

The operator budget additionally surrounds Harbor with:

    pre-Harbor bundle/git preparation
    + Harbor process
    + post-Harbor validation/artifact installation
    + final process/temp-directory cleanup

Local-only transitions receive one minute.  This includes Harbor 0.18's
one-second first retry backoff and its five-second process termination grace;
those implementation details therefore never consume an agent attempt window.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .integrations.harbor._agent_roles import INSTALLED_MINISWE_AGENT, is_installed_miniswe_agent

HARBOR_FILE_TASK_AGENT = INSTALLED_MINISWE_AGENT

# Pinned Harbor 0.18 lifecycle defaults.
HARBOR_ENVIRONMENT_START_S = 600.0
HARBOR_AGENT_SETUP_S = 360.0
HARBOR_VERIFIER_S = 600.0

# Explicit Evolve allowances for Harbor phases without their own aggregate cap.
HARBOR_ARTIFACT_LOG_COLLECTION_S = 600.0
HARBOR_TEARDOWN_FINALIZATION_S = 600.0
HARBOR_TASK_COMPILATION_S = 600.0
HARBOR_RETRY_RECREATION_S = 60.0

# Work performed outside the Harbor subprocess.
PRE_HARBOR_BUNDLE_GIT_S = 600.0
POST_HARBOR_VALIDATION_INSTALL_S = 600.0
OUTER_FINAL_CLEANUP_S = 60.0


def harbor_agent_supports_per_attempt_timeout(agent: object) -> bool:
    """Whether the runner's config-mode branch writes an agent timeout cap."""

    return is_installed_miniswe_agent(agent)


def uses_harbor_per_attempt_timeout(config: Mapping[str, object]) -> bool:
    """Whether a meta-agent config receives Harbor's per-attempt timeout."""

    return config.get("runner") == "harbor" and harbor_agent_supports_per_attempt_timeout(config.get("agent"))


@dataclass(frozen=True)
class HarborMetaAgentBudget:
    """Calculated nested and outer deadlines for one Harbor meta-agent run."""

    agent_timeout_s: float
    max_retries: int

    @property
    def attempts(self) -> int:
        return self.max_retries + 1

    @property
    def per_trial_s(self) -> float:
        return (
            HARBOR_ENVIRONMENT_START_S
            + HARBOR_AGENT_SETUP_S
            + self.agent_timeout_s
            + HARBOR_VERIFIER_S
            + HARBOR_ARTIFACT_LOG_COLLECTION_S
            + HARBOR_TEARDOWN_FINALIZATION_S
        )

    @property
    def harbor_process_s(self) -> float:
        return (
            HARBOR_TASK_COMPILATION_S + self.attempts * self.per_trial_s + self.max_retries * HARBOR_RETRY_RECREATION_S
        )

    @property
    def operator_s(self) -> float:
        return (
            PRE_HARBOR_BUNDLE_GIT_S + self.harbor_process_s + POST_HARBOR_VALIDATION_INSTALL_S + OUTER_FINAL_CLEANUP_S
        )


def harbor_meta_agent_budget(
    agent_timeout_s: float,
    max_retries: int,
) -> HarborMetaAgentBudget:
    """Return a normalized lifecycle budget."""

    return HarborMetaAgentBudget(
        agent_timeout_s=max(0.0, float(agent_timeout_s)),
        max_retries=max(0, int(max_retries)),
    )
