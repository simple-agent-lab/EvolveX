# Evolve Operator Protocol

This document describes protocol version `1` for workspace operators. The
mechanism launches operator files as subprocesses and consumes files from the
run directory. The Python ABCs and `sdk.main(...)` are the supported authoring
path, but the file contract is the protocol.

## Subprocess Contract

The mechanism invokes one file per configured operator kind under `operators/`:
select, rollout, meta_agent, optional validate/novelty/reflect, gate, and record. The copied file may be a library
variant, a recipe-local operator, or a user-provided `script:`. Python variants
normally end with `sdk.main(VariantClass)`, but any executable file that honors
the same files is valid.

Runtime state arrives through environment variables:

- `EVOLVE_WORKSPACE`: workspace root containing `archive.jsonl`, config, and
  protocol marker files.
- `EVOLVE_CHECKOUT`: checkout being evaluated or modified.
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

The rollout summary is passed directly to the meta-agent as its observation.
The mechanism does not synthesize a separate feedback bundle.

### Evaluator Evidence

An evaluator that emits per-task evidence writes two generic files under the
evaluation run directory. `task_vector.json` is a schema-versioned object with
a `tasks` map; each task contains ordered trial records with `trial`, `status`,
and `reward` fields. `evaluation_artifacts.json` is an index of the evaluator's
available trial artifacts, including each relative path, byte count, and
SHA-256. The mechanism validates the task vector and records only a
workspace-relative, hashed reference to the artifact index in the archive.

Operators may consume these files only through the archived reference and must
verify the recorded digest before using an artifact. They are evaluator
contracts, not operator-owned score inputs.

### Meta-Agent

ABC signature:

```python
def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult:
```

Implement `run`. Return `MetaAgentResult` with fields `changed`, `notes`, and
`usage`. The subprocess writes `meta_agent/changed.json`, ensures
`meta_agent/predicted_fixes.json`, may write `meta_agent/rationale.md`, and
writes `meta_agent/usage.json`. `usage` is a JSON object, commonly including
`usd`.

After the meta-agent exits, the driver checks the complete working-tree diff
against the mutable surface before any post-proposal operator runs.

### Validate (optional)

ABC signature:

```python
def validate(self, checkout: Path, ctx) -> ValidateResult:
```

Implement `validate`. Return `ValidateResult` with fields `accept`, `reason`,
and `artifacts`. The subprocess writes `validate/result.json`. It runs on the
uncommitted, surface-compliant candidate when a recipe configures
`operators.validate`; `accept: false` records `rejected_validation` and discards
the complete candidate without creating a generation tag.

### Novelty (optional)

ABC signature:

```python
def assess(self, checkout: Path, ctx) -> NoveltyResult:
```

Implement `assess`. Return `NoveltyResult` with fields `novelty` (0.0–1.0) and
`accept`. The subprocess writes `novelty.json`. Runs only when a recipe
configures `operators.novelty` (DESIGN §8, off by default): it sees the
uncommitted candidate diff, and an `accept: false` discards the generation
before eval — a near-duplicate is never committed. `NoveltyOperator`
implementations should read the ledger for prior accepted diffs, not reach for
policy helpers.

### Reflect (optional)

ABC signature:

```python
def reflect(self, archive, ctx) -> ReflectResult:
```

Implement `reflect`. Return `ReflectResult` with field `ops` (a list of
full-state playbook entries, each with an `id`). The subprocess appends the ops
to `insights/playbook.jsonl` (append-only; folding by id gives current state).
Runs only when a recipe configures `operators.reflect` (DESIGN §7, off by
default). This is the credit-backfill memory: it turns `verified_fixes` into
insights a future meta-agent can consult.

### Gate

ABC signature:

```python
def decide(self, child: Row, parent: Row | None, ctx) -> GateResult:
```

Implement `decide`. Return `GateResult` with fields `decision` and `reason`.
`decision` is `accept` or `reject`. The subprocess writes `gate.json` with
`valid_parent`, `verdict`, and `reason`; `accept` maps to `valid_parent: true`
and `verdict: keep`.

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

Library variants may use explicit research-method names when the name denotes
real behavior, inputs, and output artifacts rather than a label-only preset.
Recipe prose must not present a generic variant as though it implements a
method-specific procedure. The shipped variants are:

- select: `greedy`, `random`, `score_weighted`, `newest`, `score_child_prop`, `ahe_latest`
- rollout: `failure_focused`, `noop`, `ahe_trace_analysis`
- meta_agent: `agent_command`, `hyperagents`, `ahe_evidence_editor`
- validate: `hyperagents`
- gate: `hillclimb`, `parent_eligible`, `ahe_artifact_valid`
- record: `jsonl`, `hyperagents`, `ahe_manifest`

The AHE variants use the prompt assets
`library/rollout/prompts/ahe_debugger.md`,
`library/rollout/prompts/ahe_debugger_overview.md`, and
`library/meta_agent/prompts/ahe_evolve.md`. Their method artifacts are
`rollout/analysis/selection.json`, `rollout/analysis/failures.json`,
`rollout/analysis/overview.md`, `meta_agent/change_manifest.json`, and
`record/ahe_manifest.json`.

## Candidate Runtime Smoke

When runtime feedback is useful, meta-agents may run exactly the protected
`./evolve candidate-smoke --full` command. Each append-only attempt reports
redacted stdout and stderr artifact paths; inspect those artifacts, repair the
candidate environment with candidate-owned tools, and rerun smoke as needed.
Exit code 0 means passed, 2 means failed, and 3 means unsupported.
Smoke diagnostics are not selection classifications and never authorize
changes to evaluator-owned runtime machinery.

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
3. Own driver from evolve verbs: use `evolve init`, archive files, evaluator
   outputs, and surface checks while orchestrating the loop yourself. Stamping
   and canonical evaluation live in the verbs, so those invariants survive a
   user-written driver.

## Files Are Normative

Files, not classes, are normative. The mechanism runs subprocess files and
consumes `parents.json`, `rollout/summary.json`, `rollout/artifacts.json`,
`meta_agent/usage.json`, `validate/result.json`, `gate.json`,
`record/fields.json`, and the other artifacts listed above. Non-Python
operators are valid when they honor those files, environment variables, exit
behavior, and protocol version expectations.
