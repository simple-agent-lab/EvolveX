from pathlib import Path

import pytest
from conftest import (
    allow_local_runtime,
    contract_for_gen0,
    init_recipe_with_local_inputs,
)

from evolve.preflight import PreflightStatus, run_preflight


@pytest.mark.parametrize(
    ("recipe", "profile"),
    [
        ("aevolve", "harbor-v1"),
        ("ahe", "harbor-uv-v1"),
        ("gepa", "harbor-v1"),
        ("hyperagents", "harbor-uv-v1"),
    ],
)
def test_partner_recipe_runtime_profile_conformance(
    tmp_path: Path,
    recipe: str,
    profile: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = f"canary-key-{recipe}"
    endpoint = f"https://{recipe}.model-canary.example/v1"
    proxy = f"http://proxy-user:proxy-password@{recipe}.proxy-canary.example:8118"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("OPENAI_BASE_URL", endpoint)
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    workspace = init_recipe_with_local_inputs(tmp_path, recipe)
    allow_local_runtime(monkeypatch)

    result = run_preflight(workspace)
    contract = contract_for_gen0(workspace)

    assert result.status is PreflightStatus.PASSED, (
        result.failure_category,
        result.failure_message,
    )
    assert result.profile_name == profile
    assert contract.runtime_profile == profile
    assert contract.runtime_profile_digest == result.profile_digest
    assert result.receipt_path is not None
    receipt = result.receipt_path.read_text()
    assert all(literal not in receipt for literal in (key, endpoint, proxy, "proxy-password"))

    for root in (workspace / "target", workspace / "evaluator"):
        for path in root.rglob("*"):
            if path.is_file():
                assert "auth.json" not in path.read_text(errors="ignore")
