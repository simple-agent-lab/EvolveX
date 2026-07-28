# Single-Folder Recovery and Evolutionary Branching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an interrupted experiment recover safely from its existing folder and allow the next unused generation to branch from any certified prior parent.

**Architecture:** Keep the experiment folder authoritative. Add a small atomic branch-intent file for forced-parent persistence, reconstruct the one existing Git-tag/archive crash window from Git evidence, and reuse the current evaluation-attempt and pending-gate mechanisms. Do not add folder snapshots, backup management, destructive history truncation, or a general phase state machine.

**Tech Stack:** Python 3.11+, Typer, Git CLI, JSONL archive/receipt files, pytest, Ruff.

## Global Constraints

- Preserve every completed generation tag, archive event, receipt, and artifact during recovery.
- Treat in-flight work before candidate tagging as disposable.
- Never rerun selection for a candidate that already has a `gen/<id>` tag.
- Refuse Git/archive contradictions instead of guessing.
- Branching is non-destructive and never reuses a generation id.
- Hold the existing workspace lock for all recovery and branching mutations.
- Do not add checkpoint, snapshot, recover, backup-retention, or remote-storage commands.
- Preserve unrelated pre-existing worktree changes; stage and commit only files listed by the current task.

---

## File Structure

- Create `src/evolve/branching.py`: branch-intent schema, validation, atomic persistence, and idempotent removal.
- Modify `src/evolve/git.py`: read generation tags and direct commit parents without embedding Git parsing in the driver.
- Modify `src/evolve/driver.py`: automatic interrupted-state recovery, tagged-lineage reconstruction, forced-parent selection, and intent consumption.
- Modify `src/evolve/cli.py`: expose `--from-generation`.
- Create `tests/test_branch_intent.py`: focused persistence and schema tests.
- Create `tests/test_branching.py`: CLI/driver forced-parent and restart tests.
- Create `tests/test_run_recovery.py`: crash-boundary recovery tests.
- Modify `tests/test_m0_run_resume.py`: CLI option plumbing assertion.
- Modify `README.md`: document default resume and non-destructive branching.

---

### Task 1: Atomic Branch-Intent Persistence

**Files:**
- Create: `src/evolve/branching.py`
- Create: `tests/test_branch_intent.py`

**Interfaces:**
- Consumes: only `pathlib`, `dataclasses`, `json`, and `os`.
- Produces:
  - `BranchIntent(source_generation: str, source_tag: str, source_commit: str, target_generation: int, target_genids: tuple[str, ...], created_at: str)`
  - `branch_intent_path(workspace: Path) -> Path`
  - `load_branch_intent(workspace: Path) -> BranchIntent | None`
  - `create_branch_intent(workspace: Path, intent: BranchIntent) -> BranchIntent`
  - `consume_branch_intent(workspace: Path, intent: BranchIntent) -> None`

- [ ] **Step 1: Write failing round-trip, conflict, validation, and idempotent-consume tests**

```python
# tests/test_branch_intent.py
from pathlib import Path

import pytest

from evolve.branching import (
    BranchIntent,
    branch_intent_path,
    consume_branch_intent,
    create_branch_intent,
    load_branch_intent,
)


def intent() -> BranchIntent:
    return BranchIntent(
        source_generation="4",
        source_tag="gen/4",
        source_commit="a" * 40,
        target_generation=11,
        target_genids=("11-0", "11-1"),
        created_at="2026-07-28T00:00:00+00:00",
    )


def test_branch_intent_round_trips_and_matching_create_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    first = create_branch_intent(workspace, intent())
    second = create_branch_intent(workspace, intent())

    assert first == second == intent()
    assert load_branch_intent(workspace) == intent()


def test_branch_intent_refuses_conflicting_existing_intent(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    create_branch_intent(workspace, intent())
    conflicting = BranchIntent(**{**intent().__dict__, "source_generation": "3", "source_tag": "gen/3"})

    with pytest.raises(RuntimeError, match="conflicting branch intent"):
        create_branch_intent(workspace, conflicting)


def test_load_branch_intent_rejects_invalid_schema(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    path = branch_intent_path(workspace)
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 2}\n')

    with pytest.raises(RuntimeError, match="unsupported branch intent schema"):
        load_branch_intent(workspace)


def test_consume_branch_intent_is_idempotent_but_refuses_replacement(tmp_path: Path) -> None:
    workspace = tmp_path / "experiment"
    current = create_branch_intent(workspace, intent())
    consume_branch_intent(workspace, current)
    consume_branch_intent(workspace, current)
    assert load_branch_intent(workspace) is None
```

- [ ] **Step 2: Run the focused tests and verify the module is missing**

Run:

```bash
uv run pytest tests/test_branch_intent.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'evolve.branching'`.

- [ ] **Step 3: Implement the immutable schema and atomic file operations**

