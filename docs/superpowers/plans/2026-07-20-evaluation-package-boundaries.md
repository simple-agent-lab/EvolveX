# Evaluation Package Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the evaluation package by moving task evidence and identity into it while preserving every evaluator, archive, scoring, and selection behavior.

**Architecture:** `evaluation/evidence.py` validates evaluator JSON and converts it to the pure types in `evaluation/results.py`. `evaluation/identity.py` becomes the only constructor of archived evaluation identity; `population.py` delegates frozen-baseline identity to it, while top-level `splits.py` continues to own cross-cutting dataset partition and selection behavior.

**Tech Stack:** Python 3.11+, dataclasses, PyYAML, pytest, Ruff, Hatchling package layout.

## Global Constraints

- Preserve the external `task_vector.json` filename and archived `task_vector` field.
- Preserve existing `task_set_hash` values for equivalent evaluator configuration.
- Keep `population.py` and `splits.py` at `src/evolve/`.
- Do not add compatibility shims for removed top-level Python modules.
- Run focused tests after every boundary change and the full suite before completion.

---

### Task 1: Integrate Current Mainline Cleanup

**Files:**
- Merge: `main` into `codex/evaluation-package`
- Resolve if needed: `README.md`
- Resolve if needed: `tests/test_coherence.py`
- Resolve if needed: `docs/superpowers/specs/2026-07-20-evaluation-package-design.md`

**Interfaces:**
- Consumes: candidate-module cleanup at `main`
- Produces: one clean branch containing both candidate and evaluation package layouts

- [ ] **Step 1: Verify the worktree is clean**

Run: `git status --short --branch`

Expected: branch header only.

- [ ] **Step 2: Merge current main**

Run: `git merge --no-edit main`

Expected: merge succeeds, or conflicts are limited to documentation and the pinned module inventory.

- [ ] **Step 3: Resolve conflicts by preserving both completed refactors**

The resulting module inventory must contain:

```python
"candidate_smoke.py",
"evaluation/__init__.py",
"evaluation/execution.py",
"evaluation/results.py",
```

It must not restore `asset_discovery.py`, `candidate_runtime.py`, `evaluation.py`, or `evaluator.py`.

- [ ] **Step 4: Verify the integrated baseline**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_coherence.py tests/test_candidate_smoke.py tests/test_m1_evaluator_invariants.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit only if conflict resolution required a commit beyond Git's merge commit**

```bash
git add README.md tests/test_coherence.py docs/superpowers/specs/2026-07-20-evaluation-package-design.md
git commit -m "merge: integrate candidate module cleanup"
```

### Task 2: Establish One Evaluation Identity Implementation

**Files:**
- Create: `src/evolve/evaluation/identity.py`
- Delete: `src/evolve/task_sets.py`
- Modify: `src/evolve/population.py`
- Modify: `src/evolve/evaluation/execution.py`
- Modify: `tests/test_selection_certification.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: `evolve.git.git`, evaluator dictionaries, checkout paths, immutable `gen/0` Git contents
- Produces: `TaskSetIdentity`, `effective_task_set_identity()`, and `fixed_evaluation_identity()` from `evolve.evaluation.identity`

- [ ] **Step 1: Add equivalence and delegation tests**

Add a focused assertion that checkout identity remains byte-for-byte compatible:

```python
identity = effective_task_set_identity(
    checkout,
    {"dataset": "suite@1", "k": 2, "task_names": ["task-b", "task-a"]},
)
expected_payload = b'{"attempts":2,"dataset":"suite@1","tasks":["task-a","task-b"]}'
assert identity.digest == hashlib.sha256(expected_payload).hexdigest()
```

Add a population boundary assertion:

```python
source = (ROOT / "src/evolve/population.py").read_text()
assert "hashlib" not in source
assert "json.dumps" not in source
```

- [ ] **Step 2: Run the new tests to verify the old boundary fails**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_m1_evaluator_invariants.py tests/test_selection_certification.py`

Expected: the compatibility assertion passes and the population ownership assertion fails because hashing still lives in `population.py`.

- [ ] **Step 3: Move and centralize identity code**

Create `evaluation/identity.py` with these public signatures:

```python
@dataclass(frozen=True)
class TaskSetIdentity:
    digest: str
    members: tuple[str, ...]


def task_set_identity(
    dataset: object,
    attempts: object,
    members: tuple[str, ...],
    *,
    purpose: str = "candidate",
) -> TaskSetIdentity: ...


def effective_task_set_identity(
    checkout: Path,
    evaluator: dict[str, Any],
    *,
    purpose: str = "candidate",
) -> TaskSetIdentity: ...


def fixed_evaluation_identity(workspace: Path) -> dict[str, str] | None: ...
```

`task_set_identity()` must serialize exactly:

```python
payload = {
    "dataset": str(dataset),
    "attempts": int(attempts),
    "tasks": list(tuple(sorted(set(members)))),
}
if purpose == "anchor":
    payload["split"] = "sealed"
digest = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
```

Move the Git-tree readers from `population.py` into `identity.py`. Both the checkout and frozen candidate adapters must call `task_set_identity()` rather than serialize their own payloads.

- [ ] **Step 4: Update imports and delete the old module**

Use:

```python
from .evaluation.identity import fixed_evaluation_identity
```

