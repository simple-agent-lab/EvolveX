from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from conftest import run_evolve


class FakeCliFlag:
    def __init__(self, kwarg: str, **kwargs: Any) -> None:
        self.kwarg = kwarg
        self.kwargs = kwargs


class FakeCodex:
    CLI_FLAGS: list[FakeCliFlag] = []

    def __init__(self, logs_dir: Path, model_name: str | None = None, **kwargs: Any) -> None:
        self.logs_dir = logs_dir
        self.model_name = model_name
        self.kwargs = kwargs
        self._extra_env = dict(kwargs.get("extra_env") or {})
        self.base_setup_called = False

    def _get_env(self, name: str) -> str | None:
        return self._extra_env.get(name)

    async def setup(self, environment: object) -> None:
        self.base_setup_called = True


class FakeBaseEnvironment:
    pass


class RecordingEnvironment:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []

    async def upload_dir(self, source_dir: Path, target_dir: str) -> None:
        self.uploads.append((source_dir, target_dir))


def _install_fake_harbor(monkeypatch) -> None:
    modules = {
        "harbor": ModuleType("harbor"),
        "harbor.agents": ModuleType("harbor.agents"),
        "harbor.agents.installed": ModuleType("harbor.agents.installed"),
        "harbor.agents.installed.base": ModuleType("harbor.agents.installed.base"),
        "harbor.agents.installed.codex": ModuleType("harbor.agents.installed.codex"),
        "harbor.environments": ModuleType("harbor.environments"),
        "harbor.environments.base": ModuleType("harbor.environments.base"),
    }
    modules["harbor.agents.installed.base"].CliFlag = FakeCliFlag
    modules["harbor.agents.installed.codex"].Codex = FakeCodex
    modules["harbor.environments.base"].BaseEnvironment = FakeBaseEnvironment
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _load_target_agent(path: Path):
    spec = importlib.util.spec_from_file_location("evolve_test_builtin_codex", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_candidate_target(target: Path, *, model: str) -> Path:
    target.mkdir(parents=True)
    (target / "prompt.md").write_text(f"Prompt for {model}.\n")
    (target / "codex.toml").write_text(
        f"""[codex]
model = "{model}"

[skills]
enabled = true

[compaction]
override_defaults = false
"""
    )
    skills = target / "skills"
    skills.mkdir()
    (skills / "SKILL.md").write_text(f"Skill for {model}.\n")
    return skills


def test_builtin_codex_wrapper_injects_skills_and_opt_in_compaction(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "experiment"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "aevolve",
        "--seed",
        "builtin-codex",
        env={"EVOLVE_HOME": str(tmp_path / "home")},
    )
    assert result.returncode == 0, result.stderr
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(workspace / "target" / "agent.py")

    agent = module.HarborAgent(logs_dir=tmp_path / "logs")
    assert agent.model_name == "gpt-5.4"
    assert agent.kwargs["skills_dir"] == "/tmp/evolve-target-skills"
    assert "auto_compact_token_limit" not in agent.kwargs
    assert {flag.kwarg for flag in agent.CLI_FLAGS} >= {
        "auto_compact_token_limit",
        "auto_compact_token_limit_scope",
        "tool_output_token_limit",
    }

    environment = RecordingEnvironment()
    asyncio.run(agent.setup(environment))
    assert agent.base_setup_called is True
    assert environment.uploads == [
        (workspace / "target" / "skills", "/tmp/evolve-target-skills"),
    ]

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    auth_path = tmp_path / "home" / ".codex" / "auth.json"
    with pytest.raises(ValueError, match="auth.json does not exist"):
        agent._resolve_auth_json_path()
    auth_path.parent.mkdir(parents=True)
    auth_path.write_text("{}\n")
    assert agent._resolve_auth_json_path() == auth_path

    config_path = workspace / "target" / "codex.toml"
    config_path.write_text(config_path.read_text().replace("override_defaults = false", "override_defaults = true"))
    compacting_agent = module.HarborAgent(logs_dir=tmp_path / "logs-2")
    assert compacting_agent.kwargs["auto_compact_token_limit"] == 100000
    assert compacting_agent.kwargs["auto_compact_token_limit_scope"] == "total"
    assert compacting_agent.kwargs["tool_output_token_limit"] == 12000


def test_builtin_codex_wrapper_uses_candidate_source_from_extra_env(tmp_path: Path, monkeypatch) -> None:
    original_target = tmp_path / "original" / "target"
    original_target.mkdir(parents=True)
    source_agent = Path(__file__).resolve().parents[1] / "seeds" / "codex" / "agent.py"
    (original_target / "agent.py").write_text(source_agent.read_text())
    (original_target / "prompt.md").write_text("Original prompt.\n")
    (original_target / "codex.toml").write_text(
        """[codex]
model = "original-model"
reasoning_effort = "low"

[skills]
enabled = true

[compaction]
override_defaults = false
"""
    )
    (original_target / "skills").mkdir()

    candidate_target = tmp_path / "candidate" / "target"
    candidate_target.mkdir(parents=True)
    (candidate_target / "prompt.md").write_text("Candidate prompt.\n")
    candidate_config = candidate_target / "codex.toml"
    candidate_config.write_text(
        """[codex]
model = "candidate-model"
reasoning_effort = "medium"

[skills]
enabled = true

[compaction]
override_defaults = false
"""
    )
    candidate_skills = candidate_target / "skills"
    candidate_skills.mkdir()
    (candidate_skills / "SKILL.md").write_text("Candidate skill.\n")

    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(original_target / "agent.py")
    extra_env = {"EVOLVE_CANDIDATE_SOURCE": str(candidate_target)}
    agent = module.HarborAgent(logs_dir=tmp_path / "logs", extra_env=extra_env)

    assert agent.model_name == "candidate-model"
    assert agent.kwargs["reasoning_effort"] == "medium"
    assert agent.kwargs["prompt_template_path"] == candidate_target / "prompt.md"
    environment = RecordingEnvironment()
    asyncio.run(agent.setup(environment))
    assert environment.uploads == [
        (candidate_skills, "/tmp/evolve-target-skills"),
    ]

    candidate_config.write_text(candidate_config.read_text().replace("enabled = true", "enabled = false"))
    disabled_agent = module.HarborAgent(logs_dir=tmp_path / "disabled-logs", extra_env=extra_env)
    assert disabled_agent.kwargs["skills_dir"] is None
    disabled_environment = RecordingEnvironment()
    asyncio.run(disabled_agent.setup(disabled_environment))
    assert disabled_environment.uploads == []


@pytest.mark.parametrize("extra_env", [{}, {"EVOLVE_CANDIDATE_SOURCE": ""}])
def test_builtin_codex_wrapper_does_not_inherit_ambient_candidate_source(
    tmp_path: Path,
    monkeypatch,
    extra_env: dict[str, str],
) -> None:
    ambient_target = tmp_path / "ambient" / "target"
    _write_candidate_target(ambient_target, model="ambient-model")
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(ambient_target))
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(Path(__file__).resolve().parents[1] / "seeds" / "codex" / "agent.py")

    agent = module.HarborAgent(logs_dir=tmp_path / "logs", extra_env=extra_env)

    assert agent.model_name == "gpt-5.4"
    assert agent.kwargs["prompt_template_path"] == module.MODULE_ROOT / "prompt.md"