```python
# src/evolve/branching.py
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BranchIntent:
    source_generation: str
    source_tag: str
    source_commit: str
    target_generation: int
    target_genids: tuple[str, ...]
    created_at: str


def branch_intent_path(workspace: Path) -> Path:
    return workspace.resolve() / "runs" / "branch-intent.json"


def load_branch_intent(workspace: Path) -> BranchIntent | None:
    path = branch_intent_path(workspace)
    if not path.exists():
        return None
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid branch intent {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported branch intent schema in {path}")
    required = {
        "source_generation": str,
        "source_tag": str,
        "source_commit": str,
        "target_generation": int,
        "target_genids": list,
        "created_at": str,
    }
    for field, expected in required.items():
        if not isinstance(raw.get(field), expected):
            raise RuntimeError(f"invalid branch intent field {field} in {path}")
    if raw["target_generation"] < 1 or not raw["target_genids"]:
        raise RuntimeError(f"invalid branch intent target in {path}")
    return BranchIntent(
        source_generation=raw["source_generation"],
        source_tag=raw["source_tag"],
        source_commit=raw["source_commit"],
        target_generation=raw["target_generation"],
        target_genids=tuple(str(value) for value in raw["target_genids"]),
        created_at=raw["created_at"],
    )


def create_branch_intent(workspace: Path, intent: BranchIntent) -> BranchIntent:
    existing = load_branch_intent(workspace)
    if existing is not None:
        if existing == intent:
            return existing
        raise RuntimeError(
            f"conflicting branch intent: active gen/{existing.source_generation}, "
            f"requested gen/{intent.source_generation}"
        )
    payload = {"schema_version": SCHEMA_VERSION, **asdict(intent), "target_genids": list(intent.target_genids)}
    _atomic_write(branch_intent_path(workspace), payload)
    return intent


def consume_branch_intent(workspace: Path, intent: BranchIntent) -> None:
    path = branch_intent_path(workspace)
    existing = load_branch_intent(workspace)
    if existing is None:
        return
    if existing != intent:
        raise RuntimeError("branch intent changed before it could be consumed")
    path.unlink()


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
```

- [ ] **Step 4: Run the focused tests and Ruff**

Run:

```bash
uv run pytest tests/test_branch_intent.py -q
uv run ruff check src/evolve/branching.py tests/test_branch_intent.py
uv run ruff format --check src/evolve/branching.py tests/test_branch_intent.py
```

Expected: all commands pass.

- [ ] **Step 5: Commit only the branch-intent unit**

```bash
git add src/evolve/branching.py tests/test_branch_intent.py
git commit -m "feat: persist evolutionary branch intent"
```

---

### Task 2: Forced-Parent Branching in the Driver and CLI

**Files:**
- Modify: `src/evolve/git.py:42-60`
- Modify: `src/evolve/driver.py:84-177`
- Modify: `src/evolve/cli.py:88-103`
- Create: `tests/test_branching.py`
- Modify: `tests/test_m0_run_resume.py:51-78`

**Interfaces:**
- Consumes: `BranchIntent`, `create_branch_intent`, `load_branch_intent`, and `consume_branch_intent` from Task 1.
- Produces:
  - `generation_tags(workspace: Path) -> list[str]`
  - `RunOptions.from_generation: str | None`
  - CLI option `--from-generation GENID`
  - `_prepare_branch_intent(options: RunOptions, workspace: Path) -> BranchIntent | None`
  - `_branch_parents(intent: BranchIntent | None, generation: int, pending: list[str]) -> dict[str, str] | None`
  - `_consume_completed_branch_intent(workspace: Path, intent: BranchIntent | None) -> None`

- [ ] **Step 1: Add failing CLI plumbing and single-child branch tests**

```python
# Add to tests/test_m0_run_resume.py
def test_run_passes_from_generation_to_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured = {}

    def fake_run(options) -> None:
        captured["from_generation"] = options.from_generation

    monkeypatch.setattr(cli, "driver_run", fake_run)
    cli.run(workspace, max_generations=11, from_generation="4")

    assert captured["from_generation"] == "4"
```

```python
# tests/test_branching.py
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, run_evolve, smoke_agent_command

from evolve import driver
from evolve.branching import load_branch_intent
from evolve.driver import RunOptions, commit_child, fork_child, run


@pytest.fixture(autouse=True)
def smoke_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())


def test_run_branches_next_generation_from_certified_prior_parent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run", str(workspace), "--max-generations", "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    branched = run_evolve(
        "run", str(workspace), "--max-generations", "3", "--from-generation", "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert branched.returncode == 0, branched.stderr
    assert rows_by_genid(workspace)["3"]["parent"] == "0"
    assert rows_by_genid(workspace)["2"]["parent"] == "1"
    assert load_branch_intent(workspace) is None


def test_branch_refuses_non_certified_parent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    result = run_evolve(
        "run", str(workspace), "--max-generations", "1", "--from-generation", "99",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert result.returncode == 1
    assert "unknown parent: 99" in result.stderr
```

- [ ] **Step 2: Run the tests and verify the option and field are absent**

Run:

```bash
uv run pytest tests/test_m0_run_resume.py::test_run_passes_from_generation_to_driver tests/test_branching.py -q
```

Expected: failures identify the missing `from_generation` CLI argument and `RunOptions` field.

- [ ] **Step 3: Add generation-tag enumeration and CLI plumbing**

```python
# src/evolve/git.py
def generation_tags(workspace: Path) -> list[str]:
    output = git_stdout(workspace, "for-each-ref", "--format=%(refname:strip=2)", "refs/tags/gen/")
    return sorted(line for line in output.splitlines() if line.startswith("gen/"))
```

```python
# src/evolve/driver.py
@dataclass(frozen=True)
class RunOptions:
    workspace: Path
    max_generations: int
    children_per_gen: int = 1
    from_generation: str | None = None
```

```python
# src/evolve/cli.py
def run(
    workspace: Path,
    max_generations: int | None = typer.Option(None, "--max-generations"),
    children_per_gen: int | None = typer.Option(None, "--children-per-gen"),
    resume: bool = typer.Option(False, "--resume", help="accepted no-op; resume is the default"),
    from_generation: str | None = typer.Option(
        None,
        "--from-generation",
        help="force the next unused generation to branch from this certified parent",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="stream evaluator and operator output"),
) -> None:
    # Keep existing gens/children/environment behavior.
    driver_run(
        RunOptions(
            workspace=workspace,
            max_generations=gens,
            children_per_gen=children,
            from_generation=from_generation,
        )
    )
```

- [ ] **Step 4: Implement durable branch preparation and forced selection**

Add these helpers to `src/evolve/driver.py` and call `_prepare_branch_intent`
after genesis evaluation but before entering the generation loop:

```python
def _next_generation_number(workspace: Path) -> int:
    numbers = [
        generation_number(str(row.get("genid", "")))
        for row in rows_by_genid(workspace).values()
    ]
    numbers.extend(
        generation_number(tag.removeprefix("gen/"))
        for tag in generation_tags(workspace)
    )
    return max((value for value in numbers if value is not None), default=0) + 1


def _prepare_branch_intent(options: RunOptions, workspace: Path) -> BranchIntent | None:
    existing = load_branch_intent(workspace)
    if options.from_generation is None:
        if existing is not None:
            _validate_active_branch_intent(workspace, existing, options.children_per_gen)
            print(
                f"[evolve] branch intent resumed: gen/{existing.source_generation} "
                f"-> generation {existing.target_generation}",
                flush=True,
            )
        return existing
    source = _validate_genid(options.from_generation)
    _assert_valid_parent(workspace, source)
    unfinished = _durable_unfinished_genids(workspace)
    if unfinished:
        raise RuntimeError(
            "cannot create branch while generations need recovery: "
            + ", ".join(f"gen/{value}" for value in unfinished)
        )
    source_commit = git_stdout(workspace, "rev-parse", f"gen/{source}^{{commit}}")
    target_generation = _next_generation_number(workspace)
    if options.max_generations < target_generation:
        raise RuntimeError(
            f"--max-generations must be at least {target_generation} "
            f"to branch from gen/{source}"
        )
    target_genids = tuple(
        format_genid(target_generation, index, options.children_per_gen)
        for index in range(options.children_per_gen)
    )
    requested = BranchIntent(
        source_generation=source,
        source_tag=f"gen/{source}",
        source_commit=source_commit,
        target_generation=target_generation,
        target_genids=target_genids,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    if existing is not None:
        same_request = (
            existing.source_generation == requested.source_generation
            and existing.source_commit == requested.source_commit
            and existing.target_generation == requested.target_generation
            and existing.target_genids == requested.target_genids
        )
        if not same_request:
            raise RuntimeError(
                f"conflicting branch intent: active gen/{existing.source_generation}, "
                f"requested gen/{source}"
            )
        _validate_active_branch_intent(workspace, existing, options.children_per_gen)
        print(
            f"[evolve] branch intent resumed: gen/{existing.source_generation} "
            f"-> generation {existing.target_generation}",
            flush=True,
        )
        return existing
    created = create_branch_intent(workspace, requested)
    print(
        f"[evolve] branch intent created: gen/{source} -> generation {target_generation}",
        flush=True,
    )
    return created


def _validate_active_branch_intent(
    workspace: Path,
    intent: BranchIntent,
    children_per_gen: int,
) -> None:
    _assert_valid_parent(workspace, intent.source_generation)
    actual_commit = git_stdout(
        workspace,
        "rev-parse",
        f"gen/{intent.source_generation}^{{commit}}",
    )
    if actual_commit != intent.source_commit:
        raise RuntimeError(
            f"branch intent source gen/{intent.source_generation} changed commit"
        )
    expected_genids = tuple(
        format_genid(intent.target_generation, index, children_per_gen)
        for index in range(children_per_gen)
    )
    if expected_genids != intent.target_genids:
        raise RuntimeError(
            "branch intent children-per-gen mismatch: "
            f"expected {intent.target_genids}, requested {expected_genids}"
        )


def _durable_unfinished_genids(workspace: Path) -> list[str]:
    rows = rows_by_genid(workspace)
    pending_gate = _evaluation_pending_gate_record_genids(workspace)
    genids = set(rows)
    genids.update(tag.removeprefix("gen/") for tag in generation_tags(workspace))
    return sorted(
        (
            genid
            for genid in genids
            if genid != "0"
            and _generation_is_pending(rows.get(genid, {}), genid in pending_gate)
        ),
        key=lambda value: (generation_number(value) or -1, value),
    )


def _branch_parents(
    intent: BranchIntent | None,
    generation: int,
    pending: list[str],
) -> dict[str, str] | None:
    if intent is None or generation != intent.target_generation:
        return None
    unexpected = sorted(set(pending) - set(intent.target_genids))
    if unexpected:
        raise RuntimeError(
            f"branch intent target mismatch for generation {generation}: {', '.join(unexpected)}"
        )
    return {genid: intent.source_generation for genid in pending}


def _consume_completed_branch_intent(workspace: Path, intent: BranchIntent | None) -> None:
    if intent is None:
        return
    rows = rows_by_genid(workspace)
    pending_gate = _evaluation_pending_gate_record_genids(workspace)
    if all(
        not _generation_is_pending(rows.get(genid, {}), genid in pending_gate)
        for genid in intent.target_genids
    ):
        consume_branch_intent(workspace, intent)
        print(
            f"[evolve] branch intent consumed: generation {intent.target_generation}",
            flush=True,
        )
```

