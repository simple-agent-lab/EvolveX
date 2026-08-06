# Operator overview

Operators are the composable stages of an EvolveX generation. Their names in
this reference are identical to the keys used under `operators:` in
`evolve.yaml`.

```text
select
  → rollout
  → trace_analyzer
  → meta_agent
  → validate
  → novelty
  → canonical evaluation
  → gate
  → record
  → reflect
```

Optional stages are skipped when their configuration block is absent.
Canonical evaluation is framework-owned and is not an operator.

| Operator | Required | Responsibility |
| --- | --- | --- |
| [`select`](operators/select.md) | yes | choose valid parent generations |
| [`rollout`](operators/rollout.md) | yes | produce training behavior and execution evidence |
| [`trace_analyzer`](operators/trace_analyzer.md) | no | transform rollout cases into bounded mutation feedback |
| [`meta_agent`](operators/meta_agent.md) | yes | edit the candidate inside the declared surface |
| [`validate`](operators/validate.md) | no | run method-specific checks before canonical evaluation |
| [`novelty`](operators/novelty.md) | no | reject candidate edits that duplicate prior work |
| [`gate`](operators/gate.md) | yes | decide whether a canonical evaluation is parent-eligible |
| [`record`](operators/record.md) | yes | attach method-specific evidence to the archive |
| [`reflect`](operators/reflect.md) | no | derive reusable insights from verified history |

## Active and available implementations

After initialization:

```text
operators/<name>.py       active implementation
library/<name>/*.py       available alternatives
operators/README.md       generated active/alternative summary
```

Inspect the active configuration with:

```bash
./evolve operator list .
cat operators/README.md
```

Each operator block may select a `variant` or an explicit `script`, but not
both. Recipe-local variants take precedence over the shared library:

```yaml
operators:
  select:
    variant: greedy
    timeout_s: 600
```

## Custom implementations

Start from `library/<name>/_skeleton.py` and implement the matching interface in
`evolve.frozen.interfaces`. Put a recipe-local implementation at:

```text
my-recipe/operators/<name>/<variant>.py
```

Then select it by filename stem:

```yaml
operators:
  <name>:
    variant: <variant>
```

Operators execute as subprocesses. They should write diagnostics beneath their
generation run directory and return the typed result for their interface. They
must not write evaluator truth, generation tags, or archive outcomes directly.

