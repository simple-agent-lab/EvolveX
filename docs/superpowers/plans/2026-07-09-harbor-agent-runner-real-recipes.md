# Harbor Agent Runner Real Recipes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Evolve use Harbor as the only real evaluation path, run mutation through a simple local meta-agent primitive, split real recipes from smoke recipes, and evaluate MiniSWE source through a Harbor custom agent wrapper in `target/`.

**Architecture:** Mutation becomes three narrow parts: prompt assembly, `run_meta_agent(workspace, prompt, config)`, and `create_mutation_patch(checkout, parent_ref, surface)`. Harbor evaluation receives an explicit `evaluator.agent` value and real MiniSWE recipes generate `target/harbor_agent.py`, while smoke recipes keep cheap deterministic behavior under explicit smoke names. HyperAgents self-modification remains driver-ordered: changed mutate workflow affects later generations, while changed gate and record can affect the same child after mutation.

**Tech Stack:** Python 3.11, pytest, git CLI, shell evaluator templates, Harbor custom agents via `BaseAgent`/`BaseInstalledAgent`, MiniSWE through Harbor's `MiniSweAgent` adapter.

## Global Constraints

- Harbor is the only real benchmark execution interface.
- No real recipe may depend on `solve.sh`, `run.sh`, or `CheckoutTargetAgent` fallback behavior.
- Real recipe names are reserved for real behavior; deterministic or stub behavior must live in explicit `*-smoke` recipes.
- MiniSWE source evolution evaluates the candidate `target/` source plus `target/harbor_agent.py`.
- `MutateOperator` remains the Evolve protocol adapter; it is not the meta-agent.
- `run_meta_agent` only runs the configured local agent command in a workspace with a prompt file.
- `create_mutation_patch` owns git diffing and surface repair.
- Real self-modification admission must not inject `EVAL_STUB=1`.
- Tests that need cheap evaluator behavior must set `EVAL_STUB=1` and use smoke paths.

---

## File Structure

- Create `src/evolve/agent.py`: local meta-agent command runner and result/error types.
- Create `src/evolve/mutation.py`: mutation parent ref, surface policy loader, changed-path diff builder, and surface repair helper.
- Modify `library/mutate/agent_command.py`: thin `MutateOperator` adapter using the new runner and patch builder.
- Modify `src/evolve/workspace.py`: explicit Harbor agent configuration, target adapter overlay, and no default checkout fallback.
- Modify `src/evolve/frozen/meta_eval.py`: remove hard-coded stub replay.
- Create `templates/target/harbor/miniswe_source_agent.py`: MiniSWE source wrapper subclassing Harbor's `MiniSweAgent`.
- Modify `templates/evaluator/engines/harbor.sh`: keep native Harbor invocation, preserve custom import path handling, and improve failure surfacing only if needed.
- Keep `templates/evaluator/checkout_agent.py` only as a compatibility template, but stop vendoring it into new real workspaces.
- Create smoke recipe directories `recipes/hill_climb-smoke`, `recipes/dgm-smoke`, `recipes/ahe-smoke`, `recipes/autoresearch-smoke`, `recipes/hyperagents-smoke`, and `recipes/metaagent-smoke`.
- Modify real recipe directories `recipes/hill_climb`, `recipes/dgm`, `recipes/ahe`, `recipes/autoresearch`, `recipes/hyperagents`, and `recipes/metaagent`.
- Modify tests under `tests/` to cover runner, patch builder, mutator, evaluator env, MiniSWE wrapper, recipes, meta-eval, and HyperAgents semantics.
- Modify docs `README.md`, `DESIGN.md`, `docs/glossary.md`, and `recipes/README.md` after behavior is implemented.

### Shared Interfaces

These signatures are the cross-task contract:

```python
@dataclass(frozen=True)
class AgentRunResult:
    stdout: str
    stderr: str
    output: str
    returncode: int
    wall_s: float
    usage: dict[str, Any]


class AgentCommandError(RuntimeError):
    output: str
    usage: dict[str, Any]
    returncode: int


# run_meta_agent(workspace: Path | str, prompt: str, config: dict[str, Any] | None = None) -> AgentRunResult


@dataclass(frozen=True)
class SurfacePolicy:
    include: list[str]
    exclude: list[str]


@dataclass(frozen=True)
class MutationPatch:
    changed_paths: list[str]
    diff: str
    surface_report: dict[str, Any]
    notes: list[str]


# load_surface_policy(checkout: Path | str) -> SurfacePolicy
# mutation_parent_ref(checkout: Path | str, ctx: OperatorContext) -> str
# create_mutation_patch(checkout: Path | str, parent_ref: str, surface: SurfacePolicy, *, repair: bool = True) -> MutationPatch
```

### Task 1: Local Meta-Agent Runner

**Files:**
- Create: `src/evolve/agent.py`
- Test: `tests/test_agent_runner.py`

**Interfaces:**
- Consumes: `operators.mutate.command` as `config["command"]`, nested `config["operators"]["mutate"]["command"]`, or environment `EVOLVE_AGENT_COMMAND`.
- Produces: `AgentRunResult`, `AgentCommandError`, and `run_meta_agent(workspace, prompt, config)`.

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_agent_runner.py`:

```python
import json
import sys
from pathlib import Path

import pytest

from evolve.agent import AgentCommandError, run_meta_agent


def test_run_meta_agent_runs_command_in_workspace_with_prompt_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text(
        "import json, os, pathlib\n"
        "workspace = pathlib.Path.cwd()\n"
        "prompt = pathlib.Path(os.environ['EVOLVE_PROMPT_FILE']).read_text()\n"
        "(workspace / 'probe.json').write_text(json.dumps({'cwd': str(workspace), 'prompt': prompt}))\n"
        "print('agent stdout')\n"
    )

    result = run_meta_agent(
        workspace=workspace,
        prompt="repair target\n",
        config={"command": f"{sys.executable} {script}", "timeout_s": 30},
    )

    probe = json.loads((workspace / "probe.json").read_text())
    assert probe == {"cwd": str(workspace), "prompt": "repair target\n"}
    assert result.stdout.strip() == "agent stdout"
    assert result.stderr == ""
    assert result.returncode == 0
    assert result.usage["usd"] == 0
    assert result.usage["wall_s"] >= 0