In `_run_locked`, use `_branch_parents(...)` instead of
`_select_generation_parents(...)` for the target generation. Call
`_consume_completed_branch_intent` before the loop to finish a crash-after-terminal
transition, and after each target generation. Do not invoke the select operator
when forced parents are returned.

- [ ] **Step 5: Add restart, conflict, max-generation, and multi-child tests**

Add these concrete tests below the first two tests in `tests/test_branching.py`:

```python
from evolve.branching import BranchIntent, branch_intent_path, create_branch_intent
from evolve.git import git_stdout


def persisted_intent(workspace: Path, source: str, target: int, genids: tuple[str, ...]) -> BranchIntent:
    return create_branch_intent(
        workspace,
        BranchIntent(
            source_generation=source,
            source_tag=f"gen/{source}",
            source_commit=git_stdout(workspace, "rev-parse", f"gen/{source}^{{commit}}"),
            target_generation=target,
            target_genids=genids,
            created_at="2026-07-28T00:00:00+00:00",
        ),
    )


def test_existing_branch_intent_resumes_without_repeating_cli_flag(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run", str(workspace), "--max-generations", "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr
    persisted_intent(workspace, "0", 3, ("3",))

    resumed = run_evolve(
        "run", str(workspace), "--max-generations", "3",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert resumed.returncode == 0, resumed.stderr
    assert rows_by_genid(workspace)["3"]["parent"] == "0"
    assert load_branch_intent(workspace) is None


def test_conflicting_branch_request_preserves_existing_intent(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run", str(workspace), "--max-generations", "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr
    persisted_intent(workspace, "0", 3, ("3",))
    before = branch_intent_path(workspace).read_bytes()

    result = run_evolve(
        "run", str(workspace), "--max-generations", "3", "--from-generation", "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 1
    assert "conflicting branch intent" in result.stderr
    assert branch_intent_path(workspace).read_bytes() == before


def test_branch_requires_max_generations_to_reach_target(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run", str(workspace), "--max-generations", "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    result = run_evolve(
        "run", str(workspace), "--max-generations", "2", "--from-generation", "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 1
    assert "--max-generations must be at least 3" in result.stderr
    assert load_branch_intent(workspace) is None


def test_multi_child_branch_forces_every_target_child(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    first = run_evolve(
        "run", str(workspace), "--max-generations", "1", "--children-per-gen", "2",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )
    assert first.returncode == 0, first.stderr

    result = run_evolve(
        "run", str(workspace), "--max-generations", "2", "--children-per-gen", "2",
        "--from-generation", "0",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    rows = rows_by_genid(workspace)
    assert rows["2-0"]["parent"] == "0"
    assert rows["2-1"]["parent"] == "0"
    assert load_branch_intent(workspace) is None


def test_multi_child_branch_intent_survives_partial_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1, children_per_gen=2))
    source_commit = git_stdout(workspace, "rev-parse", "gen/0^{commit}")
    create_branch_intent(
        workspace,
        BranchIntent(
            source_generation="0",
            source_tag="gen/0",
            source_commit=source_commit,
            target_generation=2,
            target_genids=("2-0", "2-1"),
            created_at="2026-07-28T00:00:00+00:00",
        ),
    )
    real_run_child = driver._run_child

    def interrupt_second(*args, **kwargs):
        genid = args[2]
        if genid == "2-1":
            raise KeyboardInterrupt("between branch children")
        return real_run_child(*args, **kwargs)

    monkeypatch.setattr(driver, "_run_child", interrupt_second)
    with pytest.raises(KeyboardInterrupt, match="between branch children"):
        run(RunOptions(workspace, max_generations=2, children_per_gen=2))
    assert rows_by_genid(workspace)["2-0"]["parent"] == "0"
    assert load_branch_intent(workspace) is not None

    monkeypatch.setattr(driver, "_run_child", real_run_child)
    run(RunOptions(workspace, max_generations=2, children_per_gen=2))

    assert rows_by_genid(workspace)["2-1"]["parent"] == "0"
    assert load_branch_intent(workspace) is None


def test_new_branch_refuses_existing_unfinished_tagged_generation(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    child = tmp_path / "unfinished-child"
    fork_child(workspace, "1", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# unevaluated\n")
    commit_child(workspace, child, "1", "2")

    with pytest.raises(RuntimeError, match="generations need recovery: gen/2"):
        run(
            RunOptions(
                workspace,
                max_generations=3,
                from_generation="0",
            )
        )
```

