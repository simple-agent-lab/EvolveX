from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import Resource, library_root, operator_blocks
from .frozen.interfaces import OPERATORS
from .operator_library import (
    OPERATOR_NAME,
    OperatorLibraryError,
    describe_operator,
    list_operators,
    parse_operator_identity,
    resolve_operator,
    validate_operator_config,
)
from .orchestration import finalize_child, invoke_operator


def _public_operator_name(name: str) -> str:
    return "analyze" if name == "analyze" else name


def _internal_operator_name(name: str) -> str:
    return "analyze" if name == "analyze" else name


def _operator_name(script: Path, block: dict[str, object], manifest: dict[str, object]) -> str | None:
    manifest_name = manifest.get("name")
    if isinstance(manifest_name, str):
        return manifest_name
    configured = block.get("operator")
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


def _component_operators(workspace: Path) -> dict[str, dict[str, object]]:
    path = workspace / ".evolve-components.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    operators = payload.get("operators") if isinstance(payload, dict) else None
    if not isinstance(operators, dict):
        return {}
    return {stage: entry for stage, entry in operators.items() if isinstance(entry, dict)}


_SCAFFOLD_DETAILS = {
    "select": ("archive, ctx", 'SelectResult(["0"])'),
    "rollout": ("checkout, ctx", "RolloutResult({}, [])"),
    "analyze": ("checkout, ctx", "AnalyzeResult({}, [])"),
    "mutate": (
        "checkout, observation, ctx",
        'MutateResult(changed=[], notes=["{name} made no changes"], usage={"usd": 0})',
    ),
    "validate": ("checkout, ctx", 'ValidateResult(True, "generated validation accepts", [])'),
    "novelty": ("checkout, ctx", "NoveltyResult(1.0, True)"),
    "gate": ("child, parent, ctx", 'GateResult("reject", "generated gate requires policy")'),
    "record": ("child, ctx", "RecordResult({})"),
    "reflect": ("archive, ctx", "ReflectResult([])"),
}


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _new_operator_source(stage: str, name: str) -> str:
    spec = next(spec for spec in OPERATORS if spec.kind == stage)
    parameters, result = _SCAFFOLD_DETAILS[stage]
    return f'''"""Describe the {name} {stage} operator."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import {spec.abc.__name__}, {spec.result.__name__}
from library._shared.config import config_object, reject_unknown


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    config = config_object(raw)
    reject_unknown(config, set())
    return config


class {_class_name(name)}({spec.abc.__name__}):
    def {spec.method}(self, {parameters}) -> {spec.result.__name__}:
        return {result.replace("{name}", name)}


if __name__ == "__main__":
    sdk.main({_class_name(name)}, validate_config=validate_config)
'''


def _create_operator(stage: str, name: str) -> Path:
    if stage not in {spec.kind for spec in OPERATORS}:
        raise OperatorLibraryError(f"unknown operator stage: {stage}")
    if not OPERATOR_NAME.fullmatch(name):
        raise OperatorLibraryError(f"invalid operator name: {name}")
    root: Resource = library_root()
    if not isinstance(root, Path):
        raise OperatorLibraryError("operator authoring requires a source checkout")
    target = root / stage / f"{name}.py"
    if target.exists():
        raise OperatorLibraryError(f"operator already exists: {stage}/{name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_new_operator_source(stage, name))
    return target


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
        stage: str | None = typer.Argument(None),
        json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
    ) -> None:
        """List discoverable library operators."""
        entries = [
            {"stage": operator.stage, "name": operator.name, "identity": operator.identity}
            for operator in list_operators(stage)
        ]
        if json_output:
            print(json.dumps(entries, indent=2, sort_keys=True))
            return
        for entry in entries:
            print(f"{entry['identity']}")

    @operator_app.command("describe")
    @guard
    def operator_describe(
        identity: str,
        json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
    ) -> None:
        """Describe one discoverable library operator."""
        stage, name = parse_operator_identity(identity)
        operator = resolve_operator(stage, name)
        description = {"identity": operator.identity, **describe_operator(operator)}
        if json_output:
            print(json.dumps(description, indent=2, sort_keys=True))
            return
        print(f"{operator.identity}: {description.get('description', '')}")

    @operator_app.command("check")
    @guard
    def operator_check(
        identity: str,
        config: str = typer.Option("{}", "--config", help="JSON object to validate"),
        json_output: bool = typer.Option(False, "--json", help="emit normalized machine-readable JSON"),
    ) -> None:
        """Validate one library operator's configuration."""
        try:
            raw_config = json.loads(config)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--config must be valid JSON: {exc.msg}") from exc
        if not isinstance(raw_config, dict):
            raise ValueError("--config must be a JSON object")
        stage, name = parse_operator_identity(identity)
        normalized = validate_operator_config(resolve_operator(stage, name), raw_config)
        if json_output:
            print(json.dumps(normalized, indent=2, sort_keys=True))
            return
        print(f"{stage}/{name}: configuration valid")
        print(json.dumps(normalized, indent=2, sort_keys=True))

    @operator_app.command("new")
    @guard
    def operator_new(stage: str, name: str) -> None:
        """Create a minimal library operator in a source checkout."""
        target = _create_operator(stage, name)
        print(f"Created {stage}/{name}: {target}")

    @operator_app.command("active")
    @guard
    def operator_active(
        workspace: Path = typer.Argument(Path(".")),
        json_output: bool = typer.Option(False, "--json", help="emit machine-readable JSON"),
    ) -> None:
        """List configured operator capabilities in an initialized workspace."""
        workspace = workspace.resolve()
        if not (workspace / "evolve.yaml").is_file() or not (workspace / ".git").exists():
            raise ValueError(f"operator active requires an initialized workspace: {workspace}")
        configured = operator_blocks(workspace)
        provenance = _component_operators(workspace)
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
                "operator": _operator_name(script, block, provenance.get(spec.kind, {})) if enabled else None,
                "script": str(script.resolve()),
            }
            if spec.kind == "analyze":
                entry["implementation"] = spec.kind
            entries.append(entry)
        if json_output:
            print(json.dumps(entries, indent=2, sort_keys=True))
            return
        for entry in entries:
            state = "configured" if entry["configured"] else "off"
            requirement = "required" if entry["required"] else "optional"
            access = str(entry["access"])
            operator = f" operator={entry['operator']}" if entry["operator"] else ""
            print(f"{entry['name']:<16} {state:<10} {requirement:<8} {access:<12}{operator}")

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
