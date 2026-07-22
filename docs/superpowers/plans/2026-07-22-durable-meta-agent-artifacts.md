# Durable Meta-Agent Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, generation-scoped artifact channel for users and meta-agents, expose an optional free-form handoff through that channel, and make historical evidence paths portable.

**Architecture:** The workspace owns `artifacts/user/` and `artifacts/generations/<genid>/` outside the candidate Git surface. A shared helper renders runner-independent artifact guidance; Harbor stages the complete tree but transactionally imports only the current generation namespace alongside candidate editable roots. Feedback stores normalized workspace-relative evidence paths.

**Tech Stack:** Python 3.11+, pathlib, pytest, Git worktrees, Harbor artifact-return runner.

## Global Constraints

- `handoff.md` is free-form Markdown and remains optional.
- Missing handoffs never fail a generation.
- Meta-agents may persist arbitrary regular files only under their current generation namespace.
- `artifacts/user/` and earlier generation namespaces are host-authoritative.
- Durable artifacts never enter candidate patches, commits, surface checks, or benchmark runtime code.
- Harbor must reject symlinks and special files without partially installing candidate or artifact changes.
- Stored workspace evidence paths are normalized relative POSIX paths, never host-absolute paths.
- Preserve the user's existing uncommitted `.gitignore` change.

---

### Task 1: Initialize the durable artifact layout and shared path contract

**Files:**
- Create: `library/meta_agent/support/artifacts.py`
- Modify: `src/evolve/workspace.py:227-231`
- Modify: `templates/workspace/.gitignore:1-8`
- Test: `tests/test_m0_init.py:45-96`
- Create test: `tests/test_meta_agent_artifacts.py`

**Interfaces:**
- Produces: `ARTIFACT_ROOT: Path`, `artifact_generation_relative(genid: str) -> Path`, `artifact_generation_dir(workspace: Path, genid: str) -> Path`, and `render_artifact_guidance(ctx: OperatorContext, repository: Path) -> str`.
- Consumes: `OperatorContext.genid`, `OperatorContext.parent`, and `OperatorContext.workspace`.

- [ ] **Step 1: Write failing initialization and helper tests**

Add `artifacts/user` and `artifacts/generations` to `expected_paths` in
`test_init_scaffolds_hill_climb_workspace`, assert `artifacts/` is present in
the generated `.gitignore`, and create `tests/test_meta_agent_artifacts.py`
with:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from library.meta_agent.support.artifacts import (
    artifact_generation_dir,
    artifact_generation_relative,
    render_artifact_guidance,
)


def test_generation_artifact_paths_are_workspace_relative(tmp_path: Path) -> None:
    assert artifact_generation_relative("3-1") == Path("artifacts/generations/3-1")
    assert artifact_generation_dir(tmp_path, "3-1") == tmp_path / "artifacts/generations/3-1"


@pytest.mark.parametrize("genid", ["", ".", "..", "../1", "1/child", "/absolute"])
def test_generation_artifact_paths_reject_unsafe_ids(genid: str) -> None:
    with pytest.raises(ValueError, match="generation id"):
        artifact_generation_relative(genid)


def test_guidance_identifies_current_and_selected_parent_handoff(tmp_path: Path) -> None:
    handoff = tmp_path / "artifacts/generations/2/handoff.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("continue parser investigation\n")
    ctx = SimpleNamespace(workspace=tmp_path, genid="3", parent="2")

    rendered = render_artifact_guidance(ctx, Path("/app/task/workspace"))

    assert "Durable artifact root: /app/task/workspace/artifacts" in rendered
    assert "Writable generation directory: /app/task/workspace/artifacts/generations/3" in rendered
    assert "selected parent meta-agent's handoff" in rendered
    assert "/app/task/workspace/artifacts/generations/2/handoff.md" in rendered
    assert "verify its claims" in rendered
    assert "free-form handoff" in rendered


