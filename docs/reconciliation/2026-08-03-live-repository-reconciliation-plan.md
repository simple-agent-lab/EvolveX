# Live Repository Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture consistent, non-blocking repository cutoffs and construct a
reviewable reconciliation branch from GitHub `main`, the clean Codex-target
feature branch, and the replicated Harbor parser correction.

**Architecture:** Private raw cutoffs live under the primary checkout's
`.codex/reconciliation/` directory and never enter Git. The isolated
reconciliation worktree contains only sanitized inventories, deliberate
integration commits, and verification records. Active MacBook, DevBox, and
DevBoxS checkouts are read-only inputs throughout this plan.

**Tech Stack:** Git, Git worktrees, Python 3.12 standard library, `uv`, pytest,
ruff, ty, SSH, GitHub CLI.

## Global Constraints

- Do not pause an active repository-writing task.
- Do not switch, stash, reset, clean, commit, or update an input worktree.
- Do not delete, move, or rewrite local branches, bundles, snapshots, or
  experiment outputs.
- Do not read, hash, copy, stage, or print the contents of `auth.json`, `.env`,
  credential stores, private keys, or token files.
- Keep raw patches and unpublished files under `.codex/reconciliation/` with
  directory mode `0700` and file mode `0600`; never add them to Git.
- Use the exact private cutoff session directory
  `.codex/reconciliation/20260803T160000+0800/`. Refuse to overwrite it if it
  already exists; each manifest still records its actual runtime timestamps.
- Copy selected source/configuration/result-metadata files only when they are
  at most 5 MiB. Inventory larger payloads without copying them.
- Retry a moving worktree at most three times, then retain a cutoff marked
  `consistent: false` instead of blocking its writer.
- Integrate exact commits `ebb00de125244b6a416006524fcdfd2dccdb17bb` and
  `3a2d419cd93dad5d5cc83ef91a60ae7049cae797` only after re-verifying the live
  GitHub branch tips.
- Do not merge dirty Tau3 files in this plan.
- Do not push the reconciliation branch or update DevBox/DevBoxS `main` in
  this plan.

---

## File Map

### Private, never committed

- `/Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/tools/capture_cutoff.py`
  — capture local and SSH Git state, selected files, and consistency metadata.
- `/Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/tools/test_capture_cutoff.py`
  — isolated tests for secret exclusion, size policy, and retry behavior.
- `/Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/20260803T160000+0800/`
  — raw manifests, patches, copied small files, and bulk-location inventories.

### Committed on `codex/reconcile-ground-truth-20260803`

- `docs/reconciliation/2026-08-03-repository-inventory.md`
  — sanitized classification of GitHub, MacBook, DevBox, and DevBoxS state.
- `docs/reconciliation/2026-08-03-reconciliation-verification.md`
  — merge, test, security, and retention evidence.
- `tests/test_harbor_parse_score.py`
  — regression test proving the runtime trial limit overrides a larger split.
- `scaffolds/evaluators/harbor/parse_score.py`
  — minimal runtime-override ordering correction.

---

### Task 1: Build and verify the private cutoff collector

**Files:**

- Create (private): `.codex/reconciliation/tools/capture_cutoff.py`
- Create (private): `.codex/reconciliation/tools/test_capture_cutoff.py`

**Interfaces:**

- Produces:
  `capture_local(source: Path, destination: Path, label: str, max_attempts: int = 3) -> dict[str, object]`
- Produces:
  `capture_remote(host: str, source: PurePosixPath, destination: Path, label: str) -> dict[str, object]`
- Produces:
  `discover_worktrees(common_checkout: Path) -> list[Path]`
- Produces:
  `verify_archive(destination: Path) -> list[str]`, returning an empty list on
  success and one error string per mismatch.
- CLI subcommands: `local`, `local-all`, `remote`, `remote-many`,
  `remote-roots`, and `verify`.

- [ ] **Step 1: Create the private tool directory with restrictive permissions**

Run from `/Users/bytedance/Desktop/simple-evolve-agent`:

```bash
mkdir -p .codex/reconciliation/tools
chmod 700 .codex/reconciliation .codex/reconciliation/tools
```

Verify that `.codex/` remains untracked and that no path below it is staged:

