# Harbor Disposable Full Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Harbor editing agents inside one disposable `/app/workspace` containing the selected parent and complete experiment evidence, then persist only surface-allowed roots.

**Architecture:** The Harbor runner builds a self-contained Git workspace in a system temporary directory, overlays archive and run evidence, and gives that directory to Harbor as both workdir and artifact. A trusted pre-run tree manifest detects protected changes without trusting returned Git metadata; only configured editable roots are transactionally copied back. Strategy prompts use container paths, and HyperAgents prefers target edits without requiring them.

**Tech Stack:** Python 3.12, pathlib/shutil/tempfile, Git CLI, Harbor Exec, pytest.

## Global Constraints

- The real host experiment workspace must never be mounted into the Harbor task.
- `/app/workspace` is disposable and writable.
- Exclude transient `runs/worktrees` and current Harbor job trees from copied evidence.
- Ignore returned `.git`, `runs/**`, `archive.jsonl`, and evaluation receipts as output channels.
- Reject changes to protected tracked files through the existing surface policy.
- Install only `editable_roots` transactionally.
- Do not strengthen AHE manifest validation or change model pins, budgets, or recipes.

---

## File Structure

- Modify `library/meta_agent/runners/harbor.py`: assemble, launch, compare, and install a disposable full workspace.
- Modify `library/meta_agent/hyperagents.py`: use `/app/workspace` paths and target-preference wording.
- Modify `library/meta_agent/ahe.py`: advertise complete container-visible evidence paths.
- Modify `tests/test_harbor_meta_agent.py`: exercise the new artifact layout and trust boundary.
- Create `tests/test_hyperagents_meta_agent.py`: pin prompt policy and stable paths.
- Modify `tests/test_ahe_meta_agent.py`: pin AHE stable paths and raw-evidence access.
- Modify `META_AGENTS.md`: document full-workspace Harbor semantics.

### Task 1: Assemble and round-trip the disposable workspace

**Files:**
- Modify: `tests/test_harbor_meta_agent.py`
- Modify: `library/meta_agent/runners/harbor.py`

**Interfaces:**
- Produces: `_WorkspaceBundle(staging, task_root, workspace, roots)`.
- Produces: `_prepare_bundle(checkout, ctx, editable_roots, surface) -> _WorkspaceBundle`.
- Produces: `_tree_manifest(root) -> dict[str, tuple[str, str]]` for trusted before/after comparison.
- Produces: `_install_bundle(checkout, returned_workspace, bundle, parent_ref, surface) -> list[str]`.

- [ ] **Step 1: Rewrite the fake Harbor contract and add a failing full-workspace round-trip test**

Update the fake Harbor executable to require:

```python
if option("--artifact") != "/app/workspace":
    raise SystemExit("expected /app/workspace artifact")
if option("--workdir") != "/app/workspace":
    raise SystemExit("expected /app/workspace workdir")

source = Path(option("--path", "-p"))
artifact = trial_dir / "artifacts" / "app" / "workspace"
shutil.copytree(source / "workspace", artifact, symlinks=True)
```

Add assertions to `test_harbor_meta_agent_round_trips_target_and_writes_artifacts`:

```python
prompt = (meta_dir / "harbor" / "prompt.md").read_text()
assert "/app/workspace" in prompt
assert "/app/candidate" not in prompt
command = json.loads((meta_dir / "harbor" / "command.json").read_text())
assert command[command.index("--artifact") + 1] == "/app/workspace"
assert command[command.index("--workdir") + 1] == "/app/workspace"
```

- [ ] **Step 2: Add a failing evidence-completeness test**

Create archive and trace evidence before `run_agent`, then have the fake Harbor process assert they exist:

```python
(checkout / "archive.jsonl").write_text('{"genid":"0"}\n')
evidence = run_dir / "trace_analyzer" / "evidence"
evidence.mkdir(parents=True)
(evidence / "raw_traces.jsonl").write_text('{"task_name":"task-a"}\n')
```

The fake Harbor script must fail unless `/app/workspace/archive.jsonl`, the current generation trace, and `.git` are present in `source/workspace`.

- [ ] **Step 3: Run focused tests to verify RED**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py::test_harbor_meta_agent_round_trips_target_and_writes_artifacts
```

Expected: FAIL because the command still uses `/app/candidate` and the task lacks a full workspace.

- [ ] **Step 4: Implement full-workspace assembly**

Replace `_EditableBundle` with a bundle that owns a complete workspace:

```python
class _WorkspaceBundle:
    __slots__ = ("staging", "task_root", "workspace", "roots", "before")

    def __init__(self, staging: Path, task_root: Path, workspace: Path, roots: tuple[str, ...], before):
        self.staging = staging
        self.task_root = task_root
        self.workspace = workspace
        self.roots = roots
        self.before = before
