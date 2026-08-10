# EvolveX

Evidence-driven evolution of agents, prompts, and agent harnesses. Each
experiment is one Git repository (a workspace) in which a frozen evaluator
scores successive candidates and a mechanism records their lineage. This
glossary is the single ubiquitous language for the framework repository, the
skill, and every generated workspace.

## The experiment

**Workspace**:
A Git repository holding one evolution experiment: its target, evaluator,
operators, and lineage.
_Avoid_: experiment repo, evolution directory

**Target**:
The artifact under evolution, at `target/`.
_Avoid_: subject, candidate (a candidate is a snapshot, not the artifact)

**Seed**:
The initial content vendored into `target/` at initialization.

**Scaffold**:
Framework-owned files used to generate a workspace around the selected target
and evaluator engine.

**Integration**:
Framework-owned runtime behavior for an external system. Harbor integrations
live under `src/evolve/integrations/harbor/` and are vendored with the
mechanism.

**Evaluator**:
The frozen scoring contract at `evaluator/`. Fixed from generation zero; the
only source of scores.
_Avoid_: ruler, scoring contract, canonical evaluator, frozen side

**Mutable surface**:
The set of paths a candidate change may touch, declared under `surface` in
`evolve.yaml`.
_Avoid_: declared surface, mutation surface, mutation scope, write scope

**Recipe**:
An init-time template that scaffolds a workspace for one method
(`aevolve`, `ahe`, `gepa`, `hill_climb`, `hyperagents`).

**Supported recipe**:
A public configuration under `recipes/`. Development-only configurations under
`tests/fixtures/recipes/` are test fixtures, not supported recipes.

**Test fixture**:
Deterministic test-only data under `tests/fixtures/`; never part of the public
recipe or seed inventory.

**Method**:
The evolution strategy a workspace runs (Hill Climb, A-Evolve, GEPA, AHE,
HyperAgents), expressed as a configuration of stages over the same workspace
contract.
_Avoid_: algorithm, mode

## Candidates and lineage

**Candidate**:
One exact snapshot of the workspace tree proposed for evaluation.
_Avoid_: version, variant

**Generation**:
A candidate's position in the lineage, numbered and tagged `gen/<id>`.

**Baseline**:
The certified generation-zero evaluation of the untouched seed. Recorded in
the archive with purpose `genesis`.
_Avoid_: genesis (in prose)

**Parent**:
The certified candidate a new child starts from.

**Child**:
A candidate under construction in a worktree, not yet committed.
_Avoid_: draft, work-in-progress candidate

**Champion**:
The best accepted candidate, recomputed by the mechanism and recorded in
`best_ever.json`.
_Avoid_: best-ever (in prose), winner

**Lineage**:
The parent-child graph of all candidates, carried by Git tags and the archive.
_Avoid_: history, genealogy

**Archive**:
The append-only record `archive.jsonl`, one row per generation event.
_Avoid_: ledger

**Stamp**:
The evaluation record written only by the frozen side; the sole way a score
enters the lineage.
_Avoid_: self-reported score, result

## Control

**Mechanism**:
The frozen framework code behind `./evolve` that owns state transitions,
stamping, gating, and recording.
_Avoid_: framework side, lineage mechanism, workspace mechanism, evaluation
mechanism

**Console**:
The vendored `./evolve` entry point inside a workspace; the only supported way
to invoke the mechanism.
_Avoid_: CLI (for the workspace entry point)

**Outer agent**:
The coding agent operating a workspace from outside during an agent-led
generation.
_Avoid_: mutation agent, meta-agent (for the outer agent)

**Meta agent** (`mutate`):
The configured stage that edits the child from inside the loop during a
driver-led generation. The outer agent plays this same mutating role from
outside during an agent-led generation; the name `mutate` stays with the
stage and its files.
_Avoid_: meta-agent (for the outer agent)

**Driver**:
The unattended loop started by `evolve run`.
_Avoid_: built-in loop, unattended loop (as a name)

**Control path**:
Who owns producing a generation: driver-led (the configured `mutate`
stage) or agent-led (the outer agent). Both are the same role — an agent
mutating the target — which is why exactly one may own a generation.

## Stages and decisions

**Stage**:
One step of a generation, named exactly as registered: `select`, `rollout`,
`analyze`, `mutate`, `validate`, `novelty`, `gate`, `record`,
`reflect`.
_Avoid_: feedback, mutation, trace analysis, validation (as stage names)

**Operator**:
The active implementation of a stage, at `operators/<stage>.py`. Reference
variants under `library/` are not active.
_Avoid_: treating library variants as operators

**Admission**:
The pre-evaluation checks bound to an exact candidate tree: `surface-check`
plus every configured `validate` and `novelty` stage. Each produces a receipt;
editing the tree invalidates them.
_Avoid_: gate (for pre-evaluation checks)

**Gate**:
The post-evaluation accept-or-reject decision, applied only by `finalize`.
_Avoid_: admission (for the accept decision)
