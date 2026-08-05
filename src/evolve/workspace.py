from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast

from . import __version__ as _EVOLVE_VERSION
from .archive import append_event
from .config import (
    DEFAULT_RECIPE,
    OPERATOR_KINDS,
    OPTIONAL_OPERATOR_KINDS,
    SOURCE_ROOT,
    default_config,
    library_root,
    load_config,
    recipe_root,
    render_yaml,
    resource_root,
    scaffold_root,
    seed_root,
)
from .host_runtime import uv_executable
from .splits import build_manifest

_SEED_IGNORE_PATTERNS = (
    ".git",
    ".venv",
    ".env",
    ".env.*",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
)
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_GIT_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
_MINISWE_CANDIDATE_AGENT = "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent"


@dataclass(frozen=True)
class InitOptions:
    workspace: Path
    recipe: str | None = None
    seed: str | None = None
    dataset: str | None = None
    recipe_path: Path | None = None


@dataclass(frozen=True)
class _OperatorBinding:
    kind: str
    source: str
    text: str
    companion_text: str | None


def init_workspace(options: InitOptions) -> None:
    workspace = options.workspace
    if options.recipe is not None and options.recipe_path is not None:
        raise ValueError("cannot combine --recipe with --recipe-path")
    if options.seed == "builtin-dummy":
        raise ValueError("builtin-dummy is test-only; pass a local seed directory instead")
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"workspace is not empty: {workspace}")

    if options.recipe_path is None:
        recipe = options.recipe or DEFAULT_RECIPE
        recipe_directory: Path | Traversable | None = None
        config = default_config(recipe, workspace.name)
    else:
        recipe, recipe_directory, config = _path_recipe(options.recipe_path, workspace.name)
    target = config["target"]
    assert isinstance(target, dict)
    if options.seed:
        target["seed"] = options.seed
        target.pop("revision", None)
        target.pop("generate_lock", None)
    if options.dataset:
        evaluator = config["evaluator"]
        assert isinstance(evaluator, dict)
        evaluator["dataset"] = options.dataset

    evaluator = config["evaluator"]
    assert isinstance(evaluator, dict)
    _validate_evaluator_config(evaluator)
    _validate_target_config(target)
    with tempfile.TemporaryDirectory(prefix="evolve-target-") as tmp:
        staging_workspace = Path(tmp) / "workspace"
        staging_workspace.mkdir()
        _write_target(staging_workspace, target)
        staged_target = staging_workspace / "target"
        _remove_generated_target_metadata(staged_target)
        _validate_candidate_target_contract(staged_target, evaluator)
        workspace.mkdir(parents=True, exist_ok=True)
        _write_files(
            workspace,
            config,
            recipe=recipe,
            recipe_directory=recipe_directory,
            init_cwd=Path.cwd(),
        )
        shutil.copytree(staged_target, workspace / "target")
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


def _path_recipe(recipe_path: Path, experiment_id: str) -> tuple[str, Path, dict[str, Any]]:
    source = recipe_path.expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    source = source.resolve()
    config_path = source / "evolve.yaml" if source.is_dir() else source
    if config_path.name != "evolve.yaml" or not config_path.is_file():
        raise ValueError("--recipe-path must name a recipe directory or its evolve.yaml")
    config = copy.deepcopy(load_config(config_path))
    config["experiment"]["id"] = experiment_id
    return config_path.parent.name, config_path.parent, config


_CONSOLE = """#!/usr/bin/env bash
# Self-contained console for the mechanism vendored under .evolve/.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${EVOLVE_UV_BINARY:-}" ]; then
  UV="$EVOLVE_UV_BINARY"
else
  UV=$(command -v uv || true)
fi
if [ -z "$UV" ] || [ ! -x "$UV" ]; then
  echo "evolve: uv is required; install uv or set EVOLVE_UV_BINARY" >&2
  exit 1
fi
if [ -n "${EVOLVE_FRAMEWORK_PYTHON:-}" ]; then exec "$UV" run --project "$HERE" --frozen --python "$EVOLVE_FRAMEWORK_PYTHON" python "$HERE/.evolve/launch_evolve.py" "$@"; fi
exec "$UV" run --project "$HERE" --frozen python "$HERE/.evolve/launch_evolve.py" "$@"
"""


