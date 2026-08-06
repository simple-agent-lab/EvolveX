# EvolveX Operator Protocol

This document describes protocol version `1` for workspace operators. The
mechanism launches operator files as subprocesses and consumes files from the
run directory. The Python ABCs and `sdk.main(...)` are the supported authoring
path, but the file contract is the protocol.

## Subprocess Contract

The mechanism invokes required operator files for select, rollout, meta_agent,
gate, and record, plus recipe-selected optional operators such as
trace_analyzer, validate, novelty, and reflect. A copied file may be a library
variant, a recipe-local operator, or a user-provided `script:`. Python variants
normally end with `sdk.main(VariantClass)`, but any executable file that honors
the same files is valid.

Runtime state arrives through environment variables:

- `EVOLVE_WORKSPACE`: workspace root containing `archive.jsonl`, config, and
  protocol marker files.
- `EVOLVE_CHECKOUT`: checkout being evaluated or mutated.
- `EVOLVE_RUN_DIR`: current generation run directory.
- `EVOLVE_GENID`: child generation id.
- `EVOLVE_PARENT`: selected parent id, when there is one.
- `EVOLVE_ROUND`: numeric round when the runner is executing a per-round
  operator. The variable is absent when no round applies.
- `EVOLVE_OPERATOR_TIMEOUT_S`: inherited timeout cap for adapters.

Operator-specific YAML settings are passed as `--config` JSON. The framework
enforces the configured timeout around the subprocess. A nonzero exit code, a
timeout, or malformed required output makes the generation an
`operator_failed` row; the row names the operator kind and includes a note about
the failed file or field when validation reaches a file read.

`sdk.main(...)` checks `.evolve-protocol-version` from `EVOLVE_WORKSPACE` or
`EVOLVE_CHECKOUT`. Protocol version `1` is accepted; a missing marker or
another value exits nonzero with `protocol_version` in stderr.

## Per-Kind Contract

All Python operators receive an `OperatorContext` with these fields: `workspace`,
`checkout`, `run_dir`, `genid`, `parent`, `round`, `fan_out`, `config`, and
`rng`. `workspace`, `checkout`, and `run_dir` are `Path` values. `config` is the
operator config dict, and `rng` is seeded from that config.

### Select

ABC signature:

```python
def pick(self, archive: ArchiveView, ctx) -> SelectResult:
```

Implement `pick`. Return `SelectResult` with field `parents`. The subprocess
writes `parents.json`:

```json
{"parents": ["0"]}
```

`parents` must be a non-empty list of generation id strings.

### Rollout

ABC signature:

```python
def rollout(self, checkout: Path, ctx) -> RolloutResult:
```

Implement `rollout`. Return `RolloutResult` with fields `summary` and
`artifacts`. The subprocess writes `rollout/summary.json` and
`rollout/artifacts.json`. `summary` is a JSON object; `artifacts` is a list of
artifact paths or labels.

### Trace Analyzer

ABC signature:

```python
def analyze(self, checkout: Path, ctx) -> TraceAnalyzerResult:
```

Implement `analyze`. Read method-neutral rollout artifacts such as
`rollout/cases.json`, then write the selected and raw trace views under
`trace_analyzer/`. Return `TraceAnalyzerResult` with `summary` and `artifacts`;
the subprocess writes `trace_analyzer/summary.json` and
`trace_analyzer/artifacts.json`.

After trace analysis, the mechanism writes the normalized feedback bundle under
`runs/gen-<id>/feedback/` for the meta-agent to read. If the analyzer writes
`trace_analyzer/feedback.md` and `trace_analyzer/evidence/selected.md`, the
mechanism copies the bounded selection into the feedback bundle.

### Meta-Agent

ABC signature:

```python
def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult:
```

Implement `run`. Return `MetaAgentResult` with fields `changed`, `notes`, and
`usage`. The subprocess writes `meta_agent/changed.json`, may write
`meta_agent/rationale.md`, and writes `meta_agent/usage.json`. `usage` is a JSON
object, commonly including `usd`.

The workspace also exposes gitignored durable storage under `artifacts/`.
`artifacts/user/` is user-managed, while a meta-agent may persist arbitrary
files only under `artifacts/generations/<EVOLVE_GENID>/`. An optional free-form
`handoff.md` in that directory is the handoff convention. Shipped prompts point
to the selected parent's handoff when it exists; absence is non-fatal. Harbor
copies all durable artifacts into its disposable workspace but imports only the
current generation namespace, so user and prior-generation content remains
host-authoritative and artifacts do not enter candidate patches.

### Novelty (optional)

ABC signature:

```python
def assess(self, checkout: Path, ctx) -> NoveltyResult:
```

Implement `assess`. Return `NoveltyResult` with fields `novelty` (0.0–1.0) and
`accept`. The subprocess writes `novelty.json`. Runs only when a recipe
configures `operators.novelty` (DESIGN §8, off by default): it sees the
uncommitted mutation diff, and an `accept: false` discards the generation before
eval — a near-duplicate is never committed. `NoveltyOperator` implementations
should read the ledger for prior accepted diffs, not reach for policy helpers.

