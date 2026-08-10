from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import typer

from .recipe import RecipeResolutionError, ResolvedRecipe, render_recipe_problems, resolve_recipe


class _Guard(Protocol):
    def __call__[F: Callable[..., object]](self, function: F, /) -> F: ...


def recipe_check_payload(resolved: ResolvedRecipe) -> dict[str, object]:
    operators: dict[str, object] = {}
    for stage, binding in resolved.operators.items():
        operators[stage] = {
            "source_kind": binding.source_kind,
            "name": binding.name,
            "timeout_s": binding.timeout_s,
            "config": binding.config,
            "portable": binding.portable,
            "digest": binding.digest,
        }
    return {
        "name": resolved.name,
        "directory": str(resolved.directory),
        "operators": operators,
        "warnings": list(resolved.warnings),
    }


def build_recipe_app(guard: _Guard) -> typer.Typer:
    recipe_app = typer.Typer(add_completion=False, no_args_is_help=True)

    @recipe_app.command("check")
    @guard
    def recipe_check(path: Path, json_output: bool = typer.Option(False, "--json")) -> None:
        try:
            resolved = resolve_recipe(path)
        except RecipeResolutionError as error:
            print(render_recipe_problems(error.problems), file=sys.stderr)
            raise typer.Exit(1) from error
        if json_output:
            print(json.dumps(recipe_check_payload(resolved), indent=2, sort_keys=True, allow_nan=False))
        else:
            print(f"recipe check: valid ({len(resolved.operators)} operators)")
            for warning in resolved.warnings:
                print(f"warn  {warning}")

    return recipe_app
