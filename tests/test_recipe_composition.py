import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import fixture_recipe_config, generated_workspace_uv_env, write_locked_miniswe_seed

from evolve.config import RECIPE_NAMES, default_config, load_config, recipe_root, scaffold_root, seed_root
from evolve.workspace import InitOptions, _write_target, init_workspace

CANDIDATE = "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent"
FILE_TASK = "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent"
CASES = {
    "hill_climb": ("external", CANDIDATE, "codex"),
    "aevolve": ("codex", "target.agent:HarborAgent", "codex"),
    "ahe": ("external", CANDIDATE, FILE_TASK),
    "gepa": ("codex", "target.agent:HarborAgent", "codex"),
    "hyperagents": ("external", CANDIDATE, FILE_TASK),
}


@pytest.mark.parametrize(("recipe", "expected"), sorted(CASES.items()))
def test_supported_recipe_initializes_only_selected_components(
    tmp_path: Path, recipe: str, expected: tuple[str, str, str]
) -> None:
    target_kind, evaluator_agent, meta_agent = expected
    workspace = tmp_path / recipe
    seed = None
    if target_kind == "external":
        seed = str(write_locked_miniswe_seed(tmp_path / f"{recipe}-seed"))
    init_workspace(InitOptions(workspace=workspace, recipe=recipe, seed=seed))

    rendered = load_config(workspace / "evolve.yaml")
    components = json.loads((workspace / ".evolve-components.json").read_text())
    assert rendered["evaluator"]["agent"] == evaluator_agent
    assert rendered["operators"]["meta_agent"]["agent"] == meta_agent
    assert components["recipe"] == recipe
    assert components["target_seed"] == rendered["target"]["seed"]
    assert components["evaluator_engine"] == "harbor"
    assert components["integrations"] == sorted(
        {
            ref.split(":", 1)[0]
            for ref in (evaluator_agent, meta_agent)
            if ref.startswith("evolve.integrations.")
        }
    )
    assert (workspace / "target" / "codex.toml").is_file() is (target_kind == "codex")
    assert (workspace / "evaluator" / "cleanup_harbor.py").is_file()
    assert (workspace / ".evolve" / "evolve" / "integrations" / "harbor" / "miniswe_candidate.py").is_file()
    assert not (workspace / "evolve_harbor_adapter").exists()
    assert not (workspace / "evolve_harbor_agent").exists()

    sync = subprocess.run(
        ["uv", "sync", "--project", str(workspace), "--frozen", "--offline"],
        text=True,
        capture_output=True,
        check=False,
        env=generated_workspace_uv_env(),
    )
    assert sync.returncode == 0, sync.stderr

    for reference in components["integrations"]:
        probe = subprocess.run(
            [
                "uv",
                "run",
                "--project",
                str(workspace),
                "--frozen",
                "python",
                "-c",
                f"import importlib; importlib.import_module({reference!r})",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=generated_workspace_uv_env(),
        )
        assert probe.returncode == 0, probe.stderr


def test_every_production_resource_has_a_supported_consumer() -> None:
    configs = [load_config(recipe_root() / name / "evolve.yaml") for name in RECIPE_NAMES]
    engines = {str(config["evaluator"]["engine"]) for config in configs}
    builtin_seeds = {
        str(config["target"]["seed"]).removeprefix("builtin-")
        for config in configs
        if str(config["target"].get("seed", "")).startswith("builtin-")
    }
    agent_refs = {str(config["evaluator"].get("agent", "")) for config in configs} | {
        str(config["operators"]["meta_agent"].get("agent", "")) for config in configs
    }

    evaluator_scaffolds = {path.name for path in (scaffold_root() / "evaluators").iterdir() if path.is_dir()}
    seeds = {path.name for path in seed_root().iterdir() if path.is_dir()}
    integration_modules = {
        f"evolve.integrations.harbor.{path.name[:-3]}"
        for path in (
            Path(__file__).resolve().parents[1] / "src" / "evolve" / "integrations" / "harbor"
        ).glob("*.py")
        if path.name != "__init__.py"
    }

    assert evaluator_scaffolds == engines
    assert seeds == builtin_seeds
    assert integration_modules == {
        ref.split(":", 1)[0] for ref in agent_refs if ref.startswith("evolve.integrations.")
    }


COMMON_OUTPUTS = {
    ".gitignore": ".gitignore",
    ".python-version": ".python-version",
    "AGENTS.md": "AGENTS.md",
    "README.md": "README.md",
    "launch_evolve.py": ".evolve/launch_evolve.py",
    "launch_splits.py": ".evolve/launch_splits.py",
    "operators/gate.md": "operators/gate.md",
    "operators/record.md": "operators/record.md",
    "operators/rollout.md": "operators/rollout.md",
    "operators/select.md": "operators/select.md",
    "program.md": "program.md",
    "pyproject.toml": "pyproject.toml",
    "uv.lock": "uv.lock",
    "evaluator/stub_eval.py": "evaluator/stub_eval.py",
}
HARBOR_OUTPUTS = {
    "cleanup_harbor.py": "evaluator/cleanup_harbor.py",
    "harbor_artifacts.py": "evaluator/harbor_artifacts.py",
    "parse_score.py": "evaluator/parse_score.py",
    "smoke.sh": "evaluator/smoke.sh",
}


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_every_scaffold_resource_is_rendered_into_a_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "aevolve"
    init_workspace(InitOptions(workspace=workspace, recipe="aevolve"))
    common = Path(scaffold_root()) / "workspace"
    harbor = Path(scaffold_root()) / "evaluators" / "harbor"

    assert _relative_files(common) == set(COMMON_OUTPUTS) | {"evaluator/eval-prefix.sh"}
    assert _relative_files(harbor) == set(HARBOR_OUTPUTS) | {"engine.sh"}
    for source, destination in COMMON_OUTPUTS.items():
        assert (workspace / destination).read_bytes() == (common / source).read_bytes()
    for source, destination in HARBOR_OUTPUTS.items():
        assert (workspace / destination).read_bytes() == (harbor / source).read_bytes()
    assert (workspace / "evaluator/eval.sh").read_text() == (
        (common / "evaluator/eval-prefix.sh").read_text() + (harbor / "engine.sh").read_text()
    )


def test_initialization_reports_selecting_configuration_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"unsupported recipe: unknown"):
        default_config("unknown", "experiment")

    missing_agent = fixture_recipe_config("hill_climb-smoke", "missing-agent")
    missing_agent["evaluator"].pop("agent")
    with patch("evolve.workspace.default_config", return_value=missing_agent):
        with pytest.raises(ValueError, match=r"evaluator\.agent is required"):
            init_workspace(InitOptions(workspace=tmp_path / "missing-agent", recipe="hill_climb-smoke"))

    missing_engine = fixture_recipe_config("hill_climb-smoke", "missing-engine")
    missing_engine["evaluator"]["engine"] = "missing"
    with patch("evolve.workspace.default_config", return_value=missing_engine):
        with pytest.raises(ValueError, match=r"unsupported evaluator\.engine: missing"):
            init_workspace(InitOptions(workspace=tmp_path / "missing-engine", recipe="hill_climb-smoke"))

    with pytest.raises(ValueError, match=r"seed is not a local directory or git URL"):
        _write_target(tmp_path / "missing-seed", {"seed": str(tmp_path / "absent")})

    missing_seed = fixture_recipe_config("hill_climb-smoke", "required-seed")
    missing_seed["target"].pop("seed")
    destination = tmp_path / "required-seed"
    with patch("evolve.workspace.default_config", return_value=missing_seed):
        with pytest.raises(ValueError, match=r"target\.seed is required"):
            init_workspace(InitOptions(workspace=destination, recipe="hill_climb-smoke"))
    assert not destination.exists()
