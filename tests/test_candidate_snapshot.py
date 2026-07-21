import subprocess
from pathlib import Path

import pytest

from evolve.candidate.snapshot import (
    CandidateSnapshotError,
    build_candidate_snapshot,
    commit_candidate_snapshot,
    materialize_snapshot,
)


def git_stdout(checkout: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def git_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git_stdout(checkout, "init", "-q")
    git_stdout(checkout, "config", "user.name", "test")
    git_stdout(checkout, "config", "user.email", "test@example.invalid")
    (checkout / "target").mkdir()
    (checkout / "target" / "agent.py").write_text("VALUE = 1\n")
    git_stdout(checkout, "add", ".")
    git_stdout(checkout, "commit", "-qm", "parent")
    return checkout


def test_snapshot_excludes_ignored_untracked_file(tmp_path: Path) -> None:
    checkout = git_checkout(tmp_path)
    (checkout / ".gitignore").write_text("ignored.lock\n")
    (checkout / "visible.txt").write_text("visible\n")
    (checkout / "ignored.lock").write_text("ignored\n")
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=["**"], exclude=[])
    with materialize_snapshot(checkout, snapshot) as materialized:
        assert (materialized / "visible.txt").is_file()
        assert not (materialized / "ignored.lock").exists()


def test_commit_tree_equals_snapshot_tree(tmp_path: Path) -> None:
    checkout = git_checkout(tmp_path)
    (checkout / "target" / "agent.py").write_text("VALUE = 2\n")
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=["target/**"], exclude=[])
    commit = commit_candidate_snapshot(checkout, snapshot, "candidate")
    assert git_stdout(checkout, "rev-parse", f"{commit}^{{tree}}") == snapshot.tree


def test_snapshot_rejects_already_staged_path(tmp_path: Path) -> None:
    checkout = git_checkout(tmp_path)
    (checkout / "target" / "agent.py").write_text("VALUE = 2\n")
    git_stdout(checkout, "add", "target/agent.py")

    with pytest.raises(CandidateSnapshotError, match="^candidate index is not clean$"):
        build_candidate_snapshot(checkout, "HEAD", include=["target/**"], exclude=[])
