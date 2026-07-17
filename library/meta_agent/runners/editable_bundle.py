"""Stage and transactionally install repository-relative editable bundles."""

from __future__ import annotations

import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evolve.git import git, working_tree_changed_paths
from evolve.patching import SurfacePolicy
from evolve.surface import check_paths


@dataclass(frozen=True)
class EditableBundle:
    staging: Path
    task_root: Path
    candidate_root: Path
    roots: tuple[Path, ...]


def _validate_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"editable root must be a real directory: {root}")
    for path in [root, *root.rglob("*")]:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"editable bundles do not accept symlinks: {path}")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise RuntimeError(f"editable bundles do not accept special files: {path}")


def _roots(raw_roots: object, surface: SurfacePolicy) -> tuple[Path, ...]:
    if not isinstance(raw_roots, list) or not raw_roots:
        raise ValueError("editable_roots must contain at least one editable root")
    roots: list[Path] = []
    for raw in raw_roots:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("each editable root must be a non-empty relative path")
        root = Path(raw)
        if root.is_absolute():
            raise ValueError(f"editable root must be relative: {raw}")
        if any(part in ("", ".", "..") for part in root.parts):
            raise ValueError(f"editable root must not escape or contain dot components: {raw}")
        normalized = Path(*root.parts)
        if check_paths([normalized.as_posix()], surface.include, surface.exclude):
            raise ValueError(f"editable root is not covered by mutable surface: {raw}")
        roots.append(normalized)
    if len(set(roots)) != len(roots):
        raise ValueError("editable roots must not overlap")
    for index, root in enumerate(roots):
        for other in roots[index + 1 :]:
            if root in other.parents or other in root.parents:
                raise ValueError(f"editable roots must not overlap: {root} and {other}")
    return tuple(roots)


def prepare_editable_bundle(checkout: Path, raw_roots: object, surface: SurfacePolicy) -> EditableBundle:
    """Copy the selected clean repository roots into a Harbor task directory."""
    checkout = checkout.resolve()
    roots = _roots(raw_roots, surface)
    # Installation and rollback use atomic rename, so staging must live on the
    # same filesystem as the checkout even when the checkout is a mount point.
    staging = Path(tempfile.mkdtemp(prefix=".evolve-editable-bundle-", dir=checkout))
    task_root = staging / "task"
    candidate_root = task_root / "candidate"
    try:
        candidate_root.mkdir(parents=True)
        for root in roots:
            source = checkout / root
            _validate_tree(source)
            destination = candidate_root / root
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
        return EditableBundle(staging, task_root, candidate_root, roots)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def install_returned_bundle(
    checkout: Path,
    returned_candidate: Path,
    bundle: EditableBundle,
    parent_ref: str,
    surface: SurfacePolicy,
) -> list[str]:
    """Install all returned roots atomically, restoring the checkout on failure."""
    checkout = checkout.resolve()
    returned_candidate = returned_candidate.resolve()
    if not returned_candidate.is_dir() or returned_candidate.is_symlink():
        raise RuntimeError("returned candidate must be a real directory")

    expected = {root.parts[0] for root in bundle.roots}
    actual = {path.name for path in returned_candidate.iterdir()}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing roots: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected roots: " + ", ".join(unexpected))
        raise RuntimeError("invalid returned candidate (" + "; ".join(details) + ")")

    transaction = bundle.staging / "install"
    replacements = transaction / "replacements"
    backups = transaction / "backups"
    replacements.mkdir(parents=True, exist_ok=True)
    backups.mkdir()
    moved_backups: list[Path] = []
    installed: list[Path] = []
    try:
        # Copy and validate every root before changing the live checkout.
        for root in bundle.roots:
            source = returned_candidate / root
            _validate_tree(source)
            destination = replacements / root
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            _validate_tree(destination)

        for root in bundle.roots:
            live = checkout / root
            backup = backups / root
            backup.parent.mkdir(parents=True, exist_ok=True)
            live.rename(backup)
            moved_backups.append(root)
            replacement = replacements / root
            live.parent.mkdir(parents=True, exist_ok=True)
            replacement.rename(live)
            installed.append(root)

        changed = [
            path
            for path in working_tree_changed_paths(checkout, parent_ref)
            if any(path == root.as_posix() or path.startswith(root.as_posix() + "/") for root in bundle.roots)
        ]
        violations = check_paths(changed, surface.include, surface.exclude)
        if violations:
            raise RuntimeError("returned candidate mutated paths outside surface: " + ", ".join(violations))
        result = git(
            checkout, "diff", "--check", parent_ref, "--", *[root.as_posix() for root in bundle.roots], check=False
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"returned candidate failed git diff --check: {detail}")
        shutil.rmtree(transaction, ignore_errors=True)
        return changed
    except Exception:
        for root in reversed(installed):
            _remove(checkout / root)
        for root in reversed(moved_backups):
            live = checkout / root
            backup = backups / root
            _remove(live)
            if backup.exists():
                live.parent.mkdir(parents=True, exist_ok=True)
                backup.rename(live)
        shutil.rmtree(transaction, ignore_errors=True)
        raise


def cleanup_editable_bundle(bundle: EditableBundle) -> None:
    shutil.rmtree(bundle.staging, ignore_errors=True)