def test_guidance_explicitly_acknowledges_missing_parent_handoff(tmp_path: Path) -> None:
    ctx = SimpleNamespace(workspace=tmp_path, genid="1", parent="0")

    rendered = render_artifact_guidance(ctx, tmp_path)

    assert "No selected-parent handoff is available" in rendered
    assert "handoff.md is optional" in rendered
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest -q tests/test_meta_agent_artifacts.py tests/test_m0_init.py::test_init_scaffolds_hill_climb_workspace
```

Expected: collection fails because `library.meta_agent.support.artifacts` does not exist, and the initialization assertions fail once collection is unblocked.

- [ ] **Step 3: Implement the shared artifact helper and workspace layout**

Create `library/meta_agent/support/artifacts.py`:

```python
"""Portable durable-artifact paths shared by meta-agent strategies and runners."""

from __future__ import annotations

from pathlib import Path

from evolve.frozen.interfaces import OperatorContext

ARTIFACT_ROOT = Path("artifacts")
HANDOFF_NAME = "handoff.md"


def artifact_generation_relative(genid: str) -> Path:
    value = str(genid)
    if not value or Path(value).name != value or value in {".", ".."}:
        raise ValueError(f"unsafe generation id for durable artifacts: {value!r}")
    return ARTIFACT_ROOT / "generations" / value


def artifact_generation_dir(workspace: Path, genid: str) -> Path:
    return workspace / artifact_generation_relative(genid)


def render_artifact_guidance(ctx: OperatorContext, repository: Path) -> str:
    current = repository / artifact_generation_relative(ctx.genid)
    lines = [
        "# Durable Artifacts",
        "",
        f"Durable artifact root: {repository / ARTIFACT_ROOT}",
        f"Writable generation directory: {current}",
        "You may read the complete artifact tree, but write durable files only in the writable generation directory.",
    ]
    parent = str(ctx.parent) if ctx.parent is not None else ""
    parent_handoff = artifact_generation_dir(ctx.workspace, parent) / HANDOFF_NAME if parent else None
    if parent_handoff is not None and parent_handoff.is_file():
        visible = repository / artifact_generation_relative(parent) / HANDOFF_NAME
        lines.extend(
            [
                f"The selected parent meta-agent's handoff is at: {visible}",
                "Read it as context and verify its claims against the available evidence.",
            ]
        )
    else:
        lines.append("No selected-parent handoff is available for this generation.")
    lines.extend(
        [
            "Before finishing, you may write a free-form handoff for the next selected child to "
            f"{current / HANDOFF_NAME}.",
            "handoff.md is optional; its absence does not fail the generation.",
        ]
    )
    return "\n".join(lines)
```

In `src/evolve/workspace.py`, create the two directories after `runs`:

```python
    (workspace / "runs").mkdir(exist_ok=True)
    (workspace / "artifacts" / "user").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "generations").mkdir(parents=True, exist_ok=True)
```

Add `artifacts/` to `templates/workspace/.gitignore`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_meta_agent_artifacts.py tests/test_m0_init.py::test_init_scaffolds_hill_climb_workspace
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the path contract**

```bash
git add library/meta_agent/support/artifacts.py src/evolve/workspace.py templates/workspace/.gitignore tests/test_meta_agent_artifacts.py tests/test_m0_init.py
git commit -m "feat: add durable meta-agent artifact layout"
```

---

### Task 2: Store portable historical evidence references

**Files:**
- Modify: `src/evolve/feedback.py:96-128`
- Test: `tests/test_m7_harbor_rollout.py:200-280`

**Interfaces:**
- Produces: `history.json[*].raw_evidence_dir` as a workspace-relative POSIX string.
- Consumes: evidence roots constructed below `workspace/runs/`.

- [ ] **Step 1: Write a failing relative-path assertion**

In `test_feedback_bundle_copies_selected_evidence_and_history`, create evidence
for the archived generation zero before calling `write_feedback_bundle`:

```python
    historical = workspace / "runs/gen-0/trace_analyzer/evidence"
    historical.mkdir(parents=True)
    (historical / "manifest.json").write_text(json.dumps({"selected_variant": "failure_patterns"}))
    (historical / "metrics.json").write_text(json.dumps({"trials": 1}))

    manifest = write_feedback_bundle(workspace=workspace, run_dir=run_dir)

    history = json.loads((run_dir / "feedback/evidence/history.json").read_text())
    evidence_path = history[-1]["raw_evidence_dir"]
    assert evidence_path == "runs/gen-0/trace_analyzer/evidence"
    assert not Path(evidence_path).is_absolute()
    assert (workspace / evidence_path).is_dir()
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
uv run pytest -q tests/test_m7_harbor_rollout.py -k feedback
```

Expected: failure because `raw_evidence_dir` is currently an absolute temporary-workspace path.

- [ ] **Step 3: Write the minimal relative-path implementation**

In `_rollout_history`, replace the host path serialization with:

```python
                "raw_evidence_dir": (
                    evidence_root.relative_to(workspace).as_posix() if evidence_root.is_dir() else None
                ),
