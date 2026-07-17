# Python Import and Runtime Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all runtime `sys.path`/`PYTHONPATH` manipulation and run generated workspaces, Harbor, and protected adapters from one locked workspace `uv` project.

**Architecture:** `evolve init` copies a pre-locked root Python project and protected Harbor adapter into each workspace. The generated console and every Harbor boundary invoke `uv run --project <original-workspace> --frozen`; operator modules rely only on the launcher's documented checkout working directory.

**Tech Stack:** Python 3.12 workspace runtime, uv, Harbor 0.18.0, Hatchling, pytest, Ruff, ty, POSIX shell on macOS/Linux.

## Global Constraints

- Framework compatibility remains Python >=3.11; generated workspace host runtimes use Python 3.12 because Harbor 0.18.0 requires Python >=3.12.
- Supported hosts are macOS and Linux; native Windows remains unsupported.
- `agent_pythonpath` is removed without a compatibility fallback.
- Production code must not mutate `sys.path` or assign `PYTHONPATH`.
- Candidate project dependencies under `target/` remain independent from the workspace host project.
- Existing workspaces are not silently migrated.

---

### Task 1: Central host-process contract

**Files:**
- Create: `src/evolve/host_runtime.py`
- Test: `tests/test_host_runtime.py`

**Interfaces:**
- Produces: `clean_python_env(source: Mapping[str, str] | None = None) -> dict[str, str]`
- Produces: `uv_executable(env: Mapping[str, str] | None = None) -> str`
- Produces: `uv_run(workspace: Path, *command: str, env: Mapping[str, str] | None = None) -> tuple[list[str], dict[str, str]]`

- [ ] **Step 1: Write failing environment and command tests**

```python
def test_uv_run_uses_locked_workspace_and_cleans_python_environment(tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("#!/bin/sh\n")
    uv.chmod(0o755)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\nversion='0'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    source = {
        "EVOLVE_UV_BINARY": str(uv),
        "PYTHONPATH": "/unsafe",
        "PYTHONHOME": "/wrong",
        "VIRTUAL_ENV": "/other",
        "OPENAI_API_KEY": "secret",
    }

    command, env = uv_run(tmp_path, "harbor", "run", env=source)

    assert command == [str(uv), "run", "--project", str(tmp_path.resolve()), "--frozen", "harbor", "run"]
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & env.keys()
    assert env["OPENAI_API_KEY"] == "secret"
    assert source["PYTHONPATH"] == "/unsafe"
```

Add tests for fallback `PATH` lookup and the error `uv is required; install uv or set EVOLVE_UV_BINARY`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest -q tests/test_host_runtime.py`

Expected: collection fails because `evolve.host_runtime` does not exist.

- [ ] **Step 3: Implement the minimal helper**

```python
from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path


def clean_python_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(name, None)
    return env


