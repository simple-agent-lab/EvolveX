from __future__ import annotations

import copy
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

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


def evaluator_stage(workspace: Path) -> dict[str, Any] | None:
    value = evaluator_values(workspace).get("stage")
    if not isinstance(value, dict):
        return None
    tasks = value.get("tasks")
    if not isinstance(tasks, int) or isinstance(tasks, bool) or tasks < 1:
        raise ValueError("evaluator.stage.tasks must be a positive integer")
    proceed_if = str(value.get("proceed_if", "positive"))
    if proceed_if != "positive":
        raise ValueError("evaluator.stage.proceed_if must be positive")
    return {"tasks": tasks, "proceed_if": proceed_if}


def evaluator_anchor(workspace: Path) -> dict[str, Any]:
    value = evaluator_values(workspace).get("anchor")
    return dict(value) if isinstance(value, dict) else {}


def _read_section(workspace: Path, name: str) -> dict[str, Any]:
    return _read_section_file(workspace / "evolve.yaml", name)


def _read_config_file(config: Resource) -> dict[str, Any]:
    return {section: _read_section_file(config, section) for section in CONFIG_SECTIONS}


def _read_section_file(config: Resource, name: str) -> dict[str, Any]:
    # is_file() (not exists()) works for both a Path and a packaged Traversable.
    if not config.is_file():
        return {}
    values: dict[str, Any] = {}
    in_section = False
    current_list: str | None = None
    for line in config.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{name}:"):
            inline = stripped.split(":", 1)[1].strip()
            if inline:
                return {key: _coerce_scalar(value) for key, value in _parse_inline_mapping(inline).items()}
            in_section = True
            current_list = None
            continue
        if in_section and line and not line.startswith(" "):
            break
        if not in_section or not stripped:
            continue
        if current_list and stripped.startswith("- "):
            values[current_list].append(stripped[2:].strip().strip("\"'"))
            continue
        if ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        current_list = None
        if not raw:
            values[key] = []
            current_list = key
            continue
        if raw.startswith("{"):
            values[key] = {
                item_key: _coerce_scalar(item_value) for item_key, item_value in _parse_inline_mapping(raw).items()
            }
            continue
        if raw.startswith("["):
            values[key] = _parse_inline_list(raw)
            continue
        values[key] = _coerce_scalar(raw)
    return values


def _parse_inline_mapping(value: str) -> dict[str, str]:
    if not (value.startswith("{") and value.endswith("}")):
        return {}
    inner = value[1:-1].strip()
    if not inner:
        return {}
    values: dict[str, str] = {}
    for item in inner.split(","):
        if ":" not in item:
            continue
        key, raw_value = item.split(":", 1)
        values[key.strip()] = raw_value.strip()
    return values


def _parse_inline_list(value: str) -> list[str]:
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    return []


def _coerce_scalar(value: str) -> Any:
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def render_yaml(value: dict[str, Any]) -> str:
    lines: list[str] = []
    _render_mapping(lines, value, 0)
    return "\n".join(lines) + "\n"


def _render_mapping(lines: list[str], mapping: dict[str, Any], indent: int) -> None:
    prefix = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            if _is_inline_mapping(value):
                lines.append(f"{prefix}{key}: {_format_inline_mapping(value)}")
            else:
                lines.append(f"{prefix}{key}:")
                _render_mapping(lines, value, indent + 2)
        elif isinstance(value, list):
            if value:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}  - {_format_scalar(item)}")
            else:
                lines.append(f"{prefix}{key}: []")
        else:
            lines.append(f"{prefix}{key}: {_format_scalar(value)}")


def _is_inline_mapping(mapping: dict[str, Any]) -> bool:
    return all(not isinstance(item, (dict, list)) for item in mapping.values())


def _format_inline_mapping(mapping: dict[str, Any]) -> str:
    pairs = ", ".join(f"{key}: {_format_scalar(value)}" for key, value in mapping.items())
    return "{" + pairs + "}"


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)