```

Because `evidence_root` is constructed from `workspace`, `relative_to` also serves as a containment assertion.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_m7_harbor_rollout.py -k feedback
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit portable evidence paths**

```bash
git add src/evolve/feedback.py tests/test_m7_harbor_rollout.py
git commit -m "fix: make feedback evidence paths portable"
```

---

### Task 3: Put durable-artifact and handoff awareness in meta-agent prompts

**Files:**
- Modify: `library/meta_agent/hyperagents.py:106-127`
- Modify: `library/meta_agent/ahe.py:166-199`
- Test: `tests/test_hyperagents_meta_agent.py:70-125`
- Test: `tests/test_ahe_meta_agent.py:115-155`

**Interfaces:**
- Consumes: `render_artifact_guidance(ctx, repository)` from Task 1.
- Produces: explicit current-generation write guidance and selected-parent handoff acknowledgement in both strategy prompts.

- [ ] **Step 1: Write failing prompt assertions**

In both prompt test fixtures, create:

```python
    parent_handoff = ctx.workspace / "artifacts/generations/0/handoff.md"
    parent_handoff.parent.mkdir(parents=True)
    parent_handoff.write_text("PARENT HANDOFF BODY\n")
```

For the Harbor prompt assertions, require:

```python
    assert "Durable artifact root: /app/task/workspace/artifacts" in prompt
    assert "Writable generation directory: /app/task/workspace/artifacts/generations/1" in prompt
    assert "selected parent meta-agent's handoff" in prompt
    assert "/app/task/workspace/artifacts/generations/0/handoff.md" in prompt
    assert "free-form handoff" in prompt
    assert "PARENT HANDOFF BODY" not in prompt
```

Add one local-runner assertion that the displayed paths are rooted at `ctx.workspace`, not the child checkout.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py -k prompt
```

Expected: failures because neither strategy currently renders durable-artifact guidance.

- [ ] **Step 3: Add the shared guidance to both prompts**

Import the helper in each strategy:

```python
from library.meta_agent.support.artifacts import render_artifact_guidance
```

After each strategy determines `repository`, add this section before the final edit instruction:

```python
        f"{render_artifact_guidance(ctx, repository)}\n\n"
```

Do not inline the handoff body. The prompt identifies it as a handoff and gives the file path, leaving the model to read it with filesystem tools.

