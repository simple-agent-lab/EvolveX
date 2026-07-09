from __future__ import annotations

import copy
import hashlib
import json
import shlex
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import __version__ as _EVOLVE_VERSION
from .archive import append_event
from .config import (
    OPERATOR_KINDS,
    OPTIONAL_OPERATOR_KINDS,
    SOURCE_ROOT,
    default_config,
    library_root,
    recipe_root,
    render_yaml,
    resource_root,
)


@dataclass(frozen=True)
class InitOptions:
    workspace: Path
    recipe: str
    seed: str | None = None


@dataclass(frozen=True)
class _OperatorBinding:
    kind: str
    source: str
    text: str


def init_workspace(options: InitOptions) -> None:
    workspace = options.workspace
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"workspace is not empty: {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)
    config = default_config(options.recipe, workspace.name)
    if options.seed:
        target = config["target"]
        assert isinstance(target, dict)
        target["seed"] = options.seed

    _write_files(workspace, config, recipe=options.recipe, init_cwd=Path.cwd())
    _write_target(workspace, options.seed)
    _vendor_mechanism(workspace)
    _make_executable(
        workspace / "operators" / "engines" / "local.sh",
        workspace / "operators" / "preflight.sh",
        workspace / "evaluator" / "eval.sh",
        workspace / "evaluator" / "engines" / "local.sh",
        workspace / "evolve",
    )
    _init_git(workspace)
    _write_gen0_archive(workspace)


_CONSOLE = """#!/usr/bin/env bash
# Self-contained evolve console. The mechanism is vendored under .evolve/, so
# this workspace drives its own evolution loop without an installed CLI:
#   ./evolve run . --max-generations 5
# The vendored mechanism is outside the mutable surface — evolution never
# edits it. The mechanism needs Python >=3.11; prefer uv, else a modern
# python3.x on PATH.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$HERE/.evolve${PYTHONPATH:+:$PYTHONPATH}"
# The console (cli.py) uses Typer; the driver/operators stay stdlib-only. uv
# supplies Typer on the fly via --with, so the workspace needs no install step.
if command -v uv >/dev/null 2>&1; then
  exec uv run --quiet --with "typer>=0.8" --python ">=3.11" python -m evolve "$@"
fi
for py in python3.13 python3.12 python3.11 python3; do
  if command -v "$py" >/dev/null 2>&1; then exec "$py" -m evolve "$@"; fi
done
echo "evolve: need uv (recommended) or Python >=3.11 with typer on PATH" >&2
exit 1
"""


