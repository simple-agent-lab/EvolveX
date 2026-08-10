# Operator overview

A stage is a fixed lifecycle slot. An operator is one reusable implementation
at `library/<stage>/<name>.py`. A recipe is the code-free selection and
configuration of operators. Canonical evaluation is framework-owned and cannot
be replaced by a recipe operator.

```text
select
  → rollout
  → analyze
  → mutate
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
| [`analyze`](operators/analyze.md) | no | transform rollout cases into bounded mutation feedback |
| [`mutate`](operators/mutate.md) | yes | edit the candidate inside the declared surface |
| [`validate`](operators/validate.md) | no | run method-specific checks before canonical evaluation |
| [`novelty`](operators/novelty.md) | no | reject candidate edits that duplicate prior work |
| [`gate`](operators/gate.md) | yes | decide whether a canonical evaluation is parent-eligible |
| [`record`](operators/record.md) | yes | attach method-specific evidence to the archive |
| [`reflect`](operators/reflect.md) | no | derive reusable insights from verified history |

## Discover and validate the library

Discovery is filesystem-only and never imports operator code into the
framework process. Inspection runs each entry file in a subprocess:

```bash
evolve operator list
evolve operator list mutate --json
evolve operator describe mutate/hyperagents
evolve operator check mutate/hyperagents --config '{"runner":"local"}'
```

Create a complete SDK entry file in a source checkout with:

```bash
evolve operator new mutate my_operator
```

Every named library entry must expose `--describe` and `--validate-config` via
`sdk.main(..., validate_config=validate_config)`. Validation must reject
unknown or invalid settings; `library/_shared/config.py` provides common
helpers. Underscore-prefixed files and directories are helper modules, not
discoverable operators.

## Compose a recipe

Each enabled stage selects exactly one `operator` or `script`. Put every
operator-specific setting under `config`:

```yaml
operators:
  select:
    operator: greedy
    timeout_s: 600
    config: {}
  mutate:
    operator: hyperagents
    timeout_s: 3600
    config:
      runner: harbor
      editable_roots: [target]
```

Check the complete composition before initialization:

```bash
evolve recipe check /path/to/recipe/evolve.yaml
evolve recipe check /path/to/recipe/evolve.yaml --json
```

Recipe-local operator directories are rejected. A `script:` binding is still
executable, but `recipe check` marks it non-portable because it depends on a
filesystem path outside the shared named catalog.

## Inspect initialized bindings

After initialization:

```text
operators/       frozen active recipe-selected operator scripts
library/         frozen runtime helpers imported by selected library operators
evolve.yaml      normalized operator config
.evolve-components.json   source identity, digest, and portability
```

Inspect the active configuration with:

```bash
./evolve operator active .
./evolve operator active . --json
cat operators/README.md
```

Direct orchestration can invoke a configured stage and retains its artifacts:

```bash
./evolve operator run . rollout --genid 1 --parent 0
./evolve operator run . mutate --genid 1 --parent 0 --config '{}'
./evolve finalize . 1 --parent 0
```

Operators execute as subprocesses. They should write diagnostics beneath their
generation run directory and return the typed result for their interface. They
must not write evaluator truth, generation tags, or archive outcomes directly.
