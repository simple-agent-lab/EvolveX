import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from evolve.archive import merged_rows as mechanism_merged_rows


@pytest.fixture(autouse=True)
def evaluator_runtime_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLVE_RUNTIME_DIGEST", "sha256:test-runtime")
    monkeypatch.setenv("EVOLVE_HOME", str(tmp_path / "evolve-home"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def run_evolve(
    *args: str,
    env: dict[str, str | None] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if value is None:
                merged_env.pop(key, None)
            else:
                merged_env[key] = value
    if env and env.get("EVAL_STUB") == "1" and "EVOLVE_AGENT_COMMAND" not in env:
        merged_env["EVOLVE_AGENT_COMMAND"] = smoke_agent_command()
    return subprocess.run(
        [sys.executable, "-m", "evolve", *args],
        text=True,
        capture_output=True,
        env=merged_env,
        cwd=cwd,
        check=False,
    )


def smoke_agent_command() -> str:
    code = (
        "import os\n"
        "from pathlib import Path\n"
        "target = Path('target/agent.py')\n"
        "genid = os.environ.get('EVOLVE_GENID', 'unknown')\n"
        "target.write_text(target.read_text() + f'\\n# smoke-meta-agent gen {genid}\\n')\n"
        "print('predicted_fixes: []')\n"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def ahe_debugger_command() -> str:
    code = (
        "import os\n"
        "from pathlib import Path\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR'])\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "prompt = Path(os.environ['EVOLVE_PROMPT_FILE']).read_text()\n"
        "(run_dir / 'received-prompt.md').write_text(prompt)\n"
        "print('fixed debugger evidence report')\n"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def ahe_editor_command() -> str:
    code = (
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "genid = os.environ['EVOLVE_GENID']\n"
        "run_dir = Path(os.environ['EVOLVE_RUN_DIR'])\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "prompt = Path(os.environ['EVOLVE_PROMPT_FILE']).read_text()\n"
        "(run_dir / 'received-prompt.md').write_text(prompt)\n"
        "target = Path('target/agent.py')\n"
        "if genid == '1':\n"
        "    target.write_text(target.read_text() + '# AHE_REGRESSION\\n')\n"
        "    decision = 'keep'\n"
        "    change_type = 'improvement'\n"
        "    evidence_task = 'task-0'\n"
        "    predicted = ['task-0']\n"
        "    risks = ['task-1']\n"
        "else:\n"
        "    target.write_text(target.read_text().replace('# AHE_REGRESSION\\n', ''))\n"
        "    Path('target/pivot.py').write_text('# distinct prompt-level pivot\\n')\n"
        "    decision = 'rollback_pivot'\n"
        "    change_type = 'rollback'\n"
        "    evidence_task = 'task-1'\n"
        "    predicted = ['task-1']\n"
        "    risks = []\n"
        "changes = [{\n"
        "    'id': f'change-{genid}',\n"
        "    'type': change_type,\n"
        "    'files': ['target/agent.py'],\n"
        "    'failure_evidence': [{'task_id': evidence_task, 'report': f'rollout/analysis/detail/{evidence_task}.md'}],\n"
        "    'root_cause': 'deterministic attribution fixture',\n"
        "    'targeted_fix': 'deterministic source edit',\n"
        "    'predicted_fixes': predicted,\n"
        "    'risk_tasks': risks,\n"
        "    'component_level': 'control_flow',\n"
        "}]\n"
        "if decision == 'rollback_pivot':\n"
        "    changes.append({\n"
        "        'id': f'pivot-{genid}',\n"
        "        'type': 'new',\n"
        "        'files': ['target/pivot.py'],\n"
        "        'failure_evidence': [{'task_id': evidence_task, 'report': f'rollout/analysis/detail/{evidence_task}.md'}],\n"
        "        'root_cause': 'distinct prompt-level hypothesis',\n"
        "        'targeted_fix': 'introduce a separate pivot',\n"
        "        'predicted_fixes': predicted,\n"
        "        'risk_tasks': [],\n"
        "        'component_level': 'prompt',\n"
        "    })\n"
        "manifest = {\n"
        "    'schema_version': 1,\n"
        "    'generation': genid,\n"
        "    'parent': os.environ['EVOLVE_PARENT'],\n"
        "    'decision': decision,\n"
        "    'changes': changes,\n"
        "    'validation': {'status': 'passed', 'commands': ['python -m compileall target']},\n"
        "}\n"
        "Path(os.environ['EVOLVE_AHE_MANIFEST_PATH']).write_text(json.dumps(manifest) + '\\n')\n"
        "print('fixed editor result')\n"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def smoke_env(evolve_home: Path) -> dict[str, str]:
    return {
        "EVAL_STUB": "1",
        "EVOLVE_HOME": str(evolve_home),
        "EVOLVE_AGENT_COMMAND": smoke_agent_command(),
    }


def write_locked_miniswe_seed(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'mini-swe-agent'\n"
        "version = '0.0.0'\n"
        "requires-python = '>=3.11'\n"
        "dependencies = []\n"
    )
    package = path / "src" / "minisweagent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '0.0.0'\n")
    result = subprocess.run(
        ["uv", "lock", "--offline", "--python", sys.executable, "--project", str(path)],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/tmp/simple-evolve-agent-test-uv")},
    )
    assert result.returncode == 0, result.stderr
    return path


def git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def init_workspace(tmp_path: Path, experiment: str = "experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def init_miniswe_workspace(tmp_path: Path, experiment: str = "miniswe-experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    seed = write_locked_miniswe_seed(tmp_path / "miniswe-seed")
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb",
        "--seed",
        str(seed),
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home


def rows_by_genid(workspace: Path) -> dict[str, dict[str, object]]:
    return {str(row["genid"]): row for row in mechanism_merged_rows(workspace / "archive.jsonl")}


def git_show(workspace: Path, spec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(workspace), "show", spec],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


def append_archive_event(workspace: Path, evolve_home: Path, event: dict[str, object]) -> None:
    line = json.dumps(event, sort_keys=True) + "\n"
    with (workspace / "archive.jsonl").open("a") as archive:
        archive.write(line)
    mirror = evolve_home / "mirrors" / workspace.name / "archive.jsonl"
    with mirror.open("a") as archive:
        archive.write(line)