```bash
git status --short .codex
git diff --cached --name-only -- .codex
```

- [ ] **Step 2: Write focused collector tests**

Create `test_capture_cutoff.py` with `unittest`. The tests must initialize a
temporary Git repository using `git init`, configure a local test identity,
commit one file, and cover these exact cases:

```python
def test_small_source_is_copied_but_secret_and_large_file_are_not(self):
    # Modify tracked.py; add notes.py, auth.json, a >5 MiB results.json, and
    # .codex/reconciliation/loop.txt.
    # Capture once and assert:
    # - unstaged.patch exists;
    # - copied/notes.py has the original SHA-256;
    # - auth.json is listed as copied=false with no digest;
    # - the secret marker does not occur anywhere in the archive;
    # - results.json is inventory-only and has no copied payload.
    # - no file below .codex is copied or recursively inventoried.

def test_capture_retries_after_a_moving_pre_post_boundary(self):
    # Patch the attempt-state reader to return A/B for attempt 1 and C/C for
    # attempt 2. Assert attempts==2 and consistent is true.

def test_capture_retains_third_moving_attempt_as_concurrent(self):
    # Return a different post-state for all three attempts. Assert attempts==3,
    # consistent is false, and both final boundary states are retained.

def test_verify_archive_detects_a_tampered_copy(self):
    # Capture notes.py, change the archived copy, and assert verify_archive()
    # reports its relative path.
```

- [ ] **Step 3: Run the tests and verify they fail before implementation**

```bash
uv run python .codex/reconciliation/tools/test_capture_cutoff.py -v
```

Expected: failures because `capture_cutoff.py` and its interfaces do not yet
exist.

- [ ] **Step 4: Implement local state capture**

Implement these immutable policy values in `capture_cutoff.py`:

```python
MAX_COPY_BYTES = 5 * 1024 * 1024
COPY_SUFFIXES = {
    ".py", ".sh", ".md", ".toml", ".yaml", ".yml", ".json", ".jsonl",
    ".csv", ".txt", ".xml", ".lock", ".diff", ".patch",
}
COPY_ROOTS = {".", "docs", "scripts", "tests", "reports", "experiments"}
BULK_ROOTS = {
    "analysis_artifacts", "analysis_selected", "terminal-bench-2-50-19-20",
}
SECRET_BASENAMES = {"auth.json", ".env", "credentials", "credentials.json"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
EXCLUDED_ROOTS = {".git", ".venv", ".codex"}
```

Use `subprocess.run(..., check=True, capture_output=True)` with argument lists;
do not invoke a shell. Capture state with these Git commands:

```python
["git", "-C", str(source), "rev-parse", "HEAD"]
["git", "-C", str(source), "rev-parse", "HEAD^{tree}"]
["git", "-C", str(source), "symbolic-ref", "--quiet", "--short", "HEAD"]
["git", "-C", str(source), "status", "--porcelain=v2", "--branch"]
["git", "-C", str(source), "diff", "--binary", "--cached"]
["git", "-C", str(source), "diff", "--binary"]
["git", "-C", str(source), "ls-files", "--others", "--exclude-standard", "-z"]
["git", "-C", str(source), "config", "--get", "remote.origin.url"]
```

The manifest schema must contain `schema_version`, `label`, `source`, `host`,
`started_at`, `completed_at`, `attempts`, `consistent`, `pre_state`,
`post_state`, `patches`, `copied_files`, `inventory_only`, and
`excluded_secret_like`. Serialize JSON using sorted keys and indentation.

Never open secret-like paths. Reject symlinks and special files from copying.
Do not descend into `EXCLUDED_ROOTS`; in particular, excluding `.codex`
prevents the collector from observing or recursively capturing its own output.
For ordinary selected files, copy with `shutil.copyfile`, force mode `0600`,
and verify the destination SHA-256 against the source digest observed for the
accepted boundary. Write each attempt into a new directory and retain failed
attempt metadata.

- [ ] **Step 5: Implement read-only SSH metadata capture**

`capture_remote()` must use argument-list subprocess calls beginning with
`["ssh", host, "git", "-C", str(source)]`. Capture the same Git identity,
status, and binary diff outputs as local capture. Run remote sources in
metadata-only mode: do not read or copy remote untracked contents. Record
untracked path names from porcelain output, but exclude secret-like basenames
from printed logs. For a remote secret-like path, record only remote `stat`
metadata (relative path, mode, size, and modification time) and never invoke a
content-reading command for that path.