### Reflect (optional)

ABC signature:

```python
def reflect(self, archive, ctx) -> ReflectResult:
```

Implement `reflect`. Return `ReflectResult` with field `ops`. A configured
credit-reflection variant may consume optional `verified_fixes` annotations;
strategies such as AHE that do not emit predictions simply produce no credit.

### Gate

ABC signature:

```python
def decide(self, child: Row, parent: Row | None, ctx) -> GateResult:
```

Implement `decide`. Return `GateResult` with fields `decision` and `reason`.
`decision` is `accept` or `reject`. The subprocess writes `gate.json` with
`valid_parent`, `verdict`, and `reason`; `accept` maps to `valid_parent: true`
and `verdict: keep`, while `reject` maps to `valid_parent: false` and
`verdict: discard`. Contradictory pairs are rejected as malformed output.

For non-Python operators, the runner writes `gate/input.json` before launching
the gate subprocess:

```json
{"child": {"genid": "1", "task_set_hash": "hash"}, "parent": null}
```

`child` is the merged archive row for `EVOLVE_GENID`. `parent` is the selected
parent row only when that parent has a score for the child's `task_set_hash`;
otherwise it is `null`. Python operators using `sdk.main(...)` receive these
same values as `decide(child, parent, ctx)`.

### Record

ABC signature:

```python
def annotate(self, child: Row, ctx) -> RecordResult:
```

Implement `annotate`. Return `RecordResult` with field `fields`. The subprocess
writes `record/fields.json`. The driver strips mechanism-owned fields before
appending the remaining object to the archive.

## Write Your Own Variant in Three Steps

1. Copy `library/<kind>/_skeleton.py` into your own operator file, for example
   `my_select.py`.
2. Fill in the one method for that kind, returning the result dataclass with
   valid field values.
3. Point `evolve.yaml` at it with `script: ./my_select.py`, then run the file
   as the mechanism will run it: set `EVOLVE_WORKSPACE`,
   `EVOLVE_CHECKOUT`, `EVOLVE_RUN_DIR`, `EVOLVE_GENID`, and optionally
   `EVOLVE_PARENT`, then execute it with `--config '{}'` and inspect the
   expected files.

## Shipped Variants

The shipped library uses canonical algorithm names only. Recipe research names
may appear in recipe prose, but `variant:` values point to these files:

- select: `greedy`, `random`, `score_weighted`, `newest`, `pareto`
- rollout: `failure_focused`, `harbor`, `noop`
- trace_analyzer: `failure_patterns`, `failed_traces`, `trace_browser`, `trajectory_only`, `execution_records`, `gepa`, `utility_metrics`
- meta_agent: `aevolve`, `ahe`, `gepa`, `hyperagents` (`runner`: `local` or `harbor`)
- validate: `hyperagents`, `minibatch_improvement`
- gate: `hillclimb`, `parent_eligible`
- record: `gepa`, `jsonl`

## Stability Tiers

| Tier | Stability | What to depend on |
| --- | --- | --- |
| Verbs and file contract | Major-version protected | CLI verbs, subprocess execution, required files, JSON fields |
| Interfaces and SDK | Additive-only paved road | ABC names, result dataclasses, `OperatorContext`, `sdk.main(...)` |
| Library variants | Evolve freely | Algorithms under `library/<kind>/` may change as practice improves |
| Recipes | Examples, no promise | Presets encode experiment policy and can change as evidence changes |

## Escape-Hatch Ladder

1. YAML: choose a shipped `variant:` and tune its config.
2. `script:` variant: point one operator kind at your own executable file.
3. Agent orchestration: discover capabilities with `evolve operator list`, run
   configured stages with `evolve operator run`, edit a child worktree, then
   use `commit`, `eval`, and `finalize`.
4. Own driver from evolve verbs: use `evolve init`, archive files, evaluator
   outputs, and surface checks while orchestrating the loop yourself. Stamping
   and canonical evaluation live in the verbs, so those invariants survive a
   user-written driver.

Direct stage reruns retain the previous output under
`runs/gen-<id>/operator-attempts/<kind>/attempt-<n>/`. A configured validate or
novelty result includes a mechanism-owned candidate-tree receipt; the
Agent-facing commit refuses missing, rejected, or stale admission results.

## Files Are Normative

Files, not classes, are normative. The mechanism runs subprocess files and
consumes `parents.json`, `rollout/summary.json`, `rollout/artifacts.json`,
`trace_analyzer/summary.json`, `trace_analyzer/artifacts.json`,
`meta_agent/usage.json`, `gate.json`,
`record/fields.json`, and the other artifacts listed above. Non-Python
operators are valid when they honor those files, environment variables, exit
behavior, and protocol version expectations.
