# Recipe Reasoning and Budget Design

## Goal

Make the AHE and HyperAgents recipes state and enforce their intended OpenAI reasoning effort and unlimited agent budgets:

| Recipe | Meta-agent reasoning | Target-agent reasoning | Cost limits |
| --- | --- | --- | --- |
| AHE | `xhigh` | `high` | none |
| HyperAgents | `high` | `high` | none |

This change corrects a confirmed configuration-parity failure. It does not claim that reasoning effort alone explains the observed Terminal-Bench 2.0 accuracy gap.

## Confirmed Problem

The target evaluator currently passes only the model name into the evolvable MiniSWE source adapter. The adapter loads MiniSWE's `mini` config, whose model arguments contain `drop_params: true` but no reasoning effort, and constructs `LitellmModel` on the Chat Completions path.

Recorded AHE and HyperAgents seed trajectories consequently contain no configured reasoning effort and zero reasoning tokens across every response inspected. Harbor's built-in MiniSWE adapter already handles OpenAI reasoning differently: it selects MiniSWE's Responses model and supplies `reasoning.effort`.

The recipes also impose budgets that conflict with the requested experiment policy:

- AHE explicitly sets the target MiniSWE cost limit to `$3`.
- HyperAgents inherits MiniSWE's default `$3` target limit.
- HyperAgents declares an experiment-wide `budget_usd: 150`.

## Non-Goals

- Do not claim that the corrected configuration will reproduce OpenAI's official GPT-5.4 score.
- Do not treat a nonzero reasoning-token count as proof of benchmark parity.
- Do not change Terminal-Bench task timeouts, resources, task membership, scoring, retry policy, or sampling in this change.
- Do not restart, resume, or mutate existing remote experiments.
- Do not change smoke recipes or unrelated production recipes.
- Do not add a new general model-configuration subsystem.

## 1. Recipe Policy

### AHE

The Harbor meta-agent configuration must explicitly pass these native agent arguments:

```yaml
agent_kwargs:
  reasoning_effort: xhigh
  cost_limit: 0
```

The target evaluator must explicitly pass:

```yaml
agent_env:
  MINISWE_REASONING_EFFORT: "high"
  MINISWE_COST_LIMIT: "0"
```

Existing AHE target step and command-timeout settings remain unchanged.

### HyperAgents

The Harbor meta-agent configuration must explicitly pass:

```yaml
agent_kwargs:
  reasoning_effort: high
  cost_limit: 0
```

The target evaluator must explicitly pass:

```yaml
agent_env:
  MINISWE_REASONING_EFFORT: "high"
  MINISWE_COST_LIMIT: "0"
```

Remove `experiment.budget_usd` entirely. Zero means unlimited for MiniSWE agent cost limits; absence means unlimited for the experiment-wide framework budget.

## 2. Target Evaluator Data Flow

The custom MiniSWE source adapter remains responsible for running the candidate's installed Python API rather than its CLI. Extend that adapter with one environment variable:

```text
evaluator.agent_env.MINISWE_REASONING_EFFORT
  -> Harbor --ae environment
  -> MiniSweSourceAgent._source_env()
  -> candidate runner
  -> model class and model kwargs
```

`MINISWE_REASONING_EFFORT` accepts `none`, `low`, `medium`, `high`, or `xhigh`, case-insensitively after trimming whitespace. Missing or empty values retain the current non-reasoning `LitellmModel` behavior for compatibility with recipes that do not opt in. Any other non-empty value fails before the benchmark task begins.

For an `openai/` model with configured reasoning, the runner must:

1. construct `LitellmResponseModel` rather than `LitellmModel`;
2. set `model_kwargs["reasoning"] = {"effort": effort}`;
3. remove incompatible top-level reasoning keys if present;
4. preserve the candidate config's other recognized model arguments;
5. set `cost_tracking` to `ignore_errors` as it does today.

This mirrors Harbor's installed MiniSWE behavior for OpenAI reasoning models. The actual task run and model preflight must call the same model-construction helper so preflight cannot validate a different API path from the evaluated task.

