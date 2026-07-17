from __future__ import annotations

import copy
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast

from . import __version__ as _EVOLVE_VERSION
from .archive import append_event
from .asset_discovery import root_python_helpers
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
from .splits import build_manifest

_SEED_IGNORE_PATTERNS = (".git", ".venv", ".env", ".env.*", "__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules")

@dataclass(frozen=True)
class InitOptions:
    workspace: Path
    recipe: str
    seed: str | None = None
    dataset: str | None = None


@dataclass(frozen=True)
class _OperatorBinding:
    kind: str
    source: str
    text: str
    companion_text: str | None


def init_workspace(options: InitOptions) -> None:
    workspace = options.workspace
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"workspace is not empty: {workspace}")

    workspace.mkdir(parents=True, exist_ok=True)
    config = default_config(options.recipe, workspace.name)
    target = config["target"]
    assert isinstance(target, dict)
    if options.seed:
        target["seed"] = options.seed
    elif options.dataset:
        # Dataset-backed experiments should be self-contained and must not need
        # a network clone merely to freeze their evaluator split.
        target["seed"] = "builtin-codex"
    if options.dataset:
        evaluator = config["evaluator"]
        assert isinstance(evaluator, dict)
        evaluator["dataset"] = options.dataset

    _write_files(workspace, config, recipe=options.recipe, init_cwd=Path.cwd())
    _write_target(workspace, target)
    _vendor_mechanism(workspace)
    _make_executable(
        workspace / "operators" / "engines" / "local.sh",
        workspace / "operators" / "preflight.sh",
        workspace / "evaluator" / "eval.sh",
        workspace / "evaluator" / "engines" / "local.sh",
        workspace / "evolve",
        *([workspace / "evaluator" / "smoke.sh"] if (workspace / "evaluator" / "smoke.sh").is_file() else []),
    )
    _init_git(workspace)
    _write_gen0_archive(workspace)


_CONSOLE = """#!/usr/bin/env bash
# Self-contained console for the mechanism vendored under .evolve/.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$HERE/.evolve${PYTHONPATH:+:$PYTHONPATH}"
if [ -n "${EVOLVE_FRAMEWORK_PYTHON:-}" ]; then
  PYTHON="$EVOLVE_FRAMEWORK_PYTHON"
else
  PYTHON=@FRAMEWORK_PYTHON@
fi
if [ ! -x "$PYTHON" ]; then
  echo "evolve: pinned framework Python is unavailable; set EVOLVE_FRAMEWORK_PYTHON" >&2
  exit 1
fi
exec "$PYTHON" -m evolve "$@"
"""


