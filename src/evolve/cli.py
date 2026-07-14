from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

import typer

from .archive import archive_path, merged_rows, verify_integrity
from .candidate_runtime import run_candidate_smoke
from .config import RECIPE_NAMES, experiment_int
from .driver import RunOptions, commit_child, eval_child, fork_child, record_fields
from .driver import doctor as doctor_workspace
from .driver import run as driver_run
from .git import head_tag, working_tree_changed_paths
from .population import best_row
from .report import format_report, format_status
from .surface import check_paths, surface_patterns
from .workspace import InitOptions, init_workspace

app = typer.Typer(add_completion=False, no_args_is_help=True, help="evolve mechanism CLI")


def _guard(fn):
    """Wrap a command so any error prints `evolve: <error>` and exits 1, while
    Typer/Click control-flow exceptions (Exit, usage errors like BadParameter)
    pass through unchanged."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (typer.Exit, typer.BadParameter):  # control flow: exit code / usage error
            raise
        except Exception as exc:
            print(f"evolve: {exc}", file=sys.stderr)
            raise typer.Exit(1) from exc

    return wrapper


@app.command()
@_guard
def init(
    workspace: Path,
    recipe: str = typer.Option("hill_climb", help="paradigm recipe to scaffold"),
    seed: str | None = typer.Option(None, help="local target dir or git URL to vendor into target/"),
) -> None:
    """Scaffold a new evolve workspace."""
    if recipe not in RECIPE_NAMES:
        raise typer.BadParameter(
            f"invalid choice: {recipe!r} (choose from {', '.join(RECIPE_NAMES)})", param_hint="--recipe"
        )
    init_workspace(InitOptions(workspace=workspace, recipe=recipe, seed=seed))
    print(f"Initialized evolve workspace at {workspace}")


@app.command()
@_guard
def run(
    workspace: Path,
    max_generations: int | None = typer.Option(None, "--max-generations"),
    children_per_gen: int | None = typer.Option(None, "--children-per-gen"),
    resume: bool = typer.Option(False, "--resume", help="accepted no-op; resume is the default"),
) -> None:
    """Start or resume the built-in evolution loop."""
    gens = max_generations if max_generations is not None else experiment_int(workspace, "max_generations", 40)
    children = children_per_gen if children_per_gen is not None else experiment_int(workspace, "children_per_gen", 1)
    driver_run(RunOptions(workspace=workspace, max_generations=gens, children_per_gen=children))
    print(f"Ran evolve loop through generation {gens}")


@app.command()
@_guard
def fork(workspace: Path, parent: str, child_worktree: Path) -> None:
    """Create a child worktree from a parent generation."""
    fork_child(workspace, parent, child_worktree)
    print(child_worktree)


@app.command()
@_guard
def commit(
    workspace: Path,
    child_worktree: Path,
    parent: str = typer.Option(..., "--parent"),
    genid: str = typer.Option(..., "--genid"),
) -> None:
    """Commit and tag a child worktree."""
    commit_child(workspace, child_worktree, parent, genid)
    print(f"Committed gen/{genid}")


@app.command("eval")
@_guard
def eval_cmd(
    workspace: Path,
    genid: str,
    force: bool = typer.Option(False, "--force", help="re-run evaluation even when a scored row already exists"),
) -> None:
    """Evaluate a tagged child version."""
    eval_child(workspace, genid, force=force)
    print(f"Evaluated gen/{genid}")


@app.command()
@_guard
def record(
    workspace: Path,
    genid: str,
    fields: str = typer.Option(..., "--fields", help="JSON object of fields"),
) -> None:
    """Append non-stamped archive fields."""
    record_fields(workspace, genid, json.loads(fields))
    print(f"Recorded fields for gen/{genid}")


@app.command("surface-check")
@_guard
def surface_check(
    workspace: Path = typer.Argument(Path(".")),
    parent: str | None = typer.Option(None, "--parent"),
) -> None:
    """Report pending out-of-surface edits."""
    include, exclude = surface_patterns(workspace)
    parent_ref = parent or head_tag(workspace) or "gen/0"
    mutated = working_tree_changed_paths(workspace, parent_ref)
    violations = check_paths(mutated, include, exclude)
    print({"ok": not violations, "mutated": mutated, "violations": violations})
    if violations:
        raise typer.Exit(1)


@app.command("candidate-smoke")
@_guard
def candidate_smoke(
    full: bool = typer.Option(False, "--full"),
    checkout: Path = typer.Option(Path("."), "--checkout"),
) -> None:
    """Run the evaluator-provided full smoke against an exact candidate snapshot."""
    if not full:
        raise typer.BadParameter("--full is required", param_hint="--full")
    checkout = checkout.resolve()
    workspace = Path(os.environ.get("EVOLVE_WORKSPACE", checkout)).resolve()
    result = run_candidate_smoke(checkout, workspace=workspace)
    tail = result.stderr_path.read_text().splitlines()[-200:]
    if tail:
        print("\n".join(tail), file=sys.stderr)
    print(
        f"candidate-smoke: {result.status} tree={result.snapshot_tree} "
        f"result={(result.attempt_dir / 'result.json').resolve()} "
        f"stdout={result.stdout_path.resolve()} stderr={result.stderr_path.resolve()}"
    )
    if result.status == "failed":
        raise typer.Exit(2)
    if result.status == "unsupported":
        raise typer.Exit(3)


@app.command()
@_guard
def status(workspace: Path = typer.Argument(Path("."))) -> None:
    """Show current population and best-ever score."""
    print(format_status(workspace), end="")


@app.command()
@_guard
def report(workspace: Path = typer.Argument(Path("."))) -> None:
    """Write an experiment report and research-claim checklist."""
    print(format_report(workspace), end="")


@app.command()
@_guard
def doctor(workspace: Path = typer.Argument(Path("."))) -> None:
    """Detect and repair interrupted state (stale worktrees, pending generations)."""
    actions = doctor_workspace(workspace)
    for action in actions:
        print(action)
    print("doctor: healthy" if not actions else f"doctor: repaired/observed {len(actions)} item(s)")


@app.command()
@_guard
def verify(workspace: Path = typer.Argument(Path("."))) -> None:
    """Integrity fsck: recompute the champion and expose any hand-edited ledger."""
    findings = verify_integrity(workspace)
    for finding in findings:
        print(f"TAMPER: {finding}", file=sys.stderr)
    champion = best_row(workspace)
    champ = f"gen {champion['genid']} score {champion.get('score')}" if champion else "none"
    print(f"champion: {champ}")
    print(f"rows: {len(merged_rows(archive_path(workspace)))}  integrity: {'FAIL' if findings else 'ok'}")
    if findings:
        raise typer.Exit(1)


def main(argv: list[str] | None = None) -> int:
    """Entry point: translate Click/Typer's SystemExit into an int exit code so
    `python -m evolve` (SystemExit(main())) and the console script agree."""
    try:
        app(args=argv)
    except SystemExit as exit_:
        code = exit_.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    return 0