def _vendor_mechanism(workspace: Path) -> None:
    """Copy the evolve mechanism package into the workspace so it is
    self-driving (mechanism-in-workspace). The vendored copy lives under
    .evolve/ and, together with the root `evolve` console, is protected from
    mutation by the surface's implicit excludes."""
    package_src = Path(__file__).resolve().parent
    shutil.copytree(
        package_src,
        workspace / ".evolve" / "evolve",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (workspace / "evolve").write_text(_CONSOLE)


def _write_files(workspace: Path, config: dict[str, object], *, recipe: str, init_cwd: Path) -> None:
    assert isinstance(config["evaluator"], dict)
    evaluator = cast("dict[str, Any]", config["evaluator"])
    evaluator_engine = str(evaluator["engine"])
    evaluator_dataset = str(evaluator["dataset"])
    evaluator_agent = str(evaluator.get("agent") or "")
    if evaluator_engine == "harbor" and not evaluator_agent:
        raise ValueError("evaluator.agent is required for harbor recipes")
    evaluator_trials = int(evaluator.get("k", 1))
    tasks_per_round = int(evaluator.get("tasks_per_round", evaluator_trials))
    evaluator_n = int(evaluator.get("n_concurrent", evaluator_trials))
    partial_floor = float(evaluator.get("partial_floor", 0.8))
    files = {
        "evolve.yaml": render_yaml(_runtime_config(config)),
        # Static skeleton — the browsable shape of a workspace lives as real files
        # under templates/workspace/ (single source; no drift from generation).
        "README.md": _template("workspace/README.md"),
        "AGENTS.md": _template("workspace/AGENTS.md"),
        "program.md": _template("workspace/program.md"),
        ".gitignore": _template("workspace/.gitignore"),
        ".evolve-protocol-version": "1\n",
        "operators/engines/local.sh": _shell_script("operator local engine"),
        "operators/preflight.sh": _shell_script("operator preflight"),
        # Per-verb strategy prose lives beside the active scripts (not a parallel
        # meta/ tree) so code + policy travel as one pair.
        "operators/select.md": _template("workspace/operators/select.md"),
        "operators/rollout.md": _template("workspace/operators/rollout.md"),
        "operators/mutate.md": _template("workspace/operators/mutate.md"),
        "operators/gate.md": _template("workspace/operators/gate.md"),
        "operators/record.md": _template("workspace/operators/record.md"),
        "operators/mutation_brief.md": _template("workspace/operators/mutation_brief.md"),
        # Inner skill: travels into the workspace under a unified, tool-agnostic
        # `skills/` folder (not `.claude/skills/`) so Claude Code AND codex (and
        # others) can find the mutator's manual (DESIGN §4, template = skill).
        "skills/evolve-workspace/SKILL.md": _skill("evolve-workspace/SKILL.md"),
        # Human-readable operator protocol the inner skill points mutators at.
        "PROTOCOL.md": (library_root() / "PROTOCOL.md").read_text(),
        "evaluator/eval.sh": _eval_sh(evaluator_engine, evaluator_dataset),
        "evaluator/eval.env": _eval_env(
            workspace.name,
            evaluator_dataset,
            evaluator_n,
            tasks_per_round,
            evaluator_trials,
            partial_floor,
            evaluator_agent,
        ),
        "evaluator/splits.json": json.dumps({"train": 0.5, "gate": 0.4, "sealed": 0.1, "seed": 0}, indent=2) + "\n",
        "evaluator/dataset.pin": f"dataset={evaluator_dataset}\nchecksum=sha256:stub\n",
        "evaluator/parse_score.py": _template("evaluator/parse_score.py"),
        "evaluator/stub_eval.py": _template("evaluator/stub_eval.py"),
        "evaluator/engines/local.sh": _shell_script("canonical local engine"),
        "archive.jsonl": "",
    }
    bindings = _operator_bindings(config, recipe=recipe, init_cwd=init_cwd)
    for binding in bindings:
        files[f"operators/{binding.kind}.py"] = _with_provenance(binding.kind, binding.source, binding.text)
    if any(binding.kind == "novelty" for binding in bindings):
        files["operators/novelty.md"] = _template("workspace/operators/novelty.md")
    files["operators/README.md"] = _operator_index(bindings, recipe)
    files.update(_operator_palette(recipe))
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (workspace / "runs").mkdir(exist_ok=True)


def _operator_bindings(config: dict[str, object], *, recipe: str, init_cwd: Path) -> list[_OperatorBinding]:
    operators = config.get("operators")
    if not isinstance(operators, dict):
        raise ValueError("operators section must be a mapping")
    bindings: list[_OperatorBinding] = []
    optional_present = [k for k in OPTIONAL_OPERATOR_KINDS if isinstance(operators.get(k), dict)]
    for kind in (*OPERATOR_KINDS, *optional_present):
        block = operators.get(kind)
        if not isinstance(block, dict):
            raise ValueError(f"operators.{kind} must be a mapping")
        script = block.get("script")
        variant = block.get("variant")
        if script and variant:
            raise ValueError(f"operators.{kind} cannot specify both variant and script")
        if script:
            source = Path(str(script)).expanduser()
            source_path = source if source.is_absolute() else init_cwd / source
            if not source_path.is_file():
                raise ValueError(f"operators.{kind} script not found: {script}")
            bindings.append(_OperatorBinding(kind, str(source_path), source_path.read_text()))
            continue
        source = _resolve_operator_variant(recipe, kind, str(variant or "default"))
        bindings.append(_OperatorBinding(kind, _source_label(source), source.read_text()))
    return bindings


def _operator_palette(recipe: str) -> dict[str, str]:
    """Vendor the per-kind variant catalog into the workspace's own `library/`,
    mirroring the framework's `library/`. `operators/` holds only the active
    scripts the driver runs; `library/<kind>/` holds the swap-in alternatives a
    self-modifying agent can copy over and evolve. Keeping them in separate
    trees is what makes `operators/` scannable at a glance."""
    palette: dict[str, str] = {}
    for kind in OPERATOR_KINDS:
        for directory in (recipe_root() / recipe / "operators" / kind, library_root() / kind):
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if path.name.endswith(".py"):
                    palette.setdefault(
                        f"library/{kind}/{path.name}", _with_provenance(kind, _source_label(path), path.read_text())
                    )
    return palette


def _operator_index(bindings: list[_OperatorBinding], recipe: str) -> str:
    """Generated map of the active operator set, derived from the bindings +
    catalog — one glance tells you what runs and what you could swap in."""
    rows = []
    for binding in bindings:
        active = Path(binding.source).stem
        alts = [v for v in _available_operator_variants(recipe, binding.kind) if v != active]
        rows.append(
            f"| {binding.kind} | {active}.py | {_first_docstring_line(binding.text)} "
            f"| {', '.join(alts) if alts else '—'} |"
        )
    return (
        "# Active operators\n\n"
        "The loop runs exactly these scripts, one per verb — each is yours to evolve\n"
        "(the mechanism never overwrites them). Alternatives live in `library/<verb>/`;\n"
        "copy one over a script to swap strategy. This file is generated by `init`.\n\n"
        "| verb | active | what it does | swap-in (`library/<verb>/`) |\n"
        "| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    )


def _first_docstring_line(source_text: str) -> str:
    lines = source_text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    if i < len(lines):
        line = lines[i].strip()
        for marker in ('"""', "'''"):
            if line.startswith(marker):
                inner = line[3:].split(marker, 1)[0].strip()
                if inner:
                    return inner
                return lines[i + 1].strip() if i + 1 < len(lines) else "(no description)"
    return "(no description)"


def _resolve_operator_variant(recipe: str, kind: str, variant: str):
    for candidate in (
        recipe_root() / recipe / "operators" / kind / f"{variant}.py",
        library_root() / kind / f"{variant}.py",
    ):
        if candidate.is_file():
            return candidate
    available = _available_operator_variants(recipe, kind)
    suffix = f" available: {', '.join(available)}" if available else " no variants available"
    raise ValueError(f"unknown {kind} variant: {variant};{suffix}")


def _available_operator_variants(recipe: str, kind: str) -> list[str]:
    names: set[str] = set()
    for directory in (recipe_root() / recipe / "operators" / kind, library_root() / kind):
        if not directory.is_dir():
            continue
        names.update(
            path.name[:-3]
            for path in directory.iterdir()
            if path.is_file() and path.name.endswith(".py") and not path.name.startswith("_")
        )
    return sorted(names)


def _with_provenance(kind: str, source: str, source_text: str) -> str:
    return (
        f"# evolve-provenance: kind={kind} source={source} framework_version={_EVOLVE_VERSION}\n"
        "# this file is yours now - mechanism will never overwrite it; evolve it.\n\n"
        f"{source_text}"
    )


def _runtime_config(config: dict[str, object]) -> dict[str, object]:
    runtime = copy.deepcopy(config)
    operators = runtime.get("operators")
    if isinstance(operators, dict):
        for kind in OPERATOR_KINDS:
            block = operators.get(kind)
            if isinstance(block, dict):
                block.pop("variant", None)
                block.pop("script", None)
    return runtime


def _write_target(workspace: Path, seed: str | None) -> None:
    if not seed or seed == "builtin-dummy":
        target = workspace / "target"
        target.mkdir(parents=True, exist_ok=True)
        (target / "agent.py").write_text(_template("target/agent.py"))
        (target / "README.md").write_text("# Seed Target\n\nA tiny stdlib-only seed target for Evolve.\n")
        (target / "UPSTREAM.json").write_text(
            json.dumps({"kind": "builtin", "seed": "builtin-dummy"}, sort_keys=True) + "\n"
        )
        return
    if _looks_like_git_url(seed):
        with tempfile.TemporaryDirectory(prefix="evolve-seed-") as tmp:
            checkout = Path(tmp) / "seed"
            _git_clone(seed, checkout)
            _vendor_seed(workspace, checkout, seed)
        return
    source = Path(seed).expanduser()
    if not source.is_dir():
        raise ValueError(f"seed is not a local directory or git URL: {seed}")
    _vendor_seed(workspace, source.resolve(), str(source.resolve()))


def _vendor_seed(workspace: Path, source: Path, fallback_remote: str) -> None:
    shutil.copytree(source, workspace / "target", ignore=shutil.ignore_patterns(".git"))
    upstream = _git_upstream(source, fallback_remote)
    if upstream:
        (workspace / "target" / "UPSTREAM.json").write_text(json.dumps(upstream, sort_keys=True) + "\n")


def _git_upstream(source: Path, fallback_remote: str) -> dict[str, str] | None:
    if not (source / ".git").exists():
        return None
    return {
        "remote": _git_optional(source, "remote", "get-url", "origin") or fallback_remote,
        "commit": _git(source, "rev-parse", "HEAD").strip(),
    }


def _looks_like_git_url(seed: str) -> bool:
    return (
        "://" in seed or seed.startswith("git@") or (seed.endswith(".git") and ":" in seed and not Path(seed).exists())
    )


def _git_clone(url: str, destination: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for evolve init")
    result = subprocess.run(
        [git, "clone", "--depth", "1", url, str(destination)], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git clone failed")


def _init_git(workspace: Path) -> None:
    _git(workspace, "init")
    _git(workspace, "config", "user.name", "Evolve Mechanism")
    _git(workspace, "config", "user.email", "evolve@example.invalid")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "evolve gen 0")
    _git(workspace, "tag", "gen/0")


def _write_gen0_archive(workspace: Path) -> None:
    append_event(
        workspace,
        workspace.name,
        {
            "genid": "0",
            "parent": None,
            "tag": "gen/0",
            "score": 1.0,
            "status": "complete",
            "task_set_hash": _sha256_file(workspace / "evaluator" / "splits.json"),
            "task_vector": {f"task-{i}": True for i in range(8)},
            "evaluator_tree": _git(workspace, "rev-parse", "HEAD:evaluator").strip(),
            "valid_parent": True,
            "verdict": "keep",
            "reason": "built-in init stub stamped generation 0",
            "mutated": [],
            "surface_violations": [],
            "predicted_fixes": [],
            "note": "initial scaffold",
            "cost": {"usd": 0, "wall_s": 0},
        },
    )


def _git(workspace: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for evolve init")
    result = subprocess.run([git, "-C", str(workspace), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _git_optional(workspace: Path, *args: str) -> str | None:
    result = subprocess.run(
        [shutil.which("git") or "git", "-C", str(workspace), *args], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_executable(*paths: Path) -> None:
    for path in paths:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _eval_env(
    workspace_name: str,
    dataset: str,
    n_concurrent: int,
    tasks_per_round: int,
    trials: int,
    partial_floor: float,
    agent: str,
) -> str:
    expected_trials = tasks_per_round * max(trials, 1)
    return (
        f"EVOLVE_EVALUATOR_DATASET={dataset}\n"
        f"EVOLVE_HARBOR_TASKS={shlex.quote(dataset)}\n"
        f"EVOLVE_HARBOR_N_CONCURRENT={n_concurrent}\n"
        f"EVOLVE_HARBOR_EXPECTED_TRIALS={expected_trials}\n"
        f"EVOLVE_HARBOR_N={n_concurrent}\n"
        f'EVOLVE_JOBS_DIR="$HOME/.evolve/harbor-jobs/{workspace_name}"\n'
        f"EVOLVE_HARBOR_AGENT={agent}\n"
        f"EVOLVE_PARTIAL_FLOOR={partial_floor}\n"
    )


def _eval_sh(engine: str, dataset: str) -> str:
    names = {"harbor": "harbor", "docker-report": "docker-report", "train-bpb": "train-bpb", "reflection": "reflection"}
    body = (
        _template(f"evaluator/engines/{names[engine]}.sh")
        if engine in names
        else _template("evaluator/engines/unknown.sh")
    )
    body = body.replace("@ENGINE@", engine).replace("@DATASET@", dataset)
    return _template("evaluator/eval-prefix.sh") + body


def _shell_script(label: str) -> str:
    return f"#!/bin/sh\nset -eu\nprintf '%s\\n' '{label}'\n"


def _template(relative_path: str) -> str:
    return (resource_root("templates") / relative_path).read_text()


def _skill(relative_path: str) -> str:
    return (resource_root("skills") / relative_path).read_text()


def _source_label(source: object) -> str:
    return (
        source.relative_to(SOURCE_ROOT).as_posix()
        if isinstance(source, Path) and source.is_relative_to(SOURCE_ROOT)
        else str(source)
    )
