import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from evolve.agent import AgentCommandError, _timeout_float, run_meta_agent


def test_timeout_float_accepts_decimal() -> None:
    assert _timeout_float(Decimal("1.5")) == 1.5


def test_run_meta_agent_runs_command_in_workspace_with_prompt_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text(
        "import json, os, pathlib\n"
        "workspace = pathlib.Path.cwd()\n"
        "prompt = pathlib.Path(os.environ['EVOLVE_PROMPT_FILE']).read_text()\n"
        "(workspace / 'probe.json').write_text(json.dumps({'cwd': str(workspace), 'prompt': prompt}))\n"
        "print('agent stdout')\n"
    )

    result = run_meta_agent(
        workspace=workspace,
        prompt="repair target\n",
        config={"command": f"{sys.executable} {script}", "timeout_s": 30},
    )

    probe = json.loads((workspace / "probe.json").read_text())
    assert probe == {"cwd": str(workspace), "prompt": "repair target\n"}
    assert result.stdout.strip() == "agent stdout"
    assert result.stderr == ""
    assert result.returncode == 0
    assert result.usage["usd"] == 0
    assert result.usage["wall_s"] >= 0


def test_run_meta_agent_uses_nested_meta_agent_command(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text("from pathlib import Path\nPath('nested-command-ran').write_text('yes\\n')\n")

    run_meta_agent(
        workspace=workspace,
        prompt="x",
        config={"operators": {"meta_agent": {"command": f"{sys.executable} {script}"}}, "timeout_s": 30},
    )

    assert (workspace / "nested-command-ran").read_text() == "yes\n"


def test_run_meta_agent_applies_caller_owned_environment_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text(
        "import os\n"
        "for name in ('http_proxy', 'HTTPS_PROXY', 'ROLE'):\n"
        "    print(f'{name}={os.environ.get(name, False)}')\n"
    )

    result = run_meta_agent(
        workspace=workspace,
        prompt="inspect env",
        config={"command": f"{sys.executable} {script}"},
        env_overrides={"http_proxy": None, "HTTPS_PROXY": None, "ROLE": "debugger"},
    )

    assert "http_proxy=False" in result.stdout
    assert "HTTPS_PROXY=False" in result.stdout
    assert "ROLE=debugger" in result.stdout


def test_run_meta_agent_uses_env_command_and_reports_missing_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text("from pathlib import Path\nPath('env-command-ran').write_text('yes\\n')\n")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", f"{sys.executable} {script}")

    run_meta_agent(workspace=workspace, prompt="x", config={})

    assert (workspace / "env-command-ran").read_text() == "yes\n"

    monkeypatch.delenv("EVOLVE_AGENT_COMMAND")
    with pytest.raises(AgentCommandError) as excinfo:
        run_meta_agent(workspace=workspace, prompt="x", config={})
    assert "EVOLVE_AGENT_COMMAND" in str(excinfo.value)
    assert "operators.meta_agent.command" in str(excinfo.value)
    assert excinfo.value.returncode == 2


def test_run_meta_agent_timeout_kills_command_group(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "sleep.py"
    script.write_text("import time\nprint('started', flush=True)\ntime.sleep(60)\n")

    with pytest.raises(AgentCommandError) as excinfo:
        run_meta_agent(
            workspace=workspace,
            prompt="x",
            config={"command": f"{sys.executable} {script}", "timeout_s": 0.05},
        )

    assert "timeout" in str(excinfo.value).lower()
    assert excinfo.value.usage["usd"] == 0
    assert excinfo.value.usage["wall_s"] >= 0