def _vendor_mechanism(workspace: Path) -> None:
    """Vendor the self-driving mechanism under the workspace's protected .evolve/ tree."""
    package_src = Path(__file__).resolve().parent
    shutil.copytree(
        package_src,
        workspace / ".evolve" / "evolve",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (workspace / ".evolve" / "launch_evolve.py").write_text(_workspace_scaffold("launch_evolve.py"))
    (workspace / ".evolve" / "launch_splits.py").write_text(_workspace_scaffold("launch_splits.py"))
    (workspace / "evolve").write_text(_CONSOLE)


def _write_files(
    workspace: Path,
    config: dict[str, object],
    *,
    recipe: str,
    recipe_directory: Path | Traversable | None = None,
    init_cwd: Path,
) -> None:
    assert isinstance(config["evaluator"], dict)
    evaluator = cast("dict[str, Any]", config["evaluator"])
    evaluator_engine = str(evaluator["engine"])
    evaluator_dataset = str(evaluator["dataset"])
    evaluator_agent = str(evaluator.get("agent") or "")
    if evaluator_engine == "harbor" and not evaluator_agent:
        raise ValueError("evaluator.agent is required for harbor recipes")
    runtime_digest = os.environ.get("EVOLVE_RUNTIME_DIGEST", "").strip()
    if evaluator_engine == "harbor" and not runtime_digest:
        raise ValueError(
            "EVOLVE_RUNTIME_DIGEST must identify the evaluator capsule (normally an immutable image digest)"
        )
    evaluator_trials = int(evaluator.get("k", 1))
    tasks_per_round = int(evaluator.get("tasks_per_round", evaluator_trials))
    evaluator_n = int(evaluator.get("n_concurrent", evaluator_trials))
    evaluator_environment = str(evaluator.get("environment") or "")
    partial_floor = float(evaluator.get("partial_floor", 0.9))
    setup_timeout_multiplier = float(evaluator.get("agent_setup_timeout_multiplier", 1))
    agent_timeout_multiplier = float(evaluator.get("agent_timeout_multiplier", 1))
    verifier_timeout_multiplier = float(evaluator.get("verifier_timeout_multiplier", 1))
    max_retries = int(evaluator.get("max_retries", 0))
    task_scope = str(evaluator.get("task_scope", "partitioned"))
    split = evaluator.get("split")
    if task_scope == "full":
        if split is not None:
            raise ValueError("evaluator.task_scope full must not define evaluator.split")
        if evaluator.get("evaluation_split") != "train":
            raise ValueError("evaluator.task_scope full requires evaluator.evaluation_split train")
        split = {"train": 1.0, "gate": 0.0, "sealed": 0.0, "seed": 0}
    elif not isinstance(split, dict):
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
        "pyproject.toml": _workspace_scaffold("pyproject.toml"),
        "uv.lock": _workspace_scaffold("uv.lock"),
        ".python-version": _workspace_scaffold(".python-version"),
        ".evolve-components.json": json.dumps(_component_manifest(recipe, config), indent=2, sort_keys=True) + "\n",
        "evolve.yaml": render_yaml(_runtime_config(config)),
        "README.md": _workspace_scaffold("README.md"),
        "AGENTS.md": _workspace_scaffold("AGENTS.md"),
        "program.md": _workspace_scaffold("program.md"),
        "LICENSE.evolve-framework": _framework_legal_text("LICENSE"),
        "NOTICE.evolve-framework": _framework_legal_text("NOTICE"),
        ".gitignore": _workspace_scaffold(".gitignore"),
        ".evolve-protocol-version": "1\n",
        "operators/engines/local.sh": _shell_script("operator local engine"),
        "operators/preflight.sh": _shell_script("operator preflight"),
        "operators/select.md": _workspace_scaffold("operators/select.md"),
        "operators/rollout.md": _workspace_scaffold("operators/rollout.md"),
        "operators/gate.md": _workspace_scaffold("operators/gate.md"),
        "operators/record.md": _workspace_scaffold("operators/record.md"),
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
            model=str(evaluator["model"]) if evaluator.get("model") else None,
            environment=evaluator_environment,
            dataset_mode=str(evaluator.get("dataset_mode", "path")),
            task_file=str(evaluator["task_file"]) if "task_file" in evaluator else None,
            setup_timeout_multiplier=setup_timeout_multiplier,
            agent_timeout_multiplier=agent_timeout_multiplier,
            verifier_timeout_multiplier=verifier_timeout_multiplier,
            max_retries=max_retries,
        ),
        "evaluator/agent.env": _agent_env(evaluator.get("agent_env")),
        "evaluator/verifier.env": _agent_env(evaluator.get("verifier_env")),
        "evaluator/environment.kwargs": _environment_kwargs(evaluator.get("environment_kwargs")),
        "evaluator/splits.json": json.dumps(split_manifest, indent=2, sort_keys=True) + "\n",
        "evaluator/dataset.pin": (
            f"dataset={evaluator_dataset}\nchecksum={split_manifest['dataset_digest'] or 'unresolved'}\n"
        ),
        "evaluator/runtime.pin": f"{runtime_digest}\n",
        "evaluator/stub_eval.py": _workspace_scaffold("evaluator/stub_eval.py"),
        "evaluator/engines/local.sh": _shell_script("canonical local engine"),
        "archive.jsonl": "",
        "best_ever.json": "null\n",
    }
    files.update(_skill_package("evolve-agent"))
    if evaluator_engine == "harbor":
        files.update(
            {
                "evaluator/cleanup_harbor.py": _evaluator_scaffold("harbor", "cleanup_harbor.py"),
                "evaluator/harbor_artifacts.py": _evaluator_scaffold("harbor", "harbor_artifacts.py"),
                "evaluator/parse_score.py": _evaluator_scaffold("harbor", "parse_score.py"),
                "evaluator/smoke.sh": _evaluator_scaffold("harbor", "smoke.sh"),
            }
        )
    bindings = _operator_bindings(
        config,
        recipe=recipe,
        recipe_directory=recipe_directory,
        init_cwd=init_cwd,
    )
    for binding in bindings:
        files[f"operators/{binding.kind}.py"] = _with_provenance(binding.kind, binding.source, binding.text)
        if binding.companion_text is not None:
            files[f"operators/{binding.kind}.md"] = binding.companion_text
    recipe_evaluator_assets = _recipe_evaluator_assets(
        recipe,
        recipe_directory=recipe_directory,
    )
    generated_output_paths = {relative_path.casefold() for relative_path in files}
    evaluator_collisions = sorted(
        relative_path for relative_path in recipe_evaluator_assets if relative_path.casefold() in generated_output_paths
    )
    if evaluator_collisions:
        raise ValueError("recipe evaluator asset collides with generated file: " + ", ".join(evaluator_collisions))
    files["operators/README.md"] = _operator_index(
        bindings,
        recipe,
        recipe_directory=recipe_directory,
    )
    files.update(
        _operator_palette(recipe, recipe_directory=recipe_directory)
        | _operator_assets(recipe, recipe_directory=recipe_directory)
        | recipe_evaluator_assets
    )
    for relative_path, content in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (workspace / "runs").mkdir(exist_ok=True)
    (workspace / "artifacts" / "user").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "generations").mkdir(parents=True, exist_ok=True)


