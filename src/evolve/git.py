from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def git(
    workspace: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git is required")
    result = subprocess.run(
        [executable, "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
        env=None if env is None else {**os.environ, **env},
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(message)
    return result


def git_stdout(workspace: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return git(workspace, *args, env=env).stdout.strip()


def git_common_dir(workspace: Path) -> str:
    common = Path(git_stdout(workspace, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = workspace / common
    return str(common.resolve())


def head_commit(workspace: Path) -> str:
    return git_stdout(workspace, "rev-parse", "HEAD")


def head_tag(workspace: Path) -> str | None:
    output = git(workspace, "describe", "--tags", "--exact-match", "HEAD", check=False)
    if output.returncode != 0:
        return None
    return output.stdout.strip() or None


def tag_exists(workspace: Path, tag: str) -> bool:
    return git(workspace, "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0


def generation_tags(workspace: Path) -> list[str]:
    output = git_stdout(workspace, "for-each-ref", "--format=%(refname:strip=2)", "refs/tags/gen/")
    return sorted(line for line in output.splitlines() if line.startswith("gen/"))


def changed_paths(workspace: Path, parent_tag: str, child_tag: str) -> list[str]:
    output = git_stdout(workspace, "diff", "--name-only", parent_tag, child_tag)
    return [line for line in output.splitlines() if line]


def working_tree_changed_paths(worktree: Path, parent_tag: str) -> list[str]:
    tracked = git_stdout(worktree, "diff", "--name-only", parent_tag, "--")
    paths = [line for line in tracked.splitlines() if line]
    for path in dirty_paths(worktree):
        if path not in paths:
            paths.append(path)
    return paths


def evaluator_tree(workspace: Path, tag: str) -> str:
    return git_stdout(workspace, "rev-parse", f"{tag}:evaluator")


def commit_paths(workspace: Path, paths: list[str], message: str) -> str:
    git(workspace, "add", "--", *paths)
    git(workspace, "commit", "-m", message)
    return git_stdout(workspace, "rev-parse", "HEAD")


def create_tag(workspace: Path, tag: str) -> None:
    git(workspace, "tag", tag)


def dirty_paths(workspace: Path) -> list[str]:
    output = git(workspace, "status", "--porcelain").stdout
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        paths.append(path)
    return paths


def add_worktree(repo: Path, path: Path, ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "--detach", str(path), ref)


def remove_worktree(repo: Path, path: Path) -> None:
    git(repo, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        shutil.rmtree(path)
