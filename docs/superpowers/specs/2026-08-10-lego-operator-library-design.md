# Lego Operator Library Design

## Purpose

Make EvolveX a composable evolution framework in which reusable behavior lives
in a central operator library and recipes declaratively combine those operators
inside one fixed, trustworthy lifecycle.

The design deliberately fixes the lifecycle rather than introducing a general
workflow graph. Users can implement arbitrarily sophisticated behavior inside
an operator, but every operator connects to the framework through one stable
stage contract. This keeps recipes easy to read and keeps evaluation, lineage,
failure handling, and evidence integrity predictable.

## Goals

1. Make one Python file sufficient to add a discoverable library operator.
2. Let recipes select and configure operators without containing Python logic.
3. Preserve subprocess isolation between user-authored operators and the
   trusted framework process.
4. Catch recipe and operator-configuration errors before workspace creation.
5. Use one canonical vocabulary across configuration, interfaces, commands,
   artifacts, and documentation.
6. Preserve existing initialized workspaces as immutable historical systems.

## Non-goals

- User-defined stages or stage ordering.
- A general workflow DAG.
- Separately installed operator packages or a remote operator registry.
- Recipe-local operator implementations.
- Importing operator modules into the trusted framework process.
- Making canonical evaluation a user-replaceable operator.
- Migrating existing initialized workspaces in place.

## Vocabulary

**Stage** is a fixed semantic slot in the EvolveX lifecycle.

**Operator** is one reusable implementation of a stage. Operators live in the
repository-level `library/` catalog.

**Recipe** is declarative experiment configuration that selects and configures
operators. A recipe contains composition and settings, not executable operator
implementations.

**Library** is the catalog of operators. It is not a separate extension
abstraction from operators.

`mutate` is the only canonical name for the candidate-changing stage.
`meta_agent` is not part of the new public vocabulary. Likewise, `analyze` is
the canonical stage name rather than `trace_analyzer`.

## Fixed lifecycle

Every recipe uses the same ordered lifecycle:

```text
select
  -> rollout
  -> analyze?
  -> mutate
  -> validate?
  -> novelty?
  -> evaluate
  -> gate
  -> record
  -> reflect?
```

Required operator stages are:

- `select`
- `rollout`
- `mutate`
- `gate`
- `record`

Optional operator stages are:

- `analyze`
- `validate`
- `novelty`
- `reflect`

`evaluate` is fixed in the sequence but is framework-owned. It is not a
library operator and cannot be replaced by recipe configuration.

Users who need additional internal ordering implement it inside the relevant
operator. For example, a mutation operator may run planning, editing, critique,
and repair internally while presenting one `mutate` boundary to the framework.

## Ownership boundaries

### Framework

The trusted framework owns:

- lifecycle ordering and stage transitions;
- operator discovery and subprocess invocation;
- common recipe parsing and validation;
- workspace initialization and Git lineage;
- mutable-surface enforcement;
- canonical evaluation;
- archive stamping and evidence integrity;
- stage-result validation;
- typed failure classification.

The framework may inspect filesystem names and subprocess responses. It never
imports a library operator into its own process.

### Operator library

The library owns reusable evolution policy and algorithms:

```text
library/<stage>/<operator_name>.py
```

Examples:

```text
library/select/pareto.py
library/analyze/gepa.py
library/mutate/critic_editor.py
library/gate/parent_eligible.py
```

The directory is the stage identity. The filename stem is the operator name.
Every `.py` file whose name does not start with `_` is automatically
discoverable. No registry entry or separate manifest is required.

Operator names must match `[a-z][a-z0-9_]*`. This keeps recipe references,
artifact paths, and diagnostics unambiguous and prevents path-like identities.

Operator entry files may import underscore-prefixed shared helpers:

```text
library/mutate/_shared.py
library/_shared/model_runner.py
```

Underscore-prefixed files and directories are never selectable operators.

The initial authoring model assumes a source checkout or fork of EvolveX.
Adding a new operator means adding a file to the repository-level library.
Separately installed user libraries are deferred.

### Recipes

Recipes own declarative composition and experiment settings:

- selected operator for each enabled stage;
- operator-owned configuration;
- common stage execution settings;
- experiment limits and budgets;
- target and mutable surface;
- evaluator and execution runtime selection.

Recipes do not contain operator source files. A recipe containing an
`operators/` directory is invalid under the new model.

## Recipe operator syntax

`operator:` is the canonical selector for a named library operator:

```yaml
operators:
  select:
    operator: pareto
    timeout_s: 600
    config:
      seed: 0

  rollout:
    operator: harbor
    timeout_s: 3600
    config:
      budget_tasks: 10
      n_concurrent: 4

  analyze:
    operator: gepa
    timeout_s: 600
    config:
      max_cases: 10

  mutate:
    operator: critic_editor
    timeout_s: 3600
    config:
      attempts: 3

  gate:
    operator: parent_eligible

  record:
    operator: jsonl
```

