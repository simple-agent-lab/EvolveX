# Validate

`validate` performs a method-specific candidate check before canonical
evaluation and `gate`. It is optional and does not replace the fixed evaluator.

## Contract

```python
class ValidateOperator:
    def validate(self, checkout, ctx) -> ValidateResult: ...
```

The result contains an acceptance boolean, reason, and artifact paths.

## Library operators

| Operator | Validation rule |
| --- | --- |
| `minibatch_improvement` | rerun a GEPA child on the exact parent minibatch and apply an improvement criterion |
| `hyperagents` | apply the fixed HyperAgents validation contract |

## `minibatch_improvement`

```yaml
operators:
  validate:
    operator: minibatch_improvement
    timeout_s: 3600
    config:
      criterion: strict
      n_concurrent: 4
      max_retries: 1
```

The validator reads the parent's rollout cases, runs the child on the same task
names, rejects incomplete or infrastructure-invalid comparisons, and writes:

```text
runs/gen-N/validate/comparison.json
runs/gen-N/validate/parent-cases.json
runs/gen-N/validate/child-cases.json
runs/gen-N/validate/child-eval/
```

Use the criterion declared by the method, such as `strict` or
`non_decreasing`; changing it changes the experiment policy.

## `hyperagents`

The HyperAgents validator applies its fixed candidate check and retains its
compile/check log beneath:

```text
runs/gen-N/validate/
```

If no `validate` block is present, the driver proceeds from mutation (and any
configured `novelty`) to canonical evaluation.