Assert the created/resumed/consumed strings in the relevant CLI results'
`stdout` so the observability contract is locked.

- [ ] **Step 6: Run focused tests and formatting**

Run:

```bash
uv run pytest tests/test_branch_intent.py tests/test_branching.py tests/test_m0_run_resume.py -q
uv run ruff check src/evolve/branching.py src/evolve/git.py src/evolve/driver.py src/evolve/cli.py tests/test_branch_intent.py tests/test_branching.py tests/test_m0_run_resume.py
uv run ruff format --check src/evolve/branching.py src/evolve/git.py src/evolve/driver.py src/evolve/cli.py tests/test_branch_intent.py tests/test_branching.py tests/test_m0_run_resume.py
```

Expected: all commands pass.

- [ ] **Step 7: Commit the branching integration**

```bash
git add src/evolve/git.py src/evolve/driver.py src/evolve/cli.py tests/test_branching.py tests/test_m0_run_resume.py
git commit -m "feat: branch evolution from certified generation"
```

---

### Task 3: Recover a Tagged Candidate Whose Lineage Append Was Interrupted

**Files:**
- Modify: `src/evolve/git.py:53-60`
- Modify: `src/evolve/driver.py:131-176,621-689`
- Create: `tests/test_run_recovery.py`

**Interfaces:**
- Consumes: existing `append_event`, `changed_paths`, `check_paths`,
  `surface_patterns`, `ArchiveView.valid_parents()`, and Task 2's
  `generation_tags`.
- Produces:
  - `direct_parent_commit(workspace: Path, ref: str) -> str`
  - `_recover_tagged_parent(workspace: Path, exp_id: str, genid: str) -> str`
  - `_tagged_parent(workspace: Path, exp_id: str, genid: str, row: dict[str, Any]) -> str`

- [ ] **Step 1: Write a failing tag-before-lineage recovery test**

```python
# tests/test_run_recovery.py
from pathlib import Path

import pytest
from conftest import init_workspace, rows_by_genid, smoke_agent_command

from evolve import driver
from evolve.driver import RunOptions, commit_child, fork_child, run
from evolve.git import git, tag_exists


@pytest.fixture(autouse=True)
def smoke_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_STUB", "1")
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())


def completed_generation_snapshot(workspace: Path, genid: str = "0") -> tuple[object, ...]:
    row = rows_by_genid(workspace)[genid]
    artifact = row.get("artifacts")
    artifact_bytes = None
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
        artifact_bytes = (workspace / artifact["path"]).read_bytes()
    receipts = workspace / ".evolve-eval-receipts.jsonl"
    return (
        git(workspace, "rev-parse", f"gen/{genid}^{{commit}}").stdout.strip(),
        json.dumps(row, sort_keys=True),
        receipts.read_bytes(),
        artifact_bytes,
    )


def test_tagged_candidate_recovers_missing_lineage_without_reselecting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# interrupted candidate\n")
    completed_before = completed_generation_snapshot(workspace)

    real_append = driver.append_event

    def fail_lineage(*args, **kwargs):
        raise KeyboardInterrupt("after tag")

    monkeypatch.setattr(driver, "append_event", fail_lineage)
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    assert tag_exists(workspace, "gen/1")
    assert "1" not in rows_by_genid(workspace)

    monkeypatch.setattr(
        driver,
        "_select_generation_parents",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selection reran")),
    )
    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["parent"] == "0"
    assert row["mutated"] == ["target/agent.py"]
    assert row["status"] == "complete"
    assert completed_generation_snapshot(workspace) == completed_before
```

Import `json` in this test module. Capture and compare
`completed_generation_snapshot(workspace)` in every interruption test added in
Tasks 3 and 4; for the pending-gate test, snapshot generation 0 because
generation 1 is intentionally changed by recovery.

- [ ] **Step 2: Run the test and verify the driver reruns selection or skips the tag**

Run:

```bash
uv run pytest tests/test_run_recovery.py::test_tagged_candidate_recovers_missing_lineage_without_reselecting -q
```