The remote manifest must contain the SSH host, source path, command exit codes,
and `consistent: true` only when the pre/post `HEAD`, status, and patch hashes
match.

- [ ] **Step 6: Implement discovery and archive verification**

`discover_worktrees()` must parse `git worktree list --porcelain` and return
every `worktree ` path exactly once. `remote-many` must call
`capture_remote()` once per repeated `--source` argument. `remote-roots` must
list only immediate child directories with remote `find`, filter requested
patterns locally with `fnmatch`, and record remote `stat` plus optional `du -s`
output. It must support a no-size mode that records an explicit unmeasured size
instead of recursively walking a host under load; it must not copy or hash
payloads. `verify_archive()` must re-hash every copied
file and patch listed in manifests, confirm restrictive permissions, and
report any missing or mismatched item.

The CLI must create its cutoff directory with mode `0700` and must set file
creation mode to owner-only before writing any raw data.

- [ ] **Step 7: Run the private collector tests**

```bash
uv run python .codex/reconciliation/tools/test_capture_cutoff.py -v
```

Expected after the compatibility and load-shedding regressions added during
execution: 12 tests pass.

- [ ] **Step 8: Confirm the private helper is not staged**

```bash
git diff --cached --name-only -- .codex
git ls-files --error-unmatch \
  .codex/reconciliation/tools/capture_cutoff.py
```

Expected: the first command prints nothing; the second exits nonzero because
the helper is private and untracked.

---

### Task 2: Capture MacBook worktree cutoffs without pausing writers

**Files:**

- Create (private): `.codex/reconciliation/20260803T160000+0800/macbook/**`

**Interfaces:**

- Consumes: `capture_cutoff.py local-all`
- Produces: one manifest per discovered worktree and a cutoff-level index

- [ ] **Step 1: Record the cutoff identifier and initial worktree list**

Use the approved session identifier `20260803T160000+0800`; do not overwrite
an existing directory. Run:

```bash
git worktree list --porcelain
```

Save this command's output through the private collector, not through shell
redirection.

- [ ] **Step 2: Capture every discovered worktree**

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py local-all \
  --common-checkout /Users/bytedance/Desktop/simple-evolve-agent \
  --output /Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/20260803T160000+0800/macbook \
  --max-attempts 3
```

The collector must prioritize dirty worktrees but must also create identity
manifests for clean worktrees. It must not treat a changing worktree as a
failure of the whole cutoff.

- [ ] **Step 3: Verify the MacBook archive**

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py verify \
  --archive /Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/20260803T160000+0800/macbook
```

Expected: zero copied-file or patch mismatches. Concurrent worktrees may be
reported as `consistent: false` but must include all three attempt records.

- [ ] **Step 4: Check secret handling**

Inspect the manifest entry for the root checkout's `auth.json`. It must contain
only relative path, size, mode, modification time, `copied: false`, and no
content digest. Search the private archive for known secret filename patterns;
do not search for or print secret values.

---

### Task 3: Capture DevBox and DevBoxS source metadata and artifact locations

**Files:**

- Create (private): `.codex/reconciliation/20260803T160000+0800/devbox/**`
- Create (private): `.codex/reconciliation/20260803T160000+0800/devboxs/**`

**Interfaces:**

- Consumes: `capture_cutoff.py remote`
- Produces: remote checkout manifests and host-level bulk-location inventories

- [ ] **Step 1: Capture the GitHub-backed `main` checkouts**

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py remote \
  --host DevBox \
  --source /data00/home/zimuwang/simple-evolve-agent-main \
  --output .codex/reconciliation/20260803T160000+0800/devbox/main
uv run python .codex/reconciliation/tools/capture_cutoff.py remote \
  --host DevBoxS \
  --source /data00/home/zimuwang/simple-evolve-agent-main \
  --output .codex/reconciliation/20260803T160000+0800/devboxs/main
