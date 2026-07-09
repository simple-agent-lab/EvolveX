# Agent Runner, Harbor Evaluation, and Real Recipes Design

## Context

The current framework mixes three concepts that should be separate:

- The evaluated target agent, which should run through Harbor.
- The mutation agent, which edits a local git checkout.
- Smoke scaffolding, which exists to make CI and local mechanism tests cheap.

This causes confusing behavior. `CheckoutTargetAgent` can fall back to arbitrary
scripts such as `solve.sh` or `run.sh`; production recipe names still use
deterministic `fixed` mutation; HyperAgents exposes `operators/**` but the
default mutator does not actually evolve those operators; and `meta_eval`
currently forces `EVAL_STUB=1` during operator-surface admission replay.

## Goals

1. Make Harbor the only real benchmark execution interface.
2. Add a small, reusable primitive for running a local mutation agent:
   `run_agent(workspace, prompt)`.
3. Keep `MutateOperator` as the evolve protocol adapter, but make it call the
   simple agent runner instead of embedding runner logic.
4. Split real recipes from smoke recipes. Real recipes should be structurally
   real and fail fast if required live agent or Harbor configuration is missing.
5. Make HyperAgents truthful: changed mutation workflow is used in later
   generations, and changed gate or record workflow may affect the same
   generation. The docs must say this plainly.
6. Stop real self-modification admission from using the stub evaluator unless a
   smoke or test run explicitly opts into `EVAL_STUB=1`.

## Non-Goals

- Do not build a new Harbor agent framework.
- Do not make the mutation agent a Harbor `BaseAgent`.
- Do not add an executable `program.md` orchestrator in this change.
- Do not remove all cheap tests. Cheap tests move to explicit smoke recipes and
  explicit `EVAL_STUB=1` test paths.

## Core Decision

Use two agent interfaces, each with one job:

- **Target evaluation agent:** a Harbor `BaseAgent` subclass under `target/`.
  This is the only real benchmark execution path.
- **Mutation agent runner:** a local process runner that receives a workspace
  path and a prompt, then edits files in that workspace.

`MutateOperator` remains the framework protocol boundary. It builds the prompt,
calls the mutation agent runner, validates the surface, and writes evolve
artifacts.

## Architecture

### Harbor Target Agent

`templates/evaluator/checkout_agent.py` should only delegate to a Harbor
`BaseAgent` subclass. It should look for these classes:

- `target.harbor_agent.HarborAgent`
- `target.agent.HarborAgent`
- `target.agent.TargetAgent`
- `target.agent.Agent`

If none exists, Harbor evaluation fails with an actionable error naming the
accepted class locations. The real evaluator path should not execute
`target/solve.sh`, `target/run.sh`, `target/agent.sh`, `target/agent.py`,
`target/run.py`, or `target/main.py` as scripts.

The default target template should provide a minimal Harbor-compatible agent.
Smoke tests may still use `evaluator/stub_eval.py` and do not need to execute
the Harbor agent.

### Local Agent Runner

Add `src/evolve/agent.py` with a small API:

```python
result = run_agent(
    workspace=checkout,
    prompt=prompt,
    command=command,
    timeout_s=timeout_s,
)
```

`run_agent` is responsible only for process execution:

- Write the prompt to a temporary file.
- Run the configured command with `cwd=workspace`.
- Export `EVOLVE_PROMPT_FILE`.
- Capture stdout, stderr, return code, and wall time.
- Kill the process group on timeout.
- Return an `AgentRunResult`.

The configured command may come from `operators.mutate.command` or
`EVOLVE_AGENT_COMMAND`. If neither is set in a real recipe, mutation fails fast
with a clear message. The runner should not know about generation IDs, archive
rows, surface checks, or mutate artifact files.

### Mutate Operator

Refactor `library/mutate/agent_command.py` so it becomes a thin protocol
adapter:

1. Build the mutation prompt from `operators/mutate.md`, feedback files, and
   surface rules.
2. Resolve the command from operator config or `EVOLVE_AGENT_COMMAND`.
3. Call `run_agent(workspace=checkout, prompt=prompt, ...)`.
4. Run surface validation and repair.
5. Write `mutate/rationale.md`, `mutate/predicted_fixes.json`,
   `mutate/usage.json`, and `mutate/changed.json` through the existing SDK path.

The operator should not reimplement generic process management.

## Recipe Policy

Real recipe names are reserved for real behavior:

- `hill_climb`
- `dgm`
- `ahe`
- `autoresearch`
- `hyperagents`
- `metaagent`

These recipes should use Harbor as their evaluator backend and a real mutation
adapter such as `agent_command`. They may require `EVOLVE_AGENT_COMMAND`,
Harbor, Docker, and model credentials. Missing live requirements should produce
clear failures rather than silently falling back to smoke behavior.

Smoke recipes should be explicitly named:

- `hill_climb-smoke`
- `dgm-smoke`
- `ahe-smoke`
- `autoresearch-smoke`
- `hyperagents-smoke`
- `metaagent-smoke`

Smoke recipes may use `fixed`, `noop`, `EVAL_STUB=1`, and deterministic target
fixtures. Tests that only verify framework mechanics should use smoke recipes.

## HyperAgents Semantics

HyperAgents is real only when mutation can edit `operators/**` and those edits
can affect subsequent execution.

The driver semantics are:

- A changed `operators/mutate.py` cannot affect the same mutation that created
  it. It can affect future children forked from the accepted generation.
- A changed `operators/gate.py` or `operators/record.py` can affect the same
  generation because gate and record run after mutation from the tagged child
  checkout.
- A changed `operators/select.py` or `operators/rollout.py` can affect future
  generations when that generation becomes the selected checkout for those
  operators.
- `program.md` is not executable under `./evolve run`. It should not be
  presented as an evolved workflow unless a later change adds an explicit
  agent-mode orchestrator that reads and follows it.

Real HyperAgents should use `agent_command` as its mutator and include
`operators/**` in the mutable surface. The old deterministic version should be
renamed `hyperagents-smoke`.

## Self-Modification Admission

`meta_eval` should not force `EVAL_STUB=1` for real runs. It should replay using
the same evaluator path that the workspace would normally use, while preserving
its existing recursion guard and isolated `EVOLVE_HOME`.

When a test or smoke recipe wants stub admission, it should explicitly set
`EVAL_STUB=1`. This keeps real operator-surface admission from being a cheap
stub check disguised as a real HyperAgents guard.

## Error Handling

- Missing Harbor `BaseAgent` in a real evaluation fails with an actionable
  message listing accepted target classes.
- Missing Harbor executable or Docker setup remains an `infra_failed` evaluator
  result.
- Missing mutation agent command fails the mutate operator with
  `operator_failed`, naming `EVOLVE_AGENT_COMMAND` and `operators.mutate.command`
  as the accepted configuration points.
- Agent timeout kills the agent process group and records timeout details in
  mutation rationale and usage.
- Surface violations are still repaired before the mechanism sees the mutation,
  using the existing surface repair behavior.

## Testing

Add or update tests for these behaviors:

- `run_agent` runs a fake command in a temporary workspace, passes
  `EVOLVE_PROMPT_FILE`, captures output, records wall time, and handles timeout.
- `agent_command` mutator delegates process execution to `run_agent` and still
  writes valid mutate artifacts.
- `CheckoutTargetAgent` delegates only to Harbor `BaseAgent` subclasses and
  fails when no accepted class exists.
- Real recipes do not use `fixed`, `noop`, non-Harbor evaluator engines, or
  implicit stub behavior.
- Smoke recipes exist and keep deterministic mechanism tests cheap.
- `meta_eval` does not inject `EVAL_STUB=1`; tests that need stub replay set it
  explicitly.
- HyperAgents docs and tests assert the actual same-generation versus
  future-generation semantics for changed operators.

## Migration

1. Introduce the agent runner without changing recipe defaults.
2. Refactor `agent_command` to use the runner.
3. Make `CheckoutTargetAgent` Harbor-only and update the target template.
4. Split recipe directories into real and smoke names.
5. Move existing deterministic tests to smoke recipes or explicit `EVAL_STUB=1`
   setup.
6. Update README, DESIGN, glossary, and recipe docs to remove fake default
   claims.
7. Update `meta_eval` so real runs replay through the workspace evaluator
   instead of forcing the stub.

## Success Criteria

- A researcher can understand the system as:
  "Harbor runs target agents; `run_agent(workspace, prompt)` runs mutation
  agents; `MutateOperator` adapts mutation into the evolve protocol."
- Real recipes fail fast when live requirements are missing.
- Smoke behavior is never hidden behind a real recipe name.
- HyperAgents no longer claims same-generation mutation-workflow use where the
  driver cannot provide it.
- The unit suite remains fast by using explicit smoke paths.