Expected: fail with `selection reran` or a missing row for generation 1.

- [ ] **Step 3: Add the direct-parent Git helper**

```python
# src/evolve/git.py
def direct_parent_commit(workspace: Path, ref: str) -> str:
    parents = git_stdout(workspace, "show", "-s", "--format=%P", f"{ref}^{{commit}}").split()
    if len(parents) != 1:
        raise RuntimeError(f"{ref} must have exactly one Git parent, found {len(parents)}")
    return parents[0]
```

- [ ] **Step 4: Implement deterministic tagged-lineage reconstruction**

```python
# src/evolve/driver.py
def _recover_tagged_parent(workspace: Path, exp_id: str, genid: str) -> str:
    tag = f"gen/{genid}"
    parent_commit = direct_parent_commit(workspace, tag)
    candidates = []
    for row in ArchiveView(workspace).valid_parents():
        parent = str(row["genid"])
        if (
            tag_exists(workspace, f"gen/{parent}")
            and git_stdout(workspace, "rev-parse", f"gen/{parent}^{{commit}}") == parent_commit
        ):
            candidates.append(parent)
    if len(candidates) != 1:
        detail = ", ".join(f"gen/{value}" for value in candidates) or "none"
        raise RuntimeError(
            f"cannot recover lineage for {tag}: expected one certified Git parent, found {detail}"
        )
    parent = candidates[0]
    mutated = changed_paths(workspace, f"gen/{parent}", tag)
    include, exclude = surface_patterns(workspace)
    violations = check_paths(mutated, include, exclude)
    if not mutated:
        raise RuntimeError(f"cannot recover lineage for {tag}: candidate has no changes")
    if violations:
        raise RuntimeError(
            f"cannot recover lineage for {tag}: changed paths outside mutable surface: "
            f"{', '.join(violations)}"
        )
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": tag,
            "mutated": mutated,
            "surface_violations": [],
        },
    )
    return parent


def _tagged_parent(
    workspace: Path,
    exp_id: str,
    genid: str,
    row: dict[str, Any],
) -> str:
    recorded = row.get("parent")
    if recorded is None:
        return _recover_tagged_parent(workspace, exp_id, genid)
    parent = str(recorded)
    actual = direct_parent_commit(workspace, f"gen/{genid}")
    expected = git_stdout(workspace, "rev-parse", f"gen/{parent}^{{commit}}")
    if actual != expected:
        raise RuntimeError(
            f"lineage contradiction for gen/{genid}: archive parent gen/{parent} "
            f"does not match Git parent {actual}"
        )
    return parent
```

Restructure `_run_locked` so it resolves parents for tagged pending genids
before calling selection. Pass only untagged pending genids to either the branch
override or `_select_generation_parents`; merge those results with the tagged
parent map. This guarantees selection is never executed for a tagged candidate.

- [ ] **Step 5: Add contradiction and ambiguous-parent tests**

```python
from evolve.config import experiment_id


def test_tagged_candidate_refuses_archive_git_parent_contradiction(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    child = tmp_path / "child-2"
    fork_child(workspace, "1", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# child two\n")
    commit_child(workspace, child, "1", "2")
    archive_before = (workspace / "archive.jsonl").read_bytes()
    receipts_before = (workspace / ".evolve-eval-receipts.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="lineage contradiction for gen/2"):
        driver._tagged_parent(
            workspace,
            experiment_id(workspace),
            "2",
            {"parent": "0"},
        )

    assert (workspace / "archive.jsonl").read_bytes() == archive_before
    assert (workspace / ".evolve-eval-receipts.jsonl").read_bytes() == receipts_before


def test_tagged_candidate_refuses_missing_certified_git_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# interrupted candidate\n")
    real_append = driver.append_event
    monkeypatch.setattr(
        driver,
        "append_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt("after tag")),
    )
    with pytest.raises(KeyboardInterrupt, match="after tag"):
        commit_child(workspace, child, "0", "1")
    monkeypatch.setattr(driver, "append_event", real_append)
    git(workspace, "tag", "-d", "gen/0")
    archive_before = (workspace / "archive.jsonl").read_bytes()

    with pytest.raises(RuntimeError, match="expected one certified Git parent, found none"):
        driver._recover_tagged_parent(workspace, experiment_id(workspace), "1")

    assert (workspace / "archive.jsonl").read_bytes() == archive_before
```

These tests call the narrow recovery helpers directly so no unrelated driver
phase can write after the before-snapshot.

- [ ] **Step 6: Run the tagged recovery tests and regressions**

Run:

```bash
uv run pytest tests/test_run_recovery.py -q
uv run pytest tests/test_m0_run_resume.py tests/test_selection_certification.py -q
uv run ruff check src/evolve/git.py src/evolve/driver.py tests/test_run_recovery.py
uv run ruff format --check src/evolve/git.py src/evolve/driver.py tests/test_run_recovery.py
```

Expected: all commands pass.

- [ ] **Step 7: Commit tagged-lineage recovery**

