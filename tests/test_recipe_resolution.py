from __future__ import annotations

import copy
import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

from evolve.composition import RecipeResolutionError, resolve_builtin_recipe, resolve_recipe

ROOT = Path(__file__).resolve().parents[1]


def _operators() -> dict[str, object]:
    return {
        "select": {"operator": "greedy", "config": {}},
        "rollout": {"operator": "noop", "config": {}},
        "mutate": {"operator": "hyperagents", "config": {"runner": "local"}},
        "gate": {"operator": "hillclimb", "config": {"strict": True}},
        "record": {"operator": "jsonl", "config": {}},
    }


def write_recipe(tmp_path: Path, *, operators: dict[str, object]) -> Path:
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    config = {
        "experiment": {"id": "resolution-test"},
        "target": {"seed": "builtin-codex"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": operators,
        "evaluator": {"engine": "command"},
        "execution_runtime": {},
    }
    path = recipe / "evolve.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def write_recipe_with_raw_yaml_config(tmp_path: Path, yaml_value: str, *, missing_record: bool = False) -> Path:
    operators = copy.deepcopy(_operators())
    operators["mutate"] = {
        "operator": "hyperagents",
        "config": {"runner": "local", "agent_kwargs": {"opaque": "YAML_VALUE"}},
    }
    if missing_record:
        del operators["record"]
    recipe = write_recipe(tmp_path, operators=operators)
    rendered = recipe.read_text()
    assert "opaque: YAML_VALUE" in rendered
    recipe.write_text(rendered.replace("opaque: YAML_VALUE", f"opaque: {yaml_value}"))
    return recipe


def test_recipe_resolves_named_operator_and_normalizes_config(tmp_path: Path) -> None:
    recipe = write_recipe(tmp_path, operators=_operators())

    resolved = resolve_recipe(recipe)

    assert resolved.name == "recipe"
    assert resolved.directory == recipe.parent
    assert resolved.operators["gate"].name == "hillclimb"
    assert resolved.operators["gate"].config == {"strict": True}
    assert resolved.config["operators"]["gate"] == {
        "operator": "hillclimb",
        "timeout_s": 600.0,
        "config": {"strict": True},
    }
    assert len(resolved.operators["gate"].digest) == 64
    assert resolved.warnings == ()


def test_recipe_wraps_malformed_yaml_as_resolution_problem(tmp_path: Path) -> None:
    recipe = tmp_path / "evolve.yaml"
    recipe.write_text("operators: [\n")

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert len(caught.value.problems) == 1
    assert caught.value.problems[0].path == "recipe"
    assert "expected the node content" in caught.value.problems[0].message


@pytest.mark.parametrize("yaml_timeout", [".nan", ".inf", "-.inf"])
def test_recipe_aggregates_nonfinite_timeout_problem(tmp_path: Path, yaml_timeout: str) -> None:
    operators = copy.deepcopy(_operators())
    operators["select"]["timeout_s"] = "YAML_TIMEOUT"
    del operators["record"]
    recipe = write_recipe(tmp_path, operators=operators)
    rendered = recipe.read_text()
    assert "timeout_s: YAML_TIMEOUT" in rendered
    recipe.write_text(rendered.replace("timeout_s: YAML_TIMEOUT", f"timeout_s: {yaml_timeout}"))

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert {problem.path for problem in caught.value.problems} >= {
        "operators.select.timeout_s",
        "operators.record",
    }


@pytest.mark.parametrize("yaml_value", ["2026-08-10", "!!set {alpha: null}"])
def test_recipe_aggregates_non_json_yaml_config_problem(tmp_path: Path, yaml_value: str) -> None:
    recipe = write_recipe_with_raw_yaml_config(tmp_path, yaml_value, missing_record=True)

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert {problem.path for problem in caught.value.problems} >= {
        "operators.mutate.config",
        "operators.record",
    }
    config_problem = next(problem for problem in caught.value.problems if problem.path == "operators.mutate.config")
    assert "not JSON-serializable" in config_problem.message


@pytest.mark.parametrize(
    ("case", "expected_path", "expected_message"),
    [
        ("old_variant", "operators.select.variant", "variant is no longer supported; use operator"),
        ("old_stage", "operators.trace_analyzer", "stage is no longer supported; use analyze"),
        ("unknown_stage", "operators.judge", "unknown operator stage"),
        ("missing_required", "operators.record", "required operator stage is missing"),
        ("both_selectors", "operators.select", "specify exactly one of operator or script"),
        ("neither_selector", "operators.select", "specify exactly one of operator or script"),
        ("unknown_common_key", "operators.select.seed", "unknown stage key"),
        ("invalid_default_timeout", "operators.timeout_s", "must be a positive number"),
        ("invalid_stage_timeout", "operators.select.timeout_s", "must be a positive number"),
        ("invalid_operator_name", "operators.select.operator", "invalid operator name"),
        ("missing_operator", "operators.select.operator", "operator not found: select/absent"),
        ("rejected_config", "operators.gate.config", "strict: expected boolean"),
        ("config_not_mapping", "operators.select.config", "must be a mapping"),
    ],
)
def test_recipe_reports_strict_resolution_failures(
    tmp_path: Path,
    case: str,
    expected_path: str,
    expected_message: str,
) -> None:
    operators = copy.deepcopy(_operators())
    if case == "old_variant":
        operators["select"] = {"variant": "greedy", "config": {}}
    elif case == "old_stage":
        operators["trace_analyzer"] = {"operator": "failure_patterns", "config": {}}
    elif case == "unknown_stage":
        operators["judge"] = {"operator": "noop", "config": {}}
    elif case == "missing_required":
        del operators["record"]
    elif case == "both_selectors":
        operators["select"] = {"operator": "greedy", "script": "select.py", "config": {}}
    elif case == "neither_selector":
        operators["select"] = {"config": {}}
    elif case == "unknown_common_key":
        operators["select"] = {"operator": "greedy", "config": {}, "seed": 0}
    elif case == "invalid_default_timeout":
        operators["timeout_s"] = False
    elif case == "invalid_stage_timeout":
        operators["select"] = {"operator": "greedy", "config": {}, "timeout_s": 0}
    elif case == "invalid_operator_name":
        operators["select"] = {"operator": "Bad-Name", "config": {}}
    elif case == "missing_operator":
        operators["select"] = {"operator": "absent", "config": {}}
    elif case == "rejected_config":
        operators["gate"] = {"operator": "hillclimb", "config": {"strict": "yes"}}
    elif case == "config_not_mapping":
        operators["select"] = {"operator": "greedy", "config": []}
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(case)

    recipe = write_recipe(tmp_path, operators=operators)

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert any(
        problem.path == expected_path and expected_message in problem.message for problem in caught.value.problems
    )


def test_recipe_rejects_recipe_local_operator_library(tmp_path: Path) -> None:
    recipe = write_recipe(tmp_path, operators=_operators())
    (recipe.parent / "operators").mkdir()

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert ("operators", "recipe-local operator libraries are not supported") in {
        (problem.path, problem.message) for problem in caught.value.problems
    }


def test_recipe_aggregates_independent_problems(tmp_path: Path) -> None:
    operators = _operators()
    operators["timeout_s"] = False
    operators["select"] = {"operator": "Bad-Name", "config": {}}
    operators["rollout"] = {
        "operator": "noop",
        "script": "rollout.py",
        "timeout_s": False,
        "config": [],
    }
    operators["mutate"] = {"operator": "hyperagents", "config": {"runner": "local"}, "extra": 1}
    operators["judge"] = {"operator": "noop", "config": {}}
    del operators["record"]
    recipe = write_recipe(tmp_path, operators=operators)
    (recipe.parent / "operators").mkdir()

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_recipe(recipe)

    assert {problem.path for problem in caught.value.problems} >= {
        "operators",
        "operators.timeout_s",
        "operators.select.operator",
        "operators.rollout",
        "operators.rollout.timeout_s",
        "operators.rollout.config",
        "operators.mutate.extra",
        "operators.judge",
        "operators.record",
    }


def test_relative_script_resolves_from_recipe_directory_and_warns(tmp_path: Path) -> None:
    operators = _operators()
    operators["select"] = {
        "script": "custom/select.py",
        "timeout_s": 12,
        "config": {"opaque": {"value": True}},
    }
    recipe = write_recipe(tmp_path, operators=operators)
    script = recipe.parent / "custom" / "select.py"
    script.parent.mkdir()
    script.write_text("print('selected')\n")

    resolved = resolve_recipe(recipe.parent)
    binding = resolved.operators["select"]

    assert binding.source_kind == "script"
    assert binding.source == script.resolve()
    assert binding.name is None
    assert binding.timeout_s == 12.0
    assert binding.config == {"opaque": {"value": True}}
    assert binding.portable is False
    assert binding.digest == hashlib.sha256(script.read_bytes()).hexdigest()
    assert resolved.warnings == ("operators.select: script source is non-portable",)


def test_packaged_recipe_rejects_script_without_stable_filesystem_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operators = _operators()
    operators["select"] = {"script": str(tmp_path / "select.py"), "config": {}}
    (tmp_path / "select.py").write_text("print('selected')\n")
    config = {
        "experiment": {},
        "target": {},
        "surface": {},
        "operators": operators,
        "evaluator": {},
        "execution_runtime": {},
    }
    archive = tmp_path / "recipes.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("gepa/evolve.yaml", yaml.safe_dump(config, sort_keys=False))
    packaged_root = zipfile.Path(archive)
    monkeypatch.setattr("evolve.composition.recipe.recipe_root", lambda: packaged_root)

    with pytest.raises(RecipeResolutionError) as caught:
        resolve_builtin_recipe("gepa")

    assert ("operators.select.script", "script needs a stable filesystem recipe directory") in {
        (problem.path, problem.message) for problem in caught.value.problems
    }


def test_recipe_resolution_does_not_write_operator_bytecode(tmp_path: Path) -> None:
    library = tmp_path / "library"
    shutil.copytree(ROOT / "library", library, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    recipe = write_recipe(tmp_path, operators=_operators())

    resolve_recipe(recipe, library=library)

    assert not list(library.rglob("__pycache__"))
    assert not list(library.rglob("*.pyc"))


def test_paper_poster_recipe_resolves_historically_renamed_operator() -> None:
    recipe = ROOT / "evals" / "skills" / "make-paper-poster" / "recipe" / "evolve.yaml"

    resolved = resolve_recipe(recipe)

    assert resolved.operators["rollout"].name == "parent_evaluation"
    assert resolved.operators["rollout"].config["field_limit"] == 6000
    assert resolved.operators["mutate"].name == "aevolve"
    assert "evolve_tools" not in resolved.operators["mutate"].config