- [ ] **Step 4: Run prompt tests and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py
```

Expected: both complete test modules pass.

- [ ] **Step 5: Commit prompt integration**

```bash
git add library/meta_agent/hyperagents.py library/meta_agent/ahe.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py
git commit -m "feat: expose durable handoffs to meta-agents"
```

---

### Task 4: Round-trip the current generation artifact namespace through Harbor

**Files:**
- Modify: `library/meta_agent/runners/harbor.py:45-285`
- Modify: `library/meta_agent/runners/harbor.py:782-875`
- Test: `tests/test_harbor_meta_agent.py:69-313`
- Test: `tests/test_harbor_meta_agent.py:316-720`

**Interfaces:**
- Consumes: `ARTIFACT_ROOT`, `artifact_generation_dir`, and `artifact_generation_relative` from Task 1.
- Produces: a staged complete artifact tree and atomic import of only `artifacts/generations/<ctx.genid>`.
- Preserves: `_install_bundle(...) -> list[str]` returns only candidate changed paths.

- [ ] **Step 1: Extend the fake Harbor run and write failing round-trip tests**

Seed the host fixture with:

```python
    (checkout / "artifacts/user").mkdir(parents=True)
    (checkout / "artifacts/user/note.md").write_text("host user note\n")
    (checkout / "artifacts/generations/0").mkdir(parents=True)
    (checkout / "artifacts/generations/0/handoff.md").write_text("parent handoff\n")
```

Adjust the fake Harbor script to assert those files were staged, then create:

```python
    current = artifact / "artifacts/generations/1"
    (current / "nested").mkdir(parents=True, exist_ok=True)
    (current / "handoff.md").write_text("child handoff\n")
    (current / "nested/analysis.json").write_text('{"status":"useful"}\n')
```

Add assertions to the round-trip test:

```python
    assert (checkout / "artifacts/generations/1/handoff.md").read_text() == "child handoff\n"
    assert json.loads((checkout / "artifacts/generations/1/nested/analysis.json").read_text()) == {
        "status": "useful"
    }
    assert "artifacts/generations/1/handoff.md" not in result.output
```

Add separate modes/tests where Harbor changes `artifacts/user/note.md` and `artifacts/generations/0/handoff.md`; assert both host files retain their original contents while the current generation imports successfully.

- [ ] **Step 2: Run the round-trip tests and verify RED**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py -k "round_trips or artifact_namespace"
```

Expected: failures because `artifacts/` is currently treated as a protected workspace mutation and no current-generation namespace is imported.

- [ ] **Step 3: Stage the complete artifact tree and exempt it from candidate manifests**

Import the shared path helpers and change `_manifest_ignored` so the generic artifact tree is outside candidate mutation checks:

```python
    return relative.parts[0] in {".git", "runs", ARTIFACT_ROOT.as_posix()} or relative.as_posix() in {
        "archive.jsonl",
        _EVAL_RECEIPT,
    }
```

In `_prepare_bundle`, before computing `bundle.before`:

```python
        artifacts = ctx.workspace / ARTIFACT_ROOT
        if artifacts.exists():
            _validate_tree(artifacts)
            _copy_tree(artifacts, workspace / ARTIFACT_ROOT)
        (workspace / artifact_generation_relative(ctx.genid)).mkdir(parents=True, exist_ok=True)
```

Ensure `artifacts` is excluded from the checkout-copy loop so `ctx.workspace` remains authoritative even when tests or local configurations make workspace and checkout coincide.

- [ ] **Step 4: Refactor installation into one rollback-capable transaction**

Extend `_install_bundle` with keyword-only `artifact_workspace: Path` and `genid: str`. Before moving any host path:

1. Copy every candidate editable root into `install/replacements/candidate/<root>` using `_copy_returned_tree`.
2. Copy `returned/artifacts/generations/<genid>` into `install/replacements/artifacts` using a new `_copy_regular_tree` that accepts only directories and regular files and never calls Git ignore logic.
3. Treat a missing returned current-generation directory as an empty directory.
4. Build installation targets for each checkout root plus `artifact_generation_dir(artifact_workspace, genid)`.
5. Move existing targets into unique backup paths, install all replacements, and track every move.
6. Run the existing surface and `git diff --check` validation.
7. On any exception, remove installed targets and restore every backup in reverse order.

Use this complete generic copier:

```python
def _copy_regular_tree(source: Path, destination: Path) -> None:
    destination.mkdir()
    if not source.exists():
        return
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError(f"returned durable artifact namespace must be a real directory: {source}")
    for child in source.iterdir():
        mode = child.lstat().st_mode
        target = destination / child.name
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"Harbor meta-agent does not accept artifact symlinks: {child}")
        if stat.S_ISDIR(mode):
            _copy_regular_tree(child, target)
        elif stat.S_ISREG(mode):
            shutil.copy2(child, target)
        else:
            raise RuntimeError(f"Harbor meta-agent does not accept artifact special files: {child}")
```

Update `run_agent` to call:

```python
        _install_bundle(
            checkout,
            artifact,
            bundle,
            parent_ref,
            surface,
            artifact_workspace=ctx.workspace,
            genid=ctx.genid,
        )
```

Update direct unit-test calls to supply the keyword arguments.

- [ ] **Step 5: Write and run failing safety tests before completing rollback support**

Add these direct installer tests, using the existing `_checkout`, `_ctx`, and
`_prepare_bundle` helpers. Pass `artifact_workspace=checkout` and `genid="1"`
to every `_install_bundle` call:

```python
def test_install_bundle_rejects_returned_artifact_symlink_atomically(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, _ctx(checkout, run_dir), ["target"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(bundle.workspace, returned, symlinks=True)
    (returned / "target/agent.py").write_text("print('child')\n")
    current = returned / "artifacts/generations/1"
    current.mkdir(parents=True, exist_ok=True)
    (current / "link").symlink_to("handoff.md")
    before_target = (checkout / "target/agent.py").read_text()
    before_user = (checkout / "artifacts/user/note.md").read_text()
    try:
        with pytest.raises(RuntimeError, match="artifact symlinks"):
            runner._install_bundle(
                checkout,
                returned,
                bundle,
                "gen/0",
                surface,
                artifact_workspace=checkout,
                genid="1",
            )
        assert (checkout / "target/agent.py").read_text() == before_target
        assert (checkout / "artifacts/user/note.md").read_text() == before_user
        assert not (checkout / "artifacts/generations/1").exists()
    finally:
        shutil.rmtree(bundle.staging, ignore_errors=True)


def test_install_bundle_accepts_empty_returned_generation_namespace(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    existing = checkout / "artifacts/generations/1"
    existing.mkdir(parents=True)
    (existing / "stale.md").write_text("replace me\n")
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, _ctx(checkout, run_dir), ["target"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(bundle.workspace, returned)
    shutil.rmtree(returned / "artifacts/generations/1")
    try:
        runner._install_bundle(
            checkout,
            returned,
            bundle,
            "gen/0",
            surface,
            artifact_workspace=checkout,
            genid="1",
        )
        assert (checkout / "artifacts/generations/1").is_dir()
        assert list((checkout / "artifacts/generations/1").iterdir()) == []
    finally:
        shutil.rmtree(bundle.staging, ignore_errors=True)


def test_install_bundle_rolls_back_candidate_when_artifact_install_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    current = checkout / "artifacts/generations/1"
    current.mkdir(parents=True)
    (current / "before.md").write_text("before\n")
    runner = _harbor_runner_module()
    surface = runner.load_surface_policy(checkout)
    bundle = runner._prepare_bundle(checkout, _ctx(checkout, run_dir), ["target"], surface)
    returned = tmp_path / "returned"
    shutil.copytree(bundle.workspace, returned)
    (returned / "target/agent.py").write_text("print('child')\n")
    (returned / "artifacts/generations/1/after.md").write_text("after\n")
    rename = Path.rename

    def fail_artifact_install(path: Path, target: Path) -> Path:
        if path.as_posix().endswith("replacements/artifacts"):
            raise OSError("simulated artifact install failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_artifact_install)
    try:
        with pytest.raises(OSError, match="artifact install failure"):
            runner._install_bundle(
                checkout,
                returned,
                bundle,
                "gen/0",
                surface,
                artifact_workspace=checkout,
                genid="1",
            )
        assert (checkout / "target/agent.py").read_text() == "print('parent')\n"
        assert (current / "before.md").read_text() == "before\n"
        assert not (current / "after.md").exists()
    finally:
        shutil.rmtree(bundle.staging, ignore_errors=True)
```