@pytest.mark.parametrize(
    "extra_env",
    ["EVOLVE_CANDIDATE_SOURCE=/tmp/not-a-mapping", {"EVOLVE_CANDIDATE_SOURCE": 42}],
)
def test_builtin_codex_wrapper_rejects_malformed_candidate_environment(
    tmp_path: Path,
    monkeypatch,
    extra_env: object,
) -> None:
    ambient_target = tmp_path / "ambient" / "target"
    _write_candidate_target(ambient_target, model="ambient-model")
    monkeypatch.setenv("EVOLVE_CANDIDATE_SOURCE", str(ambient_target))
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(Path(__file__).resolve().parents[1] / "seeds" / "codex" / "agent.py")

    assert module._target_root(extra_env) == module.MODULE_ROOT


def test_builtin_codex_wrapper_isolates_candidate_root_per_instance(tmp_path: Path, monkeypatch) -> None:
    first_target = tmp_path / "first" / "target"
    first_skills = _write_candidate_target(first_target, model="first-model")
    second_target = tmp_path / "second" / "target"
    second_skills = _write_candidate_target(second_target, model="second-model")
    _install_fake_harbor(monkeypatch)
    module = _load_target_agent(Path(__file__).resolve().parents[1] / "seeds" / "codex" / "agent.py")

    first = module.HarborAgent(
        logs_dir=tmp_path / "first-logs",
        extra_env={"EVOLVE_CANDIDATE_SOURCE": str(first_target)},
    )
    second = module.HarborAgent(
        logs_dir=tmp_path / "second-logs",
        extra_env={"EVOLVE_CANDIDATE_SOURCE": str(second_target)},
    )

    assert first.model_name == "first-model"
    assert first.kwargs["prompt_template_path"] == first_target / "prompt.md"
    assert second.model_name == "second-model"
    assert second.kwargs["prompt_template_path"] == second_target / "prompt.md"
    first_environment = RecordingEnvironment()
    second_environment = RecordingEnvironment()
    asyncio.run(first.setup(first_environment))
    asyncio.run(second.setup(second_environment))
    assert first_environment.uploads == [(first_skills, "/tmp/evolve-target-skills")]
    assert second_environment.uploads == [(second_skills, "/tmp/evolve-target-skills")]
