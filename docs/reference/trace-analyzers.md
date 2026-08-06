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
| `trajectory_only` | A-Evolve-style behavior-only signals, failure-focused compression, and LLM proxy verdicts; no evaluator labels, task text, or raw-case paths. |
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

Most variants write the same auditable base files:

- `trace_analyzer/evidence/raw_traces.jsonl`;
- `trace_analyzer/evidence/failure_records.json`;
- `trace_analyzer/evidence/failure_patterns.json`;
- `trace_analyzer/evidence/passing_behaviors.json`;
- `trace_analyzer/evidence/reflective_records.jsonl`;
- `trace_analyzer/evidence/metrics.json`;
- `trace_analyzer/evidence/manifest.json`;
- `trace_analyzer/evidence/selected.md`.

`trajectory_only` is deliberately narrower. It first asks an isolated,
read-only LLM judge to estimate each trajectory's score, category, outcome, and
failure reason using the compressed behavior alone. It then writes only
`manifest.json`, `trajectory_only.json`, and `selected.md`; it does not
place reward, outcome, verifier output, task input, or `raw_traces.jsonl` in
the meta-agent evidence directory.

`selected.md` is copied into `feedback/evidence/selected.md` and its body is
injected into the meta-agent prompt. Raw files remain available through
`$EVOLVE_RUN_DIR/trace_analyzer/evidence/`.

For `trajectory_only`, the A-Evolve meta-agent receives only the selected
behavior view. Its Harbor workspace bundle omits `archive.jsonl` and `runs/`,
so evaluator labels cannot be recovered by filesystem discovery.

## Fidelity boundary

All variants except `trajectory_only` are deterministic: they parse, filter,
cluster, serialize, and truncate existing rollout facts without another model
call. `trajectory_only` intentionally adds the same separate behavior-only
proxy-judge stage used by the official A-Evolve path. The judge may use the
configured meta-agent model but runs in an empty read-only Harbor task and
cannot inspect evaluator labels or the candidate workspace. These variants
define trace-retention interfaces; they do not reproduce every surrounding
search capability of the papers that motivated the former profiles.
