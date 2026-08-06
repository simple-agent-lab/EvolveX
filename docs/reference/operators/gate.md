# Gate

`gate` decides whether a canonically evaluated child is eligible to join the
parent population. It is required. It consumes evaluator truth; it does not
calculate or overwrite scores.

## Contract

```python
class GateOperator:
    def decide(self, child, parent, ctx) -> GateResult: ...
```

The result is `accept` or `reject` with a reason.

## Variants

| Variant | Decision rule |
| --- | --- |
| `hillclimb` | compare the child's score with the matched parent's score |
| `parent_eligible` | accept a canonical benchmark-complete child that is marked selection-eligible |
| `ahe_artifact_valid` | require canonical AHE completion, selection eligibility, and valid artifacts |

## Configuration

```yaml
operators:
  gate:
    variant: hillclimb
    strict: true
    timeout_s: 600
```

For `hillclimb`:

- `strict: true` requires an improvement;
- `strict: false` allows a tie under the gate rule.

The comparison must use the matched parent under the same evaluation identity.
Gate cannot admit an incomplete, infrastructure-invalid, or noncanonical
evaluation by manufacturing a score.

The mechanism retains the gate decision with the generation run and durable
archive event.