```

Implement `_prepare_bundle` with these exact behaviors:

```python
staging = Path(tempfile.mkdtemp(prefix="evolve-harbor-"))
task_root = staging / "task"
agent_workspace = task_root / "workspace"
git(ctx.workspace, "clone", "--quiet", "--no-hardlinks", str(ctx.workspace), str(agent_workspace))
git(agent_workspace, "checkout", "--quiet", "--detach", head_commit(checkout))
copy selected-parent working files from checkout, excluding `.git`, `runs`, and `archive.jsonl`
copy experiment `archive.jsonl` and `runs`, excluding `runs/worktrees` and Harbor `jobs`
ensure the current `ctx.run_dir` is present at `runs/gen-<ctx.genid>`
before = _tree_manifest(agent_workspace)
```

Use `tempfile.mkdtemp` outside the experiment workspace so evidence copying cannot recurse into its own staging tree.

- [ ] **Step 5: Change Harbor workdir and artifact paths**

Set:

```python
_ARTIFACT_SOURCE = "/app/workspace"
```

and construct the editing command with:

```python
"--workdir", "/app/workspace"
```

Keep evidence-only `run_readonly_agent` at `/app`; it does not need a repository artifact.

- [ ] **Step 6: Implement trusted comparison and root-only installation**

Implement a manifest that ignores runtime/output channels:

```python
_IGNORED_OUTPUTS = {".git", "runs", "archive.jsonl"}

def _tree_manifest(root: Path) -> dict[str, tuple[str, str]]:
    # Walk without following symlinks. Skip .git/**, runs/**, archive.jsonl,
    # and mechanism-owned evaluation receipts. Record regular-file SHA-256,
    # directory markers, and symlink targets.
```

In `_install_bundle`:

```python
after = _tree_manifest(returned_workspace)
changed = sorted(path for path in set(bundle.before) | set(after) if bundle.before.get(path) != after.get(path))
violations = check_paths(changed, surface.include, surface.exclude)
if violations:
    raise RuntimeError("returned workspace mutated paths outside surface: " + ", ".join(violations))
for root in bundle.roots:
    _validate_tree(returned_workspace / root)
# transactionally replace only bundle.roots; never install any other returned path
```

- [ ] **Step 7: Run Harbor runner tests to verify GREEN**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add library/meta_agent/runners/harbor.py tests/test_harbor_meta_agent.py
git commit -m "feat: run Harbor meta-agents in disposable workspaces"
```

### Task 2: Reject protected edits and preserve transactional installs

**Files:**
- Modify: `tests/test_harbor_meta_agent.py`
- Modify: `library/meta_agent/runners/harbor.py`

**Interfaces:**
- Consumes: `_tree_manifest` and `_install_bundle` from Task 1.
- Guarantees: only paths matched by the surface policy can persist.

- [ ] **Step 1: Add a failing protected-edit test**

Teach the fake Harbor script a `protected-edit` mode:

```python
if os.environ.get("FAKE_HARBOR_MODE") == "protected-edit":
    (artifact / "evolve.yaml").write_text("experiment: {id: compromised}\n")
```

Add:

```python
def test_harbor_meta_agent_rejects_protected_workspace_edits(tmp_path, monkeypatch):
    checkout, run_dir = _checkout(tmp_path)
    before = (checkout / "evolve.yaml").read_text()
    # install fake Harbor and set FAKE_HARBOR_MODE=protected-edit
    with pytest.raises(AgentCommandError, match="outside surface"):
        _harbor_runner_module().run_agent(checkout, "evidence", _ctx(checkout, run_dir))
    assert (checkout / "evolve.yaml").read_text() == before
    assert (checkout / "target" / "agent.py").read_text() == "print('parent')\n"
```

