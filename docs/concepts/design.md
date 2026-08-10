# EvolveX design

This document describes the framework model and rationale. The executable
module inventory lives in
[ARCHITECTURE.md on GitHub](https://github.com/simple-agent-lab/EvolveX/blob/main/ARCHITECTURE.md);
the operator contract in `src/evolve/frozen/interfaces.py` is authoritative for
interfaces.

## The model

EvolveX evolves a candidate under a frozen evaluator while retaining a Git
lineage. A workspace is a separate Git repository: generation tags identify
candidates, `archive.jsonl` records stamped outcomes, and the evaluator stays
outside the candidate's mutable surface.

The governing boundary is simple: framework code owns the mechanics that make
scores trustworthy; a recipe selects the evolvable policy. Operators run as
subprocesses, so the mechanism never imports workspace operator code in-process.

A **stage** is a fixed lifecycle slot. An **operator** is a reusable
implementation at `library/<stage>/<name>.py`. A **recipe** is code-free
selection and configuration of operators. **Evaluate** is the framework-owned
trusted mechanism and is never resolved from the operator library.

## Recipe-driven initialization

`evolve init` resolves one supported recipe YAML, validates every named
operator in a subprocess, and freezes its normalized configuration. The recipe
is the selection authority; adding `library/<stage>/<name>.py` makes an
operator discoverable without editing a registry.

```text
recipe YAML
  -> target seed resolution
  -> common workspace scaffold
  -> evaluator-engine scaffold
  -> rendered config and component manifest
  -> vendored framework runtime
  -> generation-zero Git snapshot
```

The framework ships `aevolve`, `ahe`, `ahe_codex`, `gepa`, `gepa_local`,
`hill_climb`, `hill_climb_codex`, `hyperagents`, and `hyperagents_codex`.
Development smoke recipes live under `tests/fixtures/recipes/` and are not part
of the public recipe inventory.

## Source ownership

| Source | Responsibility |
| --- | --- |
| `recipes/` | supported experiment configurations |
| `scaffolds/workspace/` | files common to every generated workspace |
| `scaffolds/evaluators/harbor/` | Harbor-specific evaluator files |
| `seeds/` | built-in evolvable target content |
| `src/evolve/integrations/harbor/` | Harbor adapters owned by the framework |
| `library/` | discoverable, reusable operator implementations |
| `tests/fixtures/` | deterministic test-only resources |

Harbor integrations are framework modules. A generated workspace vendors them
as part of `.evolve/evolve/integrations/harbor/`; it does not receive standalone
adapter packages.

## Workspace boundaries

```text
<workspace>/
├─ target/          candidate selected by the recipe's seed
├─ operators/       frozen active recipe-selected operator scripts
├─ library/         frozen catalog alternatives and imported helpers
├─ evaluator/       frozen evaluator and selected engine files
├─ skills/          workspace operating manual
├─ .evolve/         vendored framework runtime and launcher
├─ evolve.yaml      rendered experiment configuration
├─ .evolve-components.json
├─ archive.jsonl    append-only lineage ledger
└─ runs/, artifacts/  generated run state and durable context
```

Initialization records normalized operator config in `evolve.yaml`, freezes
selected bytes in `operators/`, and records source identity and SHA-256
provenance in `.evolve-components.json`. Existing initialized workspaces are
never rewritten when the source catalog changes. The mutable surface in
`evolve.yaml` controls what a candidate may edit; the evaluator, archive stamps,
and vendored mechanism remain outside it.

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
