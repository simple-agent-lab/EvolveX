from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal, cast

import yaml

from .config import RECIPE_NAMES, Resource, library_root, load_config, recipe_root
from .frozen.interfaces import OPERATOR_BY_KIND, REQUIRED_OPERATOR_KINDS
from .operator_library import OPERATOR_NAME, OperatorLibraryError, resolve_operator, validate_operator_config

_STAGE_KEYS = frozenset({"operator", "script", "timeout_s", "config"})
_OLD_STAGES = {"trace_analyzer": "analyze", "meta_agent": "mutate"}
_DEFAULT_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class RecipeProblem:
    path: str
    message: str


@dataclass(frozen=True)
class ResolvedOperator:
    stage: str
    source_kind: Literal["library", "script"]
    source: Path | Traversable
    name: str | None
    timeout_s: float
    config: dict[str, object]
    portable: bool
    digest: str


@dataclass(frozen=True)
class ResolvedRecipe:
    name: str
    directory: Path | Traversable
    config: dict[str, object]
    operators: dict[str, ResolvedOperator]
    warnings: tuple[str, ...]


class RecipeResolutionError(ValueError):
    def __init__(self, problems: Sequence[RecipeProblem]) -> None:
        self.problems = tuple(problems)
        super().__init__(render_recipe_problems(self.problems))


def render_recipe_problems(problems: Sequence[RecipeProblem]) -> str:
    return "\n".join(f"{problem.path}: {problem.message}" for problem in problems)


def resolve_recipe(path: Path, *, library: Resource | None = None) -> ResolvedRecipe:
    selected = path.expanduser()
    config_resource = selected / "evolve.yaml" if selected.is_dir() else selected
    directory = config_resource.parent
    return _resolve_recipe(directory.name, directory, config_resource, library)


def resolve_builtin_recipe(name: str, *, library: Resource | None = None) -> ResolvedRecipe:
    if name not in RECIPE_NAMES:
        supported = ", ".join(RECIPE_NAMES)
        raise RecipeResolutionError((RecipeProblem("recipe", f"unsupported recipe: {name}; choose from {supported}"),))
    directory = recipe_root() / name
    return _resolve_recipe(name, directory, directory / "evolve.yaml", library)


def _resolve_recipe(
    name: str,
    directory: Path | Traversable,
    config_resource: Resource,
    library: Resource | None,
) -> ResolvedRecipe:
    problems: list[RecipeProblem] = []
    warnings: list[str] = []
    if not config_resource.is_file():
        raise RecipeResolutionError((RecipeProblem("recipe", f"config file does not exist: {config_resource}"),))
    try:
        config = cast("dict[str, object]", load_config(config_resource))
    except (ValueError, yaml.YAMLError) as error:
        raise RecipeResolutionError((RecipeProblem("recipe", str(error)),)) from error
    if isinstance(directory, Path) and (directory / "operators").is_dir():
        problems.append(RecipeProblem("operators", "recipe-local operator libraries are not supported"))

    raw_operators = config.get("operators")
    if not isinstance(raw_operators, Mapping):
        problems.append(RecipeProblem("operators", "must be a mapping"))
        raw_operators = {}
    operator_blocks = cast("Mapping[object, object]", raw_operators)
    default_timeout = _timeout(
        operator_blocks.get("timeout_s", _DEFAULT_TIMEOUT_S),
        "operators.timeout_s",
        problems,
        _DEFAULT_TIMEOUT_S,
    )

    for raw_stage in operator_blocks:
        stage = str(raw_stage)
        if stage == "timeout_s" or stage in OPERATOR_BY_KIND:
            continue
        replacement = _OLD_STAGES.get(stage)
        message = f"stage is no longer supported; use {replacement}" if replacement else "unknown operator stage"
        problems.append(RecipeProblem(f"operators.{stage}", message))
    for stage in REQUIRED_OPERATOR_KINDS:
        if stage not in operator_blocks:
            problems.append(RecipeProblem(f"operators.{stage}", "required operator stage is missing"))

    resolved: dict[str, ResolvedOperator] = {}
    normalized: dict[str, object] = {"timeout_s": default_timeout}
    selected_library = library or library_root()
    for stage in OPERATOR_BY_KIND:
        if stage not in operator_blocks:
            continue
        binding = _resolve_stage(
            stage,
            operator_blocks[stage],
            directory,
            selected_library,
            default_timeout,
            problems,
            warnings,
        )
        if binding is None:
            continue
        resolved[stage] = binding
        block: dict[str, object] = {
            "timeout_s": binding.timeout_s,
            "config": binding.config,
        }
        if binding.name is None:
            block["script"] = str(cast(Path, binding.source))
        else:
            block["operator"] = binding.name
        normalized[stage] = block

    if problems:
        raise RecipeResolutionError(problems)
    config["operators"] = normalized
    return ResolvedRecipe(name, directory, config, resolved, tuple(warnings))