def test_run_meta_agent_uses_env_command_and_reports_missing_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "agent.py"
    script.write_text("from pathlib import Path\nPath('env-command-ran').write_text('yes\\n')\n")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", f"{sys.executable} {script}")

    run_meta_agent(workspace=workspace, prompt="x", config={})

    assert (workspace / "env-command-ran").read_text() == "yes\n"

    monkeypatch.delenv("EVOLVE_AGENT_COMMAND")
    with pytest.raises(AgentCommandError) as excinfo:
        run_meta_agent(workspace=workspace, prompt="x", config={})
    assert "EVOLVE_AGENT_COMMAND" in str(excinfo.value)
    assert "operators.mutate.command" in str(excinfo.value)
    assert excinfo.value.returncode == 2


def test_run_meta_agent_timeout_kills_command_group(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "sleep.py"
    script.write_text("import time\nprint('started', flush=True)\ntime.sleep(60)\n")

    with pytest.raises(AgentCommandError) as excinfo:
        run_meta_agent(
            workspace=workspace,
            prompt="x",
            config={"command": f"{sys.executable} {script}", "timeout_s": 0.05},
        )

    assert "timeout" in str(excinfo.value).lower()
    assert excinfo.value.usage["usd"] == 0
    assert excinfo.value.usage["wall_s"] >= 0
```

- [ ] **Step 2: Run runner tests to verify failure**

Run: `uv run pytest tests/test_agent_runner.py -q`

Expected: FAIL during import with `ModuleNotFoundError: No module named 'evolve.agent'`.

- [ ] **Step 3: Implement `src/evolve/agent.py`**

Create `src/evolve/agent.py`:

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentRunResult:
    stdout: str
    stderr: str
    output: str
    returncode: int
    wall_s: float
    usage: dict[str, Any]


class AgentCommandError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        output: str = "",
        usage: dict[str, Any] | None = None,
        returncode: int = 1,
    ) -> None:
        super().__init__(message)
        self.output = output
        self.usage = usage or {"usd": 0}
        self.returncode = returncode if isinstance(returncode, int) and returncode else 1


def run_meta_agent(workspace: Path | str, prompt: str, config: dict[str, Any] | None = None) -> AgentRunResult:
    root = Path(workspace).resolve()
    command = _resolve_command(config or {})
    start = time.monotonic()
    timeout = _configured_timeout(config or {})
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(prompt)
        prompt_file = handle.name
    env = {**os.environ, "EVOLVE_PROMPT_FILE": prompt_file}
    try:
        if timeout is not None and timeout <= 0.01:
            usage = _usage(start)
            raise AgentCommandError(f"meta-agent timeout after {timeout}s", usage=usage)
        proc = subprocess.Popen(
            ["sh", "-c", command],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            stdout, stderr = proc.communicate()
            output = _combined_output(stdout or "", stderr or "")
            raise AgentCommandError(
                f"meta-agent timeout after {timeout}s",
                output=output,
                usage=_usage(start),
                returncode=1,
            )
    finally:
        Path(prompt_file).unlink(missing_ok=True)
    stdout = stdout or ""
    stderr = stderr or ""
    output = _combined_output(stdout, stderr)
    usage = _usage(start)
    if proc.returncode != 0:
        raise AgentCommandError(
            stderr.strip() or stdout.strip() or "meta-agent command failed",
            output=output,
            usage=usage,
            returncode=proc.returncode,
        )
    return AgentRunResult(stdout=stdout, stderr=stderr, output=output, returncode=0, wall_s=usage["wall_s"], usage=usage)


def _resolve_command(config: dict[str, Any]) -> str:
    command = config.get("command")
    if command:
        return str(command)
    operators = config.get("operators")
    if isinstance(operators, dict):
        mutate = operators.get("mutate")
        if isinstance(mutate, dict) and mutate.get("command"):
            return str(mutate["command"])
    env_command = os.environ.get("EVOLVE_AGENT_COMMAND")
    if env_command:
        return env_command
    raise AgentCommandError(
        "missing meta-agent command; set EVOLVE_AGENT_COMMAND or operators.mutate.command",
        returncode=2,
    )


def _configured_timeout(config: dict[str, Any]) -> float | None:
    timeout = _timeout_float(config.get("timeout_s"))
    inherited = _timeout_float(os.environ.get("EVOLVE_OPERATOR_TIMEOUT_S"))
    if inherited is None:
        return timeout
    cap = _timeout_headroom(inherited)
    return cap if timeout is None else min(timeout, cap)


def _timeout_float(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timeout_headroom(timeout: float | None) -> float | None:
    if timeout is None or timeout <= 0:
        return timeout
    if timeout < 1:
        return max(0.001, timeout * 0.05)
    return max(0.01, timeout - min(5.0, max(0.5, timeout * 0.05)))


def _combined_output(stdout: str, stderr: str) -> str:
    if not stderr:
        return stdout
    if not stdout:
        return stderr
    return stdout + ("" if stdout.endswith("\n") else "\n") + stderr


def _usage(start: float) -> dict[str, Any]:
    return {"wall_s": round(time.monotonic() - start, 6), "usd": 0}


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, 9)
    except Exception:
        proc.kill()
```

- [ ] **Step 4: Run runner tests to verify pass**

Run: `uv run pytest tests/test_agent_runner.py -q`

Expected: PASS, all three tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/evolve/agent.py tests/test_agent_runner.py
git commit -m "Add local meta-agent runner"
```

### Task 2: Mutation Patch Builder

**Files:**
- Create: `src/evolve/mutation.py`
- Test: `tests/test_mutation_patch.py`

**Interfaces:**
- Consumes: `evolve.git.working_tree_changed_paths`, `evolve.surface.check_paths`, and `evolve.surface.surface_patterns`.
- Produces: `SurfacePolicy`, `MutationPatch`, `load_surface_policy`, `mutation_parent_ref`, and `create_mutation_patch`.

- [ ] **Step 1: Write failing patch-builder tests**

Create `tests/test_mutation_patch.py`:

```python
import subprocess
from pathlib import Path

from evolve.mutation import SurfacePolicy, create_mutation_patch


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / "target").mkdir()
    (root / "target" / "agent.py").write_text("print('parent')\n")
    (root / "README.md").write_text("parent\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "parent")
    _git(root, "tag", "gen/0")
    return root


def test_create_mutation_patch_reports_changed_paths_and_diff(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "+print('child')" in patch.diff
    assert patch.notes == []


def test_create_mutation_patch_repairs_out_of_surface_paths(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")
    (root / "README.md").write_text("leak\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "README.md" not in patch.diff
    assert (root / "README.md").read_text() == "parent\n"
    assert patch.notes == ["repaired surface violations by reverted: README.md"]


def test_create_mutation_patch_reports_remaining_violation_when_repair_disabled(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "README.md").write_text("leak\n")

    patch = create_mutation_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
        repair=False,
    )

    assert patch.changed_paths == ["README.md"]
    assert patch.surface_report == {"ok": False, "mutated": ["README.md"], "violations": ["README.md"]}
    assert patch.notes == []
```

- [ ] **Step 2: Run patch-builder tests to verify failure**

Run: `uv run pytest tests/test_mutation_patch.py -q`

Expected: FAIL during import with `ModuleNotFoundError: No module named 'evolve.mutation'`.

- [ ] **Step 3: Implement `src/evolve/mutation.py`**

Create `src/evolve/mutation.py`:

```python
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .git import git, head_tag, working_tree_changed_paths
from .surface import check_paths, surface_patterns


@dataclass(frozen=True)
class SurfacePolicy:
    include: list[str]
    exclude: list[str]


@dataclass(frozen=True)
class MutationPatch:
    changed_paths: list[str]
    diff: str
    surface_report: dict[str, Any]
    notes: list[str]


def load_surface_policy(checkout: Path | str) -> SurfacePolicy:
    include, exclude = surface_patterns(Path(checkout))
    return SurfacePolicy(include=include, exclude=exclude)


def mutation_parent_ref(checkout: Path | str, ctx: Any) -> str:
    parent = getattr(ctx, "parent", None)
    if parent:
        return f"gen/{parent}"
    return head_tag(Path(checkout)) or "gen/0"


def create_mutation_patch(
    checkout: Path | str,
    parent_ref: str,
    surface: SurfacePolicy,
    *,
    repair: bool = True,
) -> MutationPatch:
    root = Path(checkout).resolve()
    notes: list[str] = []
    changed = working_tree_changed_paths(root, parent_ref)
    violations = check_paths(changed, surface.include, surface.exclude)
    if violations and repair:
        repaired = _repair_surface_violations(root, parent_ref, violations)
        if repaired:
            notes.append("repaired surface violations by " + "; ".join(repaired))
        changed = working_tree_changed_paths(root, parent_ref)
        violations = check_paths(changed, surface.include, surface.exclude)
    diff = git(root, "diff", "--binary", parent_ref, "--").stdout
    surface_report = {"ok": not violations, "mutated": changed, "violations": violations}
    return MutationPatch(changed_paths=changed, diff=diff, surface_report=surface_report, notes=notes)


def _repair_surface_violations(root: Path, parent_ref: str, violations: list[str]) -> list[str]:
    reverted: list[str] = []
    removed: list[str] = []
    for path in violations:
        action = _repair_surface_path(root, parent_ref, path)
        if action == "reverted":
            reverted.append(path)
        elif action == "removed":
            removed.append(path)
    notes: list[str] = []
    if reverted:
        notes.append("reverted: " + ", ".join(reverted))
    if removed:
        notes.append("removed untracked: " + ", ".join(removed))
    return notes


def _repair_surface_path(root: Path, parent_ref: str, path: str) -> str | None:
    rel = Path(path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return None
    candidate = root / rel
    status = git(root, "status", "--porcelain", "--", path, check=False)
    if status.stdout.startswith("??"):
        if candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)
        elif candidate.exists():
            candidate.unlink()
        return "removed"
    result = git(root, "checkout", parent_ref, "--", path, check=False)
    if result.returncode == 0:
        return "reverted"
    return None
```

- [ ] **Step 4: Run patch-builder tests to verify pass**

Run: `uv run pytest tests/test_mutation_patch.py -q`

Expected: PASS, all three tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/evolve/mutation.py tests/test_mutation_patch.py
git commit -m "Add mutation patch builder"
```

### Task 3: Thin `agent_command` Mutate Operator

**Files:**
- Modify: `library/mutate/agent_command.py`
- Test: `tests/test_agent_command_mutate.py`

**Interfaces:**
- Consumes: `run_meta_agent`, `create_mutation_patch`, `mutation_parent_ref`, and `load_surface_policy`.
- Produces: `AgentCommandMutate.mutate()` with a small four-step body: build prompt, run meta-agent, create patch, write result.

- [ ] **Step 1: Write failing mutator behavior tests**

Create `tests/test_agent_command_mutate.py`:

```python
import json
import random
import subprocess
import sys
from pathlib import Path

from evolve.frozen.interfaces import OperatorContext
from library.mutate.agent_command import AgentCommandMutate


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    (checkout / "target").mkdir(parents=True)
    (checkout / "operators").mkdir()
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "operators" / "mutate.md").write_text("# Mutate\n\nImprove the target.\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  mutate: {timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n  agent: target.harbor_agent:MiniSweSourceAgent\n"
    )
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    return checkout, run_dir


def _ctx(checkout: Path, run_dir: Path, command: str) -> OperatorContext:
    return OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={"command": command, "timeout_s": 30},
        rng=random.Random(0),
    )


def test_agent_command_mutate_runs_meta_agent_and_writes_artifacts(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    script = tmp_path / "agent.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('target/agent.py').write_text(\"print('child')\\n\")\n"
        "print('predicted_fixes: [\"task-1\"]')\n"
    )

    result = AgentCommandMutate().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))

    assert result.changed == ["target/agent.py"]
    assert json.loads((run_dir / "mutate" / "changed.json").read_text()) == ["target/agent.py"]
    assert json.loads((run_dir / "mutate" / "predicted_fixes.json").read_text()) == ["task-1"]
    assert json.loads((run_dir / "mutate" / "surface-check.json").read_text())["ok"] is True
    assert json.loads((run_dir / "mutate" / "usage.json").read_text())["usd"] == 0
    rationale = (run_dir / "mutate" / "rationale.md").read_text()
    assert "written-by: operators/mutate.py" in rationale
    assert "variant: agent_command" in rationale


def test_agent_command_mutate_exits_nonzero_after_writing_failure_artifacts(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    script = tmp_path / "agent.py"
    script.write_text("import sys\nprint('bad')\nsys.exit(7)\n")

    try:
        AgentCommandMutate().mutate(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {script}"))
    except SystemExit as exc:
        assert exc.code == 7
    else:
        raise AssertionError("expected SystemExit")

    assert json.loads((run_dir / "mutate" / "changed.json").read_text()) == []
    assert "error:" in (run_dir / "mutate" / "rationale.md").read_text()
```

- [ ] **Step 2: Run mutator tests to verify expected failure**

Run: `uv run pytest tests/test_agent_command_mutate.py -q`

Expected: The first test fails because the current mutator returns `changed=[]` after running the agent, even when the checkout changed.

- [ ] **Step 3: Refactor `library/mutate/agent_command.py`**

Replace the runner and surface code in `library/mutate/agent_command.py` with a small adapter:

```python
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.agent import AgentCommandError, AgentRunResult, run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.mutation import MutationPatch, create_mutation_patch, load_surface_policy, mutation_parent_ref


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _safe_usage(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"usd": 0}
    normalized = dict(usage)
    usd = normalized.get("usd", 0)
    normalized["usd"] = usd if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0
    return normalized


def _predicted_fixes(text: str) -> list[Any]:
    for line in text.splitlines():
        if line.strip().startswith("predicted_fixes:"):
            try:
                value = json.loads(line.split(":", 1)[1].strip())
            except Exception:
                return []
            return value if isinstance(value, list) else []
    return []


def _feedback_text(run_dir: Path) -> str:
    root = (run_dir / "feedback").resolve()
    index = root / "index.md"
    seen: set[Path] = set()
    parts: list[tuple[str, str]] = []
    if index.exists():
        text = index.read_text()
        parts.append(("feedback/index.md", text))
        seen.add(index.resolve())
        for rel in re.findall(r"\[[^\]]+\]\(([^)#]+)", text):
            path = (root / rel.strip()).resolve()
            if path.is_file() and (path == root or root in path.parents) and path not in seen:
                parts.append((f"feedback/{path.relative_to(root).as_posix()}", path.read_text()))
                seen.add(path)
    rules = root / "rules.md"
    if rules.exists() and rules.resolve() not in seen:
        parts.append(("feedback/rules.md", rules.read_text()))
    return "\n".join("## %s\n%s" % (name, text.rstrip()) for name, text in parts if text.strip())


def _surface_rules(checkout: Path) -> str:
    surface = load_surface_policy(checkout)
    return "- Surface include: %s\n- Surface exclude: %s" % (surface.include, surface.exclude)


def build_mutation_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    feedback = _feedback_text(ctx.run_dir) or observation.strip()
    return (
        "\n\n".join(
            chunk
            for chunk in [
                (checkout / "operators" / "mutate.md").read_text().rstrip(),
                feedback,
                "# Surface Rules\n\n%s" % _surface_rules(checkout),
                '# Output Contract\n\nEdit the checkout directly. Do not output patches, diffs, or fenced file blocks. Optional final line: predicted_fixes: ["task-id"].',
            ]
            if chunk
        )
        + "\n"
    )


def _write_mutation_result(
    run_dir: Path,
    agent_run: AgentRunResult | None,
    patch: MutationPatch,
    notes: list[str],
    *,
    output: str = "",
    usage: dict[str, Any] | None = None,
) -> MutateResult:
    mutate_dir = run_dir / "mutate"
    mutate_dir.mkdir(parents=True, exist_ok=True)
    combined_output = output or (agent_run.output if agent_run else "")
    all_notes = [*notes, *patch.notes, "written-by: operators/mutate.py", "variant: agent_command"]
    if combined_output.strip():
        all_notes.append("agent-output: %s" % combined_output.strip().splitlines()[0])
    usage_payload = _safe_usage(usage or (agent_run.usage if agent_run else {"usd": 0}))
    _write_json(mutate_dir / "changed.json", patch.changed_paths)
    _write_json(mutate_dir / "surface-check.json", patch.surface_report)
    (mutate_dir / "rationale.md").write_text("\n".join(all_notes) + "\n")
    (mutate_dir / "predicted_fixes.json").write_text(json.dumps(_predicted_fixes(combined_output)) + "\n")
    _write_json(mutate_dir / "usage.json", usage_payload)
    return MutateResult(changed=patch.changed_paths, notes=all_notes, usage=usage_payload)


class AgentCommandMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        prompt = build_mutation_prompt(checkout, observation, ctx)
        try:
            agent_run = run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
            patch = create_mutation_patch(
                checkout=checkout,
                parent_ref=mutation_parent_ref(checkout, ctx),
                surface=load_surface_policy(checkout),
            )
            result = _write_mutation_result(ctx.run_dir, agent_run, patch, [])
        except AgentCommandError as exc:
            patch = create_mutation_patch(
                checkout=checkout,
                parent_ref=mutation_parent_ref(checkout, ctx),
                surface=load_surface_policy(checkout),
            )
            _write_mutation_result(
                ctx.run_dir,
                None,
                patch,
                ["error: %s" % exc],
                output=exc.output,
                usage=exc.usage,
            )
            raise SystemExit(exc.returncode)
        if not result.changed:
            return result
        if not (ctx.run_dir / "mutate" / "surface-check.json").exists():
            raise SystemExit(1)
        return result


if __name__ == "__main__":
    sdk.main(AgentCommandMutate)
```

After green tests, add one small refinement: if `patch.surface_report["ok"]` is false, return artifacts and raise `SystemExit(1)`.

- [ ] **Step 4: Run mutator tests and focused operator tests**

Run: `uv run pytest tests/test_agent_command_mutate.py tests/test_m5_operator_runner.py tests/test_m5_driver_operators.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add library/mutate/agent_command.py tests/test_agent_command_mutate.py
git commit -m "Refactor agent command mutator"
```

### Task 4: Explicit Harbor Agent Configuration

**Files:**
- Modify: `src/evolve/workspace.py`
- Modify: `templates/evaluator/engines/harbor.sh` only if tests expose missing diagnostics.
- Test: `tests/test_harbor_evaluator_config.py`
- Test: `tests/test_m0_init.py`

**Interfaces:**
- Consumes: `evaluator.agent` from recipe config.
- Produces: `evaluator/eval.env` with `EVOLVE_HARBOR_AGENT=<configured import path>` and no default `CheckoutTargetAgent` dependency in new workspaces.

- [ ] **Step 1: Write failing Harbor config tests**

Create `tests/test_harbor_evaluator_config.py`:

```python
from pathlib import Path

import pytest

from evolve.workspace import _eval_env, init_workspace, InitOptions


def test_eval_env_uses_configured_harbor_agent() -> None:
    env = _eval_env(
        "exp",
        "swe-bench-lite",
        n_concurrent=2,
        tasks_per_round=3,
        trials=1,
        partial_floor=0.8,
        agent="target.harbor_agent:MiniSweSourceAgent",
    )

    assert "EVOLVE_HARBOR_AGENT=target.harbor_agent:MiniSweSourceAgent\n" in env
    assert "CheckoutTargetAgent" not in env


def test_init_real_harbor_recipe_requires_evaluator_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evolve import workspace as workspace_module

    config = {
        "experiment": {"id": "broken"},
        "target": {"seed": "builtin-dummy"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": {
            "select": {"variant": "greedy"},
            "rollout": {"variant": "noop"},
            "mutate": {"variant": "noop"},
            "gate": {"variant": "parent_eligible"},
            "record": {"variant": "jsonl"},
        },
        "evaluator": {"engine": "harbor", "dataset": "swe-bench-lite"},
    }
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    with pytest.raises(ValueError, match="evaluator.agent is required"):
        init_workspace(InitOptions(workspace=tmp_path / "w", recipe="broken"))
```

- [ ] **Step 2: Run Harbor config tests to verify failure**

Run: `uv run pytest tests/test_harbor_evaluator_config.py -q`

Expected: FAIL because `_eval_env` has no `agent` parameter and writes `CheckoutTargetAgent`.

- [ ] **Step 3: Implement explicit `evaluator.agent`**

Modify `src/evolve/workspace.py`:

```python
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
        "README.md": _template("workspace/README.md"),
        "AGENTS.md": _template("workspace/AGENTS.md"),
        "program.md": _template("workspace/program.md"),
        ".gitignore": _template("workspace/.gitignore"),
        ".evolve-protocol-version": "1\n",
        "operators/engines/local.sh": _shell_script("operator local engine"),
        "operators/preflight.sh": _shell_script("operator preflight"),
        "operators/select.md": _template("workspace/operators/select.md"),
        "operators/rollout.md": _template("workspace/operators/rollout.md"),
        "operators/mutate.md": _template("workspace/operators/mutate.md"),
        "operators/gate.md": _template("workspace/operators/gate.md"),
        "operators/record.md": _template("workspace/operators/record.md"),
        "operators/mutation_brief.md": _template("workspace/operators/mutation_brief.md"),
        "skills/evolve-workspace/SKILL.md": _skill("evolve-workspace/SKILL.md"),
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
```

Modify `_eval_env`:

```python
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
```

Update `tests/test_m0_init.py` expected paths by removing `evaluator/checkout_agent.py` from new workspace expectations.

- [ ] **Step 4: Run Harbor config and init tests**

Run: `uv run pytest tests/test_harbor_evaluator_config.py tests/test_m0_init.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/evolve/workspace.py tests/test_harbor_evaluator_config.py tests/test_m0_init.py
git commit -m "Require explicit Harbor agent config"
```

### Task 5: MiniSWE Source Harbor Wrapper

**Files:**
- Create: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `src/evolve/workspace.py`
- Test: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: recipe `target.harbor_agent: miniswe-source`.
- Produces: `target/harbor_agent.py` containing `MiniSweSourceAgent(MiniSweAgent)` that uploads and installs candidate source.

- [ ] **Step 1: Write failing wrapper tests**

Create `tests/test_miniswe_harbor_wrapper.py`:

```python
import asyncio
import importlib.util
import sys
import types
from pathlib import Path


def _install_fake_harbor(monkeypatch):
    root = types.ModuleType("harbor")
    agents = types.ModuleType("harbor.agents")
    installed = types.ModuleType("harbor.agents.installed")
    mini = types.ModuleType("harbor.agents.installed.mini_swe_agent")

    class MiniSweAgent:
        async def exec_as_agent(self, environment, command: str):
            environment.commands.append(command)

    mini.MiniSweAgent = MiniSweAgent
    monkeypatch.setitem(sys.modules, "harbor", root)
    monkeypatch.setitem(sys.modules, "harbor.agents", agents)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed", installed)
    monkeypatch.setitem(sys.modules, "harbor.agents.installed.mini_swe_agent", mini)
    return MiniSweAgent


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("target.harbor_agent", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_miniswe_wrapper_subclasses_harbor_miniswe_and_installs_candidate_source(tmp_path: Path, monkeypatch) -> None:
    base = _install_fake_harbor(monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    wrapper = target / "harbor_agent.py"
    wrapper.write_text(Path("templates/target/harbor/miniswe_source_agent.py").read_text())
    module = _load(wrapper)

    class Environment:
        def __init__(self) -> None:
            self.uploads = []
            self.commands = []

        async def upload_dir(self, source_dir, target_dir):
            self.uploads.append((Path(source_dir), target_dir))

    environment = Environment()
    agent = module.MiniSweSourceAgent()
    asyncio.run(agent.install(environment))

    assert issubclass(module.MiniSweSourceAgent, base)
    assert environment.uploads == [(target.resolve(), "/installed-agent/miniswe-source")]
    assert "uv tool install --force /installed-agent/miniswe-source" in environment.commands
    assert any("mini-swe-agent" in command for command in environment.commands)


def test_init_with_local_miniswe_seed_writes_target_harbor_wrapper(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module
    from evolve.workspace import InitOptions, init_workspace

    seed = tmp_path / "miniswe"
    (seed / "mini_swe_agent").mkdir(parents=True)
    (seed / "mini_swe_agent" / "__init__.py").write_text("__version__ = '0.test'\n")
    (seed / "pyproject.toml").write_text("[project]\nname = 'mini-swe-agent'\nversion = '0.test'\n")
    workspace = tmp_path / "workspace"
    config = workspace_module.default_config("hill_climb", workspace.name)
    config["target"]["harbor_agent"] = "miniswe-source"
    config["evaluator"]["agent"] = "target.harbor_agent:MiniSweSourceAgent"
    monkeypatch.setattr(workspace_module, "default_config", lambda recipe, experiment_id: config)

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    wrapper = workspace / "target" / "harbor_agent.py"
    assert wrapper.exists()
    assert "class MiniSweSourceAgent(MiniSweAgent):" in wrapper.read_text()
```

- [ ] **Step 2: Run wrapper tests to verify failure**

Run: `uv run pytest tests/test_miniswe_harbor_wrapper.py -q`

Expected: FAIL because the template and `target.harbor_agent` overlay do not exist.

- [ ] **Step 3: Add MiniSWE wrapper template**

Create `templates/target/harbor/miniswe_source_agent.py`:

```python
from __future__ import annotations

from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent


class MiniSweSourceAgent(MiniSweAgent):
    async def install(self, environment):
        source_dir = Path(__file__).resolve().parent
        if not (source_dir / "pyproject.toml").is_file():
            raise RuntimeError("MiniSWE source target must contain target/pyproject.toml")
        if not (source_dir / "mini_swe_agent").is_dir():
            raise RuntimeError("MiniSWE source target must contain target/mini_swe_agent/")
        await environment.upload_dir(source_dir, "/installed-agent/miniswe-source")
        await self.exec_as_agent(
            environment,
            command="uv tool install --force /installed-agent/miniswe-source",
        )
        await self.exec_as_agent(
            environment,
            command=(
                "python -c \"import shutil, sys; "
                "exe = shutil.which('mini-swe-agent'); "
                "print(exe or 'missing mini-swe-agent'); "
                "sys.exit(0 if exe else 1)\""
            ),
        )
```

- [ ] **Step 4: Add target adapter overlay during init**

Modify `src/evolve/workspace.py`:

```python
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

    _write_files(workspace, config, recipe=options.recipe, init_cwd=Path.cwd())
    _write_target(workspace, target)
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
```

Replace `_write_target(workspace: Path, seed: str | None)` with:

```python
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
```

- [ ] **Step 5: Run wrapper tests**

Run: `uv run pytest tests/test_miniswe_harbor_wrapper.py tests/test_m0_init.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/evolve/workspace.py templates/target/harbor/miniswe_source_agent.py tests/test_miniswe_harbor_wrapper.py tests/test_m0_init.py
git commit -m "Add MiniSWE Harbor source wrapper"
```

### Task 6: Real and Smoke Recipes

**Files:**
- Create: `recipes/hill_climb-smoke/*`, `recipes/dgm-smoke/*`, `recipes/ahe-smoke/*`, `recipes/autoresearch-smoke/*`, `recipes/hyperagents-smoke/*`, `recipes/metaagent-smoke/*`
- Modify: `recipes/*/evolve.yaml`
- Modify: `recipes/*/README.md`
- Modify: `recipes/README.md`
- Modify: `tests/conftest.py`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: tests that call `init_workspace` through conftest only if expectations mention `hill_climb`.

**Interfaces:**
- Consumes: existing recipe names and operator variants.
- Produces: real recipes using Harbor plus `agent_command`, and smoke recipes using deterministic operators under explicit smoke names.

- [ ] **Step 1: Write failing recipe policy tests**

Replace `tests/test_phase_e_recipes.py` with:

```python
from pathlib import Path

from evolve.config import RECIPE_NAMES

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
REAL_RECIPES = {"hill_climb", "dgm", "ahe", "autoresearch", "hyperagents", "metaagent"}
SMOKE_RECIPES = {f"{name}-smoke" for name in REAL_RECIPES}


def _config(name: str) -> str:
    return (RECIPES / name / "evolve.yaml").read_text()


def test_all_recipes_are_recipe_artifacts_only() -> None:
    recipe_names = tuple(path.name for path in sorted(RECIPES.iterdir()) if path.is_dir())
    assert set(recipe_names) == set(RECIPE_NAMES)
    assert set(RECIPE_NAMES) == REAL_RECIPES | SMOKE_RECIPES
    for name in RECIPE_NAMES:
        recipe = RECIPES / name
        assert (recipe / "README.md").is_file()
        assert (recipe / "evolve.yaml").is_file()
        assert {path.name for path in recipe.iterdir()} <= {"README.md", "evolve.yaml", "notes.md"}
        config = _config(name)
        for section in ("experiment:", "target:", "surface:", "operators:", "evaluator:"):
            assert section in config


def test_real_recipes_use_harbor_and_real_agent_mutation() -> None:
    for name in REAL_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "mutate: {variant: agent_command" in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "harbor_agent: miniswe-source" in config
        assert "variant: fixed" not in config
        assert "variant: noop" not in config
        assert "engine: docker-report" not in config
        assert "engine: reflection" not in config
        assert "engine: train-bpb" not in config


def test_smoke_recipes_are_explicitly_named_and_deterministic() -> None:
    for name in SMOKE_RECIPES:
        config = _config(name)
        assert "engine: harbor" in config
        assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
        assert "mutate: {variant: fixed" in config or "mutate: {variant: noop" in config
```

Modify `tests/conftest.py`:

```python
def init_workspace(tmp_path: Path, experiment: str = "experiment") -> tuple[Path, Path]:
    workspace = tmp_path / experiment
    evolve_home = tmp_path / "evolve-home"
    result = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "hill_climb-smoke",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 0, result.stderr
    return workspace, evolve_home
```

- [ ] **Step 2: Run recipe tests to verify failure**

Run: `uv run pytest tests/test_phase_e_recipes.py -q`

Expected: FAIL because smoke recipes do not exist and real recipes still use `fixed` or non-Harbor engines.

- [ ] **Step 3: Create smoke recipes from current deterministic recipes**

Create the six `*-smoke` directories by copying the current recipe files, then set each smoke recipe's `experiment.id` to the smoke name. Ensure all smoke recipes use:

```yaml
evaluator:
  engine: harbor
  dataset: pass@k
  agent: target.harbor_agent:MiniSweSourceAgent
```

Smoke recipes can keep deterministic `fixed` or `noop` mutation because tests will run them with `EVAL_STUB=1`.

- [ ] **Step 4: Convert real recipes to MiniSWE source plus live meta-agent mutation**

For each real recipe, set:

```yaml
target:
  seed: https://github.com/SWE-agent/mini-swe-agent.git
  harbor_agent: miniswe-source
operators:
  mutate: {variant: agent_command, timeout_s: 3600}
evaluator:
  engine: harbor
  dataset: swe-bench-lite
  agent: target.harbor_agent:MiniSweSourceAgent
```

Keep recipe-specific selection and gate behavior:

```yaml
# hill_climb
select: {variant: greedy}
gate: {variant: hillclimb}

# dgm
select: {variant: score_weighted, seed: 0}
gate: {variant: parent_eligible}
children_per_gen: 4

# ahe
select: {variant: greedy}
gate: {variant: parent_eligible}

# autoresearch
select: {variant: greedy}
gate: {variant: hillclimb}
mode: agent

# hyperagents
select: {variant: random, seed: 0}
gate: {variant: parent_eligible}
surface.include:
  - target/**
  - operators/**

# metaagent
select: {variant: newest}
gate: {variant: parent_eligible}
surface.include:
  - target/**
  - operators/*.md
```

- [ ] **Step 5: Run recipe and init tests**

Run: `uv run pytest tests/test_phase_e_recipes.py tests/test_m0_init.py tests/test_m5_driver_operators.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add recipes tests/conftest.py tests/test_phase_e_recipes.py tests/test_m0_init.py tests/test_m5_driver_operators.py
git commit -m "Split real and smoke recipes"
```

### Task 7: Real Meta-Eval and HyperAgents Semantics

**Files:**
- Modify: `src/evolve/frozen/meta_eval.py`
- Modify: `tests/test_m3_meta_eval.py`
- Add or modify: `tests/test_hyperagents_semantics.py`

**Interfaces:**
- Consumes: current driver ordering: rollout, mutate, meta-eval admission, novelty, commit, eval, gate, record.
- Produces: `meta_eval` that replays with the caller's evaluator environment and only uses stub when caller explicitly sets `EVAL_STUB=1`.

- [ ] **Step 1: Write failing meta-eval environment test**

Add to `tests/test_m3_meta_eval.py`:

```python
import json
import subprocess
import sys


def test_meta_eval_replay_does_not_inject_eval_stub(tmp_path: Path, monkeypatch) -> None:
    captured_env = {}

    def fake_sh(cmd, cwd, *, check=True, env=None, timeout=600):
        if cmd[:3] == [sys.executable, "-m", "evolve"]:
            captured_env.update(env or {})
            (cwd / "archive.jsonl").write_text(json.dumps({"score": 1.0}) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.delenv("EVAL_STUB", raising=False)
    monkeypatch.setattr(meta_eval, "_sh", fake_sh)

    score = meta_eval._replay(tmp_path, k=1, seed="s")

    assert score == 1.0
    assert "EVAL_STUB" not in captured_env
    assert captured_env["EVOLVE_HOME"] == str(tmp_path / ".meta-home")
```

Update `test_meta_eval_admits_noninferior_operator_edit` to set stub explicitly:

```python
def test_meta_eval_admits_noninferior_operator_edit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    workspace, _ = init_workspace(tmp_path)
    sel = workspace / "operators" / "select.py"
    sel.write_text(sel.read_text() + "\n# harmless comment\n")
    verdict = meta_eval.admit(workspace, "gen/0", workspace, k=2)
    assert verdict["admitted"] is True, verdict
    assert verdict["old_best"] == 1.0 and verdict["new_best"] == 1.0
```

- [ ] **Step 2: Run meta-eval test to verify failure**

Run: `uv run pytest tests/test_m3_meta_eval.py::test_meta_eval_replay_does_not_inject_eval_stub -q`

Expected: FAIL because `captured_env` contains `EVAL_STUB`.

- [ ] **Step 3: Remove forced stub from `meta_eval._replay`**

Modify `src/evolve/frozen/meta_eval.py`:

```python
def _replay(tree: Path, k: int, seed: str) -> float:
    """Fresh repo plus K micro-generations; return the best score."""
    git = ["git", "-c", "user.name=meta-eval", "-c", "user.email=meta@local"]
    _sh(["git", "init", "-q", "-b", "main"], tree)
    _sh(git + ["add", "-A"], tree)
    _sh(git + ["commit", "-qm", "replay-genesis"], tree)
    _sh(["git", "tag", "gen/0"], tree)
    _write_genesis(tree)
    result = _sh(
        [sys.executable, "-m", "evolve", "run", ".", "--max-generations", str(k)],
        tree,
        check=False,
        env={"EVOLVE_HOME": str(tree / ".meta-home"), "EVOLVE_SEED": str(seed)},
    )
    if result.returncode != 0:
        raise RuntimeError(f"replay run failed: {result.stderr.strip()[:300]}")
    scores = [
        float(row["score"])
        for line in (tree / "archive.jsonl").read_text().splitlines()
        if line.strip()
        for row in [json.loads(line)]
        if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
    ]
    if not scores:
        raise RuntimeError("replay produced an empty ledger")
    return max(scores)
```

- [ ] **Step 4: Add HyperAgents ordering test**

Create `tests/test_hyperagents_semantics.py`:

```python
from pathlib import Path

from conftest import git, init_workspace, rows_by_genid
from evolve.driver import RunOptions
from evolve.driver import run as driver_run


def test_hyperagents_mutate_change_affects_later_generation_not_current_one(tmp_path: Path, monkeypatch) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_HOME", str(evolve_home))
    evolve_yaml = (workspace / "evolve.yaml").read_text()
    (workspace / "evolve.yaml").write_text(
        evolve_yaml.replace("    - target/**\n  exclude: []", "    - target/**\n    - operators/**\n  exclude: []")
    )
    (workspace / "operators" / "mutate.py").write_text(
        "import os, sys\n"
        "sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]\n"
        "from evolve.frozen import sdk\n"
        "from evolve.frozen.interfaces import MutateOperator, MutateResult\n"
        "class M(MutateOperator):\n"
        "    def mutate(self, checkout, observation, ctx):\n"
        "        script = checkout / 'operators' / 'mutate.py'\n"
        "        script.write_text(script.read_text().replace('first-child', 'later-child'))\n"
        "        agent = checkout / 'target' / 'agent.py'\n"
        "        agent.write_text(agent.read_text() + '\\n# first-child\\n')\n"
        "        return MutateResult(changed=['operators/mutate.py', 'target/agent.py'], notes=['self changed'], usage={'usd': 0})\n"
        "if __name__ == '__main__':\n"
        "    sdk.main(M)\n"
    )
    git(workspace, "add", "-A")
    git(workspace, "commit", "-qm", "enable hyperagents test")
    git(workspace, "tag", "-f", "gen/0")

    driver_run(RunOptions(workspace=workspace, max_generations=2, children_per_gen=1))

    rows = rows_by_genid(workspace)
    assert "1" in rows
    assert "# first-child" in git(workspace, "show", "gen/1:target/agent.py")
    if "2" in rows:
        assert "# later-child" in git(workspace, "show", "gen/2:target/agent.py")
```

- [ ] **Step 5: Run meta-eval and HyperAgents tests**

Run: `uv run pytest tests/test_m3_meta_eval.py tests/test_hyperagents_semantics.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```bash
git add src/evolve/frozen/meta_eval.py tests/test_m3_meta_eval.py tests/test_hyperagents_semantics.py
git commit -m "Make meta-eval use real evaluator environment"
```

### Task 8: Documentation and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `DESIGN.md`
- Modify: `docs/glossary.md`
- Modify: `recipes/README.md`
- Modify: recipe README files as needed.

**Interfaces:**
- Consumes: completed behavior from Tasks 1 through 7.
- Produces: docs that say Harbor runs benchmarks, `target/harbor_agent.py` adapts MiniSWE source, `run_meta_agent` edits local workspaces, smoke recipes are explicit, and HyperAgents mutation workflow changes apply to later generations.

- [ ] **Step 1: Write doc coherence test**

Add to `tests/test_coherence.py`:

```python
def test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "DESIGN.md",
        ROOT / "docs" / "glossary.md",
        ROOT / "recipes" / "README.md",
    ]
    text = "\n".join(path.read_text() for path in docs if path.exists())
    assert "solve.sh" not in text
    assert "run.sh" not in text
    assert "CheckoutTargetAgent" not in text
    assert "hyperagents-smoke" in text
    assert "target.harbor_agent:MiniSweSourceAgent" in text
```

- [ ] **Step 2: Run doc coherence test to verify failure**

Run: `uv run pytest tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback -q`

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update docs**

Update docs with these exact statements:

```markdown
Harbor is the only real benchmark execution path. Real recipes call Harbor with
an explicit `evaluator.agent` value. Smoke recipes are named `*-smoke` and are
the only recipes intended for deterministic `EVAL_STUB=1` mechanism tests.
```

```markdown
For MiniSWE source evolution, `target/` is the MiniSWE source checkout plus
`target/harbor_agent.py`. Harbor imports
`target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into the
task container, installs that source, and then reuses Harbor's MiniSWE run
behavior.
```

```markdown
`run_meta_agent(workspace, prompt, config)` is the local mutation-agent runner.
It receives a checkout and prompt, then runs the configured command in that
checkout. It does not know about generation IDs, archive rows, Harbor, or
surface policy.
```

```markdown
HyperAgents can evolve `operators/**`. A changed `operators/mutate.py` affects
later children forked from the accepted generation; changed gate or record code
can affect the same generation because those operators run after mutation.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
git diff --check
```

Expected: all commands pass.

- [ ] **Step 5: Commit Task 8**

```bash
git add README.md DESIGN.md docs/glossary.md recipes/README.md recipes/*/README.md tests/test_coherence.py
git commit -m "Document Harbor real recipes"
```

## Self-Review Checklist

- Spec coverage: Tasks 1 and 3 cover the simple meta-agent runner and thin `MutateOperator`; Task 2 covers patch creation and surface repair; Tasks 4 and 5 cover Harbor explicit agents and MiniSWE source wrapper; Task 6 covers real versus smoke recipes; Task 7 covers real meta-eval and HyperAgents semantics; Task 8 covers docs.
- Placeholder scan: the plan avoids deferred placeholders and names every file, interface, command, and expected failure.
- Type consistency: `AgentRunResult`, `AgentCommandError`, `SurfacePolicy`, and `MutationPatch` are defined once in the shared interfaces and reused by later tasks.
- TDD cycle: each task starts with failing tests, verifies red, implements the minimal behavior, verifies green, and commits.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-harbor-agent-runner-real-recipes.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
