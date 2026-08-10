from __future__ import annotations

import json
from pathlib import Path

import yaml
from conftest import FIXTURE_RECIPES, run_evolve

SMOKE_RECIPE = FIXTURE_RECIPES / "hill_climb-smoke" / "evolve.yaml"


def test_recipe_check_reports_valid_resolved_recipe() -> None:
    result = run_evolve("recipe", "check", str(SMOKE_RECIPE))

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "recipe check: valid (5 operators)\n"


def test_recipe_check_json_reports_resolved_values() -> None:
    result = run_evolve("recipe", "check", str(SMOKE_RECIPE), "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "hill_climb-smoke"
    assert payload["warnings"] == []
    assert payload["operators"]["mutate"]["source_kind"] == "library"
    assert payload["operators"]["mutate"]["name"] == "hyperagents"
    assert payload["operators"]["mutate"]["timeout_s"] == 3600.0
    assert payload["operators"]["mutate"]["config"]["runner"] == "local"
    assert payload["operators"]["mutate"]["portable"] is True
    assert len(payload["operators"]["mutate"]["digest"]) == 64


def test_recipe_check_renders_every_problem_and_exits_one(tmp_path: Path) -> None:
    config = yaml.safe_load(SMOKE_RECIPE.read_text())
    config["operators"]["select"] = {"variant": "greedy"}
    config["operators"]["mutate"] = {
        "operator": "hyperagents",
        "script": "mutate.py",
        "config": {"runner": "local"},
    }
    del config["operators"]["record"]
    recipe = tmp_path / "evolve.yaml"
    recipe.write_text(yaml.safe_dump(config, sort_keys=False))

    result = run_evolve("recipe", "check", str(recipe))

    assert result.returncode == 1
    assert "operators.select.variant:" in result.stderr
    assert "operators.mutate:" in result.stderr
    assert "operators.record:" in result.stderr


def test_recipe_check_warns_for_nonportable_script(tmp_path: Path) -> None:
    config = yaml.safe_load(SMOKE_RECIPE.read_text())
    script = tmp_path / "select.py"
    script.write_text("print('selected')\n")
    config["operators"]["select"] = {"script": "select.py", "config": {}}
    recipe = tmp_path / "evolve.yaml"
    recipe.write_text(yaml.safe_dump(config, sort_keys=False))

    result = run_evolve("recipe", "check", str(recipe))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "warn  operators.select: script source is non-portable" in result.stdout


def test_recipe_check_keeps_yaml_date_config_in_typed_diagnostics(tmp_path: Path) -> None:
    config = yaml.safe_load(SMOKE_RECIPE.read_text())
    config["operators"]["mutate"]["config"]["agent_kwargs"] = {"opaque": "YAML_VALUE"}
    recipe = tmp_path / "evolve.yaml"
    rendered = yaml.safe_dump(config, sort_keys=False)
    assert "opaque: YAML_VALUE" in rendered
    recipe.write_text(rendered.replace("opaque: YAML_VALUE", "opaque: 2026-08-10"))

    result = run_evolve("recipe", "check", str(recipe))

    assert result.returncode == 1
    assert "operators.mutate.config:" in result.stderr
    assert "not JSON-serializable" in result.stderr
    assert "TypeError" not in result.stderr
