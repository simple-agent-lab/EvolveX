from __future__ import annotations

import functools
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from dotenv import dotenv_values

from .archive import archive_path, merged_rows, verify_integrity
from .candidate.smoke import run_candidate_smoke
from .config import DEFAULT_RECIPE, RECIPE_NAMES, experiment_int
from .driver import RunOptions
from .driver import doctor as doctor_workspace
from .driver import run as driver_run
from .git import head_tag, working_tree_changed_paths
from .operator_cli import attach_orchestration_commands
from .orchestration import commit_agent_child, eval_agent_child, fork_agent_child, record_agent_fields
from .population import best_row
from .report import format_report, format_status
from .surface import check_paths, surface_patterns
from .workspace import InitOptions, init_workspace

app = typer.Typer(add_completion=False, no_args_is_help=True, help="evolve mechanism CLI")
DEFAULT_WORKSPACE = Path("~/.evolve-workspace")


def _enable_live_output(enabled: bool) -> None:
    if enabled:
        os.environ["EVOLVE_LIVE_OUTPUT"] = "1"


@contextmanager
def _workspace_environment(workspace: Path) -> Iterator[None]:
    workspace_env = workspace.resolve() / ".env"
    caller_env = Path.cwd().resolve() / ".env"
    added: list[str] = []
    try:
        for path in dict.fromkeys((workspace_env, caller_env)):
            for name, value in dotenv_values(path).items():
                if value is not None and name not in os.environ:
                    os.environ[name] = value
                    added.append(name)
        yield
    finally:
        for name in reversed(added):
            os.environ.pop(name, None)


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


attach_orchestration_commands(app, _guard, _workspace_environment, _enable_live_output)


@app.command()
@_guard
def init(
    workspace: Path | None = typer.Argument(
        None,
        help="workspace directory (default: ~/.evolve-workspace)",
    ),
    recipe: str | None = typer.Option(
        None,
        help=f"supported public recipe to scaffold (default: {DEFAULT_RECIPE})",
    ),
    recipe_path: Path | None = typer.Option(
        None,
        "--recipe-path",
        help="opt-in recipe directory or evolve.yaml path",
    ),
    seed: str | None = typer.Option(
        None, help="git URL to vendor into target/; local target dir; builtin-codex"
    ),
    dataset: str | None = typer.Option(None, help="local Harbor task directory to split and freeze"),
) -> None:
    """Scaffold a new evolve workspace."""
    workspace = (workspace or DEFAULT_WORKSPACE).expanduser()
    if recipe is not None and recipe_path is not None:
        raise typer.BadParameter(
            "cannot combine --recipe with --recipe-path",
            param_hint="--recipe-path",
        )
    selected_recipe = recipe or DEFAULT_RECIPE
    if recipe_path is None and selected_recipe not in RECIPE_NAMES:
        raise typer.BadParameter(
            f"invalid choice: {selected_recipe!r} (choose from {', '.join(RECIPE_NAMES)})",
            param_hint="--recipe",
        )
    init_workspace(
        InitOptions(
            workspace=workspace,
            recipe=selected_recipe if recipe_path is None else None,
            seed=seed,
            dataset=dataset,
            recipe_path=recipe_path,
        )
    )
    print(f"Initialized evolve workspace at {workspace}")


@app.command()
@_guard
def preflight(
    workspace: Path | None = typer.Argument(
        None,
        help="workspace directory (default: ~/.evolve-workspace)",
    ),
    recipe: str | None = typer.Option(
        None,
        help=f"supported public recipe to scaffold (default: {DEFAULT_RECIPE})",
    ),
    recipe_path: Path | None = typer.Option(
        None,
        "--recipe-path",
        help="opt-in recipe directory or evolve.yaml path",
    ),
    seed: str | None = typer.Option(
        None, help="git URL to vendor into target/; local target dir; builtin-codex"
    ),
    dataset: str | None = typer.Option(None, help="local Harbor task directory to split and freeze"),
) -> None:
    """Check every `evolve init` precondition without writing anything.

    Takes the same arguments as init and reports one checklist instead of one
    refusal at a time."""
    from .preflight import render, run_preflight

    checks = run_preflight(
        workspace=(workspace or DEFAULT_WORKSPACE).expanduser(),
        recipe=recipe,
        recipe_path=recipe_path,
        seed=seed,
        dataset=dataset,
    )
    output, ready = render(checks)
    print(output)
    if not ready:
        raise typer.Exit(1)


@app.command()
@_guard
def run(
    workspace: Path,
    max_generations: int | None = typer.Option(None, "--max-generations"),
    children_per_gen: int | None = typer.Option(None, "--children-per-gen"),
    resume: bool = typer.Option(False, "--resume", help="accepted no-op; resume is the default"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="stream evaluator and operator output"),
) -> None:
    """Start or resume the driver, the unattended evolution loop."""
    gens = max_generations if max_generations is not None else experiment_int(workspace, "max_generations", 40)
    children = children_per_gen if children_per_gen is not None else experiment_int(workspace, "children_per_gen", 1)
    _enable_live_output(verbose)
    with _workspace_environment(workspace):
        driver_run(RunOptions(workspace=workspace, max_generations=gens, children_per_gen=children))
    print(f"Ran evolve loop through generation {gens}")


@app.command()
@_guard
def fork(workspace: Path, parent: str, child_worktree: Path) -> None:
    """Create a child worktree from a parent generation."""
    fork_agent_child(workspace, parent, child_worktree)
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
    commit_agent_child(workspace, child_worktree, parent, genid)
    print(f"Committed gen/{genid}")


@app.command("eval")
@_guard
def eval_cmd(
    workspace: Path,
    genid: str,
    force: bool = typer.Option(False, "--force", help="re-run evaluation even when a scored row already exists"),
) -> None:
    """Evaluate a tagged child version."""
    with _workspace_environment(workspace):
        eval_agent_child(workspace, genid, force=force)
    print(f"Evaluated gen/{genid}")


@app.command()
@_guard
def record(
    workspace: Path,
    genid: str,
    fields: str = typer.Option(..., "--fields", help="JSON object of fields"),
) -> None:
    """Append non-stamped archive fields."""
    record_agent_fields(workspace, genid, json.loads(fields))
    print(f"Recorded fields for gen/{genid}")


@app.command("surface-check")
@_guard
def surface_check(
    workspace: Path = typer.Argument(Path(".")),
    parent: str | None = typer.Option(None, "--parent"),
) -> None:
    """Report pending out-of-surface edits."""
    include, exclude = surface_patterns(workspace)
    parent_ref = f"gen/{parent}" if parent and not parent.startswith("gen/") else parent
    parent_ref = parent_ref or head_tag(workspace) or "gen/0"
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
    with _workspace_environment(workspace):
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
    """Integrity fsck: recompute the champion and expose any hand-edited archive."""
    findings = verify_integrity(workspace)
    champion = best_row(workspace)
    best_ever_path = workspace / "best_ever.json"
    try:
        materialized = json.loads(best_ever_path.read_text())
    except (OSError, json.JSONDecodeError):
        materialized = object()
    if materialized != champion:
        findings.append("best_ever.json does not match the mechanism-derived champion")
    for finding in findings:
        print(f"TAMPER: {finding}", file=sys.stderr)
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