```bash
git add src/evolve/git.py src/evolve/driver.py tests/test_run_recovery.py
git commit -m "fix: recover tagged candidate lineage"
```

---

### Task 4: Clean Untagged Work and Resume Evaluation/Gate Boundaries

**Files:**
- Modify: `src/evolve/driver.py:131-176,421-435,454-470`
- Modify: `tests/test_run_recovery.py`

**Interfaces:**
- Consumes: Task 3's tagged-parent classification, existing `next_attempt`,
  `_evaluation_pending_gate_record_genids`, `_generation_is_pending`, and
  `remove_worktree`.
- Produces:
  - `_clear_untagged_generation_state(workspace: Path, generation: int, genids: list[str]) -> list[str]`
  - enhanced `doctor(workspace: Path) -> list[str]`

- [ ] **Step 1: Add a failing stale-output cleanup test**

```python
def test_untagged_generation_discards_stale_operator_output_before_rerun(
    tmp_path: Path,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    stale = workspace / "runs" / "gen-1" / "meta_agent.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"stale": true}\n')

    run(RunOptions(workspace, max_generations=1))

    assert rows_by_genid(workspace)["1"]["status"] == "complete"
    assert not stale.exists()
```

Use a stale filename that the smoke recipe does not recreate. This proves the
old directory was removed rather than merely overwritten.

- [ ] **Step 2: Add a failing interrupted-evaluation-attempt test**

```python
def test_tagged_candidate_starts_new_evaluation_attempt_after_partial_attempt(
    tmp_path: Path,
) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    child = tmp_path / "child"
    fork_child(workspace, "0", child)
    target = child / "target" / "agent.py"
    target.write_text(target.read_text() + "\n# candidate\n")
    commit_child(workspace, child, "0", "1")
    commit = git(workspace, "rev-parse", "gen/1^{commit}").stdout.strip()
    partial = (
        workspace / "runs" / "evaluations" / "candidate" / "gen-1"
        / f"candidate-{commit}" / "attempt-1"
    )
    partial.mkdir(parents=True)
    (partial / "partial-sentinel").write_text("interrupted\n")

    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["attempt"] == 2
    assert (partial / "partial-sentinel").read_text() == "interrupted\n"
```

Import the subprocess-returning Git helper as
`from evolve.git import git`; do not use the string-returning test helper in
this test.

- [ ] **Step 3: Run both tests to expose stale state behavior**

Run:

```bash
uv run pytest \
  tests/test_run_recovery.py::test_untagged_generation_discards_stale_operator_output_before_rerun \
  tests/test_run_recovery.py::test_tagged_candidate_starts_new_evaluation_attempt_after_partial_attempt \
  -q
```

Expected: the stale-output assertion fails before cleanup is implemented; the
evaluation test should already pass through `next_attempt` and becomes a locked
regression.

- [ ] **Step 4: Implement exact untagged cleanup before selection**

```python
def _clear_untagged_generation_state(
    workspace: Path,
    generation: int,
    genids: list[str],
) -> list[str]:
    actions: list[str] = []
    select_dir = workspace / "runs" / f"gen-{generation}" / "select"
    if select_dir.exists():
        shutil.rmtree(select_dir)
        actions.append(f"discarded stale selection output for generation {generation}")
    for genid in genids:
        child = _child_worktree_path(workspace, genid)
        if child.exists():
            remove_worktree(workspace, child)
            actions.append(f"removed stale worktree {child.name}")
        run_dir = _run_dir(workspace, genid)
        if run_dir.exists():
            shutil.rmtree(run_dir)
            actions.append(f"discarded stale operator output for gen/{genid}")
    git(workspace, "worktree", "prune", check=False)
    return actions
```

Call this helper only for untagged pending genids, after tagged candidates have
been separated and before parent selection runs. Print each action with the
existing `[evolve]` progress prefix. Never pass a tagged or terminal genid to
this helper.

When `_resume_tagged_child` finds an existing non-canonical or infrastructure
evaluation and starts a new attempt, print:

```python
print(f"[evolve] gen/{genid} evaluation: starting recovery attempt", flush=True)
```

Before `_run_gate_and_record` resumes a pending decision, print:

```python
print(f"[evolve] gen/{genid} gate/record: resuming", flush=True)
```

Assert both messages in their corresponding recovery tests.

- [ ] **Step 5: Add and lock the pending-gate-only recovery test**

```python
import json

from evolve.archive import STAMPED_FIELDS, read_events


def _remove_gate_event(path: Path, genid: str) -> None:
    events = read_events(path)
    candidates = [
        index
        for index, event in enumerate(events)
        if str(event.get("genid")) == genid
        and STAMPED_FIELDS.isdisjoint(event)
        and {"valid_parent", "verdict", "reason"} <= set(event)
    ]
    assert len(candidates) == 1
    del events[candidates[0]]
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events))


def test_completed_evaluation_resumes_only_pending_gate_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evolve_home = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=1))
    _remove_gate_event(workspace / "archive.jsonl", "1")
    _remove_gate_event(evolve_home / "mirrors" / workspace.name / "archive.jsonl", "1")
    assert rows_by_genid(workspace)["1"]["pending_gate_record"] is True
    monkeypatch.setattr(
        driver,
        "eval_child",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("evaluation reran")),
    )
    monkeypatch.setattr(
        driver,
        "_select_generation_parents",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selection reran")),
    )

    run(RunOptions(workspace, max_generations=1))

    row = rows_by_genid(workspace)["1"]
    assert row["pending_gate_record"] is False
    assert row["status"] == "complete"
```

