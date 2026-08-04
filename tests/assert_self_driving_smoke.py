from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from evolve.archive import RECEIPT_CERTIFIED_FIELD, archive_path, merged_rows, read_events
from evolve.git import dirty_paths, git
from evolve.population import tag_matches_candidate


def assert_self_driving_smoke(workspace: Path, through: int) -> None:
    """Assert that a deterministic smoke run produced a complete, usable lineage."""
    if through < 0:
        raise ValueError("through must be non-negative")

    workspace = workspace.resolve()
    archive = archive_path(workspace)
    operator_failures = [
        str(event.get("genid", "?")) for event in read_events(archive) if event.get("status") == "operator_failed"
    ]
    if operator_failures:
        raise AssertionError(f"operator_failed events recorded for generations: {', '.join(operator_failures)}")

    rows = merged_rows(archive)
    expected = [str(generation) for generation in range(through + 1)]
    actual = [str(row.get("genid", "")) for row in rows]
    if actual != expected:
        raise AssertionError(f"expected exactly generations {expected}, got {actual}")

    for genid, row in zip(expected, rows, strict=True):
        required = {
            "status": "complete",
            "selection_eligible": True,
            "valid_parent": True,
            "verdict": "keep",
            RECEIPT_CERTIFIED_FIELD: True,
        }
        for field, value in required.items():
            if row.get(field) != value:
                raise AssertionError(f"gen/{genid}: expected {field}={value!r}, got {row.get(field)!r}")
        if not tag_matches_candidate(workspace, row, genid):
            raise AssertionError(f"gen/{genid}: tag does not resolve to candidate_commit")
        if genid != "0":
            if row.get("mutated") != ["target/agent.py"]:
                raise AssertionError(f"gen/{genid}: expected deterministic target mutation, got {row.get('mutated')!r}")
            candidate = git(workspace, "show", f"gen/{genid}:target/agent.py").stdout
            marker = f"# smoke-meta-agent gen {genid}"
            if marker not in candidate.splitlines():
                raise AssertionError(f"gen/{genid}: candidate code is missing deterministic marker")

    dirty = dirty_paths(workspace)
    if dirty:
        raise AssertionError(f"workspace is dirty: {', '.join(dirty)}")

    registered = _registered_worktrees(workspace)
    stray_registered = [path for path in registered if path != workspace]
    if stray_registered:
        raise AssertionError(f"stray registered worktrees: {', '.join(map(str, stray_registered))}")

    worktree_root = workspace / "runs" / "worktrees"
    stale_paths = sorted(worktree_root.iterdir()) if worktree_root.is_dir() else []
    if stale_paths:
        raise AssertionError(f"stale worktree paths: {', '.join(map(str, stale_paths))}")


def _registered_worktrees(workspace: Path) -> list[Path]:
    output = git(workspace, "worktree", "list", "--porcelain").stdout
    return [
        Path(line.removeprefix("worktree ")).resolve() for line in output.splitlines() if line.startswith("worktree ")
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assert that a self-driving smoke run actually evolved candidates")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("through", type=int, help="last expected numeric generation")
    args = parser.parse_args(argv)

    try:
        assert_self_driving_smoke(args.workspace, args.through)
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"self-driving smoke failed: {error}\n")

    print(f"self-driving smoke ok: generations 0..{args.through}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