- [ ] **Step 2: Run the protected-edit test to verify RED**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py::test_harbor_meta_agent_rejects_protected_workspace_edits
```

Expected: FAIL until the full-tree comparison rejects `evolve.yaml`.

- [ ] **Step 3: Complete protected-path detection**

Ensure `_tree_manifest` detects additions, modifications, deletions, file-type changes, and symlinks outside ignored runtime trees. Ensure violations are checked before any editable root is moved into the checkout.

- [ ] **Step 4: Adapt rollback and symlink tests to the full workspace**

Build returned fixtures with:

```python
returned = tmp_path / "returned-workspace"
shutil.copytree(bundle.workspace, returned, symlinks=True)
```

Keep the existing assertions that a failure during the second root replacement restores both original roots and that returned symlinks never reach the checkout.

- [ ] **Step 5: Run Harbor tests to verify GREEN**

```bash
uv run pytest -q tests/test_harbor_meta_agent.py
```

Expected: all tests pass, including rollback, source-symlink, returned-symlink, and protected-edit cases.

- [ ] **Step 6: Commit Task 2**

```bash
git add library/meta_agent/runners/harbor.py tests/test_harbor_meta_agent.py
git commit -m "test: enforce disposable workspace surface boundary"
```

### Task 3: Update HyperAgents and AHE prompts

**Files:**
- Create: `tests/test_hyperagents_meta_agent.py`
- Modify: `tests/test_ahe_meta_agent.py`
- Modify: `library/meta_agent/hyperagents.py`
- Modify: `library/meta_agent/ahe.py`

**Interfaces:**
- Both prompt builders advertise `/app/workspace` as the repository root.
- HyperAgents permits justified operator-only proposals while preferring target improvements.

- [ ] **Step 1: Write failing HyperAgents prompt tests**

Add a focused module-loading test that builds a minimal `OperatorContext` and asserts:

```python
prompt = module.build_prompt(checkout, "fallback", ctx)
assert "Repository: /app/workspace" in prompt
assert "/app/workspace/archive.jsonl" in prompt
assert "/app/workspace/runs/gen-1/trace_analyzer/evidence" in prompt
assert "strongly prefer" in prompt.lower()
assert "operator-only" in prompt.lower()
assert "must include at least one substantive `target/**` change" not in prompt
assert str(ctx.workspace) not in prompt
```

- [ ] **Step 2: Extend the AHE prompt test to verify stable evidence paths**

Add assertions:

```python
assert "/app/workspace" in prompt
assert "/app/workspace/runs/gen-1/trace_analyzer/evidence" in prompt
assert "/app/workspace/archive.jsonl" in prompt
assert str(ctx.workspace) not in prompt
```

- [ ] **Step 3: Run prompt tests to verify RED**

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py::test_ahe_prompt_uses_official_decisions_and_required_manifest
```

Expected: FAIL because HyperAgents requires target edits and emits host paths, while AHE lacks stable container paths.

- [ ] **Step 4: Implement the prompt changes**

Use wording equivalent to:

```text
Strongly prefer a substantive target/** improvement in every proposal. An
operator-only proposal is allowed when evidence shows that improving the search
or improvement process is higher leverage; explain how it should benefit later
target proposals. Do not add cosmetic target edits merely to satisfy this
preference.
```

Replace host paths with:

```python
root = "/app/workspace"
current = f"{root}/runs/gen-{ctx.genid}"
```

- [ ] **Step 5: Run prompt tests to verify GREEN**

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add library/meta_agent/hyperagents.py library/meta_agent/ahe.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py
git commit -m "feat: expose complete evidence to evolution strategies"
```

### Task 4: Documentation and full verification

**Files:**
- Modify: `META_AGENTS.md`
- Test: `tests/test_harbor_meta_agent.py`
- Test: `tests/test_hyperagents_meta_agent.py`
- Test: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Documents the actual container path and trust boundary implemented above.

- [ ] **Step 1: Update Harbor runner documentation**

Replace the candidate-bundle description with:

```markdown
The Harbor runner assembles a disposable full experiment repository at
`/app/workspace`. It includes the selected parent, Git history, archive, prior
runs, feedback, and raw traces. The agent works there normally. On return, the
host rejects protected tracked changes and transactionally imports only
configured editable roots; returned history and runtime evidence are discarded.
```

- [ ] **Step 2: Run formatting and focused verification**

```bash
uv run ruff check library/meta_agent/runners/harbor.py library/meta_agent/hyperagents.py library/meta_agent/ahe.py tests/test_harbor_meta_agent.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py
uv run pytest -q tests/test_harbor_meta_agent.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py tests/test_hyperagents_semantics.py tests/test_ahe_trace_analyzer.py
```

Expected: no Ruff findings and all focused tests pass.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Review the final diff**

```bash
git diff --check
git status --short
git diff --stat HEAD~3..HEAD
```

Expected: no whitespace errors; only the planned runner, strategy, tests, and documentation files changed.

- [ ] **Step 5: Commit documentation if it is not already included**

```bash
git add META_AGENTS.md
git commit -m "docs: describe disposable Harbor workspaces"
```
