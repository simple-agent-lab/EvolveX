# Reflect

`reflect` derives reusable insights from verified archive history. It is
optional and is distinct from `trace_analyzer`: trace analysis prepares
generation-local mutation feedback, while reflection backfills knowledge from
outcomes that have already been verified.

## Contract

```python
class ReflectOperator:
    def reflect(self, archive, ctx) -> ReflectResult: ...
```

The result contains reflection artifacts and annotations defined by the
operator interface.

## Variants

| Variant | Reflection policy |
| --- | --- |
| `credit` | convert verified fixes and notes into reusable playbook insights, retaining generation provenance |

## Configuration

```yaml
operators:
  reflect:
    variant: credit
    timeout_s: 600
```

`credit` reads verified archive fields such as confirmed fixes and notes,
groups reusable insights, and retains the generations that support each entry.

Because `reflect` uses verified history, it should not be used to expose sealed
or protected evaluation data to the current mutation prompt. Reflection output
must follow the same evidence-visibility policy as the recipe.

