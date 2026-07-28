# Workspace Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one verified canonical branch from the current local `main`, retain essential changes from divergent branches, supersede PR #17 with focused fixes, and remove only artifacts proven redundant.

**Architecture:** Treat `3028f49` as the integration baseline and replay focused changes onto `codex/workspace-consolidation`. Preserve dirty and stash-only state before integration, use one failing regression test per bug fix, replay cohesive branch series commit-by-commit, and postpone destructive cleanup until the consolidated tree passes the complete verification gate.

**Tech Stack:** Git worktrees, Python 3.14, pytest/pytest-xdist, Ruff, ty, uv, GitHub Actions.

## Global Constraints

- Do not merge PR #17 wholesale.
- Preserve all dirty worktree and stash-only material before removing any worktree, branch, stash, or untracked artifact.
- Keep the current local-main proxy, timeout-budget, secret-redaction, verifier-environment, and Harbor configuration behavior.
- Every production bug fix follows red-green TDD.
- A divergent branch is replayed only when each commit remains coherent on the canonical baseline.
- No destructive cleanup happens before full tests, Ruff, and ty pass.

---

### Task 1: Preservation manifest and backups

**Files:**
- Create: `docs/workspace-consolidation/2026-07-28-inventory.md`
- Create outside Git: `.worktrees/_preservation-20260728/*.patch`
- Create outside Git: `.worktrees/_preservation-20260728/*.tar.gz`

**Interfaces:**
- Consumes: local refs, four stashes, dirty linked worktrees, and root untracked artifacts.
- Produces: an auditable inventory plus binary-safe patches/archives that make later cleanup recoverable.

- [x] **Step 1: Record canonical refs and cleanup categories**

Record `main=3028f49`, `origin/main=933450b`, PR #17 commits `6f92fd9` and `5f9179e`, every dirty worktree, all four stashes, and root untracked artifacts in the inventory.

- [x] **Step 2: Export dirty tracked changes**

Run:

```bash
git -C .worktrees/framework-hardening diff --binary --output=.worktrees/_preservation-20260728/framework-hardening.patch
git -C .worktrees/harbor-evaluator-agent-runner diff --binary --output=.worktrees/_preservation-20260728/harbor-evaluator-agent-runner.patch
```

Expected: both patch files are non-empty and pass `git apply --stat`.

- [x] **Step 3: Archive dirty untracked files**

Archive:

```text
.worktrees/current-experiment-lark-report/current_shared_optimizer_experiments_report.xml
.worktrees/harbor-evaluator-agent-runner/src/evolve/agent.py
.worktrees/harbor-evaluator-agent-runner/tests/test_agent_runner.py
.worktrees/harbor-evaluator-agent-runner/tests/test_harbor_evaluator_template.py
```

Expected: a tar listing contains all four paths.

- [x] **Step 4: Export every stash**

Use `git stash show --binary --include-untracked --patch` to create `stash-0.patch` through `stash-3.patch`, and record each stash base commit and subject in the inventory.

- [x] **Step 5: Verify preservation**

Run SHA-256 checks over every preservation file and record them in `SHA256SUMS`.

- [ ] **Step 6: Commit the inventory**

```bash
git add docs/workspace-consolidation/2026-07-28-inventory.md
git commit -m "docs: inventory workspace consolidation state"
```

### Task 2: Port PR #17 ignored-checkout isolation

**Files:**
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `tests/test_harbor_meta_agent.py`
- Modify: `META_AGENTS.md`

**Interfaces:**
- Consumes: a Git checkout and the existing Harbor workspace-copy boundary.
- Produces: `_ignored_checkout_paths(checkout: Path) -> set[str]`, `_checkout_copy_ignore(checkout: Path, ignored: set[str])`, and `_copy_checkout_inputs(checkout: Path, workspace: Path, excluded_roots: set[str]) -> None`.

- [ ] **Step 1: Write the failing nested-ignore regression**

