"""Shared configuration and filesystem helpers for GEPA operators."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def component_paths(config: dict[str, Any]) -> dict[str, list[str]]:
    raw = config.get("components")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("GEPA requires a non-empty components mapping")
    normalized: dict[str, list[str]] = {}
    for raw_name, raw_paths in raw.items():
        name = str(raw_name).strip()
        values = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        if not name or not values or not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("each GEPA component must map to one or more relative paths")
        paths: list[str] = []
        for value in values:
            relative = Path(value.strip())
            if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in {"", "."}:
                raise ValueError(f"GEPA component path must be checkout-relative: {value}")
            paths.append(relative.as_posix().rstrip("/"))
        normalized[name] = paths
    return normalized


def selected_component_names(config: dict[str, Any], genid: str) -> list[str]:
    names = list(component_paths(config))
    strategy = str(config.get("component_strategy") or "round_robin")
    if strategy == "all":
        return names
    if strategy != "round_robin":
        raise ValueError("component_strategy must be 'round_robin' or 'all'")
    match = re.search(r"\d+", genid)
    generation = int(match.group()) if match else 1
    return [names[(max(generation, 1) - 1) % len(names)]]


def path_in_scopes(path: str, scopes: list[str]) -> bool:
    normalized = Path(path).as_posix().rstrip("/")
    return any(normalized == scope or normalized.startswith(scope + "/") for scope in scopes)