```

Record `HEAD`, the locally remembered `origin/main`, status, and origin URL.
Do not fetch or update either checkout.

- [ ] **Step 2: Capture the detached Codex-target snapshots**

Run this exact source set once with `--host DevBox` and once with
`--host DevBoxS`, changing only the final output host directory:

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py remote-many \
  --host DevBox \
  --output .codex/reconciliation/20260803T160000+0800/devbox/codex-target \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r2 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r3 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r4 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260731-r5 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260731-r6
uv run python .codex/reconciliation/tools/capture_cutoff.py remote-many \
  --host DevBoxS \
  --output .codex/reconciliation/20260803T160000+0800/devboxs/codex-target \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r2 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r3 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730-r4 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260731-r5 \
  --source /data00/home/zimuwang/simple-evolve-agent-codex-target-20260731-r6
```

The expected `r6` tracked change is
`scaffolds/evaluators/harbor/parse_score.py`. Preserve its binary patch in the
private archive and record its SHA-256. Do not infer equality between hosts;
compare their independently captured patch hashes.

- [ ] **Step 3: Capture legacy/repository-adjacent metadata**

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py remote-many \
  --host DevBox \
  --output .codex/reconciliation/20260803T160000+0800/devbox/adjacent \
  --source /data00/home/zimuwang/simple-agent-lab \
  --source /data00/home/zimuwang/tau3-adapter-safe-worktree
```

Classify them by their own Git root, origin URL, and file layout. Do not merge
them into `simple-evolve-agent` merely because their contents are related.

- [ ] **Step 4: Inventory top-level experiment roots without copying payloads**

On each host, record path, mode, modification time, and observed allocated size
for top-level directories matching `simple-evolve-agent*`, `tau3-*`, and
`harbor-*`:

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py remote-roots \
  --host DevBox \
  --home /data00/home/zimuwang \
  --output .codex/reconciliation/20260803T160000+0800/devbox/bulk-roots.json \
  --pattern 'simple-evolve-agent*' --pattern 'tau3-*' --pattern 'harbor-*'
uv run python .codex/reconciliation/tools/capture_cutoff.py remote-roots \
  --host DevBoxS \
  --home /data00/home/zimuwang \
  --output .codex/reconciliation/20260803T160000+0800/devboxs/bulk-roots.json \
  --pattern 'simple-evolve-agent*' --pattern 'tau3-*' --pattern 'harbor-*'
```

Do not traverse `.git`, Docker storage, caches, task datasets, or per-trial
payloads for copying.

Mark each size as an observation that may change during active jobs. Hash only
small top-level summary metadata already covered by the inclusion policy.

- [ ] **Step 5: Verify both remote archives locally**

Run the collector's `verify` command over `devbox/` and `devboxs/`. Confirm that
all command failures are represented explicitly and that neither host was
modified.

---

### Task 4: Commit the sanitized repository inventory

**Files:**

- Create: `docs/reconciliation/2026-08-03-repository-inventory.md`

**Interfaces:**

- Consumes: private cutoff manifests only
- Produces: a secret-free classification used by integration and retention

- [ ] **Step 1: Write the inventory from captured facts**

Use these sections and tables:

```markdown
# Repository Inventory at 20260803T160000+0800

## Canonical anchors
| Role | Ref | Commit | Verification source |

## MacBook worktrees
| Path | Branch | HEAD | Dirty entries | Cutoff consistency | Classification |

## DevBox source checkouts
| Path | Branch/detached | HEAD | Dirty summary | Classification |

## DevBoxS source checkouts
| Path | Branch/detached | HEAD | Dirty summary | Classification |

## Replicated unpublished changes
## Bulk artifact retention locations
## Secret-like excluded paths
## Deferred concurrent work
```

Use only paths, commit IDs, classifications, counts, sizes, and hashes. Mention
`auth.json` only as an excluded path; never include its content or digest.

- [ ] **Step 2: Verify the inventory against the raw manifests**

Check every table row back to its source manifest. Confirm that GitHub `main`
and the Codex-target feature values came from the live API verification rather
than a stale remote-tracking ref.

- [ ] **Step 3: Scan the proposed inventory for secret material**

Run this credential-value scan over the single inventory file:

```bash
rg -n '(gho_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|OPENAI_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]+|password[[:space:]]*=[[:space:]]*[^[:space:]]+)' \
  docs/reconciliation/2026-08-03-repository-inventory.md
```

