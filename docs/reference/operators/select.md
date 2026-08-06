# Select

`select` chooses one or more valid parent generations from the durable archive.
It is required and runs before a child checkout is created.

## Contract

Implementation interface:

```python
class SelectOperator:
    def pick(self, archive, ctx) -> SelectResult: ...
```

The result contains parent generation IDs. A selector must use valid archive
parents; it must not invent a generation or select an ineligible row.

## Variants

| Variant | Selection policy |
| --- | --- |
| `greedy` | highest-scoring valid parent |
| `newest` | newest valid parent |
| `random` | uniform random valid parent |
| `score_weighted` | random parent weighted by nonnegative score |
| `ahe_latest` | newest structurally valid AHE generation, independent of score |
| `pareto` | GEPA selection from per-task Pareto frontiers |
| `score_child_prop` | HyperAgents score-proportional selection with a child-count penalty |

## Configuration

```yaml
operators:
  select:
    variant: greedy
    timeout_s: 600
```

Stochastic selectors use the experiment/operator seed so a frozen workspace can
reproduce their decision process. Method-specific variants may write selection
diagnostics; for example, `pareto` writes:

```text
runs/gen-N/select/pareto.json
```

## Choosing a variant

- Use `greedy` for a simple hill-climbing baseline.
- Use `ahe_latest` when artifact-valid iteration matters more than current
  aggregate score.
- Use `pareto` when per-task coverage defines the population.
- Use `score_child_prop` when high-scoring parents should be favored without
  repeatedly expanding the same lineage.