- [ ] **Step 6: Extend doctor observability**

Add this focused test, then update `doctor` to make it pass without modifying
completed state:

```python
def test_doctor_reports_active_branch_intent(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run(RunOptions(workspace, max_generations=0))
    intent = BranchIntent(
        source_generation="0",
        source_tag="gen/0",
        source_commit=git(workspace, "rev-parse", "gen/0^{commit}").stdout.strip(),
        target_generation=1,
        target_genids=("1",),
        created_at="2026-07-28T00:00:00+00:00",
    )
    create_branch_intent(workspace, intent)

    assert "active branch intent: gen/0 -> generation 1" in doctor(workspace)
```

Extend the tag-before-lineage test from Task 3 with:

```python
assert "tagged candidate needs lineage recovery: 1" in doctor(workspace)
```

Keep the existing pending output unchanged:

```text
pending gate/record (run will resume): 8
```

- [ ] **Step 7: Run recovery, lifecycle, and driver regressions**

Run:

```bash
uv run pytest \
  tests/test_run_recovery.py \
  tests/test_evaluation_lifecycle.py \
  tests/test_driver_lock.py \
  tests/test_m0_run_resume.py \
  tests/test_m5_record_verb.py \
  -q
uv run ruff check src/evolve/driver.py tests/test_run_recovery.py
uv run ruff format --check src/evolve/driver.py tests/test_run_recovery.py
```

Expected: all commands pass.

- [ ] **Step 8: Commit interrupted-state recovery**

```bash
git add src/evolve/driver.py tests/test_run_recovery.py
git commit -m "fix: resume interrupted experiment state safely"
```

---

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `README.md:230-245`
- Verify only: all files changed in Tasks 1-4

**Interfaces:**
- Consumes: the completed CLI and recovery behavior.
- Produces: user-facing command documentation and repository-wide verification evidence.

- [ ] **Step 1: Document default recovery and branching**

Add this text beneath the CLI verb list:

````markdown
`run` resumes interrupted work from the experiment folder by default. Work
before a candidate is tagged may be discarded and rerun; tagged candidates,
certified evaluations, and completed generations are preserved.

To branch future evolution non-destructively from a prior certified candidate:

```bash
evolve run <workspace> --from-generation 4 --max-generations 11
```

This creates the next unused generation with `gen/4` as its parent. It does not
delete generations 5–10. If the process stops before the branch generation
finishes, the forced-parent intent is resumed automatically.
````

Also add `[--from-generation GENID]` to the `evolve run` syntax line.

- [ ] **Step 2: Run the focused feature suite**

Run:

```bash
uv run pytest \
  tests/test_branch_intent.py \
  tests/test_branching.py \
  tests/test_run_recovery.py \
  tests/test_m0_run_resume.py \
  tests/test_driver_lock.py \
  tests/test_evaluation_lifecycle.py \
  tests/test_m5_record_verb.py \
  tests/test_selection_certification.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 3: Run the full repository test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass. If a failure reproduces on the pre-task commit because
of unrelated pre-existing worktree changes, record that baseline explicitly and
do not modify unrelated files to hide it.

- [ ] **Step 4: Run repository-wide lint and format verification**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Expected: all commands pass for task-owned files; report any unrelated
pre-existing failure separately.

- [ ] **Step 5: Inspect scope and commit documentation**

Run:

```bash
git status --short
git diff -- README.md
git diff --stat HEAD~4..HEAD
```

Confirm the implementation did not stage or overwrite unrelated working-tree
changes, then commit:

```bash
git add README.md
git commit -m "docs: explain experiment recovery and branching"
```

- [ ] **Step 6: Perform the final behavior check**

In a temporary smoke workspace:

```bash
recovery_smoke_dir="$(mktemp -d)"
EVAL_STUB=1 uv run evolve init "$recovery_smoke_dir/experiment" --recipe hill_climb-smoke
EVAL_STUB=1 uv run evolve run "$recovery_smoke_dir/experiment" --max-generations 2
EVAL_STUB=1 uv run evolve run "$recovery_smoke_dir/experiment" --max-generations 3 --from-generation 0
uv run evolve status "$recovery_smoke_dir/experiment"
git -C "$recovery_smoke_dir/experiment" tag --list 'gen/*'
```

Expected:

- tags `gen/0` through `gen/3` exist;
- generation 3 records parent `0`;
- generations 1 and 2 remain present;
- `runs/branch-intent.json` is absent after generation 3 becomes terminal.
