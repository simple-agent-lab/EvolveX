# RSIHub design

This document describes the framework model and rationale. The executable
module inventory lives in
[ARCHITECTURE.md on GitHub](https://github.com/simple-agent-lab/RSIHub/blob/main/ARCHITECTURE.md);
the operator contract in `src/evolve/frozen/interfaces.py` is authoritative for
interfaces.

## The model

RSIHub evolves a candidate under a frozen evaluator while retaining a Git
lineage. A workspace is a separate Git repository: generation tags identify
candidates, `archive.jsonl` records stamped outcomes, and the evaluator stays
outside the candidate's mutable surface.

The governing boundary is simple: framework code owns the mechanics that make
scores trustworthy; a recipe selects the evolvable policy. Operators run as
subprocesses, so the mechanism never imports workspace operator code in-process.

## Recipe-driven initialization

`evolve init` reads one supported recipe YAML and validates its selected
`target.seed`, `evaluator.engine`, `evaluator.agent`, and
`operators.meta_agent.agent`. The recipe is the selection authority; there is
no second runtime component registry.

```text
recipe YAML
  -> target seed resolution
  -> common workspace scaffold
  -> evaluator-engine scaffold
  -> rendered config and component manifest
  -> vendored framework runtime
  -> generation-zero Git snapshot
```

The framework has five supported recipes: `aevolve`, `ahe`, `gepa`,
`hill_climb`, and `hyperagents`. Development smoke recipes live under
`tests/fixtures/recipes/` and are not part of the public recipe inventory.

## Source ownership

| Source | Responsibility |
| --- | --- |
| `recipes/` | supported experiment configurations |
| `scaffolds/workspace/` | files common to every generated workspace |
| `scaffolds/evaluators/harbor/` | Harbor-specific evaluator files |
| `seeds/` | built-in evolvable target content |
| `src/evolve/integrations/harbor/` | Harbor adapters owned by the framework |
| `library/` | reference operator variants available in a workspace |
| `tests/fixtures/` | deterministic test-only resources |

Harbor integrations are framework modules. A generated workspace vendors them
as part of `.evolve/evolve/integrations/harbor/`; it does not receive standalone
adapter packages.

## Workspace boundaries

```text
<workspace>/
├─ target/          candidate selected by the recipe's seed
├─ operators/       active recipe-selected operator scripts
├─ library/         operator variants copied for the workspace
├─ evaluator/       frozen evaluator and selected engine files
├─ skills/          workspace operating manual
├─ .evolve/         vendored framework runtime and launcher
├─ evolve.yaml      rendered experiment configuration
├─ .evolve-components.json
├─ archive.jsonl    append-only lineage ledger
└─ runs/, artifacts/  generated run state and durable context
```

The mutable surface in `evolve.yaml` controls what a candidate may edit. The
target and, for recipes that select it, operator scripts are evolvable. The
evaluator, archive stamps, and vendored mechanism are not.

## Invariants

1. The evaluator is frozen for the lineage and cannot be mutated by a candidate.
2. Scores enter the archive only through the mechanism's stamped evaluation path.
3. Reports recompute best-known results from stamped archive entries.
4. A local Harbor dataset is frozen by task name and by deterministic task-tree
   digests (paths, file bytes, file types, and modes) at initialization. Each
   canonical run executes a fresh selected-task snapshot verified against those
   digests, never the mutable source directory that was checked earlier.
5. A selectable score is bound to the commit currently named by its `gen/<id>`
   tag; moving the tag invalidates the score instead of transferring it.
6. Candidate dependency preparation uses an immutable shared seed plus a
   disposable per-attempt overlay. Candidate project build code runs only in
   the evaluator environment, not on the host preparation path.
7. Evaluation replay verifies every indexed artifact's path, size, and digest,
   then collects cases from a temporary view containing only those certified
   bytes.
8. A candidate enters the lineage only through canonical evaluation.

Resolved version-1 split manifests remain readable for historical inspection,
but they are not eligible for new canonical evaluation or parent selection
because they do not contain task-content identities. Start a new experiment to
upgrade that boundary; do not silently compare new scores with a legacy task
set.

## Versioning

The repository source is the single framework source of truth. Vendoring it
into `.evolve/` deploys that source with a generated workspace; it does not
create a second implementation lineage. Changes to required operator interfaces
are made through the frozen interface contract and its tests.