The framework understands the common keys `operator`, `script`, `timeout_s`,
and `config`. A stage block must specify exactly one of `operator` or `script`.
The selected operator exclusively owns the contents of `config`.

The existing `script:` escape hatch remains available for advanced use:

```yaml
operators:
  mutate:
    script: /absolute/path/to/custom_mutate.py
    timeout_s: 3600
    config:
      arbitrary: true
```

A script-based selection is explicitly non-portable. It must obey the runtime
file protocol but may omit early configuration validation.

## Operator contract

An operator may use any internal functions, classes, agents, subprocesses, or
shared helpers. Its fixed boundary consists of:

1. the stage interface;
2. operator-owned configuration validation;
3. SDK command handling;
4. the stage result schema and artifact contract.

The canonical interface and result pairs are:

```text
SelectOperator    -> SelectResult
RolloutOperator   -> RolloutResult
AnalyzeOperator   -> AnalyzeResult
MutateOperator    -> MutateResult
ValidateOperator  -> ValidateResult
NoveltyOperator   -> NoveltyResult
GateOperator      -> GateResult
RecordOperator    -> RecordResult
ReflectOperator   -> ReflectResult
```

A typical library entry file has this shape:

```python
from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult


def validate_config(raw: dict[str, object]) -> dict[str, object]:
    attempts = raw.get("attempts", 3)
    if not isinstance(attempts, int) or attempts < 1:
        raise ValueError("attempts must be a positive integer")
    unknown = set(raw) - {"attempts"}
    if unknown:
        raise ValueError(f"unknown settings: {sorted(unknown)}")
    return {"attempts": attempts}


class CriticEditor(MutateOperator):
    def mutate(self, checkout, observation, ctx) -> MutateResult:
        ...


if __name__ == "__main__":
    sdk.main(CriticEditor, validate_config=validate_config)
```

The example shows the public boundary, not a required internal architecture.
A library operator is otherwise free to organize its implementation however it
needs.

### Configuration validation mode

Every named library operator must support:

```bash
python library/mutate/critic_editor.py \
  --validate-config \
  --config '{"attempts": 3}'
```

On success, the operator writes normalized configuration as JSON and exits
zero. On invalid input, it exits nonzero with a concise actionable error. A
validator must reject invalid values and should reject unknown keys rather than
silently ignore likely misspellings.

Validation executes in a subprocess with a bounded timeout. The framework does
not import the file to inspect its validator.

Configuration validation is mandatory for named library operators and optional
for `script:` operators.

### Runtime mode

At runtime the framework supplies:

- workspace and candidate-checkout paths;
- a stage-specific run directory;
- generation, parent, and fan-out identity;
- normalized operator configuration;
- stage-specific input artifacts and evidence;
- a framework-enforced timeout.

The operator writes its stage result and artifacts through the versioned file
protocol. The framework validates the result before advancing to the next
stage.

## Discovery and resolution

Library discovery is convention-based:

1. Scan only the fixed stage directories.
2. Include non-underscore `.py` files.
3. Derive stage and name from the path.
4. Do not import discovered modules.
5. Reject duplicate logical identities.

An unknown non-underscore top-level directory under `library/` is a repository
layout error; adding a directory must never add a stage implicitly. The
reserved `library/_shared/` tree may contain common helpers.

Recipe resolution is read-only and precedes workspace creation:

```text
recipe YAML
  -> validate common structure
  -> validate fixed stage inventory
  -> resolve named library operators
  -> invoke configuration validators in subprocesses
  -> collect normalized configuration
  -> produce a resolved recipe
```

Resolution rejects:

- unknown stages;
- missing required stages;
- a stage block containing both `operator` and `script` or neither;
- an unknown or underscore-prefixed operator name;
- invalid common stage settings;
- operator configuration rejected by the selected operator;
- recipe-local operator directories;
- invalid target, surface, evaluator, or runtime configuration.

Where checks are independent, resolution reports all failures in one pass.

## Workspace initialization and reproducibility

After successful resolution, `evolve init` freezes:

- the normalized recipe;
- selected operator entry files under `operators/`;
- the complete underscore-prefixed shared-helper namespace under `library/`;
- selected operator source identities and content digests;
- the target seed and mutable-surface contract;
- evaluator and runtime configuration;
- the framework mechanism;
- generation-zero lineage and archive evidence.

The complete repository commit remains the source version for library content.
The generated workspace additionally records selected file digests so reports
can state exactly which operator bytes initialized the experiment.

Shared helpers are available to initialized operators but remain outside the
candidate mutable surface unless a future design explicitly changes that
boundary. A recipe that permits operator co-evolution permits edits to selected
active files under `operators/`, not to the frozen library catalog.

## Commands and authoring workflow

The normal workflow is:

```bash
evolve operator new mutate critic_editor
evolve operator check mutate/critic_editor --config '{"attempts": 3}'
evolve operator describe mutate/critic_editor
evolve operator list mutate
evolve recipe check recipes/my_method
```

