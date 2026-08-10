# Record

`record` attaches method-specific evidence and compact experience to the
append-only archive after gate handling. It is required.

## Contract

```python
class RecordOperator:
    def annotate(self, child, ctx) -> RecordResult: ...
```

The result contains archive fields and artifact paths. The framework stamps the
durable archive row; the operator does not write outcome truth directly.

## Variants

| Variant | Recorded data |
| --- | --- |
| `jsonl` | generic meta-agent, gate, task-vector, usage, and artifact pointers |
| `gepa` | GEPA proposal, comparison, component paths, and reflective-dataset pointers |
| `hyperagents` | compact HyperAgents experience |

## Artifacts

`gepa` writes:

```text
runs/gen-N/record/gepa-experience.json
```

`hyperagents` writes:

```text
runs/gen-N/record/experience.json
```

`jsonl` reads standard contract artifacts such as:

```text
runs/gen-N/mutate/predicted_fixes.json
runs/gen-N/mutate/rationale.md
runs/gen-N/mutate/usage.json
runs/gen-N/gate.json
```

Use the record variant paired with the recipe's method. Record artifacts are
evidence and archive annotations; they must not disguise a failed stage or
create a generation tag for an invalid child.

