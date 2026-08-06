from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import operator_blocks
from .frozen.interfaces import OPERATORS
from .orchestration import finalize_child, invoke_operator


def _public_operator_name(name: str) -> str:
    return "analyze" if name == "trace_analyzer" else name


def _internal_operator_name(name: str) -> str:
    return "trace_analyzer" if name == "analyze" else name


def _operator_variant(script: Path, block: dict[str, object]) -> str | None:
    configured = block.get("variant")
    if configured:
        return str(configured)
    if not script.is_file():
        return None
    first_line = script.read_text(errors="replace").splitlines()[:1]
    marker = " source=library/"
    if not first_line or marker not in first_line[0]:
        return None
    source = first_line[0].split(marker, 1)[1].split()[0]
    return Path(source).stem


def build_operator_app(guard, workspace_environment, enable_live_output) -> typer.Typer:
    """Build the composable-operator command group with shared CLI policies."""

    operator_app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="Inspect and invoke evolution operators as composable agent tools.",
    )

    @operator_app.command("list")
    @guard
    def operator_list(
        workspace: Path = typer.Argument(Path(".")),
        json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
    ) -> None:
        """List configured operator capabilities and their active variants."""
        workspace = workspace.resolve()
        configured = operator_blocks(workspace)
        entries = []
        for spec in OPERATORS:
            block = configured.get(spec.kind)
            enabled = isinstance(block, dict)
            script = workspace / "operators" / f"{spec.kind}.py"
            entry = {
                "name": _public_operator_name(spec.kind),
                "configured": enabled,
                "required": spec.required,
                "access": (
                    "finalize" if spec.kind in {"gate", "record"} else "driver" if spec.kind == "reflect" else "direct"
                ),
                "variant": _operator_variant(script, block) if enabled else None,
                "script": str(script.resolve()),
            }
            if spec.kind == "trace_analyzer":
                entry["implementation"] = spec.kind
            entries.append(entry)
        if json_output:
            print(json.dumps(entries, indent=2, sort_keys=True))
            return
        for entry in entries:
            state = "configured" if entry["configured"] else "off"
            requirement = "required" if entry["required"] else "optional"
            access = str(entry["access"])
            variant = f" variant={entry['variant']}" if entry["variant"] else ""
            print(f"{entry['name']:<16} {state:<10} {requirement:<8} {access:<12}{variant}")

    @operator_app.command("run")
    @guard
    def operator_run(
        workspace: Path,
        name: str,
        genid: str = typer.Option(..., "--genid", help="generation evidence namespace"),
        parent: str | None = typer.Option(None, "--parent", help="selected valid parent"),
        checkout: Path | None = typer.Option(None, "--checkout", help="candidate checkout; defaults to workspace"),
        config: str = typer.Option("{}", "--config", help="JSON object recursively merged over recipe config"),
        timeout_s: float | None = typer.Option(None, "--timeout-s", help="override this invocation timeout"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="stream operator output"),
    ) -> None:
        """Run one configured operator and retain its generation artifacts."""
        try:
            override = json.loads(config)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"--config must be valid JSON: {exc.msg}", param_hint="--config") from exc
        if not isinstance(override, dict):
            raise typer.BadParameter("--config must be a JSON object", param_hint="--config")
        enable_live_output(verbose)
        internal_name = _internal_operator_name(name)
        with workspace_environment(workspace):
            invocation = invoke_operator(
                workspace,
                internal_name,
                genid,
                parent=parent,
                checkout=checkout,
                config_override=override,
                timeout_s=timeout_s,
            )
        print(
            json.dumps(
                {
                    "operator": name,
                    "genid": genid,
                    "status": "complete",
                    "artifacts": str(invocation.run_dir.resolve()),
                    "wall_s": round(invocation.result.wall_s, 3),
                },
                sort_keys=True,
            )
        )

    return operator_app


def attach_orchestration_commands(app, guard, workspace_environment, enable_live_output) -> None:
    """Attach the operator group and manual-workflow finalization command."""

    app.add_typer(
        build_operator_app(guard, workspace_environment, enable_live_output),
        name="operator",
    )

    @app.command()
    @guard
    def finalize(
        workspace: Path,
        genid: str,
        parent: str | None = typer.Option(None, "--parent", help="optional parent consistency check"),
    ) -> None:
        """Apply gate and record after a manually orchestrated evaluation."""
        with workspace_environment(workspace):
            changed = finalize_child(workspace, genid, parent=parent)
        state = "finalized" if changed else "already finalized"
        print(f"gen/{genid}: {state}")