def _operator_bindings(
    config: dict[str, object],
    *,
    recipe: str,
    recipe_directory: Path | Traversable | None = None,
    init_cwd: Path,
) -> list[_OperatorBinding]:
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
        source = _resolve_operator_variant(
            recipe,
            kind,
            str(variant or "default"),
            recipe_directory=recipe_directory,
        )
        companion = source.with_suffix(".md")
        companion_text = companion.read_text() if companion.is_file() else None
        bindings.append(_OperatorBinding(kind, _source_label(source), source.read_text(), companion_text))
    return bindings


def _operator_palette(
    recipe: str,
    *,
    recipe_directory: Path | Traversable | None = None,
) -> dict[str, str]:
    """Vendor the per-kind variant catalog into the workspace's own `library/`,
    mirroring the framework's `library/`. `operators/` holds only the active
    scripts the driver runs; `library/<kind>/` holds the swap-in alternatives a
    self-modifying agent can copy over and evolve. Keeping them in separate
    trees is what makes `operators/` scannable at a glance."""
    palette: dict[str, str] = {}
    for kind in (*OPERATOR_KINDS, *OPTIONAL_OPERATOR_KINDS):
        for directory in (_recipe_directory(recipe, recipe_directory) / "operators" / kind, library_root() / kind):
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


