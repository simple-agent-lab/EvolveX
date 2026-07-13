from __future__ import annotations

import copy
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml

from .frozen.interfaces import OPTIONAL_OPERATOR_KINDS as _OPTIONAL_OPERATOR_KINDS
from .frozen.interfaces import REQUIRED_OPERATOR_KINDS


def hill_climb_config(experiment_id: str) -> dict[str, Any]:
    return default_config("hill_climb", experiment_id)


CONFIG_SECTIONS = ("experiment", "target", "surface", "operators", "evaluator")
# The operator set is defined once in interfaces.OPERATORS; kind lists derive
# from it so they cannot drift (mechanism 6). Required kinds always run; optional
# kinds run only when a recipe opts in (DESIGN §8, off by default).
OPERATOR_KINDS = REQUIRED_OPERATOR_KINDS
OPTIONAL_OPERATOR_KINDS = _OPTIONAL_OPERATOR_KINDS
Resource = Path | Traversable
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def resource_root(name: str) -> Resource:
    source_path = SOURCE_ROOT / name
    if source_path.exists():
        return source_path
    return resources.files("evolve") / name


def recipe_root() -> Resource:
    return resource_root("recipes")


def library_root() -> Resource:
    return resource_root("library")


def _recipe_names() -> tuple[str, ...]:
    root = recipe_root()
    if not root.is_dir():
        return ()
    return tuple(
        path.name for path in sorted(root.iterdir(), key=lambda item: item.name) if (path / "evolve.yaml").is_file()
    )


RECIPE_NAMES = _recipe_names()


def default_config(recipe: str, experiment_id: str) -> dict[str, Any]:
    if recipe not in RECIPE_NAMES:
        raise ValueError(f"unsupported recipe: {recipe}")
    config = _read_config_file(recipe_root() / recipe / "evolve.yaml")
    config = copy.deepcopy(config)
    config["experiment"]["id"] = experiment_id
    return config


def experiment_id(workspace: Path) -> str:
    return experiment_values(workspace).get("id") or workspace.name


def experiment_int(workspace: Path, key: str, default: int) -> int:
    value = experiment_values(workspace).get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def experiment_values(workspace: Path) -> dict[str, str]:
    values = _read_section(workspace, "experiment")
    return {key: str(value) for key, value in values.items() if not isinstance(value, (dict, list))}


def surface_lists(workspace: Path) -> tuple[list[str], list[str]]:
    values = _read_section(workspace, "surface")
    include = values.get("include")
    exclude = values.get("exclude")
    return _string_list(include) or ["target/**"], _string_list(exclude)


def operator_blocks(workspace: Path) -> dict[str, Any]:
    return _read_section(workspace, "operators")


def evaluator_values(workspace: Path) -> dict[str, Any]:
    return _read_section(workspace, "evaluator")


def evaluator_sampling(workspace: Path) -> str:
    value = evaluator_values(workspace).get("sampling", "static")
    return str(value or "static")


def evaluator_boolean(values: dict[str, Any], key: str, default: bool = False) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"evaluator.{key} must be a boolean")
    return value


def _read_section(workspace: Path, name: str) -> dict[str, Any]:
    return _read_section_file(workspace / "evolve.yaml", name)


def _read_config_file(config: Resource) -> dict[str, Any]:
    return load_config(config)


def load_config(config: Resource) -> dict[str, Any]:
    # is_file() (not exists()) works for both a Path and a packaged Traversable.
    if not config.is_file():
        return {section: {} for section in CONFIG_SECTIONS}
    loaded = yaml.safe_load(config.read_text())
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError("config document must be a mapping")
    unknown = sorted(str(key) for key in loaded if key not in CONFIG_SECTIONS)
    if unknown:
        raise ValueError("unknown top-level config sections: %s" % ", ".join(unknown))
    result: dict[str, Any] = {}
    for section in CONFIG_SECTIONS:
        value = loaded.get(section, {})
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValueError(f"{section} section must be a mapping")
        result[section] = value
    return result


def _read_section_file(config: Resource, name: str) -> dict[str, Any]:
    return dict(load_config(config)[name])


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def render_yaml(value: dict[str, Any]) -> str:
    validated = {section: value.get(section, {}) for section in CONFIG_SECTIONS}
    return yaml.safe_dump(validated, sort_keys=False, allow_unicode=False)