def uv_executable(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    configured = values.get("EVOLVE_UV_BINARY")
    candidate = configured or shutil.which("uv", path=values.get("PATH"))
    if not candidate or not Path(candidate).is_file():
        raise RuntimeError("uv is required; install uv or set EVOLVE_UV_BINARY")
    return str(Path(candidate).expanduser().resolve())


def uv_run(
    workspace: Path,
    *command: str,
    env: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    clean = clean_python_env(env)
    root = workspace.resolve()
    for name in ("pyproject.toml", "uv.lock"):
        if not (root / name).is_file():
            raise RuntimeError(f"workspace uv project is missing {root / name}")
    return [uv_executable(clean), "run", "--project", str(root), "--frozen", *command], clean
```

- [ ] **Step 4: Verify GREEN and run type/lint checks**

Run: `uv run pytest -q tests/test_host_runtime.py && uv run ruff check src/evolve/host_runtime.py tests/test_host_runtime.py && uv run ty check`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/host_runtime.py tests/test_host_runtime.py
git commit -m "feat: define locked host runtime contract"
```

### Task 2: Generate one locked workspace project

**Files:**
- Create: `templates/workspace/pyproject.toml`
- Create: `templates/workspace/.python-version`
- Create: `templates/workspace/evolve_harbor_adapter/__init__.py`
- Generate: `templates/workspace/uv.lock`
- Modify: `src/evolve/workspace.py`
- Modify: `templates/workspace/.gitignore`
- Modify: `pyproject.toml`
- Test: `tests/test_m0_init.py`
- Test: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: the workspace resource-copy mechanism in `src/evolve/workspace.py`.
- Produces: a fixed `evolve-workspace-runtime` project with Harbor 0.18.0 and an importable `evolve_harbor_adapter.MiniSweSourceAgent`.

- [ ] **Step 1: Write failing workspace-layout tests**

```python
def test_init_writes_single_locked_host_project(tmp_path):
    workspace, _ = init_workspace(tmp_path)
    assert (workspace / "pyproject.toml").is_file()
    assert (workspace / "uv.lock").is_file()
    assert (workspace / ".python-version").read_text() == "3.12\n"
    assert (workspace / "evolve_harbor_adapter" / "__init__.py").is_file()
    assert ".venv/" in (workspace / ".gitignore").read_text().splitlines()
    assert not (workspace / "target" / "harbor_agent.py").exists()
```

Update existing adapter tests to load `evolve_harbor_adapter/__init__.py` and set `EVOLVE_CANDIDATE_SOURCE` to the fixture target.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/test_m0_init.py tests/test_miniswe_harbor_wrapper.py`

Expected: failures report missing root project/adapter and the obsolete target adapter still exists.

- [ ] **Step 3: Add the root project template**

```toml
[project]
name = "evolve-workspace-runtime"
version = "0"
requires-python = ">=3.12"
dependencies = [
    "harbor==0.18.0",
    "PyYAML>=6.0",
    "typer>=0.12",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["evolve_harbor_adapter"]
```

Copy the existing MiniSWE adapter into `evolve_harbor_adapter/__init__.py`, replacing `Path(__file__).resolve().parent` with:

```python
source = self._get_env("EVOLVE_CANDIDATE_SOURCE")
if not source:
    raise RuntimeError("EVOLVE_CANDIDATE_INVALID: candidate_source_missing")
source_dir = Path(source).expanduser().resolve()
```

- [ ] **Step 4: Generate and validate the shipped lock**

Run: `UV_CACHE_DIR=/tmp/evolve-plan-uv-cache uv lock --project templates/workspace --python 3.12`

Expected: `templates/workspace/uv.lock` records `harbor==0.18.0` and the local workspace project. Then add `"templates" = "evolve/templates"` coverage assertions to the wheel resource test rather than generating a lock during `evolve init`.

- [ ] **Step 5: Copy resources during initialization and remove target adapter generation**

Extend `_write_files` with the root project, lock, Python version, and adapter files. Delete `_write_target_harbor_agent`; retain validation of supported `target.harbor_agent` recipe values while rendering the protected adapter name `evolve_harbor_adapter:MiniSweSourceAgent` into evaluator config.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest -q tests/test_m0_init.py tests/test_miniswe_harbor_wrapper.py tests/test_phase_e_recipes.py tests/test_harbor_evaluator_config.py`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add templates/workspace src/evolve/workspace.py pyproject.toml tests/test_m0_init.py tests/test_miniswe_harbor_wrapper.py tests/test_phase_e_recipes.py tests/test_harbor_evaluator_config.py
git commit -m "feat: generate locked workspace host projects"
```

### Task 3: Route the console and evaluator through uv

**Files:**
- Create: `templates/workspace/launch_evolve.py`
- Create: `templates/workspace/launch_splits.py`
- Modify: `src/evolve/workspace.py`
- Modify: `src/evolve/evaluator.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Test: `tests/test_runtime.py`
- Test: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: workspace root project from Task 2 and `clean_python_env` from Task 1.
- Produces: a console and evaluator that never export an import path.

- [ ] **Step 1: Write failing console/evaluator tests**

Assert that generated `evolve` contains `run --project`, `--frozen`, and `.evolve/launch_evolve.py`; assert the evaluator invokes `.evolve/launch_splits.py`, passes `EVOLVE_WORKSPACE`, and contains no import-path export. Preserve the existing unusual-interpreter-path and caller-CWD tests.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/test_runtime.py tests/test_harbor_evaluator_template.py`

Expected: assertions fail against the current path-exporting scripts.

- [ ] **Step 3: Implement adjacent launchers and uv console**

```python
# templates/workspace/launch_evolve.py
from evolve.cli import main

raise SystemExit(main())
```

```python
# templates/workspace/launch_splits.py
from evolve.splits import main

raise SystemExit(main())
```

Generate `./evolve` as a quoted shell wrapper around:

```bash
exec "$UV" run --project "$HERE" --frozen python "$HERE/.evolve/launch_evolve.py" "$@"
```

Use `EVOLVE_UV_BINARY` or `command -v uv`, with the same missing-uv message as Task 1.

- [ ] **Step 4: Update evaluator environment and shell**

Set `EVOLVE_WORKSPACE` in `_run_eval_script`, remove Python import variables via `clean_python_env`, execute split selection with the original workspace project, and prefix Harbor with `uv run --project "$EVOLVE_WORKSPACE" --frozen harbor`.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest -q tests/test_runtime.py tests/test_harbor_evaluator_template.py tests/test_m8_dataset_splits.py`

Expected: all tests pass without Docker.

- [ ] **Step 6: Commit**

```bash
git add templates/workspace/launch_evolve.py templates/workspace/launch_splits.py src/evolve/workspace.py src/evolve/evaluator.py templates/evaluator/engines/harbor.sh tests/test_runtime.py tests/test_harbor_evaluator_template.py
git commit -m "refactor: launch workspace runtime through uv"
```

### Task 4: Route Python Harbor runners through the workspace project

**Files:**
- Modify: `library/rollout/harbor.py`
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `META_AGENTS.md`
- Test: `tests/test_m7_harbor_rollout.py`
- Test: `tests/test_harbor_meta_agent.py`

**Interfaces:**
- Consumes: `uv_run` and `clean_python_env` from Task 1.
- Produces: both Python Harbor boundaries using the exact locked prefix.

- [ ] **Step 1: Replace fake Harbor fixtures with fake uv fixtures**

The fake `uv` must verify `run --project <workspace> --frozen harbor`, record the sanitized environment, remove the prefix, and execute the existing fake Harbor body. Add assertions that ambient `harbor` is ignored and legacy `agent_pythonpath` raises `AgentCommandError` mentioning its removal.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/test_m7_harbor_rollout.py tests/test_harbor_meta_agent.py`

Expected: current runners call `harbor` directly and leak/inject import variables.

- [ ] **Step 3: Implement the locked prefix**

Replace `shutil.which("harbor")` and `_harbor_env` with `uv_run(ctx.workspace, "harbor", ...)`. Ensure the evaluator adapter commands add:

```text
--ae EVOLVE_CANDIDATE_SOURCE=<checkout>/target
```

Reject `agent_pythonpath` before building a command:

```python
if "agent_pythonpath" in ctx.config:
    raise ValueError("agent_pythonpath was removed; add the adapter to the workspace pyproject.toml and uv.lock")
```

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest -q tests/test_m7_harbor_rollout.py tests/test_harbor_meta_agent.py`

Expected: all tests pass and captured children contain no Python import variables.

- [ ] **Step 5: Commit**

```bash
git add library/rollout/harbor.py library/meta_agent/runners/harbor.py META_AGENTS.md tests/test_m7_harbor_rollout.py tests/test_harbor_meta_agent.py
git commit -m "refactor: run Harbor from locked workspace environments"
```

### Task 5: Remove repository-wide path mutation

**Files:**
- Modify: every `library/**/*.py` file containing `sys.path`
- Modify: `tests/test_hyperagents_semantics.py`
- Modify: `tests/test_m5_driver_operators.py`
- Modify: `tests/test_m5_record_verb.py`
- Modify: `tests/test_harbor_artifacts.py`
- Modify: `pyproject.toml`
- Create: `tests/test_import_hygiene.py`

**Interfaces:**
- Produces: a static regression guard and ordinary top-of-file imports.

- [ ] **Step 1: Write the failing AST/shell hygiene test**

Parse production `.py` files and fail on assignment/calls targeting `sys.path`. Scan production `.sh` templates and Python environment dictionaries for assignments to the import-path variable. Exclude documentation prose but not tests or generated templates.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/test_import_hygiene.py`

Expected: the test lists the current operator, runner, console, and evaluator violations.

- [ ] **Step 3: Remove mutations and reorder imports**

Delete the `os`/`sys` imports used only for path repair, move Evolve imports to the normal import block, remove `# ruff: noqa: E402`, and delete the broad `library/**` and `templates/**` E402 exemptions. Replace the test-only `sys.path.insert` in `test_harbor_artifacts.py` with `importlib.util.spec_from_file_location`.

- [ ] **Step 4: Verify GREEN and operator behavior**

Run: `uv run pytest -q tests/test_import_hygiene.py tests/test_m5_driver_operators.py tests/test_m5_record_verb.py tests/test_hyperagents_semantics.py tests/test_harbor_artifacts.py`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add library tests/test_import_hygiene.py tests/test_hyperagents_semantics.py tests/test_m5_driver_operators.py tests/test_m5_record_verb.py tests/test_harbor_artifacts.py pyproject.toml
git commit -m "refactor: eliminate Python path mutation"
```

### Task 6: Documentation and macOS/Linux CI

**Files:**
- Modify: `README.md`
- Modify: `META_AGENTS.md`
- Modify: `templates/workspace/README.md`
- Modify: `.github/workflows/test.yml`

**Interfaces:**
- Produces: user-facing breaking migration guidance and a two-host test matrix.

- [ ] **Step 1: Write documentation assertions**

Extend recipe/config tests to require the protected adapter name, root lock explanation, Python 3.12 workspace runtime, custom adapter dependency instructions, and an explicit statement that existing experiments must be regenerated or manually migrated.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest -q tests/test_phase_e_recipes.py tests/test_config_parser.py tests/test_runtime.py`

Expected: documentation assertions fail.

- [ ] **Step 3: Update documentation and CI**

Replace path-based adapter examples with `uv add --project <workspace> <adapter-package>` followed by `uv lock --project <workspace>`. Change the test job to:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest]
runs-on: ${{ matrix.os }}
```

Keep Docker/model-dependent tests mocked; run the existing init → run → verify stub smoke on both hosts.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest -q tests/test_phase_e_recipes.py tests/test_config_parser.py tests/test_runtime.py`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md META_AGENTS.md templates/workspace/README.md .github/workflows/test.yml tests/test_phase_e_recipes.py tests/test_config_parser.py tests/test_runtime.py
git commit -m "docs: explain locked workspace runtime migration"
```

### Task 7: Full verification and packaging smoke

**Files:**
- Modify if required by failures: only files already listed in Tasks 1-6

**Interfaces:**
- Consumes: the complete implementation.
- Produces: evidence that source, wheel resources, generated workspaces, and both supported CI hosts use the same contract.

- [ ] **Step 1: Run formatting and static analysis**

Run: `uv run ruff format --check . && uv run ruff check . && uv run ty check`

Expected: all commands exit 0.

- [ ] **Step 2: Run the complete test suite**

Run: `uv run pytest -q`

Expected: zero failures.

- [ ] **Step 3: Build and inspect distribution resources**

Run: `uv build && python -m zipfile -l dist/evolve_framework-0.1.0-py3-none-any.whl`

Expected: the wheel contains workspace `pyproject.toml`, `uv.lock`, `.python-version`, launchers, and `evolve_harbor_adapter`.

- [ ] **Step 4: Run a clean generated-workspace smoke**

```bash
smoke_dir=$(mktemp -d /tmp/evolve-runtime-smoke.XXXXXX)
EVOLVE_RUNTIME_DIGEST=sha256:runtime-cleanup-smoke uv run evolve init "$smoke_dir/workspace" --recipe hill_climb-smoke
EVAL_STUB=1 EVOLVE_HOME="$smoke_dir/home" "$smoke_dir/workspace/evolve" run "$smoke_dir/workspace" --max-generations 1
EVOLVE_HOME="$smoke_dir/home" "$smoke_dir/workspace/evolve" verify "$smoke_dir/workspace"
```

Expected: initialization, run, and verification exit 0; no production file assigns an import path.

- [ ] **Step 5: Review the final diff and commit verification-only adjustments**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intentional files remain. If verification required an adjustment, commit it as `fix: complete locked runtime migration`; otherwise create no empty commit.
