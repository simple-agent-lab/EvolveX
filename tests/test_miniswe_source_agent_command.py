import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


def _install_fake_miniswe(monkeypatch, run_result=None):
    captured: dict[str, object] = {}
    root = types.ModuleType("minisweagent")
    root.__version__ = "0.test"
    agents = types.ModuleType("minisweagent.agents")
    default = types.ModuleType("minisweagent.agents.default")
    config = types.ModuleType("minisweagent.config")
    environments = types.ModuleType("minisweagent.environments")
    local = types.ModuleType("minisweagent.environments.local")
    models = types.ModuleType("minisweagent.models")
    litellm_model = types.ModuleType("minisweagent.models.litellm_model")

    class AgentConfig:
        model_fields = {"step_limit": None, "cost_limit": None, "wall_time_limit_seconds": None, "output_path": None}

    class LocalEnvironmentConfig:
        model_fields = {"cwd": None, "timeout": None}

    class LitellmModelConfig:
        model_fields = {"model_name": None, "cost_tracking": None}

    class LitellmModel:
        def __init__(self, **kwargs) -> None:
            captured["model_kwargs"] = kwargs
            captured["proxies_before_model"] = {
                name for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY") if name in os.environ
            }

    class LocalEnvironment:
        def __init__(self, **kwargs) -> None:
            captured["environment_kwargs"] = kwargs

    class DefaultAgent:
        def __init__(self, model, environment, **kwargs) -> None:
            captured["agent_kwargs"] = kwargs

        def run(self, prompt: str):
            captured["prompt"] = prompt
            return {"exit_status": "submitted", "submission": "useful source-agent report"} if run_result is None else run_result

    def get_config_from_spec(spec: str):
        captured["config_spec"] = spec
        return {"agent": {}, "environment": {}, "model": {}}

    default.AgentConfig = AgentConfig
    default.DefaultAgent = DefaultAgent
    config.get_config_from_spec = get_config_from_spec
    local.LocalEnvironment = LocalEnvironment
    local.LocalEnvironmentConfig = LocalEnvironmentConfig
    litellm_model.LitellmModel = LitellmModel
    litellm_model.LitellmModelConfig = LitellmModelConfig
    for name, module in {
        "minisweagent": root,
        "minisweagent.agents": agents,
        "minisweagent.agents.default": default,
        "minisweagent.config": config,
        "minisweagent.environments": environments,
        "minisweagent.environments.local": local,
        "minisweagent.models": models,
        "minisweagent.models.litellm_model": litellm_model,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return captured


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("tools.miniswe_source_agent_command", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_command_runs_miniswe_from_source_with_proxy_safe_role_output(tmp_path: Path, monkeypatch) -> None:
    captured = _install_fake_miniswe(monkeypatch)
    tool = Path("tools/miniswe_source_agent_command.py")
    module = _load(tool)
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Repair the source agent.\n")
    output_path = tmp_path / "runs" / "miniswe-source-debugger.trajectory.json"
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.example:8118")
    monkeypatch.setenv("EVOLVE_PROMPT_FILE", str(prompt_file))
    monkeypatch.setenv("EVOLVE_SOURCE_AGENT_ROLE", "debugger")
    monkeypatch.setenv("EVOLVE_META_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)

    assert module.main([]) == 0

    assert captured["prompt"] == "Repair the source agent.\n"
    assert captured["environment_kwargs"] == {"cwd": str(Path.cwd()), "timeout": 30}
    assert captured["agent_kwargs"] == {
        "step_limit": 12,
        "cost_limit": 3.0,
        "wall_time_limit_seconds": 900,
        "output_path": str(output_path),
        "instance_template": module.ANALYSIS_INSTANCE_TEMPLATE,
        "format_error_template": module.ANALYSIS_FORMAT_ERROR_TEMPLATE,
    }
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in module.ANALYSIS_INSTANCE_TEMPLATE
    assert "ANALYSIS_REPORT" in module.ANALYSIS_INSTANCE_TEMPLATE
    assert "marker-only" in module.ANALYSIS_FORMAT_ERROR_TEMPLATE
    assert captured["proxies_before_model"] == set()
    assert output_path.parent.is_dir()


def test_source_command_prints_only_sanitized_submission_and_protocol(tmp_path: Path, monkeypatch, capsys) -> None:
    api_key = "sk-test-secret-value"
    token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
    opaque_secret = "cobalt-eleven-private"
    credential_url = "https://api-user:api-password@llm.example/v1"
    result = {
        "exit_status": "submitted",
        "submission": (
            "Useful debugger finding: retry the parser boundary.\n"
            f"Leaked exact env value: {api_key}\n"
            f"Leaked token pattern: {token}\n"
            f"Leaked exact env secret: {opaque_secret}\n"
            f"Leaked URL: {credential_url}\n"
        ),
        "api_key": api_key,
        "base_url": credential_url,
        "environment": {"OPENAI_API_KEY": api_key, "OPENAI_BASE_URL": credential_url},
        "messages": ["private transcript"],
        "config": {"token": token},
    }
    _install_fake_miniswe(monkeypatch, run_result=result)
    module = _load(Path("tools/miniswe_source_agent_command.py"))
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Repair without leaking credentials.\n")
    monkeypatch.setenv("EVOLVE_PROMPT_FILE", str(prompt_file))
    monkeypatch.setenv("EVOLVE_SOURCE_AGENT_ROLE", "debugger")
    monkeypatch.setenv("EVOLVE_META_MODEL", "test-model")
    monkeypatch.setenv("EVOLVE_DEBUGGER_PASSWORD", opaque_secret)
    monkeypatch.chdir(tmp_path)

    assert module.main([]) == 0

    stdout = capsys.readouterr().out
    assert "Useful debugger finding: retry the parser boundary." in stdout
    assert api_key not in stdout
    assert token not in stdout
    assert opaque_secret not in stdout
    assert credential_url not in stdout
    assert "OPENAI_API_KEY" not in stdout
    assert "OPENAI_BASE_URL" not in stdout
    assert "private transcript" not in stdout
    assert "submitted" not in stdout
    assert "[REDACTED]" in stdout
    assert "miniswe-source-agent-complete role=debugger" in stdout
    assert "predicted_fixes: []" in stdout


@pytest.mark.parametrize(
    ("role", "result"),
    [
        ("debugger", {"exit_status": "submitted"}),
        ("overview", {"exit_status": "submitted", "submission": "  \n\t"}),
    ],
)
def test_source_command_rejects_empty_analysis_submission(
    tmp_path: Path,
    monkeypatch,
    capsys,
    role: str,
    result: dict[str, str],
) -> None:
    _install_fake_miniswe(monkeypatch, run_result=result)
    module = _load(Path("tools/miniswe_source_agent_command.py"))
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Analyze the trace.\n")
    monkeypatch.setenv("EVOLVE_PROMPT_FILE", str(prompt_file))
    monkeypatch.setenv("EVOLVE_SOURCE_AGENT_ROLE", role)
    monkeypatch.setenv("EVOLVE_META_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)

    assert module.main([]) != 0
    assert capsys.readouterr().out == ""


def test_source_command_allows_empty_evolution_submission(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = _install_fake_miniswe(monkeypatch, run_result={"exit_status": "submitted", "submission": "  \n"})
    module = _load(Path("tools/miniswe_source_agent_command.py"))
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Edit the source.\n")
    monkeypatch.setenv("EVOLVE_PROMPT_FILE", str(prompt_file))
    monkeypatch.setenv("EVOLVE_SOURCE_AGENT_ROLE", "evolution")
    monkeypatch.setenv("EVOLVE_META_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)

    assert module.main([]) == 0
    assert "instance_template" not in captured["agent_kwargs"]
    assert capsys.readouterr().out == "miniswe-source-agent-complete role=evolution\npredicted_fixes: []\n"
