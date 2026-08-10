"""Render one truthful candidate-workspace contract for mutate prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evolve.patching import load_surface_policy


def _relative(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"mutate context path must be checkout-relative: {path}")
    return path.as_posix()


def _detected_prompt(checkout: Path, config: dict[str, Any]) -> str | None:
    configured = _relative(config.get("prompt_path"))
    if configured is not None:
        return configured
    components = config.get("components")
    if isinstance(components, dict):
        for name in ("system_prompt", "prompt"):
            candidate = _relative(components.get(name))
            if candidate is not None:
                return candidate
    for candidate in (
        "target/prompt.md",
        "target/src/minisweagent/config/mini.yaml",
        "target/prompts/system.md",
    ):
        if (checkout / candidate).is_file():
            return candidate
    return None


def _detected_directory(checkout: Path, config: dict[str, Any], key: str, default: str) -> str | None:
    configured = _relative(config.get(key))
    if configured is not None:
        return configured
    return default if (checkout / default).is_dir() else None


def _editable_roots(config: dict[str, Any], includes: list[str]) -> list[str]:
    configured = config.get("editable_roots")
    if configured is not None:
        if not isinstance(configured, list) or not all(
            isinstance(item, str) and item and Path(item).name == item for item in configured
        ):
            raise ValueError("editable_roots must contain top-level relative directory names")
        return list(dict.fromkeys(configured))
    roots: list[str] = []
    for pattern in includes:
        root = pattern.split("/", 1)[0]
        if root and not any(char in root for char in "*?[") and root not in roots:
            roots.append(root)
    return roots or ["target"]


def _location(label: str, path: str | None) -> str:
    return f"- {label}: `{path}`" if path is not None else f"- {label}: not configured or detected"


def workspace_contract(
    checkout: Path,
    config: dict[str, Any],
    *,
    action_paths: list[str] | None = None,
) -> str:
    """Describe mutation permission separately from candidate runtime context paths."""
    surface = load_surface_policy(checkout)
    includes = list(surface.include)
    excludes = list(surface.exclude)
    roots = _editable_roots(config, includes)
    prompt = _detected_prompt(checkout, config)
    skills = _detected_directory(checkout, config, "skills_dir", "target/skills")
    memory = _detected_directory(checkout, config, "memory_dir", "target/memory")
    permissions = "\n".join(f"- You CAN modify any file under `{root}/`." for root in roots)
    scope = (
        "- This method further restricts the current proposal to: "
        + ", ".join(f"`{path}`" for path in action_paths)
        + "."
        if action_paths
        else "- This method does not impose a narrower per-proposal path scope."
    )
    return (
        "# Candidate Workspace Contract\n\n"
        "## Mutation Permission\n\n"
        f"{permissions}\n"
        f"- Enforced surface include: {includes}\n"
        f"- Enforced surface exclude: {excludes}\n"
        f"{scope}\n\n"
        "`prompt_path`, `skills_dir`, and `memory_dir` identify runtime components; "
        "they do not narrow the mutation permission above.\n\n"
        "## Runtime Context Locations\n\n"
        f"{_location('Runtime prompt/config', prompt)}\n"
        f"{_location('Reusable skills', skills)}\n"
        f"{_location('Long-term memory', memory)}\n\n"
        "A file in a skills or memory directory affects the deployed agent only if the candidate runtime "
        "loads or invokes it. When proposing such a file, verify or implement that runtime path in the same candidate."
    )
