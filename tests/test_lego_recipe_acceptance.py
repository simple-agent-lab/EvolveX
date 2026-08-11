import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURE_SEEDS
from typer.testing import CliRunner

from evolve.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def monkeypatch_source_root(monkeypatch: pytest.MonkeyPatch, project: Path) -> None:
    from evolve import config as config_module

    monkeypatch.setattr(config_module, "SOURCE_ROOT", project)


def prepare_source_style_project(tmp_path: Path) -> Path:
    project = tmp_path / "source-project"
    project.mkdir()
    for name in ("library", "recipes", "scaffolds", "seeds", "skills", "containers"):
        shutil.copytree(ROOT / name, project / name)
    shutil.copy2(ROOT / "pyproject.toml", project / "pyproject.toml")
    (project / "src/evolve").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    return project


def write_lego_smoke_recipe(project: Path) -> Path:
    source = ROOT / "tests/fixtures/recipes/hill_climb-smoke"
    destination = project / "custom-recipe"
    shutil.copytree(source, destination)
    config = yaml.safe_load((destination / "evolve.yaml").read_text())
    config["operators"]["mutate"] = {
        "operator": "test_editor",
        "timeout_s": 60,
        "config": {},
    }
    (destination / "evolve.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    return destination / "evolve.yaml"


def invoke_cli(*args: str):
    return runner.invoke(app, list(args))


TEST_MUTATE_OPERATOR = """
from evolve.frozen import sdk
from evolve.frozen.config import Config, integer
from evolve.frozen.interfaces import MutateOperator, MutateResult

CONFIG = Config({"attempts": integer(default=2, minimum=1)})

class TestEditor(MutateOperator):
    def mutate(self, checkout, observation, ctx):
        target = checkout / "target/agent.py"
        target.write_text(target.read_text() + f"\\n# edited by test_editor attempts={ctx.config['attempts']}\\n")
        return MutateResult(changed=["target/agent.py"], notes=["deterministic test edit"], usage={"usd": 0})

if __name__ == "__main__":
    sdk.main(TestEditor, config_schema=CONFIG)
""".lstrip()


def test_user_adds_operator_composes_recipe_and_runs_one_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = prepare_source_style_project(tmp_path)
    monkeypatch_source_root(monkeypatch, project)
    operator = project / "library/mutate/test_editor.py"
    created = invoke_cli("operator", "new", "mutate", "test_editor")
    assert created.exit_code == 0, created.output
    operator.write_text(TEST_MUTATE_OPERATOR)
    recipe = write_lego_smoke_recipe(project)

    assert invoke_cli("operator", "describe", "mutate/test_editor").exit_code == 0
    assert invoke_cli("operator", "check", "mutate/test_editor").exit_code == 0
    assert invoke_cli("recipe", "check", str(recipe)).exit_code == 0

    workspace = tmp_path / "workspace"
    preflighted = invoke_cli(
        "preflight",
        str(workspace),
        "--recipe-path",
        str(recipe),
        "--seed",
        str(FIXTURE_SEEDS / "dummy"),
    )
    assert preflighted.exit_code == 0, preflighted.output
    initialized = invoke_cli(
        "init",
        str(workspace),
        "--recipe-path",
        str(recipe),
        "--seed",
        str(FIXTURE_SEEDS / "dummy"),
    )
    assert initialized.exit_code == 0, initialized.output
    normalized = yaml.safe_load((workspace / "evolve.yaml").read_text())
    assert normalized["operators"]["mutate"]["config"] == {"attempts": 2}
    assert invoke_cli("operator", "active", str(workspace)).exit_code == 0
    monkeypatch.setenv("EVAL_STUB", "1")
    completed = invoke_cli(
        "run",
        str(workspace),
        "--max-generations",
        "1",
    )
    assert completed.exit_code == 0, completed.output
    assert (workspace / "runs/gen-1/mutate/changed.json").is_file()