def _resolve_stage(
    stage: str,
    raw_block: object,
    directory: Path | Traversable,
    library: Resource,
    default_timeout: float,
    problems: list[RecipeProblem],
    warnings: list[str],
) -> ResolvedOperator | None:
    prefix = f"operators.{stage}"
    if not isinstance(raw_block, Mapping):
        problems.append(RecipeProblem(prefix, "must be a mapping"))
        return None
    block = cast("Mapping[object, object]", raw_block)
    for raw_key in block:
        key = str(raw_key)
        if key in _STAGE_KEYS:
            continue
        message = "variant is no longer supported; use operator" if key == "variant" else "unknown stage key"
        problems.append(RecipeProblem(f"{prefix}.{key}", message))

    has_operator = "operator" in block
    has_script = "script" in block
    timeout = _timeout(block.get("timeout_s", default_timeout), f"{prefix}.timeout_s", problems, default_timeout)
    raw_config = block.get("config", {})
    config_is_mapping = isinstance(raw_config, Mapping)
    if not config_is_mapping:
        problems.append(RecipeProblem(f"{prefix}.config", "must be a mapping"))
    operator_config = {str(key): value for key, value in raw_config.items()} if config_is_mapping else {}
    if has_operator == has_script:
        if not ("variant" in block and not has_operator):
            problems.append(RecipeProblem(prefix, "specify exactly one of operator or script"))
        return None
    if not config_is_mapping:
        return None

    if has_operator:
        raw_name = block["operator"]
        if not isinstance(raw_name, str) or not OPERATOR_NAME.fullmatch(raw_name):
            problems.append(RecipeProblem(f"{prefix}.operator", "invalid operator name"))
            return None
        try:
            operator = resolve_operator(stage, raw_name, library)
        except OperatorLibraryError as error:
            problems.append(RecipeProblem(f"{prefix}.operator", str(error)))
            return None
        try:
            normalized = validate_operator_config(operator, operator_config)
        except OperatorLibraryError as error:
            problems.append(RecipeProblem(f"{prefix}.config", str(error)))
            return None
        source = operator.source
        return ResolvedOperator(
            stage,
            "library",
            source,
            raw_name,
            timeout,
            normalized,
            True,
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )

    raw_script = block["script"]
    if not isinstance(raw_script, str) or not raw_script:
        problems.append(RecipeProblem(f"{prefix}.script", "must be a non-empty path"))
        return None
    if not isinstance(directory, Path):
        problems.append(RecipeProblem(f"{prefix}.script", "script needs a stable filesystem recipe directory"))
        return None
    script = Path(raw_script).expanduser()
    if not script.is_absolute():
        script = directory / script
    script = script.resolve()
    if not script.is_file():
        problems.append(RecipeProblem(f"{prefix}.script", f"script does not exist: {raw_script}"))
        return None
    warnings.append(f"{prefix}: script source is non-portable")
    return ResolvedOperator(
        stage,
        "script",
        script,
        None,
        timeout,
        operator_config,
        False,
        hashlib.sha256(script.read_bytes()).hexdigest(),
    )


def _timeout(
    value: object,
    path: str,
    problems: list[RecipeProblem],
    fallback: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        problems.append(RecipeProblem(path, "must be a positive number"))
        return fallback
    return float(value)
