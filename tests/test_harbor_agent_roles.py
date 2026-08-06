from evolve.integrations.harbor._agent_roles import (
    CANDIDATE_MINISWE_AGENT,
    INSTALLED_MINISWE_AGENT,
    LEGACY_CANDIDATE_MINISWE_AGENT,
    LEGACY_INSTALLED_MINISWE_AGENT,
    is_candidate_miniswe_agent,
    is_installed_miniswe_agent,
    uses_miniswe_submission,
)


def test_miniswe_role_predicates_accept_only_exact_first_party_identifiers() -> None:
    assert is_installed_miniswe_agent(INSTALLED_MINISWE_AGENT)
    assert is_installed_miniswe_agent(LEGACY_INSTALLED_MINISWE_AGENT)
    assert is_candidate_miniswe_agent(CANDIDATE_MINISWE_AGENT)
    assert is_candidate_miniswe_agent(LEGACY_CANDIDATE_MINISWE_AGENT)

    assert not is_installed_miniswe_agent("custom:InstalledMiniSweAgent")
    assert not is_installed_miniswe_agent("custom:FileTaskMiniSweAgent")
    assert not is_candidate_miniswe_agent("custom:CandidateMiniSweAgent")
    assert not is_candidate_miniswe_agent("custom:MiniSweSourceAgent")


def test_submission_contract_is_limited_to_installed_miniswe_agents() -> None:
    assert uses_miniswe_submission("mini-swe-agent")
    assert uses_miniswe_submission(INSTALLED_MINISWE_AGENT)
    assert uses_miniswe_submission(LEGACY_INSTALLED_MINISWE_AGENT)
    assert not uses_miniswe_submission(CANDIDATE_MINISWE_AGENT)
    assert not uses_miniswe_submission("custom:FileTaskMiniSweAgent")