`evolve operator new <stage> <name>` creates exactly one entry file with:

- the correct interface and result imports;
- a minimal stage implementation;
- a `validate_config` function;
- an `sdk.main(...)` entrypoint.

`evolve operator check` verifies discovery identity, protocol support, and
configuration validation without creating a workspace or calling a model.

`evolve operator describe` invokes the operator in a subprocess and renders its
stage, name, docstring summary, and configuration-validation availability.

`evolve operator list [stage]` lists convention-discovered library operators.

`evolve recipe check <path>` resolves the complete recipe without writing a
workspace. Its diagnostics use recipe paths and include available operator
names when resolution fails.

Example:

```text
recipe check failed with 3 problems:

operators.mutate.operator:
  unknown mutate operator "critic_edtor"
  available: critic_editor, gepa, prompt_editor

operators.rollout.config.n_concurrent:
  expected a positive integer, received 0

operators.reflect:
  specify exactly one of "operator" or "script"
```

## Failure model

Recipe authoring failures and experiment runtime failures remain distinct.

Recipe checking treats these as blocking configuration failures:

- operator not found;
- validator missing for a named library operator;
- validator timeout or crash;
- malformed validator JSON;
- invalid normalized configuration;
- common recipe contract violation.

Runtime treats these as typed generation failures:

- operator process exits nonzero;
- operator exceeds its timeout;
- required output is missing;
- stage result is malformed;
- the operator changes paths outside its authority.

A runtime failure records the stage, operator identity, failure category, and
safe diagnostic artifact. It does not silently skip a required stage or
reinterpret malformed output.

## Migration

The repository source, built-in recipes, tests, and maintained documentation
migrate atomically to the new vocabulary:

```text
meta_agent                    -> mutate
trace_analyzer                -> analyze
variant:                      -> operator:
library/meta_agent/           -> library/mutate/
library/trace_analyzer/       -> library/analyze/
operators/meta_agent.py       -> operators/mutate.py
operators/trace_analyzer.py   -> operators/analyze.py
```

New source recipes reject the old keys. The new public API does not present
aliases as competing vocabulary.

Existing initialized workspaces are not migrated. They retain their vendored
historical mechanism, configuration, operator names, and commands. This is the
existing workspace-versioning boundary, not a compatibility layer in the new
source framework.

Recipe-local operator lookup and precedence are removed. The `script:` escape
hatch remains during this migration.

## Testing strategy

### Discovery tests

- Every non-underscore file in a fixed stage directory is discovered.
- Underscore-prefixed files and helpers are excluded.
- Unknown non-underscore stage directories are rejected; they never become
  stages implicitly.
- No discovery path imports operator code into the test process.

### Operator contract tests

- Every discovered operator supports the SDK protocol.
- Every discovered operator exposes mandatory configuration validation.
- Validator success returns a JSON object.
- Validator errors are structured and actionable.
- Validator crashes, timeouts, and malformed output are rejected.
- Each operator's runtime result is checked by the stage result validator.

### Recipe tests

- Every built-in recipe resolves successfully.
- Every recipe-selected operator accepts its configuration.
- Required and optional stage rules are enforced.
- `operator` and `script` exclusivity is enforced.
- Unknown common keys and invalid common values are rejected.
- Recipe-local operator directories are rejected.
- Script-based recipes are marked non-portable.

### Integration tests

- One deterministic external-style recipe uses only named library operators,
  initializes a workspace, and completes a lightweight generation.
- The initialized workspace records normalized configuration and selected
  operator digests.
- A recipe-check failure writes no workspace state.
- Historical fixture workspaces remain readable by their vendored mechanisms
  and are never rewritten.

Slow or live tests continue to follow the repository test-tier policy. Model,
Docker, Harbor, or credential-dependent checks are not routine validation.

## Acceptance criteria

The design is complete when all of the following are true:

1. Adding `library/mutate/my_operator.py` makes `my_operator` discoverable
   without editing a registry.
2. A valid new operator and recipe can be created and checked without creating
   a workspace or running a model.
3. A recipe contains no executable operator implementation.
4. Every named library operator validates its own opaque configuration before
   initialization.
5. The trusted framework never imports operator code.
6. Recipes use only the fixed stage set and ordering.
7. Canonical evaluation remains framework-owned.
8. `mutate`, `analyze`, and `operator:` are the sole public replacements for
   `meta_agent`, `trace_analyzer`, and `variant:` respectively.
9. Operator and recipe errors identify an actionable configuration path.
10. Existing initialized workspaces remain untouched.

## Deferred extensions

The following may be designed later if demonstrated use cases require them:

- separately installed or user-scoped operator libraries;
- remote operator catalogs and package version resolution;
- non-Python named library operators;
- richer machine-readable operator metadata;
- a general workflow graph;
- user-defined stages.

None of these extensions is required for the repository-level Lego model.
