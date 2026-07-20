# Evaluation Package Design

## Goal

Replace the ambiguous sibling modules `evaluation.py` and `evaluator.py` with
one `evolve.evaluation` package whose internal filenames describe what they
contain. Preserve the existing separation between pure result classification
and side-effectful evaluation execution. This is an organizational refactor;
evaluation behavior and persisted record formats must not change.

## Package Structure

```text
src/evolve/evaluation/
├── __init__.py
├── execution.py
└── results.py
```

`results.py` owns the values and rules produced by evaluation:

- `Outcome`
- `CANONICAL_OUTCOMES`
- `TrialResult`
- `EvaluationRecord`
- `evaluation_status()`
- `classify_evaluation()`

It remains a pure module with only standard-library dependencies. Archive,
task-vector, reporting, and selection code may depend on these definitions
without importing Git, subprocess, filesystem, or runtime behavior.

`execution.py` owns how an evaluation is performed:

- `evaluate()`
- `EvaluationInterrupted`
- detached-worktree setup and cleanup
- evaluator-tree and runtime fingerprinting
- attempt directory allocation
- evaluator script invocation
- task-vector, cost, setup-outcome, and artifact loading
- conversion of collected evidence into an `EvaluationRecord`

`execution.py` depends on `results.py`; `results.py` never depends on
`execution.py`.

`__init__.py` is the result facade. It re-exports the pure result API currently
used outside the package, while execution callers import explicitly from
`evolve.evaluation.execution`. Keeping execution out of the eager package
facade prevents archive and configuration imports from forming a cycle:

```python
from evolve.evaluation import (
    CANONICAL_OUTCOMES,
    EvaluationRecord,
    Outcome,
    TrialResult,
    classify_evaluation,
    evaluation_status,
)

from evolve.evaluation.execution import EvaluationInterrupted, evaluate
```

Private execution helpers remain importable from
`evolve.evaluation.execution` only where focused tests need them.

## Data Flow

`driver.py` calls `evaluation.execution.evaluate()`. Execution collects
evidence in an isolated checkout, converts the task vector to `TrialResult`
values, and calls `results.classify_evaluation()`. The resulting
`EvaluationRecord` returns to the driver and is persisted by `archive.py`.

The dependency direction is therefore:

```text
driver/archive/task_vectors
        ↓
evolve.evaluation result facade
        ↓
results.py ← execution.py
```

## Migration

1. Move the current `evaluation.py` definitions into `evaluation/results.py`.
2. Move the current `evaluator.py` implementation into
   `evaluation/execution.py`.
3. Move `EvaluationInterrupted` from the result definitions to execution,
   because it represents execution lifecycle control rather than persisted
   evaluation data.
4. Add the pure result facade exports in `evaluation/__init__.py`; import
   execution APIs explicitly from `evaluation.execution`.
5. Replace imports from `evolve.evaluator` with imports from
   `evolve.evaluation.execution`; retain existing result imports from
   `evolve.evaluation` through the facade.
6. Update focused tests that intentionally import private execution helpers to
   use `evolve.evaluation.execution`.
7. Update the pinned module list in `tests/test_coherence.py` and the README
   source map for the package paths.
8. Remove the two superseded top-level modules. Do not leave compatibility
   shims, because the repository requires exactly one implementation of each
   mechanism concept.

## Error Handling

The refactor preserves all current behavior:

- evaluator-tree mismatches still fail before consuming an attempt identity;
- ordinary execution errors still produce infrastructure-failed records;
- cancellation still carries a cancelled record through
  `EvaluationInterrupted` for append-before-reraise;
- cleanup still removes detached worktrees on every exit path;
- invalid or incomplete evidence still follows the same classification
  precedence in `classify_evaluation()`.

No exception type, record field, outcome value, or failure precedence changes.

## Testing

Tests must establish both compatibility and the intended boundary:

- existing evaluation-record classification tests continue to pass through
  the package facade;
- evaluator execution and lifecycle tests continue to pass after import
  updates;
- archive, task-vector, selection-certification, runtime, and driver tests
  verify downstream compatibility;
- coherence tests recognize the three package modules and reject the removed
  top-level modules;
- the full test suite and Ruff checks pass.

## Non-goals

- changing evaluation semantics, scoring, retry policy, or record schemas;
- redesigning the evaluator shell contract;
- renaming public classes or functions;
- introducing compatibility aliases for `evolve.evaluator`;
- refactoring unrelated validation or candidate-selection code.