Expected: no matches. A separate filename scan may match the intentionally
documented excluded path `auth.json`; that path-only match is acceptable.

- [ ] **Step 4: Commit the sanitized inventory**

```bash
git add docs/reconciliation/2026-08-03-repository-inventory.md
git diff --cached --check
git commit -m "docs: inventory repository reconciliation sources"
```

---

### Task 5: Merge the exact Codex-target feature history

**Files changed by the expected clean merge:**

- Modify: `scaffolds/evaluators/harbor/engine.sh`
- Modify: `seeds/codex/agent.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_m7_codex_seed.py`

**Interfaces:**

- Consumes: GitHub feature commit
  `3a2d419cd93dad5d5cc83ef91a60ae7049cae797`
- Produces: a non-fast-forward merge commit on the reconciliation branch

- [ ] **Step 1: Re-verify live branch tips**

```bash
gh api repos/simple-agent-lab/simple-evolve-agent/branches/main --jq .commit.sha
gh api 'repos/simple-agent-lab/simple-evolve-agent/branches/codex%2Fcodex-target-experiments' --jq .commit.sha
```

Expected values are `ebb00de125244b6a416006524fcdfd2dccdb17bb` and
`3a2d419cd93dad5d5cc83ef91a60ae7049cae797`. If either value differs, record
the observed value and stop this task before merging.

- [ ] **Step 2: Confirm the merge shape**

```bash
git merge-base HEAD 3a2d419cd93dad5d5cc83ef91a60ae7049cae797
git diff --name-only origin/main...3a2d419cd93dad5d5cc83ef91a60ae7049cae797
```

Expected merge base: `e23a847f2358ac22246372bff94a163903d71c7b`.
Expected effective feature delta: the four files listed above. The planning
merge simulation reported no conflict.

- [ ] **Step 3: Create the history-preserving merge commit**

```bash
git merge --no-ff 3a2d419cd93dad5d5cc83ef91a60ae7049cae797 \
  -m "merge: reconcile codex-target experiments"
```

Do not use blanket `ours` or `theirs` conflict selection. An unexpected
conflict blocks this step and must be recorded before any path is edited.

- [ ] **Step 4: Run focused feature tests**

```bash
uv run pytest -q \
  tests/test_harbor_evaluator_template.py \
  tests/test_m7_codex_seed.py
uv run ruff check \
  seeds/codex/agent.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_m7_codex_seed.py
```

Expected: all focused tests and lint checks pass.

- [ ] **Step 5: Record the merge result in the inventory**

Add the merge commit ID, effective changed paths, and focused verification
results to the sanitized inventory in a separate documentation commit if the
inventory commit already exists.

---

### Task 6: Add the Harbor expected-trial regression fix with red/green proof

**Files:**

- Create: `tests/test_harbor_parse_score.py`
- Modify: `scaffolds/evaluators/harbor/parse_score.py`

**Interfaces:**

- Tests: `_expected_trials(run_dir: Path, env_values: dict[str, str]) -> int`
- Behavior: the live process environment variable
  `EVOLVE_HARBOR_EXPECTED_TRIALS` overrides a larger persisted task split;
  without the live variable, the existing split/env-file fallback remains.

- [ ] **Step 1: Add the exact regression test without the fix**

Create `tests/test_harbor_parse_score.py`:

```python
import importlib.util
import json
import sys
from pathlib import Path

from evolve.config import scaffold_root


def _load_parse_score():
    path = scaffold_root() / "evaluators" / "harbor" / "parse_score.py"
    spec = importlib.util.spec_from_file_location("harbor_parse_score", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_runtime_trial_limit_overrides_larger_selected_pool(tmp_path: Path, monkeypatch) -> None:
    parse_score = _load_parse_score()
    (tmp_path / "task-split.json").write_text(json.dumps({"tasks": [f"task-{i}" for i in range(50)]}))
    monkeypatch.setenv("EVOLVE_HARBOR_EXPECTED_TRIALS", "2")

    assert parse_score._expected_trials(
        tmp_path,
        {"EVOLVE_HARBOR_EXPECTED_TRIALS": "50", "EVOLVE_HARBOR_ATTEMPTS": "1"},
    ) == 2
```

