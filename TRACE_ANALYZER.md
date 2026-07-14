# Trace analyzer operator

Trace selection is independent from rollout:

```text
rollout -> rollout/cases.json -> trace_analyzer -> feedback bundle -> meta_agent
```

Harbor remains one rollout engine, but it no longer chooses or renders meta-agent
evidence. The required `trace_analyzer` operator reads method-neutral cases and
writes the selected view under `runs/gen-N/trace_analyzer/`.

## Variants

```yaml
operators:
  rollout: {variant: harbor, budget_tasks: 8}
  trace_analyzer: {variant: failure_patterns, max_chars: 30000}
```

| Variant | Selected meta-agent evidence |
|---|---|
| `failure_patterns` | Aggregate metrics, verifier-grounded failure signatures, representatives, and passing behavior to preserve. |
| `failed_traces` | Aggregate metrics plus detailed failed/agent-error execution records. |
| `trace_browser` | A small metrics summary and filesystem instructions for raw traces, source, and prior generations. |
| `execution_records` | Complete per-case input/output, ordered actions, tool results, verifier feedback, metrics, and history pointers. |
| `utility_metrics` | Per-task downstream utility and the current editable source; trajectories are not emphasized. |

The variants describe evidence shape, not a paper or search algorithm. Several
former method-named profiles produced the same shape and are intentionally
merged:

| Former profile(s) | New variant |
|---|---|
| `self_harness` | `failure_patterns` |
| `dgm` | `failed_traces` |
| `hyperagents`, `meta_harness` | `trace_browser` |
| `sia`, `ace`, `mce`, `adas`, `aflow`, `gepa` | `execution_records` |
| `stop` | `utility_metrics` |

This is a configuration migration table only. Method names are not runtime
variant names and do not appear in new manifests.

## Inputs and artifacts

The analyzer reads:

- `rollout/cases.json`: normalized task identity, reward/outcome, ordered
  message/tool-call/tool-result events, verifier evidence, exceptions, usage,
  timing, and artifact inventory;
- prior run metrics and lineage through the feedback history generated after
  analysis.

Every variant writes the same auditable base files:

- `trace_analyzer/evidence/raw_traces.jsonl`;
- `trace_analyzer/evidence/failure_records.json`;
- `trace_analyzer/evidence/failure_patterns.json`;
- `trace_analyzer/evidence/passing_behaviors.json`;
- `trace_analyzer/evidence/reflective_records.jsonl`;
- `trace_analyzer/evidence/metrics.json`;
- `trace_analyzer/evidence/manifest.json`;
- `trace_analyzer/evidence/selected.md`.

`selected.md` is copied into `feedback/evidence/selected.md` and its body is
injected into the meta-agent prompt. Raw files remain available through
`$EVOLVE_RUN_DIR/trace_analyzer/evidence/`.

## Fidelity boundary

The analyzer is deterministic: it parses, filters, clusters, serializes, and
truncates existing rollout facts without another model call. The later meta-agent
model performs reflection and editing. These variants define trace-retention
interfaces; they do not reproduce the full search algorithms of the papers that
motivated the former profiles.