in `population.py`, and:

```python
from .identity import effective_task_set_identity
```

in `evaluation/execution.py`. Delete `src/evolve/task_sets.py` without a shim.

- [ ] **Step 5: Run identity, population, and evaluator tests**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_m1_evaluator_invariants.py tests/test_selection_certification.py`

Expected: both focused test files pass.

- [ ] **Step 6: Commit the identity boundary**

```bash
git add src/evolve/evaluation/identity.py src/evolve/evaluation/execution.py src/evolve/population.py src/evolve/task_sets.py tests/test_m1_evaluator_invariants.py tests/test_selection_certification.py
git commit -m "refactor: centralize evaluation identity"
```

### Task 3: Move Task-Result Evidence Into the Package

**Files:**
- Create: `src/evolve/evaluation/evidence.py`
- Delete: `src/evolve/task_vectors.py`
- Modify: `src/evolve/evaluation/execution.py`
- Modify: `library/record/jsonl.py`
- Modify: `tests/test_task_vectors.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: evaluator JSON payloads and `Outcome`/`TrialResult` from `evaluation/results.py`
- Produces: unchanged `TaskVectorError`, `normalize_task_vector()`, `validate_task_vector()`, `trial_results()`, and `task_passed()` behavior from `evolve.evaluation.evidence`

- [ ] **Step 1: Change focused tests to the intended import boundary**

Replace top-level imports with:

```python
from evolve.evaluation.evidence import (
    TaskVectorError,
    normalize_task_vector,
    task_passed,
    trial_results,
)
```

- [ ] **Step 2: Run tests to verify the package module is missing**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py`

Expected: collection fails with `ModuleNotFoundError: evolve.evaluation.evidence`.

- [ ] **Step 3: Move the implementation unchanged except for its relative import**

`evaluation/evidence.py` must import:

```python
from .results import Outcome, TrialResult
```

All validation branches, exception messages, legacy normalization, trial ordering, and pass/fail semantics must remain unchanged.

- [ ] **Step 4: Update production consumers and remove the old module**

Use:

```python
from .evidence import trial_results, validate_task_vector
```

in `evaluation/execution.py`, and:

```python
from evolve.evaluation.evidence import task_passed
```

in `library/record/jsonl.py`. Delete `src/evolve/task_vectors.py` without a shim.

- [ ] **Step 5: Run evidence and record tests**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py tests/test_m5_record_verb.py`

Expected: all tests pass with unchanged assertions and exception messages.

- [ ] **Step 6: Commit the evidence boundary**

```bash
git add src/evolve/evaluation/evidence.py src/evolve/evaluation/execution.py src/evolve/task_vectors.py library/record/jsonl.py tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py
git commit -m "refactor: move evaluation evidence into package"
```

### Task 4: Clarify Split Digest Naming and Enforce the Source Tree

**Files:**
- Modify: `src/evolve/splits.py`
- Modify: `tests/test_m8_dataset_splits.py`
- Modify: `tests/test_coherence.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-20-evaluation-package-design.md`

**Interfaces:**
- Consumes: split name and deterministically selected task names
- Produces: `split_selection_digest()`, `configured_split_selection_digest()`, and the unchanged `task_set_hash` runtime artifact filename

- [ ] **Step 1: Update split tests to require explicit operational naming**

Import and assert:

```python
from evolve.splits import split_selection_digest

assert split_selection_digest("gate", ["a"]) != split_selection_digest("sealed", ["a"])
```

Update existing `task_set_hash()` calls in split tests to `split_selection_digest()`.

- [ ] **Step 2: Run the split test to verify the new name is missing**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_m8_dataset_splits.py`

Expected: collection fails because `split_selection_digest` is not defined.

- [ ] **Step 3: Rename only the Python API**

In `splits.py`, define:

```python
def split_selection_digest(split_name: str, names: list[str]) -> str:
    payload = json.dumps(
        {"split": split_name, "tasks": sorted(names)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()
```

Rename `configured_task_set_hash()` to `configured_split_selection_digest()` and update internal calls. Continue writing the evaluator shell artifact at `run_dir / "task_set_hash"`; its filename is an external compatibility constraint.

- [ ] **Step 4: Update the pinned module inventory and source map**

The approved source inventory must include:

```python
"evaluation/__init__.py",
"evaluation/evidence.py",
"evaluation/execution.py",
"evaluation/identity.py",
"evaluation/results.py",
```

and exclude `task_sets.py` and `task_vectors.py`. Document `evidence.py` as evaluator-output validation and `identity.py` as evaluation comparability.

- [ ] **Step 5: Run boundary and split tests**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q tests/test_m8_dataset_splits.py tests/test_coherence.py tests/test_import_hygiene.py`

Expected: all tests pass and no removed top-level module remains importable.

- [ ] **Step 6: Run full verification**

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run pytest -q`

Expected: all tests pass.

Run: `UV_CACHE_DIR=/tmp/evolve-uv-cache uv run ruff check .`

Expected: `All checks passed!`

- [ ] **Step 7: Commit final consistency changes**

```bash
git add README.md src/evolve/splits.py tests/test_m8_dataset_splits.py tests/test_coherence.py docs/superpowers/specs/2026-07-20-evaluation-package-design.md
git commit -m "refactor: complete evaluation package boundaries"
```
