import shutil
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
from evolve.frozen.interfaces import MutateOperator, MutateResult
from library._shared.config import config_object, reject_unknown

def validate_config(raw):
    config = config_object(raw)
    reject_unknown(config, set())
    return config

class TestEditor(MutateOperator):
    def mutate(self, checkout, observation, ctx):
        target = checkout / "target/agent.py"
        target.write_text(target.read_text() + "\\n# edited by test_editor\\n")
        return MutateResult(changed=["target/agent.py"], notes=["deterministic test edit"], usage={"usd": 0})

if __name__ == "__main__":
    sdk.main(TestEditor, validate_config=validate_config)
""".lstrip()


def test_user_adds_operator_composes_recipe_and_runs_one_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = prepare_source_style_project(tmp_path)
    operator = project / "library/mutate/test_editor.py"
    operator.write_text(TEST_MUTATE_OPERATOR)
    recipe = write_lego_smoke_recipe(project)

    monkeypatch_source_root(monkeypatch, project)

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
    monkeypatch.setenv("EVAL_STUB", "1")
    completed = invoke_cli(
        "run",
        str(workspace),
        "--max-generations",
        "1",
    )
    assert completed.exit_code == 0, completed.output
    assert (workspace / "runs/gen-1/mutate/changed.json").is_file()
