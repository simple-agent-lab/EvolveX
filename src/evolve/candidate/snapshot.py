from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..git import add_worktree, commit_paths, git, git_stdout, remove_worktree, working_tree_changed_paths
from ..surface import check_paths


class CandidateSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSnapshot:
    parent_ref: str
    commit: str
    tree: str
    changed_paths: tuple[str, ...]


def build_candidate_snapshot(
    checkout: Path,
    parent_ref: str,
    *,
    include: list[str],
    exclude: list[str],
) -> CandidateSnapshot:
    if git(checkout, "diff", "--cached", "--quiet", check=False).returncode:
        raise CandidateSnapshotError("candidate index is not clean")
    changed = tuple(working_tree_changed_paths(checkout, parent_ref))
    violations = check_paths(list(changed), include, exclude)
    if violations:
        raise CandidateSnapshotError("changed paths outside mutable surface: " + ", ".join(violations))
    with tempfile.TemporaryDirectory(prefix="evolve-index-") as temporary:
        env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(checkout, "read-tree", parent_ref, env=env)
        if changed:
            git(checkout, "add", "-A", "--", *changed, env=env)
        tree = git_stdout(checkout, "write-tree", env=env)
        commit = git_stdout(checkout, "commit-tree", tree, "-p", parent_ref, "-m", "evolve snapshot")
    return CandidateSnapshot(parent_ref, commit, tree, changed)


@contextmanager
def materialize_snapshot(repo: Path, snapshot: CandidateSnapshot) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="evolve-snapshot-") as temporary:
        checkout = Path(temporary) / "checkout"
        add_worktree(repo, checkout, snapshot.commit)
        try:
            yield checkout
        finally:
            remove_worktree(repo, checkout)


def commit_candidate_snapshot(checkout: Path, snapshot: CandidateSnapshot, message: str) -> str:
    commit = commit_paths(checkout, list(snapshot.changed_paths), message)
    if git_stdout(checkout, "rev-parse", f"{commit}^{{tree}}") != snapshot.tree:
        raise CandidateSnapshotError("candidate commit differs from reviewed snapshot")
    return commit
