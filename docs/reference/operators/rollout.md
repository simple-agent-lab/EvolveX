# Rollout

`rollout` produces the training behavior and evidence used to propose a child.
It is required. Rollout evidence may inform mutation, so a benchmark rollout
must consume only the frozen train split.

## Contract

```python
class RolloutOperator:
    def rollout(self, checkout, ctx) -> RolloutResult: ...
```

The result contains a summary and artifact paths.

## Variants

| Variant | Behavior |
| --- | --- |
| `harbor` | run a bounded train batch through Harbor and normalize trajectories, verifier output, usage, and failures |
| `parent_evaluation` | expose sanitized, certified evaluation evidence already attached to the selected parent |
| `failure_focused` | select failure-oriented training/evaluation metadata |
| `noop` | emit empty rollout evidence for controlled tests |

## `harbor` configuration

```yaml
operators:
  rollout:
    variant: harbor
    budget_tasks: 10
    task_sampling: generation_shuffle
    n_concurrent: 4
    agent_setup_timeout_multiplier: 1
    verifier_timeout_multiplier: 1
    max_retries: 1
    timeout_s: 3600
```

Important keys:

- `budget_tasks`: maximum train tasks in this generation;
- `task_sampling`: `head` or deterministic `generation_shuffle`;
- `task_names`: optional exact names from the frozen train split;
- `n_concurrent`: concurrent Harbor trials;
- `agent_setup_timeout_multiplier`, `agent_timeout_multiplier`, and
  `verifier_timeout_multiplier`: multiply the corresponding limits declared
  by each task's `task.toml`; keep the operator `timeout_s` large enough for
  the resulting longest trial;
- `agent_env` and agent/runtime settings: inputs forwarded to the rollout
  adapter;
- `max_retries` and `timeout_s`: infrastructure retry and operator limits.

`operators.rollout.path` is incompatible with a resolved frozen split because
it would bypass frozen dataset membership.

## Artifacts

The Harbor variant writes normalized evidence such as:

```text
runs/gen-N/rollout/summary.json
runs/gen-N/rollout/cases.json
runs/harbor-rollouts/gen-N/
```

`cases.json` is the method-neutral input to `trace_analyzer`. It includes task
identity, ordered model/tool events, verifier evidence, outcome, exception,
usage, timing, and artifact inventory.
