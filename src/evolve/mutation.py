from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .git import git, head_tag, working_tree_changed_paths
from .surface import check_paths, surface_patterns


@dataclass(frozen=True)
class SurfacePolicy:
    include: list[str]
    exclude: list[str]


@dataclass(frozen=True)
class MutationPatch:
    changed_paths: list[str]
    diff: str
    surface_report: dict[str, Any]
    notes: list[str]


def load_surface_policy(checkout: Path | str) -> SurfacePolicy:
    include, exclude = surface_patterns(Path(checkout))
    return SurfacePolicy(include=include, exclude=exclude)


def mutation_parent_ref(checkout: Path | str, ctx: Any) -> str:
    parent = getattr(ctx, "parent", None)
    if parent:
        return f"gen/{parent}"
    return head_tag(Path(checkout)) or "gen/0"


def create_mutation_patch(
    checkout: Path | str,
    parent_ref: str,
    surface: SurfacePolicy,
    *,
    repair: bool = True,
) -> MutationPatch:
    root = Path(checkout).resolve()
    notes: list[str] = []
    changed = working_tree_changed_paths(root, parent_ref)
    violations = check_paths(changed, surface.include, surface.exclude)

    if violations and repair:
        repaired = _repair_surface_violations(root, parent_ref, violations)
        if repaired:
            notes.append("repaired surface violations by " + "; ".join(repaired))
        changed = working_tree_changed_paths(root, parent_ref)
        violations = check_paths(changed, surface.include, surface.exclude)

    diff = git(root, "diff", "--binary", parent_ref, "--").stdout
    surface_report = {"ok": not violations, "mutated": changed, "violations": violations}
    return MutationPatch(changed_paths=changed, diff=diff, surface_report=surface_report, notes=notes)


def _repair_surface_violations(root: Path, parent_ref: str, violations: list[str]) -> list[str]:
    notes: list[str] = []
    reverted: list[str] = []
    removed: list[str] = []
    for path in violations:
        action = _repair_surface_path(root, parent_ref, path)
        if action == "reverted":
            reverted.append(path)
        elif action == "removed":
            removed.append(path)
    if reverted:
        notes.append("reverted: " + ", ".join(reverted))
    if removed:
        notes.append("removed untracked: " + ", ".join(removed))
    return notes


def _repair_surface_path(root: Path, parent_ref: str, path: str) -> str | None:
    rel = Path(path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return None

    candidate = root / rel
    status = git(root, "status", "--porcelain", "--", path, check=False)
    if status.stdout.startswith("??"):
        if candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)
        elif candidate.exists():
            candidate.unlink()
        return "removed"

    result = git(root, "checkout", parent_ref, "--", path, check=False)
    if result.returncode == 0:
        return "reverted"
    return None