def _vendor_mechanism(workspace: Path) -> None:
    """Vendor the self-driving mechanism under the workspace's protected .evolve/ tree."""
    package_src = Path(__file__).resolve().parent
    shutil.copytree(
        package_src,
        workspace / ".evolve" / "evolve",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (workspace / "evolve").write_text(_CONSOLE.replace("@FRAMEWORK_PYTHON@", shlex.quote(sys.executable)))


def _write_files(workspace: Path, config: dict[str, object], *, recipe: str, init_cwd: Path) -> None:
    assert isinstance(config["evaluator"], dict)
    evaluator = cast("dict[str, Any]", config["evaluator"])
    evaluator_engine = str(evaluator["engine"])
    evaluator_dataset = str(evaluator["dataset"])
    evaluator_agent = str(evaluator.get("agent") or "")
    if evaluator_engine == "harbor" and not evaluator_agent:
        raise ValueError("evaluator.agent is required for harbor recipes")
    runtime_digest = os.environ.get("EVOLVE_RUNTIME_DIGEST", "").strip()
    if evaluator_engine == "harbor" and not runtime_digest:
        raise ValueError("EVOLVE_RUNTIME_DIGEST must identify the evaluator capsule (normally an immutable image digest)")
    evaluator_trials = int(evaluator.get("k", 1))
    tasks_per_round = int(evaluator.get("tasks_per_round", evaluator_trials))
    evaluator_n = int(evaluator.get("n_concurrent", evaluator_trials))
    partial_floor = float(evaluator.get("partial_floor", 0.8))
    setup_timeout_multiplier = float(evaluator.get("agent_setup_timeout_multiplier", 1))
    max_retries = int(evaluator.get("max_retries", 0))
    split = evaluator.get("split")
    if not isinstance(split, dict):
        raise ValueError("evaluator.split must be a mapping")
    split_manifest = build_manifest(
        evaluator_dataset,
        split,
        base_dir=init_cwd,
        sampling=str(evaluator.get("sampling", "static")),
        gate_limit=tasks_per_round,
    )
    evaluator_dataset = str(split_manifest["dataset"])
    files = {
        "evolve.yaml": render_yaml(_runtime_config(config)),
        "README.md": _template("workspace/README.md"),
        "AGENTS.md": _template("workspace/AGENTS.md"),
        "program.md": _template("workspace/program.md"),
        ".gitignore": _template("workspace/.gitignore"),
        ".evolve-protocol-version": "1\n",
        "operators/engines/local.sh": _shell_script("operator local engine"),
        "operators/preflight.sh": _shell_script("operator preflight"),
        "operators/select.md": _template("workspace/operators/select.md"),
        "operators/rollout.md": _template("workspace/operators/rollout.md"),
        "operators/meta_agent.md": _template("workspace/operators/meta_agent.md"),
        "operators/gate.md": _template("workspace/operators/gate.md"),
        "operators/record.md": _template("workspace/operators/record.md"),
        "operators/meta_agent_brief.md": _template("workspace/operators/meta_agent_brief.md"),
        "skills/evolve-workspace/SKILL.md": _skill("evolve-workspace/SKILL.md"),
        "PROTOCOL.md": (library_root() / "PROTOCOL.md").read_text(),
        "evaluator/eval.sh": _eval_sh(evaluator_engine, evaluator_dataset),
        "evaluator/eval.env": _eval_env(
            workspace.name, evaluator_dataset, evaluator_n,
            tasks_per_round,
            evaluator_trials,
            partial_floor,
            evaluator_agent,
            dataset_mode=str(evaluator.get("dataset_mode", "path")),
            task_file=str(evaluator["task_file"]) if "task_file" in evaluator else None,
            setup_timeout_multiplier=setup_timeout_multiplier,
            max_retries=max_retries,
        ),
        "evaluator/splits.json": json.dumps(split_manifest, indent=2, sort_keys=True) + "\n",
        "evaluator/dataset.pin": f"dataset={evaluator_dataset}\nchecksum=sha256:stub\n",
        "evaluator/runtime.pin": f"{runtime_digest}\n",
        "evaluator/harbor_artifacts.py": _template("evaluator/harbor_artifacts.py"),
        "evaluator/parse_score.py": _template("evaluator/parse_score.py"),
        "evaluator/stub_eval.py": _template("evaluator/stub_eval.py"),
        "evaluator/engines/local.sh": _shell_script("canonical local engine"),
        "archive.jsonl": "",
    }
    if evaluator_engine == "harbor":
        files["evaluator/cleanup_harbor.py"] = _template("evaluator/cleanup_harbor.py")
        files["evaluator/smoke.sh"] = _template("evaluator/smoke.sh")
    bindings = _operator_bindings(config, recipe=recipe, init_cwd=init_cwd)
    for binding in bindings:
        files[f"operators/{binding.kind}.py"] = _with_provenance(binding.kind, binding.source, binding.text)
        if binding.companion_text is not None:
            files[f"operators/{binding.kind}.md"] = binding.companion_text
    if any(binding.kind == "novelty" for binding in bindings):
        files["operators/novelty.md"] = _template("workspace/operators/novelty.md")
    files["operators/README.md"] = _operator_index(bindings, recipe)
    files.update(_operator_palette(recipe) | _operator_assets(recipe) | _recipe_evaluator_assets(recipe))
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
            companion = source_path.with_suffix(".md")
            companion_text = companion.read_text() if companion.is_file() else None
            bindings.append(_OperatorBinding(kind, str(source_path), source_path.read_text(), companion_text))
            continue
        source = _resolve_operator_variant(recipe, kind, str(variant or "default"))
        companion = source.with_suffix(".md")
        companion_text = companion.read_text() if companion.is_file() else None
        bindings.append(_OperatorBinding(kind, _source_label(source), source.read_text(), companion_text))
    return bindings


def _operator_palette(recipe: str) -> dict[str, str]:
    """Vendor the per-kind variant catalog into the workspace's own `library/`,
    mirroring the framework's `library/`. `operators/` holds only the active
    scripts the driver runs; `library/<kind>/` holds the swap-in alternatives a
    self-modifying agent can copy over and evolve. Keeping them in separate
    trees is what makes `operators/` scannable at a glance."""
    palette: dict[str, str] = {}
    for kind in (*OPERATOR_KINDS, *OPTIONAL_OPERATOR_KINDS):
        for directory in (recipe_root() / recipe / "operators" / kind, library_root() / kind):
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if path.name.endswith(".py"):
                    palette.setdefault(
                        f"library/{kind}/{path.name}", _with_provenance(kind, _source_label(path), path.read_text())
                    )
    return palette


def _walk_files(root: Path | Traversable, prefix: Path = Path("")):
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        relative = prefix / item.name
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if isinstance(item, Path) and item.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {item}")
        if item.is_dir():
            yield from _walk_files(item, relative)
        elif item.is_file():
            yield relative, item


def _text_files(root: Path | Traversable):
    for relative, source in _walk_files(root):
        try:
            yield relative, source.read_text()
        except UnicodeDecodeError:
            continue


def _operator_assets(recipe: str) -> dict[str, str]:
    assets: dict[str, str] = {}
    for kind in (*OPERATOR_KINDS, *OPTIONAL_OPERATOR_KINDS):
        for directory in (recipe_root() / recipe / "operators" / kind, library_root() / kind):
            if directory.is_dir():
                for relative, text in _text_files(directory):
                    if relative.suffix != ".py" or len(relative.parts) > 1:
                        assets.setdefault(f"library/{kind}/{relative.as_posix()}", text)
    return assets | {f"library/{name}": text for name, text in root_python_helpers(library_root())}


def _recipe_evaluator_assets(recipe: str) -> dict[str, str]:
    root = recipe_root() / recipe / "evaluator"
    return {} if not root.is_dir() else {f"evaluator/{relative.as_posix()}": text for relative, text in _text_files(root)}


def _operator_index(bindings: list[_OperatorBinding], recipe: str) -> str:
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


def _write_target(workspace: Path, target_config: dict[str, Any]) -> None:
    seed = target_config.get("seed")
    seed_text = str(seed) if seed else None
    if not seed_text or seed_text == "builtin-dummy":
        target = workspace / "target"
        target.mkdir(parents=True, exist_ok=True)
        (target / "agent.py").write_text(_template("target/agent.py"))
        (target / "README.md").write_text("# Seed Target\n\nA tiny stdlib-only seed target for Evolve.\n")
        (target / "UPSTREAM.json").write_text(
            json.dumps({"kind": "builtin", "seed": "builtin-dummy"}, sort_keys=True) + "\n"
        )
        _write_target_harbor_agent(workspace, target_config)
        return
    if seed_text == "builtin-codex":
        _copy_resource_tree(resource_root("templates") / "target" / "codex", workspace / "target")
        (workspace / "target" / "UPSTREAM.json").write_text(
            json.dumps({"kind": "builtin", "seed": "builtin-codex"}, sort_keys=True) + "\n"
        )
        _write_target_harbor_agent(workspace, target_config)
        return
    if _looks_like_git_url(seed_text):
        with tempfile.TemporaryDirectory(prefix="evolve-seed-") as tmp:
            checkout = Path(tmp) / "seed"
            _git_clone(seed_text, checkout)
            _vendor_seed(workspace, checkout, seed_text)
        _write_target_harbor_agent(workspace, target_config)
        return
    source = Path(seed_text).expanduser()
    if not source.is_dir():
        raise ValueError(f"seed is not a local directory or git URL: {seed_text}")
    _vendor_seed(workspace, source.resolve(), str(source.resolve()))
    _write_target_harbor_agent(workspace, target_config)


def _write_target_harbor_agent(workspace: Path, target_config: dict[str, Any]) -> None:
    kind = str(target_config.get("harbor_agent") or "")
    if not kind:
        return
    if kind != "miniswe-source":
        raise ValueError(f"unsupported target.harbor_agent: {kind}")
    (workspace / "target" / "harbor_agent.py").write_text(_template("target/harbor/miniswe_source_agent.py"))


def _copy_resource_tree(source: Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_resource_tree(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _vendor_seed(workspace: Path, source: Path, fallback_remote: str) -> None:
    shutil.copytree(source, workspace / "target", ignore=shutil.ignore_patterns(*_SEED_IGNORE_PATTERNS))
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
            "score": None,
            "status": "pending",
            "valid_parent": False,
            "verdict": "pending",
            "reason": "generation zero requires real evaluation",
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
    _workspace_name: str, dataset: str, n_concurrent: int,
    tasks_per_round: int,
    trials: int,
    partial_floor: float,
    agent: str, *, dataset_mode: str = "path", task_file: str | None = None,
    setup_timeout_multiplier: float = 1, max_retries: int = 0,
) -> str:
    expected_trials = tasks_per_round * max(trials, 1)
    text = (
        f"EVOLVE_EVALUATOR_DATASET={dataset}\n"
        f"EVOLVE_HARBOR_TASKS={shlex.quote(dataset)}\n"
        f"EVOLVE_HARBOR_DATASET_MODE={shlex.quote(dataset_mode)}\n"
        f"EVOLVE_HARBOR_N_CONCURRENT={n_concurrent}\n"
        f"EVOLVE_HARBOR_ATTEMPTS={max(trials, 1)}\n"
        f"EVOLVE_HARBOR_EXPECTED_TRIALS={expected_trials}\n"
        f"EVOLVE_HARBOR_N={n_concurrent}\n"
        f"EVOLVE_HARBOR_AGENT={shlex.quote(agent)}\n"
        f"EVOLVE_PARTIAL_FLOOR={partial_floor}\n"
    )
    if setup_timeout_multiplier > 1:
        text += f"EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER={setup_timeout_multiplier}\n"
    if max_retries > 0:
        text += f"EVOLVE_HARBOR_MAX_RETRIES={max_retries}\n"
    return text + (f"EVOLVE_HARBOR_TASK_FILE={shlex.quote(task_file)}\n" if task_file else "")


def _eval_sh(engine: str, _dataset: str) -> str:
    if engine != "harbor":
        raise ValueError(f"unsupported evaluator.engine: {engine}")
    return _template("evaluator/eval-prefix.sh") + _template("evaluator/engines/harbor.sh")


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