def _root_python_helpers(root: Path | Traversable):
    for source in sorted(root.iterdir(), key=lambda entry: entry.name):
        if source.name.startswith((".", "_")) or not source.name.endswith(".py") or not source.is_file():
            continue
        if isinstance(source, Path) and source.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {source}")
        try:
            yield source.name, source.read_text()
        except UnicodeDecodeError:
            continue


def _operator_assets(
    recipe: str,
    *,
    recipe_directory: Path | Traversable | None = None,
) -> dict[str, str]:
    assets: dict[str, str] = {}
    for kind in (*OPERATOR_KINDS, *OPTIONAL_OPERATOR_KINDS):
        for directory in (_recipe_directory(recipe, recipe_directory) / "operators" / kind, library_root() / kind):
            if directory.is_dir():
                for relative, text in _text_files(directory):
                    if relative.suffix != ".py" or len(relative.parts) > 1:
                        assets.setdefault(f"library/{kind}/{relative.as_posix()}", text)
    return assets | {f"library/{name}": text for name, text in _root_python_helpers(library_root())}


def _recipe_evaluator_assets(
    recipe: str,
    *,
    recipe_directory: Path | Traversable | None = None,
) -> dict[str, str]:
    root = _recipe_directory(recipe, recipe_directory) / "evaluator"
    return (
        {} if not root.is_dir() else {f"evaluator/{relative.as_posix()}": text for relative, text in _text_files(root)}
    )


def _operator_index(
    bindings: list[_OperatorBinding],
    recipe: str,
    *,
    recipe_directory: Path | Traversable | None = None,
) -> str:
    rows = []
    for binding in bindings:
        active = Path(binding.source).stem
        alts = [
            variant
            for variant in _available_operator_variants(
                recipe,
                binding.kind,
                recipe_directory=recipe_directory,
            )
            if variant != active
        ]
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


def _resolve_operator_variant(
    recipe: str,
    kind: str,
    variant: str,
    *,
    recipe_directory: Path | Traversable | None = None,
):
    for candidate in (
        _recipe_directory(recipe, recipe_directory) / "operators" / kind / f"{variant}.py",
        library_root() / kind / f"{variant}.py",
    ):
        if candidate.is_file():
            return candidate
    available = _available_operator_variants(
        recipe,
        kind,
        recipe_directory=recipe_directory,
    )
    suffix = f" available: {', '.join(available)}" if available else " no variants available"
    raise ValueError(f"unknown {kind} variant: {variant};{suffix}")


def _available_operator_variants(
    recipe: str,
    kind: str,
    *,
    recipe_directory: Path | Traversable | None = None,
) -> list[str]:
    names: set[str] = set()
    for directory in (_recipe_directory(recipe, recipe_directory) / "operators" / kind, library_root() / kind):
        if not directory.is_dir():
            continue
        names.update(
            path.name[:-3]
            for path in directory.iterdir()
            if path.is_file() and path.name.endswith(".py") and not path.name.startswith("_")
        )
    return sorted(names)


def _recipe_directory(
    recipe: str,
    recipe_directory: Path | Traversable | None,
) -> Path | Traversable:
    return recipe_root() / recipe if recipe_directory is None else recipe_directory


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


def _component_manifest(recipe: str, config: dict[str, object]) -> dict[str, object]:
    evaluator = cast("dict[str, Any]", config["evaluator"])
    operators = cast("dict[str, Any]", config["operators"])
    meta_agent = cast("dict[str, Any]", operators["meta_agent"])
    references = (str(evaluator.get("agent") or ""), str(meta_agent.get("agent") or ""))
    return {
        "recipe": recipe,
        "target_seed": cast("dict[str, Any]", config["target"]).get("seed"),
        "evaluator_engine": evaluator.get("engine"),
        "integrations": sorted(
            {reference.split(":", 1)[0] for reference in references if reference.startswith("evolve.integrations.")}
        ),
    }


