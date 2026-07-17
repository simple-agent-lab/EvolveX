# Official-Style AHE Recipe Alignment Design

**Date:** 2026-07-17

**Status:** Approved direction; pending written-spec review

**Baseline:** `main` at `c5dda920b9b90547d0e30129f4445f5a9664647a`

## Goal

Make the existing AHE recipe substantially closer to the official
`china-qijizhifeng/agentic-harness-engineering` implementation while keeping AHE
an ordinary composition of this framework's existing operators. The result must
remain a recipe, not a second orchestration framework.

The defining loop is:

```text
evaluate current harness
-> run one LLM debugger analysis per evaluated task
-> aggregate official-style task reports
-> attribute current outcomes to the preceding change manifest
-> let the evolve agent KEEP, REVISE, or ROLLBACK + PIVOT
-> validate one manifest-backed target edit
-> evaluate that child in the next iteration
```

## Scope

This design changes only the AHE recipe and small AHE-specific operator variants,
plus shared Harbor code only when a genuinely method-neutral helper is necessary.
It does not add AHE branches to `src/evolve/driver.py`, change the operator
protocol, vendor the official orchestrator, or revive the earlier
`codex/method-faithful-ahe` subsystem.

HyperAgents validation and prompt changes are a separate design and implementation
cycle.

## Current Main Behavior

Current `main` already supplies the correct operator lifecycle and most debugger
input preparation:

1. `rollout/harbor.py` executes the selected MiniSWE harness and emits normalized
   task cases containing instructions, messages, tool calls, observations,
   verifier output, exceptions, usage, and timing.
2. `trace_analyzer/ahe.py` redacts and bounds those cases, prioritizes failures,
   and writes deterministic evidence.
3. `meta_agent/ahe.py` gives the evidence to one Harbor MiniSWE agent that both
   diagnoses and edits the target.
4. Greedy selection and a strict hill-climb gate discard a lower-scoring child.
5. `ahe-report.json` is optional and is referenced by a host path that the
   containerized editor cannot reliably write.

The missing official-style behavior is a required per-task LLM debugger stage,
cross-iteration change attribution, a required change manifest, and sequential
evolution that can observe and respond to a regression.

## Architecture

### Existing mechanism remains unchanged

The generic driver continues to invoke:

```text
select -> rollout -> trace_analyzer -> meta_agent -> validate -> evaluation -> gate -> record
```

All new policy remains in AHE library variants and their artifacts. Harbor remains
the only live execution backend. `target/**` remains the only mutable AHE surface;
the evaluator, Harbor adapter, model selection, task partitions, credentials, and
resource limits remain frozen.

### AHE operator composition

The recipe uses:

```yaml
operators:
  select: {variant: ahe_latest}
  rollout: {variant: harbor, ...}
  trace_analyzer: {variant: ahe, max_tasks: 90, max_concurrent: 16,
                   timeout_per_task: 600, retry_attempts: 3, timeout_s: 3600}
  meta_agent: {variant: ahe, runner: harbor, agent: mini-swe-agent,
               model: openai/gpt-5.4, environment: docker,
               editable_roots: [target], max_retries: 0, timeout_s: 3600}
  gate: {variant: ahe_artifact_valid}
  record: {variant: jsonl}
```

The recipe removes `budget_usd` because the framework does not enforce it. It
also removes the obsolete `max_cases` setting.

## Official-Style LLM Debugger

### Task grouping and ordering

`trace_analyzer/ahe.py` groups all rollout cases by task name. One debugger call
receives every available rollout for that task so it can compare passing and
failing attempts. Tasks are ordered like the official implementation:

1. timeouts and tasks with failed attempts;
2. all-pass tasks for success summaries.

The analyzer retains the official configuration names and defaults:

- `max_tasks: 90`;
- `max_concurrent: 16`;
- `timeout_per_task: 600` seconds;
- `retry_attempts: 3`.

With the current eight-task rollout, every task is analyzed. `max_tasks` remains
an explicit official-style upper bound rather than an unbounded local extension.

### Debugger input

Each debugger prompt contains only redacted, bounded evidence for one task:

- task instruction and identity;
- rollout verdict labels;
- ordered agent messages and events;
- tool calls, arguments, observations, and final response;
- verifier reward and failure output;
- exceptions and timeout timing;
- passing-versus-failing traces when `k > 1`.

Failure prompts ask for the failure point, root cause, correct alternative, and a
general harness mechanism. All-pass prompts ask for the key strategy, success
factors, reusable pattern, and fragility risk. These are adapted directly from
the official AHE debugger prompts.

### Model and Harbor configuration

No second model configuration is introduced. The trace analyzer reads the frozen
`operators.meta_agent` block from the workspace's `evolve.yaml` and reuses an
allowlisted subset:

- `agent`, `model`, `environment`, and `image`;
- `agent_kwargs`, `agent_env`, and `agent_pythonpath`;
- Harbor authentication and proxy environment already handled by the runner.

Mutation-only values such as `editable_roots` are never inherited. Each debugger
call is a separate evidence-only Harbor Exec task. It receives no candidate
checkout and cannot modify `target/**`. Its final response is the debugger report.

### Concurrency and failure semantics

The first task runs serially to expose setup/authentication errors deterministically.
Remaining task calls run with a bounded thread pool of `max_concurrent` workers.
Each task may be attempted `retry_attempts` times within `timeout_per_task`.

There is deliberately no analysis fallback. After retries, any Harbor error,
timeout, missing trial, trial exception, missing response, or malformed result
makes the trace-analyzer subprocess exit nonzero. The framework records
`operator_failed`, and the meta-agent does not run. This differs from the official
repository's fallback prose but follows the explicit experiment requirement that
a missing debugger must fail visibly rather than silently degrade the method.

### Debugger artifacts

The analyzer writes:

```text
trace_analyzer/
├── analysis/
│   ├── overview.md
│   ├── change_evaluation.json
│   └── detail/
│       └── <safe-task-name>.md
├── debugger/
│   ├── command-<task>.json
│   ├── prompt-<task>.md
│   ├── harbor-<task>.log
│   └── jobs/
└── evidence/
    ├── overview.json
    └── cases.jsonl
```

`overview.md` is an official-style deterministic aggregation of the per-task LLM
reports; it is not an additional overview LLM call. This matches the current
official implementation. It lists timeouts, failure diagnoses, and all-pass
summaries and points to every detail report.

`feedback.md` and `evidence/selected.md` contain the overview followed by the
validated per-task reports. This is intentional: the Harbor editor receives the
feedback as prompt context and cannot follow host-only filesystem paths. Raw
bounded cases remain separate for auditability.

## Cross-Generation Attribution

The AHE selector advances to the newest structurally valid generation rather than
the highest score. Generation `N` therefore rolls out generation `N-1`; the prior
run's rollout describes generation `N-2`. With static training sampling, the
trace analyzer compares task outcomes across those two rollouts to evaluate the
manifest that produced generation `N-1`.

`analysis/change_evaluation.json` records, per task:

- `fail_to_pass`;
- `pass_to_fail`;
- `unchanged_pass`;
- `unchanged_fail`;
- infrastructure/unknown transitions;
- whether the transition matched a predicted effect or declared risk in the
  preceding manifest.

The first generation has no preceding comparison and records a baseline status.
Missing prior artifacts after the baseline are an explicit analyzer failure,
because silent loss of attribution would violate the method claim.

## Required Change Manifest

The current optional `ahe-report.json` is replaced by a required
`meta_agent/change_manifest.json`. Because the Harbor editor cannot write a host
run-directory path, the prompt requires its final response to contain exactly one
delimited JSON manifest. `meta_agent/ahe.py` extracts, validates, and persists it
after Harbor returns the candidate bundle.

The manifest contains:

```json
{
  "schema_version": 1,
  "generation": "1",
  "parent": "0",
  "decision": "keep|revise|rollback_pivot",
  "changes": [
    {
      "id": "change-1",
      "type": "new|improvement|rollback",
      "files": ["target/path.py"],
      "evidence_tasks": ["task-name"],
      "root_cause": "...",
      "targeted_fix": "...",
      "predicted_effects": ["task-name"],
      "risk_tasks": ["task-name"],
      "component": "prompt|tool|control_flow|memory|middleware|other"
    }
  ],
  "validation": {
    "commands": ["..."],
    "result": "passed"
  }
}
```