Add a parametrized test for both `expose_gate_data` values. Create ignored root `.venv`, nested `target/.venv`, and another ignored cache; assert none enter the Harbor bundle while tracked source files remain.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/pytest -q -n 0 tests/test_harbor_meta_agent.py -k "omits_gitignored_virtual_environments"
```

Expected: FAIL because nested ignored paths are copied by the current implementation.

- [ ] **Step 3: Implement the minimal checkout-copy filter**

Use `git ls-files --others --ignored --exclude-standard --directory -z` once per bundle, convert paths to checkout-relative POSIX names, and pass a `shutil.copytree` ignore callback through both bundle-copy modes. Retain the existing explicit hidden roots as defense in depth.

- [ ] **Step 4: Verify green**

Run the test from Step 2 and all `tests/test_harbor_meta_agent.py`.

- [ ] **Step 5: Update the boundary documentation**

Document that Harbor omits Git-ignored host state, while local runners remain trusted host commands.

- [ ] **Step 6: Commit**

```bash
git add META_AGENTS.md library/meta_agent/runners/harbor.py tests/test_harbor_meta_agent.py
git commit -m "fix: omit ignored state from Harbor workspaces"
```

### Task 3: Stop Git maintenance from racing Harbor bundle transport

**Files:**
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `tests/test_harbor_meta_agent.py`

**Interfaces:**
- Consumes: `_initialize_sanitized_git(workspace: Path)`.
- Produces: a sanitized repository with repository-local `gc.auto=0` and `maintenance.auto=false`.

- [ ] **Step 1: Write the failing repository-policy test**

Create a Harbor bundle with `expose_gate_data=false` and assert:

```python
assert git(bundle.workspace, "config", "--get", "gc.auto").stdout.strip() == "0"
assert git(bundle.workspace, "config", "--get", "maintenance.auto").stdout.strip() == "false"
```

- [ ] **Step 2: Verify red**

Run the new test alone and confirm the configuration is absent.

- [ ] **Step 3: Implement the minimal policy**

Set both repository-local Git configuration keys immediately after `git init` and before the baseline commit.

- [ ] **Step 4: Verify green and transport regressions**

Run:

```bash
.venv/bin/pytest -q -n 0 tests/test_harbor_meta_agent.py -k "maintenance or multi_root_install or ignored_runtime_tree"
```

- [ ] **Step 5: Commit**

```bash
git add library/meta_agent/runners/harbor.py tests/test_harbor_meta_agent.py
git commit -m "fix: disable maintenance in Harbor bundle repositories"
```

### Task 4: Replay experiment recovery and branching

**Files:**
- Replay commits: `b869117`, `bd5b618`, `6ca2dff`, `71163c4`, `b1d2a16`, `c8d9a73`, `ddc3e29`, `5d1c832`, `ca24d5e`, `04e8e36`, `df4b5cf`
- Test: `tests/test_branch_intent.py`
- Test: recovery-related tests selected by each commit

**Interfaces:**
- Consumes: current canonical archive, tag, worktree, evaluation, and recovery APIs.
- Produces: persisted branch intent, certified-generation branching, safe interrupted-run recovery, and documentation.

- [ ] **Step 1: Replay one commit at a time**

Cherry-pick each listed commit in order. For conflicts, retain current-main runtime budgets, proxy behavior, and evaluation records; apply only the recovery/branching behavior from the replayed commit.

- [ ] **Step 2: Verify after each behavioral commit**

Run the test file modified by that commit plus:

```bash
.venv/bin/pytest -q -n 0 tests/test_branch_intent.py
```

- [ ] **Step 3: Run the recovery gate**

Run:

```bash
.venv/bin/pytest -q -n 0 tests/test_branch_intent.py tests/test_selection_certification.py tests/test_evaluation_lifecycle.py
```

Expected: all pass.

### Task 5: Audit and replay open-source cleanup

**Files:**
- Replay commits: `7cbe294`, `37a93a6`, `0965392`, `27472c3`, `d948ad4`, `899f9fb`, `e6a1249`, `d4eea5b`, `b90ad85`, `e31bb56`, `8c1c052`, `54caea6`, `c02274a`, `2df02bf`, `ddd23b5`, `232db6f`, `3884156`, `4eaf553`, `c236326`, `9abc652`, `c22959e`
- Test: `tests/test_recipe_composition.py`
- Test: `tests/test_coherence.py`
- Test: `tests/test_m0_init.py`

**Interfaces:**
- Consumes: current recipe, workspace initialization, Harbor adapter, and repository-boundary APIs.
- Produces: public-source layout, recipe-driven composition, hardened initialization, and public community documentation.

- [ ] **Step 1: Classify each commit before replay**

For each listed commit, inspect its patch against the canonical tree. Mark it `replay`, `already present`, or `obsolete` in the inventory with a one-sentence reason.

- [ ] **Step 2: Replay only `replay` commits in original order**

Cherry-pick one commit at a time. Never resolve a conflict by replacing a current canonical file wholesale.

- [ ] **Step 3: Verify recipe composition after structural commits**

Run:

```bash
.venv/bin/pytest -q -n 0 tests/test_recipe_composition.py tests/test_coherence.py tests/test_m0_init.py
```

- [ ] **Step 4: Verify source-cleanup acceptance**

Run every test added or modified by the replayed commits.

### Task 6: Full consolidated verification

**Files:**
- No production changes unless verification exposes a separately reproduced defect.

**Interfaces:**
- Consumes: completed consolidation tree.
- Produces: verification evidence suitable for advancing local `main`.

- [ ] **Step 1: Run unit and integration tests**

```bash
.venv/bin/pytest -q
```

Expected: zero failures.

- [ ] **Step 2: Run lint**

```bash
.venv/bin/ruff check .
```

Expected: success.

- [ ] **Step 3: Run type checking**

```bash
.venv/bin/ty check
```

Expected: success.

- [ ] **Step 4: Verify clean state and commit graph**

Confirm the worktree has no untracked or modified files and list all commits relative to `origin/main`.

### Task 7: Cleanup classification and execution

**Files:**
- Update: `docs/workspace-consolidation/2026-07-28-inventory.md`

**Interfaces:**
- Consumes: preservation backups and verified consolidated commit graph.
- Produces: exact keep/delete decisions and a clean primary checkout.

- [ ] **Step 1: Mark safe deletions**

Branches fully contained in the consolidated branch, duplicate worktrees, superseded PR #17 refs, byte-identical artifacts, and fully incorporated stashes may be marked `safe-delete`.

- [ ] **Step 2: Re-verify every destructive target**

Immediately before removal, confirm each worktree is clean or backed up, each branch is an ancestor of the consolidated branch or explicitly classified obsolete, and each stash has a verified preservation patch.

- [ ] **Step 3: Remove only `safe-delete` targets**

Remove exact worktree paths first, then exact local branch names, then exact stash entries from highest index to lowest. Do not use recursive globs.

- [ ] **Step 4: Advance local main**

After user-visible verification evidence, fast-forward local `main` to `codex/workspace-consolidation`. Do not force-push or rewrite `origin/main`.

- [ ] **Step 5: Final audit**

Run:

```bash
git status --short --branch
git worktree list
git branch --all --verbose --no-abbrev
git stash list
```

Expected: clean primary checkout and only intentionally retained refs.