def _validate_evaluator_config(evaluator: dict[str, Any]) -> None:
    engine = str(evaluator.get("engine") or "")
    _evaluator_scaffold(engine, "engine.sh")
    if engine == "harbor" and not evaluator.get("agent"):
        raise ValueError("evaluator.agent is required for harbor recipes")


def _validate_target_config(target: dict[str, Any]) -> None:
    seed = target.get("seed")
    if not seed:
        raise ValueError("target.seed is required")
    if not isinstance(seed, str):
        raise ValueError("target.seed must be a string")
    if seed == "builtin-dummy":
        raise ValueError("builtin-dummy is test-only; pass a local seed directory instead")

    revision = target.get("revision")
    if revision is not None and (not isinstance(revision, str) or _GIT_COMMIT.fullmatch(revision) is None):
        raise ValueError("target.revision must be a full 40-character git commit")
    generate_lock = target.get("generate_lock", False)
    if not isinstance(generate_lock, bool):
        raise ValueError("target.generate_lock must be a boolean")

    if seed in ("builtin-codex", "builtin-local-smoke") or _looks_like_git_url(seed):
        return
    if revision is not None:
        raise ValueError("target.revision requires a git URL seed")
    if not Path(seed).expanduser().is_dir():
        raise ValueError(f"seed is not a local directory or git URL: {seed}")