Extend `test_harbor_trial_exception_does_not_modify_target` by seeding
`artifacts/generations/1/before.md` before the run and asserting afterward that
it is unchanged. Run these four tests before completing the installer and
confirm that they fail because artifact validation/import/rollback is absent.

- [ ] **Step 6: Run the full Harbor runner module and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py
```

Expected: the complete module passes, including existing protected-file, symlink, multi-root rollback, instruction transport, and artifact-return tests.

- [ ] **Step 7: Commit Harbor persistence**

```bash
git add library/meta_agent/runners/harbor.py tests/test_harbor_meta_agent.py
git commit -m "feat: persist generation artifacts through Harbor"
```

---

### Task 5: Document the generic artifact channel and verify the complete contract

**Files:**
- Modify: `META_AGENTS.md:117-145`
- Modify: `library/PROTOCOL.md:91-110`
- Modify: `templates/workspace/README.md:12-30`
- Test: `tests/test_coherence.py`

**Interfaces:**
- Documents: artifact ownership, read/write boundaries, handoff convention, and relative evidence paths.
- Verifies: the current source, vendored workspace behavior, and tests remain coherent.

- [ ] **Step 1: Add a failing documentation coherence test**

Add a focused test in `tests/test_coherence.py`:

```python
def test_meta_agent_docs_describe_durable_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    meta_agents = (root / "META_AGENTS.md").read_text()
    protocol = (root / "library/PROTOCOL.md").read_text()
    workspace_readme = (root / "templates/workspace/README.md").read_text()
    for text in (meta_agents, protocol, workspace_readme):
        assert "artifacts/generations/<genid>/" in text
        assert "handoff.md" in text
    assert "workspace-relative" in meta_agents
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
uv run pytest -q tests/test_coherence.py -k durable_artifacts
```

Expected: failure because the durable artifact contract is not documented yet.

- [ ] **Step 3: Document the exact behavior**

Add this contract, adapting only heading levels to each document:

```markdown
## Durable meta-agent artifacts

`artifacts/` is persistent experiment state outside the candidate mutation
surface. Users may place arbitrary files under `artifacts/user/`. Meta-agents
may read the complete tree and write arbitrary regular files only under
`artifacts/generations/<genid>/` for their current generation.

The optional `artifacts/generations/<genid>/handoff.md` is a free-form handoff
to a future child that selects this generation as its parent. Missing handoffs
do not fail a generation. Prompts identify the selected parent's handoff path
but do not inline or interpret its contents.

Harbor receives the complete artifact tree and returns only the current
generation namespace to persistent storage. Returned changes to `user/` or
earlier generations are discarded. Durable artifacts never enter candidate
patches, commits, surface checks, or benchmark runtime code.

Paths in feedback that refer to workspace evidence are workspace-relative
POSIX paths, such as `runs/gen-3/trace_analyzer/evidence`, so the same reference
resolves on the host and under `/app/task/workspace` in Harbor.
```

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
uv run pytest -q tests/test_coherence.py -k durable_artifacts
uv run pytest -q tests/test_meta_agent_artifacts.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py tests/test_harbor_meta_agent.py tests/test_m7_harbor_rollout.py tests/test_m0_init.py
uv run pytest -q
```

Expected: all commands exit zero with no failures.

- [ ] **Step 5: Inspect the final diff and artifact isolation**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the implementation files from this plan and the user's pre-existing `.gitignore` modification appear before the final commit.

- [ ] **Step 6: Commit documentation and final integration**

```bash
git add META_AGENTS.md library/PROTOCOL.md templates/workspace/README.md tests/test_coherence.py
git commit -m "docs: explain durable meta-agent artifacts"
```
