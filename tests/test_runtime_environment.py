import json
from pathlib import Path

import pytest

from evolve.runtime_environment import (
    RuntimeEnvironmentPlan,
    RuntimeEnvironmentResolutionError,
    resolve_legacy_runtime_environment,
    resolve_runtime_environment,
    write_harbor_environment_inputs,
)
from evolve.runtime_profiles import ResolvedRuntimeProfileV1, resolve_runtime_profile


def resolved_profile() -> ResolvedRuntimeProfileV1:
    result = resolve_runtime_profile(
        {
            "experiment": {"id": "test"},
            "target": {"seed": "builtin-codex"},
            "surface": {"include": ["target/**"], "exclude": []},
            "operators": {"meta_agent": {"agent": "codex"}},
            "evaluator": {
                "engine": "harbor",
                "agent": "target.agent:HarborAgent",
                "runtime": {"profile": "harbor-v1"},
            },
        },
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert result is not None
    return result


def complete_environment() -> dict[str, str]:
    return {
        "OPENAI_API_KEY": "sensitive-key-value",
        "OPENAI_BASE_URL": "https://model.example/v1",
        "HTTPS_PROXY": "http://user:password@proxy.example:8118",
        "NO_PROXY": "pypi.org,.internal.example",
    }


def test_environment_plan_uses_safe_templates_and_unchanged_proxy() -> None:
    environment = complete_environment()
    environment["UNRELATED_MULTILINE_VALUE"] = "first\nsecond"

    plan = resolve_runtime_environment(
        resolved_profile(), environment, meta_agent_kind="codex"
    )

    assert plan.agent_env()["OPENAI_API_KEY"].startswith("${EVOLVE_RUNTIME_AGENT_")
    assert plan.agent_env()["OPENAI_BASE_URL"].startswith("${EVOLVE_RUNTIME_AGENT_")
    assert plan.meta_agent_env()["OPENAI_API_KEY"].startswith("${EVOLVE_RUNTIME_META_AGENT_")
    assert "OPENAI_API_KEY" not in plan.verifier_env()
    assert "OPENAI_BASE_URL" not in plan.verifier_env()
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_NO_PROXY"] == "pypi.org,.internal.example"

    serialized = json.dumps(plan.persisted_payload())
    assert "sensitive-key-value" not in serialized
    assert "model.example" not in serialized
    assert "password" not in serialized


def test_only_standard_uppercase_proxy_names_are_forwarded() -> None:
    environment = complete_environment()
    environment.update(
        {
            "HTTP_PROXY": "http://proxy.example:8118",
            "http_proxy": "http://proxy.example:8118",
            "NO_PROXY": "localhost",
            "no_proxy": "localhost",
        }
    )

    plan = resolve_runtime_environment(resolved_profile(), environment)

    agent = plan.agent_env()
    process = plan.process_env()
    assert "http_proxy" not in agent
    assert "no_proxy" not in agent
    assert process["EVOLVE_RUNTIME_AGENT_HTTP_PROXY"] == "http://proxy.example:8118"
    assert process["EVOLVE_RUNTIME_AGENT_NO_PROXY"] == "localhost"


def test_lowercase_proxy_alias_does_not_override_standard_value() -> None:
    environment = complete_environment()
    environment["https_proxy"] = "http://different.example:8118"

    plan = resolve_runtime_environment(resolved_profile(), environment)
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_HTTPS_PROXY"] == environment["HTTPS_PROXY"]


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY"])
def test_missing_required_credentials_are_reported_by_name(missing: str) -> None:
    environment = complete_environment()
    environment.pop(missing)

    with pytest.raises(RuntimeEnvironmentResolutionError, match=missing):
        resolve_runtime_environment(resolved_profile(), environment)


def test_implicit_codex_auth_switch_is_rejected() -> None:
    environment = complete_environment()
    environment["CODEX_FORCE_AUTH_JSON"] = "1"

    with pytest.raises(RuntimeEnvironmentResolutionError, match="CODEX_FORCE_AUTH_JSON"):
        resolve_runtime_environment(resolved_profile(), environment)


def test_environment_endpoint_must_match_the_resolved_endpoint_digest() -> None:
    environment = complete_environment()
    environment["OPENAI_BASE_URL"] = "https://other.example/v1"

    with pytest.raises(RuntimeEnvironmentResolutionError, match="endpoint digest") as excinfo:
        resolve_runtime_environment(resolved_profile(), environment)

    assert "other.example" not in str(excinfo.value)


def test_safe_overrides_are_templated_and_protected_overrides_are_rejected() -> None:
    plan = resolve_runtime_environment(
        resolved_profile(),
        complete_environment(),
        agent_overrides={"STEP_LIMIT": "100"},
        verifier_overrides={"VERIFY_TIMEOUT": "60"},
    )

    assert plan.agent_env()["STEP_LIMIT"] == "${EVOLVE_RUNTIME_AGENT_STEP_LIMIT}"
    assert plan.verifier_env()["VERIFY_TIMEOUT"] == "${EVOLVE_RUNTIME_VERIFIER_VERIFY_TIMEOUT}"
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_STEP_LIMIT"] == "100"
    assert plan.process_env()["EVOLVE_RUNTIME_VERIFIER_VERIFY_TIMEOUT"] == "60"

    with pytest.raises(RuntimeEnvironmentResolutionError, match="OPENAI_API_KEY"):
        resolve_runtime_environment(
            resolved_profile(),
            complete_environment(),
            agent_overrides={"OPENAI_API_KEY": "override"},
        )


def test_harbor_inputs_contain_templates_and_redacted_evidence_only(tmp_path: Path) -> None:
    plan = resolve_runtime_environment(resolved_profile(), complete_environment())

    write_harbor_environment_inputs(tmp_path, plan)

    agent = (tmp_path / "runtime-agent.env").read_text()
    verifier = (tmp_path / "runtime-verifier.env").read_text()
    evidence = (tmp_path / "runtime-environment-evidence.json").read_text()
    assert "OPENAI_API_KEY=${EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY}" in agent
    assert "sensitive-key-value" not in agent + verifier + evidence
    assert "model.example" not in agent + verifier + evidence
    assert "password" not in agent + verifier + evidence
    assert not list(tmp_path.glob("*.tmp"))


def test_harbor_writer_rejects_literal_values(tmp_path: Path) -> None:
    plan = RuntimeEnvironmentPlan(
        process_environment=(),
        agent_environment=(("OPENAI_API_KEY", "literal-secret"),),
        verifier_environment=(),
        meta_agent_environment=(),
        evidence=(),
    )

    with pytest.raises(RuntimeEnvironmentResolutionError, match="Harbor environment template"):
        write_harbor_environment_inputs(tmp_path, plan)


def test_legacy_environment_plan_preserves_api_and_proxy_compatibility() -> None:
    plan = resolve_legacy_runtime_environment(
        {
            "OPENAI_API_KEY": "legacy-key",
            "OPENAI_BASE_URL": "https://model.example/v1",
            "HTTPS_PROXY": "http://proxy.example:8118",
            "NO_PROXY": "pypi.org,.internal.example",
        },
        agent_overrides={"STEP_LIMIT": 100},
        verifier_overrides={"JUDGE_MODEL": "judge-model"},
    )

    assert plan.agent_env()["OPENAI_API_KEY"] == "${EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY}"
    assert plan.agent_env()["STEP_LIMIT"] == "${EVOLVE_RUNTIME_AGENT_STEP_LIMIT}"
    assert plan.verifier_env()["JUDGE_MODEL"] == "${EVOLVE_RUNTIME_VERIFIER_JUDGE_MODEL}"
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY"] == "legacy-key"
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_NO_PROXY"] == "pypi.org,.internal.example"
    assert not any("CODEX" in name for name in plan.process_env())


def test_legacy_environment_plan_accepts_explicit_file_auth(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")
    plan = resolve_legacy_runtime_environment({"CODEX_AUTH_JSON_PATH": str(auth)})
    assert plan.process_env()["EVOLVE_RUNTIME_AGENT_CODEX_AUTH_JSON_PATH"] == str(
        auth.resolve()
    )


def test_legacy_proxy_override_is_rejected_in_agent_env() -> None:
    with pytest.raises(RuntimeEnvironmentResolutionError, match="protected name NO_PROXY"):
        resolve_legacy_runtime_environment(
            {"NO_PROXY": "::1"}, agent_overrides={"NO_PROXY": "localhost"}
        )


def test_legacy_proxy_plan_passes_standard_bypass_unchanged() -> None:
    plan = resolve_legacy_runtime_environment(
        {
            "OPENAI_BASE_URL": "https://model.example/v1",
            "http_proxy": "http://dependency-proxy.example:8118",
            "https_proxy": "http://dependency-proxy.example:8118",
            "no_proxy": ".internal.example,github.com,files.pythonhosted.org",
            "NO_PROXY": ".upper.example,objects.githubusercontent.com,astral.sh",
        }
    )

    process = plan.process_env()
    expected = ".upper.example,objects.githubusercontent.com,astral.sh"
    assert process["EVOLVE_RUNTIME_AGENT_NO_PROXY"] == expected
    assert process["EVOLVE_RUNTIME_VERIFIER_NO_PROXY"] == expected