def _validate_candidate_target_contract(prepared_target: Path, evaluator: dict[str, Any]) -> None:
    if evaluator.get("agent") != _MINISWE_CANDIDATE_AGENT:
        return
    missing = [relative for relative in ("pyproject.toml", "uv.lock") if not (prepared_target / relative).is_file()]
    if missing:
        raise ValueError(
            "MiniSWE candidate target is incomplete; the prepared target must "
            f"contain target/{' and target/'.join(missing)}"
        )
    if not ((prepared_target / "src" / "minisweagent").is_dir() or (prepared_target / "minisweagent").is_dir()):
        raise ValueError(
            "MiniSWE candidate target is incomplete; the prepared target must "
            "contain target/src/minisweagent or target/minisweagent"
        )
    checked = subprocess.run(
        [
            uv_executable(),
            "lock",
            "--check",
            "--python",
            sys.executable,
            "--project",
            str(prepared_target),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if checked.returncode:
        detail = checked.stderr.strip() or checked.stdout.strip() or "invalid lock"
        raise ValueError(f"MiniSWE candidate uv lock --check failed: {detail}")


def _write_target(workspace: Path, target_config: dict[str, Any]) -> None:
    _validate_target_config(target_config)
    seed_text = cast(str, target_config["seed"])
    revision_value = target_config.get("revision")
    revision = cast(str | None, revision_value)
    generate_lock = target_config.get("generate_lock", False)
    if seed_text in ("builtin-codex", "builtin-local-smoke"):
        _copy_resource_tree(seed_root() / seed_text.removeprefix("builtin-"), workspace / "target")
        (workspace / "target" / "UPSTREAM.json").write_text(
            json.dumps({"kind": "builtin", "seed": seed_text}, sort_keys=True) + "\n"
        )
    elif _looks_like_git_url(seed_text):
        with tempfile.TemporaryDirectory(prefix="evolve-seed-") as tmp:
            checkout = Path(tmp) / "seed"
            _git_clone(seed_text, checkout, revision=revision)
            _vendor_seed(workspace, checkout, seed_text)
    else:
        if revision is not None:
            raise ValueError("target.revision requires a git URL seed")
        source = Path(seed_text).expanduser()
        if not source.is_dir():
            raise ValueError(f"seed is not a local directory or git URL: {seed_text}")
        _vendor_seed(workspace, source.resolve(), str(source.resolve()))
    if generate_lock:
        _generate_target_lock(workspace / "target")


def _copy_resource_tree(source: Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_resource_tree(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _vendor_seed(workspace: Path, source: Path, fallback_remote: str) -> None:
    _validate_seed_symlinks(source)
    shutil.copytree(
        source,
        workspace / "target",
        symlinks=True,
        ignore=shutil.ignore_patterns(*_SEED_IGNORE_PATTERNS),
    )
    upstream = _git_upstream(source, fallback_remote)
    if upstream:
        (workspace / "target" / "UPSTREAM.json").write_text(json.dumps(upstream, sort_keys=True) + "\n")


def _git_upstream(source: Path, fallback_remote: str) -> dict[str, str] | None:
    if not (source / ".git").exists():
        return None
    return {
        "remote": _sanitize_upstream_remote(_git_optional(source, "remote", "get-url", "origin") or fallback_remote),
        "commit": _git(source, "rev-parse", "HEAD").strip(),
    }


def _validate_seed_symlinks(source: Path) -> None:
    root = source.resolve()
    for path in source.rglob("*"):
        if not path.is_symlink():
            continue
        target = path.readlink()
        if target.is_absolute():
            raise ValueError(f"target seed contains an absolute symlink: {path}")
        resolved = (path.parent / target).resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError(f"target seed contains a symlink escaping its root: {path}") from None


def _sanitize_upstream_remote(remote: str) -> str:
    parsed = urllib.parse.urlsplit(remote)
    if not parsed.scheme or not parsed.netloc:
        return remote
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port is not None else ""
    return urllib.parse.urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))


def _looks_like_git_url(seed: str) -> bool:
    return (
        "://" in seed or seed.startswith("git@") or (seed.endswith(".git") and ":" in seed and not Path(seed).exists())
    )


def _git_clone(url: str, destination: Path, *, revision: str | None = None) -> None:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for evolve init")
    if revision is None:
        commands = [[git, "clone", "--depth", "1", url, str(destination)]]
    else:
        commands = [
            [git, "init", str(destination)],
            [git, "-C", str(destination), "remote", "add", "origin", url],
        ]
    for command in commands:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git clone failed")
    if revision is None:
        return
    fetch = subprocess.run(
        [git, "-C", str(destination), "fetch", "--depth", "1", "origin", revision],
        text=True,
        capture_output=True,
        check=False,
    )
    if fetch.returncode != 0:
        fetch = subprocess.run(
            [git, "-C", str(destination), "fetch", "origin"],
            text=True,
            capture_output=True,
            check=False,
        )
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or "git fetch failed")
    checkout = subprocess.run(
        [git, "-C", str(destination), "checkout", "--detach", revision],
        text=True,
        capture_output=True,
        check=False,
    )
    if checkout.returncode != 0:
        raise RuntimeError(checkout.stderr.strip() or "git checkout failed")


def _generate_target_lock(target: Path) -> None:
    if not (target / "pyproject.toml").is_file():
        raise ValueError("target.generate_lock requires the prepared target to contain target/pyproject.toml")
    result = subprocess.run(
        [uv_executable(), "lock", "--python", sys.executable, "--project", str(target)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "uv lock failed"
        raise RuntimeError(f"target.generate_lock failed: {detail}")
    if not (target / "uv.lock").is_file():
        raise ValueError("target.generate_lock did not produce target/uv.lock")


def _remove_generated_target_metadata(target: Path) -> None:
    for path in target.rglob("*.egg-info"):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _init_git(workspace: Path) -> None:
    _git(workspace, "init")
    _git(workspace, "config", "user.name", "Evolve Mechanism")
    _git(workspace, "config", "user.email", "evolve@example.invalid")
    _git(workspace, "add", ".")
    # A vendored seed is an exact experiment input. Its own ignore rules must
    # not silently remove copied files (for example an upstream-ignored
    # uv.lock) from the generation-zero snapshot. Sensitive and generated
    # paths have already been removed by _SEED_IGNORE_PATTERNS during copy.
    _git(workspace, "add", "-f", "target")
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


def _agent_env(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, dict):
        raise ValueError("evaluator.agent_env must be a mapping")
    for name in value:
        if not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None:
            raise ValueError(f"invalid evaluator.agent_env name: {name!r}")
    lines: list[str] = []
    for name in sorted(value):
        raw = value[name]
        if isinstance(raw, bool):
            rendered = "true" if raw else "false"
        elif isinstance(raw, (str, int, float)):
            rendered = str(raw)
        else:
            raise ValueError(f"evaluator.agent_env value for {name} must be scalar")
        if "\0" in rendered:
            raise ValueError(f"evaluator.agent_env value for {name} must not contain NUL")
        if "\n" in rendered or "\r" in rendered:
            raise ValueError(f"evaluator.agent_env value for {name} must be single-line")
        lines.append(f"{name}={rendered}\n")
    return "".join(lines)


def _environment_kwargs(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, dict):
        raise ValueError("evaluator.environment_kwargs must be a mapping")
    lines: list[str] = []
    for name in sorted(value):
        if not isinstance(name, str) or _ENV_NAME.fullmatch(name) is None:
            raise ValueError(f"invalid evaluator.environment_kwargs name: {name!r}")
        try:
            rendered = json.dumps(value[name], separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"evaluator.environment_kwargs value for {name} must be JSON-serializable") from exc
        lines.append(f"{name}={rendered}\n")
    return "".join(lines)


def _eval_env(
    _workspace_name: str,
    dataset: str,
    n_concurrent: int,
    tasks_per_round: int,
    trials: int,
    partial_floor: float,
    agent: str,
    *,
    model: str | None = None,
    environment: str = "",
    dataset_mode: str = "path",
    task_file: str | None = None,
    setup_timeout_multiplier: float = 1,
    agent_timeout_multiplier: float = 1,
    verifier_timeout_multiplier: float = 1,
    max_retries: int = 0,
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
    if environment:
        text += f"EVOLVE_HARBOR_ENVIRONMENT={shlex.quote(environment)}\n"
    if setup_timeout_multiplier > 1:
        text += f"EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER={setup_timeout_multiplier}\n"
    if agent_timeout_multiplier > 1:
        text += f"EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER={agent_timeout_multiplier}\n"
    if verifier_timeout_multiplier > 1:
        text += f"EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER={verifier_timeout_multiplier}\n"
    if max_retries > 0:
        text += f"EVOLVE_HARBOR_MAX_RETRIES={max_retries}\n"
    if model:
        text += f"EVOLVE_HARBOR_MODEL={shlex.quote(model)}\n"
    return text + (f"EVOLVE_HARBOR_TASK_FILE={shlex.quote(task_file)}\n" if task_file else "")


def _eval_sh(engine: str, _dataset: str) -> str:
    return _workspace_scaffold("evaluator/eval-prefix.sh") + _evaluator_scaffold(engine, "engine.sh")


def _shell_script(label: str) -> str:
    return f"#!/bin/sh\nset -eu\nprintf '%s\\n' '{label}'\n"


def _workspace_scaffold(relative_path: str) -> str:
    return (scaffold_root() / "workspace" / relative_path).read_text()


def _framework_legal_text(name: str) -> str:
    source = SOURCE_ROOT / name
    if (SOURCE_ROOT / "pyproject.toml").is_file() and source.is_file():
        return source.read_text()
    return (resource_root("licenses") / name).read_text()


def _evaluator_scaffold(engine: str, relative_path: str) -> str:
    root = scaffold_root() / "evaluators" / engine
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"unsupported evaluator.engine: {engine}")
    return path.read_text()


def _skill_package(name: str) -> dict[str, str]:
    root = resource_root("skills") / name
    if not root.is_dir():
        raise ValueError(f"skill package not found: {name}")
    files: dict[str, str] = {}

    def visit(directory: Traversable, relative: str = "") -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            child_relative = f"{relative}/{child.name}" if relative else child.name
            if child.is_dir():
                visit(child, child_relative)
            elif child.is_file():
                files[f"skills/{name}/{child_relative}"] = child.read_text()

    visit(root)
    return files


def _source_label(source: object) -> str:
    return (
        source.relative_to(SOURCE_ROOT).as_posix()
        if isinstance(source, Path) and source.is_relative_to(SOURCE_ROOT)
        else str(source)
    )