For non-OpenAI providers, the adapter may continue using `LitellmModel`; this design does not add provider-specific reasoning mappings because both affected recipes use OpenAI GPT-5.4.

## 3. Unlimited Budget Semantics

The target runner continues to derive `AgentConfig.cost_limit` from `MINISWE_COST_LIMIT` when present. A value of `0` is passed through as numeric zero, which MiniSWE defines as unlimited.

Reasoning effort and budget remain independent. Configuring `high` or `xhigh` must not silently insert a default cost limit. Conversely, selecting unlimited cost must not change reasoning effort.

The meta-agent uses Harbor's native MiniSWE `reasoning_effort` support. Explicit `cost_limit: 0` documents and enforces the unlimited policy even though the current Harbor default is already zero.

## 4. Template Consistency

The framework maintains two copies of the custom source adapter:

- `templates/workspace/evolve_harbor_adapter/__init__.py` for initialized workspaces;
- `templates/target/harbor/miniswe_source_agent.py` as the source template.

Both copies must receive equivalent reasoning, validation, preflight, and cost-limit behavior. Existing unrelated workspace changes, including mounted-cache link mode, must be preserved.

## 5. Failure Behavior and Evidence

Invalid reasoning effort must fail with a message that names `MINISWE_REASONING_EFFORT`, the invalid value, and the accepted values. The failure occurs during model preflight, before paid task execution.

The generated MiniSWE trajectory remains the authoritative runtime evidence. A configuration canary is successful only when its trajectory shows:

- the Responses model class;
- the requested reasoning effort in model arguments;
- cost limit `0`;
- at least one model response with nonzero reasoning tokens.

The first three conditions prove framework propagation. The fourth proves that the selected external endpoint honored the request for that canary. None proves expected Terminal-Bench accuracy.

## 6. Benchmark-Parity Follow-Up

After implementation, run a paid canary separately from the code change. First use one task to verify endpoint behavior and collect cost. Then use a fixed small task subset to compare failure modes before scheduling a full evaluation.

If a correctly configured run remains far below a reasonable MiniSWE baseline, investigate these boundaries independently:

1. internal endpoint versus official OpenAI endpoint behavior;
2. Responses API payload and returned reasoning usage;
3. MiniSWE versus Codex harness and prompt differences;
4. 30-second command-timeout frequency and recovery;
5. model-call, token, and wall-clock termination;
6. Terminal-Bench dataset commit and task configuration;
7. reward parsing, aggregation, and `k` semantics;
8. infrastructure failures classified as benchmark failures.

That audit is a distinct diagnostic task. It must compare trajectories and task outcomes rather than assuming the reasoning correction resolves the performance gap.

## Verification

### Recipe Tests

- AHE declares meta-agent `xhigh`, target-agent `high`, and zero agent cost limits.
- HyperAgents declares `high` for both agents and zero agent cost limits.
- HyperAgents has no `budget_usd` field.
- Unrelated recipe settings remain unchanged.

### Adapter Tests

- `_source_env()` forwards `MINISWE_REASONING_EFFORT`.
- Missing effort preserves the existing `LitellmModel` path.
- OpenAI plus `high` or `xhigh` constructs `LitellmResponseModel` with nested `reasoning.effort`.
- The model preflight and task runner use the same construction path.
- Invalid effort fails before task execution with the documented message.
- `MINISWE_COST_LIMIT=0` reaches `AgentConfig.cost_limit` as numeric zero.
- Both adapter templates implement equivalent behavior.
- Existing candidate-install, proxy, cache, and runtime-evidence tests continue to pass.

### Runtime Canary

- Inspect the saved trajectory rather than relying on YAML alone.
- Confirm the requested effort and unlimited cost in serialized configuration.
- Confirm nonzero reasoning tokens from the endpoint.
- Record task, endpoint, model snapshot, token usage, cost, and outcome for later parity analysis.
