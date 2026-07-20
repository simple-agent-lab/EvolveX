# Evaluation Package Design

## Goal

Replace the ambiguous sibling modules `evaluation.py` and `evaluator.py` with
one `evolve.evaluation` package whose internal filenames describe what they
contain. Bring task-result validation and evaluation identity into that
package, remove duplicate identity construction from `population.py`, and
preserve the separation between pure classification and side-effectful
execution. Persisted record formats and evaluator output filenames do not
change.

## Package Structure

```text
src/evolve/evaluation/
├── __init__.py
├── evidence.py
├── execution.py
├── identity.py
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
evidence, reporting, and selection code may depend on these definitions
without importing Git, subprocess, filesystem, or runtime behavior.

`evidence.py` owns the boundary between evaluator-produced JSON and canonical
evaluation results:

- `TaskVectorError`
- legacy task-vector normalization
- versioned task-vector validation
- conversion to `TrialResult` values
- per-task pass/fail queries used by record operators

The module name describes its role rather than preserving the misleading
"vector" name. The external `task_vector.json` filename and archived
`task_vector` field remain compatible in this refactor. Internally,
`TrialResult` is the canonical typed representation.

`identity.py` is the single owner of evaluation comparability:

- `TaskSetIdentity`
- canonical hashing of dataset, attempt count, purpose-specific split marker,
  and task members
- identity resolution from the checkout being evaluated
- frozen baseline identity resolution from `gen/0`
- evaluator-tree and runtime fingerprints needed by population certification

Checkout and Git-tree loading remain separate adapters, but both call one
canonical task-set identity constructor. No other module assembles or hashes
that payload independently.

The constructor preserves the current digest contract. Its payload is
`dataset`, `attempts`, and sorted unique `tasks`; anchor identities additionally
contain `split: sealed`. Checkout membership continues to come from explicit
`task_names`, `task_file`, or the sealed split fallback for anchors. This
refactor centralizes that contract without invalidating existing archive rows.

`execution.py` owns how an evaluation is performed:

- `evaluate()`
- `EvaluationInterrupted`
- detached-worktree setup and cleanup
- evaluator-tree and runtime fingerprinting
- attempt directory allocation
- evaluator script invocation
- task-result evidence, cost, setup-outcome, and artifact loading
- conversion of collected evidence into an `EvaluationRecord`

`execution.py` depends on `evidence.py`, `identity.py`, and `results.py`;
those modules never depend on `execution.py`.

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

## Boundaries Outside the Package

`population.py` remains top-level because it owns lineage and parent-selection
queries: generation identifiers, valid parents, and best-row selection. Its
evaluation-identity readers and hash construction move to `identity.py`.
Population asks the evaluation package for the frozen baseline identity and
does not know its serialization details.

`splits.py` also remains top-level because it is shared by workspace
initialization, train rollout, and gate/sealed evaluation. It owns dataset
discovery, deterministic partitioning, and selection of task members. It does
not own score comparability. Evaluation identity consumes the selected members
and applies the one canonical identity algorithm.

The existing split-membership digest may remain as an operational artifact for
the evaluator shell contract, but it must be named and documented as a split
selection digest rather than treated as the archived evaluation
`task_set_hash`. The archived `task_set_hash` comes only from `identity.py`.

## Data Flow

`driver.py` calls `evaluation.execution.evaluate()`. Execution resolves the
configured task members, using `splits.py` for the existing sealed-anchor
fallback, constructs their canonical identity through `identity.py`, collects
evidence in an isolated checkout, converts evaluator JSON to `TrialResult`
values through `evidence.py`, and calls `results.classify_evaluation()`. The
resulting `EvaluationRecord` returns to the driver and is persisted by
`archive.py`.

The dependency direction is therefore:

```text
workspace/rollout/execution → splits.py
                              ↓ selected members
population.py → identity.py ← execution.py
                                ↓
driver/archive → result facade → results.py ← evidence.py
```

## Migration

1. Move the current `evaluation.py` definitions into `evaluation/results.py`.
2. Move the current `evaluator.py` implementation into
   `evaluation/execution.py`.
3. Move `task_vectors.py` into `evaluation/evidence.py` and update framework,
   library, and test imports without changing the external JSON contract.
4. Move `task_sets.py` into `evaluation/identity.py`. Extract the duplicate
   canonical identity construction and frozen `gen/0` readers from
   `population.py`; make both checkout and frozen-tree paths call the same
   canonical constructor.
5. Keep `splits.py` top-level. Rename its digest API to distinguish operational
   split membership from archived evaluation identity, and route evaluation
   identity construction through `identity.py`.
6. Move `EvaluationInterrupted` from the result definitions to execution,
   because it represents execution lifecycle control rather than persisted
   evaluation data.
7. Add the pure result facade exports in `evaluation/__init__.py`; import
   execution APIs explicitly from `evaluation.execution`.
8. Replace imports from `evolve.evaluator` with imports from
   `evolve.evaluation.execution`; retain existing result imports from
   `evolve.evaluation` through the facade.
9. Update focused tests that intentionally import private execution helpers to
   use `evolve.evaluation.execution`.
10. Update the pinned module list in `tests/test_coherence.py` and the README
    source map for all five package modules.
11. Remove the four superseded top-level modules. Do not leave compatibility
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

Malformed identity inputs retain their current handling. Checkout and
frozen-baseline identity resolution must produce the same value for the same
effective candidate evaluation; the refactor must not introduce different
payload construction between the two adapters. No exception type, record
field, outcome value, task-set hash, or failure precedence changes.

## Testing

Tests must establish both compatibility and the intended boundary:

- existing evaluation-record classification tests continue to pass through
  the package facade;
- evaluator execution and lifecycle tests continue to pass after import
  updates;
- archive, evidence, selection-certification, split, runtime, and driver tests
  verify downstream compatibility;
- identity tests prove checkout and `gen/0` adapters produce the same digest;
- tests prove population delegates identity construction and contains no
  duplicate task-set hashing;
- split tests distinguish the operational split digest from the archived
  evaluation identity;
- coherence tests recognize the five package modules and reject the removed
  top-level modules;
- the full test suite and Ruff checks pass.

## Non-goals

- changing evaluation semantics, scoring, retry policy, or record schemas;
- redesigning the evaluator shell contract;
- removing legacy task-vector input or archive compatibility;
- moving `population.py` or `splits.py` into the evaluation package;
- introducing compatibility aliases for `evolve.evaluator`;
- refactoring unrelated validation or candidate-selection code.
