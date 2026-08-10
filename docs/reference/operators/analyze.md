# Analyze

`analyze` converts method-neutral rollout cases into bounded evidence for
`mutate`. It is optional, but recipes that need structured observations
should configure it explicitly.

```text
rollout/cases.json
  → analyze
  → analyze/evidence/
  → feedback/evidence/selected.md
  → mutate
```

## Contract

```python
class AnalyzeOperator:
    def analyze(self, checkout, ctx) -> AnalyzeResult: ...
```

The result contains a summary and artifact paths.

## Library operators

| Operator | Selected evidence |
| --- | --- |
| `failure_patterns` | aggregate metrics, verifier-grounded failure clusters, representatives, and passing behavior |
| `trace_browser` | compact metrics and filesystem instructions for retained raw traces |
| `trajectory_only` | A-Evolve behavior-only proxy judgments without evaluator labels or task text |
| `ahe` | per-task debugger analysis for Agentic Harness Engineering |
| `gepa` | component-oriented reflective examples and datasets |
| `artifact_rubric` | artifact-oriented rubric evidence for poster and document tasks |

## Configuration

```yaml
operators:
  rollout:
    operator: harbor
    config:
      budget_tasks: 8
  analyze:
    operator: failure_patterns
    timeout_s: 600
    config:
      max_chars: 30000
```

Common bounds include `max_chars`, `max_cases`, `max_tasks`, `field_limit`,
history depth, concurrency, retry count, and per-task timeout. Operator-specific
keys should be copied from the closest supported recipe.

## Inputs and artifacts

Most deterministic operators write an auditable evidence bundle:

```text
runs/gen-N/analyze/evidence/raw_traces.jsonl
runs/gen-N/analyze/evidence/failure_records.json
runs/gen-N/analyze/evidence/failure_patterns.json
runs/gen-N/analyze/evidence/passing_behaviors.json
runs/gen-N/analyze/evidence/reflective_records.jsonl
runs/gen-N/analyze/evidence/metrics.json
runs/gen-N/analyze/evidence/manifest.json
runs/gen-N/analyze/evidence/selected.md
```

`selected.md` is copied to `feedback/evidence/selected.md` and included in the
mutate prompt.

`gepa` additionally writes reflective datasets and per-component reflection.
`ahe` writes debugger-oriented case analysis.

## Fidelity boundary

All operators except `trajectory_only` deterministically parse, filter, cluster,
serialize, and truncate existing rollout facts.

`trajectory_only` adds an isolated behavior-only model judge. Its evidence
directory intentionally omits reward, verifier output, task input, and raw-case
paths. The A-Evolve Harbor bundle also omits archive and run history so those
labels cannot be recovered by filesystem inspection.

The operator selects an evidence shape; it does not by itself reproduce every
search or optimization capability of the method that motivated it.