Validation requires exact generation and parent identity, one coherent decision,
safe `target/**` paths, coverage of every changed path exactly once, cited tasks
present in the current debugger artifacts, and nonempty causal/prediction fields.
`rollback_pivot` requires at least one rollback change and a distinct non-rollback
pivot. A missing, malformed, inconsistent, or incomplete manifest fails the
meta-agent operator and prevents candidate evaluation.

## Evolve-Agent Prompt

`meta_agent/ahe.py` remains the reasoning and editing operator. Its prompt is
adapted from the official evolve prompt and makes the two-generation convention
explicit:

- current debugger reports evaluate the selected parent;
- `change_evaluation.json` evaluates the preceding manifest;
- the agent must decide `KEEP`, `REVISE`, or `ROLLBACK + PIVOT` before editing;
- every edit must cite debugger evidence and state a falsifiable effect;
- repeated failure at one component level should pivot to another level;
- pass@1 remains the optimization target;
- the final response must contain the required manifest.

The prompt embeds the overview, detail reports, attribution, relevant prior
manifest, recent archive outcomes, surface rules, and remaining iterations. It
does not expose sealed evaluation artifacts or mutable resource/model settings.

## Selection, Gate, and Final Champion

`ahe_latest` selects the newest valid AHE generation. It never chooses by score.
This permits the next iteration to diagnose a regression and roll it back, which
strict hill climbing prevents.

`ahe_artifact_valid` accepts a child only when canonical evaluation completed and
the required manifest was validated. Aggregate score does not control parent
eligibility. Operator, surface, validation, evaluation, or manifest failure still
rejects the child.

The archive retains scores for reporting. The existing final-anchor behavior may
still evaluate the best observed eligible candidate for the sealed result; this
does not feed another mutation.

## Testing

### Trace-analyzer tests

- group all rollouts for the same task into one debugger request;
- order failed/timeout tasks before all-pass tasks;
- enforce official defaults and `max_tasks` behavior;
- verify failure and success prompt variants for `k=1` and `k>1`;
- verify reuse of allowlisted meta-agent Harbor configuration only;
- verify bounded concurrency and retry counts;
- fail on exhausted retry, timeout, malformed Harbor result, or empty response;
- write overview and safe per-task detail paths;
- preserve redaction and bounded evidence behavior;
- compare current and prior static rollouts into exact transition classes.

### Meta-agent and manifest tests

- embed debugger overview, details, attribution, and prior manifest in the prompt;
- extract exactly one delimited manifest from Harbor output;
- reject missing, malformed, stale-generation, incomplete, or path-mismatched
  manifests;
- reject incomplete rollback/pivot decisions;
- preserve Harbor usage and failure artifacts.

### Recipe and lifecycle tests

- initialize `ahe_latest`, the official debugger defaults, AHE meta-agent, and
  `ahe_artifact_valid` from the recipe;
- remove `budget_usd` and `max_cases` from the AHE recipe;
- demonstrate baseline -> accepted change -> regression -> rollback/pivot across
  deterministic fake-Harbor generations;
- prove a lower-scoring but structurally valid generation remains the next parent;
- prove debugger failure prevents meta-agent execution;
- run the full unit suite, Ruff, `ty`, package build, and diff checks;
- run a real two-task Harbor smoke before starting the long experiment.

## Acceptance Criteria

1. Every rollout task selected under the official `max_tasks` bound receives one
   required LLM debugger analysis containing all its rollouts; the current
   eight-task recipe therefore analyzes every rollout task.
2. The AHE editor receives official-style overview/detail reports and explicit
   cross-generation attribution.
3. Every candidate has one validated manifest covering the complete target diff.
4. A debugger or manifest failure is visible and stops the generation.
5. A valid regression can become the next parent and drive an explicit
   rollback/pivot decision.
6. No AHE-specific branch or schema is added to the generic driver or interfaces.
7. The implementation remains a small recipe composition over existing operator
   contracts.
8. A real two-task smoke completes before the expensive experiment begins.
