from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .candidate.snapshot import build_candidate_snapshot
from .git import git, head_tag, working_tree_changed_paths
from .surface import check_paths, surface_patterns


@dataclass(frozen=True)
class SurfacePolicy:
    include: list[str]
    exclude: list[str]


@dataclass(frozen=True)
class CandidatePatch:
    changed_paths: list[str]
    diff: str
    surface_report: dict[str, Any]
    notes: list[str]


def load_surface_policy(checkout: Path | str) -> SurfacePolicy:
    include, exclude = surface_patterns(Path(checkout))
    return SurfacePolicy(include=include, exclude=exclude)


def patch_parent_ref(checkout: Path | str, ctx: Any) -> str:
    parent = getattr(ctx, "parent", None)
    if parent:
        return f"gen/{parent}"
    return head_tag(Path(checkout)) or "gen/0"


def create_candidate_patch(
    checkout: Path | str,
    parent_ref: str,
    surface: SurfacePolicy,
    *,
    repair: bool = True,
) -> CandidatePatch:
    root = Path(checkout).resolve()
    notes: list[str] = []
    if _restore_unchanged_injected_archive(root, parent_ref):
        notes.append("ignored unchanged framework-injected archive.jsonl")
    changed = working_tree_changed_paths(root, parent_ref)
    violations = check_paths(changed, surface.include, surface.exclude)

    if violations and repair:
        repaired = _repair_surface_violations(root, parent_ref, violations)
        if repaired:
            notes.append("repaired surface violations by " + "; ".join(repaired))
        changed = working_tree_changed_paths(root, parent_ref)
        violations = check_paths(changed, surface.include, surface.exclude)

    if violations:
        diff = _candidate_diff(root, parent_ref, changed)
    else:
        snapshot = build_candidate_snapshot(root, parent_ref, include=surface.include, exclude=surface.exclude)
        changed = list(snapshot.changed_paths)
        diff = git(root, "diff", "--binary", parent_ref, snapshot.commit, "--").stdout
    surface_report = {"ok": not violations, "mutated": changed, "violations": violations}
    return CandidatePatch(changed_paths=changed, diff=diff, surface_report=surface_report, notes=notes)


def _restore_unchanged_injected_archive(root: Path, parent_ref: str) -> bool:
    workspace_raw = os.environ.get("EVOLVE_WORKSPACE")
    checkout_raw = os.environ.get("EVOLVE_CHECKOUT")
    if not workspace_raw or not checkout_raw:
        return False
    workspace = Path(workspace_raw).resolve()
    if workspace == root or Path(checkout_raw).resolve() != root:
        return False
    live_archive = workspace / "archive.jsonl"
    checkout_archive = root / "archive.jsonl"
    try:
        unchanged = (
            live_archive.is_file()
            and checkout_archive.is_file()
            and (live_archive.read_bytes() == checkout_archive.read_bytes())
        )
    except OSError:
        return False
    if not unchanged:
        return False
    return _repair_surface_path(root, parent_ref, "archive.jsonl") is not None


def _candidate_diff(root: Path, parent_ref: str, changed: list[str]) -> str:
    if not changed:
        return ""
    untracked = {
        path for path in changed if git(root, "status", "--porcelain", "--", path, check=False).stdout.startswith("??")
    }
    tracked = [path for path in changed if path not in untracked]
    parts: list[str] = []
    if tracked:
        parts.append(git(root, "diff", "--binary", parent_ref, "--", *tracked).stdout)
    for path in changed:
        if path in untracked:
            parts.append(git(root, "diff", "--binary", "--no-index", "--", "/dev/null", path, check=False).stdout)
    return "".join(parts)


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