- [ ] **Step 2: Run the regression test and verify the red state**

```bash
uv run pytest -q tests/test_harbor_parse_score.py
```

Expected: fail with an assertion equivalent to `50 == 2`, proving the selected
50-task split currently wins over the runtime limit.

- [ ] **Step 3: Apply the minimal ordering correction**

At the beginning of `_expected_trials()`, before reading `task-split.json`, add:

```python
runtime_expected = os.environ.get("EVOLVE_HARBOR_EXPECTED_TRIALS")
if runtime_expected is not None:
    return max(1, int(runtime_expected))
```

In the final fallback, remove the nested live-environment lookup and retain:

```python
env_values.get("EVOLVE_HARBOR_EXPECTED_TRIALS", env_values.get("EVOLVE_HARBOR_N", "1"))
```

- [ ] **Step 4: Run the green test and relevant evaluator tests**

```bash
uv run pytest -q \
  tests/test_harbor_parse_score.py \
  tests/test_harbor_evaluator_template.py
uv run ruff check \
  scaffolds/evaluators/harbor/parse_score.py \
  tests/test_harbor_parse_score.py
```

Expected: all selected tests and lint checks pass.

- [ ] **Step 5: Confirm the applied correction matches the replicated cutoff**

Compare the final `parse_score.py` SHA-256 with the independently captured
MacBook, DevBox `r6`, and DevBoxS `r6` working-file hashes. Record equality or
the exact mismatch in the inventory; do not assume they match.

- [ ] **Step 6: Commit the regression fix**

```bash
git add \
  scaffolds/evaluators/harbor/parse_score.py \
  tests/test_harbor_parse_score.py
git diff --cached --check
git commit -m "fix: honor runtime Harbor trial limit"
```

---

### Task 7: Produce final verification and retention evidence

**Files:**

- Modify: `docs/reconciliation/2026-08-03-repository-inventory.md`
- Create: `docs/reconciliation/2026-08-03-reconciliation-verification.md`

**Interfaces:**

- Consumes: final branch state and private cutoff manifests
- Produces: review gate; does not push or update server checkouts

- [ ] **Step 1: Re-verify every private archive manifest**

```bash
uv run python .codex/reconciliation/tools/capture_cutoff.py verify \
  --archive /Users/bytedance/Desktop/simple-evolve-agent/.codex/reconciliation/20260803T160000+0800
```

Expected: zero hash or permission mismatches. List any source marked
concurrent; concurrency is acceptable only when its attempt history is intact.

- [ ] **Step 2: Run the complete repository checks**

From the reconciliation worktree:

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ty check
git diff --check origin/main...HEAD
```

Expected: all four project checks pass and Git reports no whitespace errors.

- [ ] **Step 3: Verify isolation and private-data boundaries**

```bash
git status --short --branch
git ls-files .codex
git diff --cached --name-only
```

Expected: the reconciliation worktree has no accidental changes; `.codex`
prints no tracked paths; nothing remains staged. Re-read the primary checkout's
branch and `HEAD` to confirm it was not switched by this workflow. Record
current active-worktree states without requiring them to equal earlier cutoffs.

- [ ] **Step 4: Write the verification report**

Include:

```markdown
# Reconciliation Verification

## Cutoff identity and consistency
## GitHub anchors and merge commit
## Parser red/green evidence
## Full test, lint, and type-check results
## Secret and private-archive boundary
## Retained DevBox and DevBoxS locations
## Concurrent work deferred from integration
## Actions intentionally not performed
```

State exact commands, exit codes, pass counts, commit IDs, and concurrent
cutoff labels. Explicitly state that no push, server update, cleanup, reset,
stash, or deletion occurred.

- [ ] **Step 5: Commit the final sanitized evidence**

```bash
git add \
  docs/reconciliation/2026-08-03-repository-inventory.md \
  docs/reconciliation/2026-08-03-reconciliation-verification.md
git diff --cached --check
git commit -m "docs: verify repository reconciliation"
```

- [ ] **Step 6: Stop at the review boundary**

Report the branch, worktree, commit sequence, cutoff directory, verification
results, and deferred concurrent work. Do not push, update a remote checkout,
or delete an archive. The next action requires explicit review of the completed
reconciliation branch.
