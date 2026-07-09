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
- Do not use Harbor's built-in `mini-swe-agent` agent for MiniSWE source-code
  evolution. That built-in agent evaluates an installed MiniSWE package; our
  recipe must evaluate the candidate MiniSWE source and Harbor wrapper in
  `target/`.

## Core Decision

Use two agent interfaces, each with one job:

- **Target evaluation agent:** a Harbor `BaseAgent` or `BaseInstalledAgent`
  wrapper inside `target/`, imported through Harbor's normal custom-agent path.
  This wrapper lives next to the open-source agent source being evolved and is
  the only real benchmark execution path.
- **Mutation agent runner:** a local process runner that receives a workspace
  path and a prompt, then edits files in that workspace.

`MutateOperator` remains the framework protocol boundary. It builds the prompt,
calls the mutation agent runner, validates the surface, and writes evolve
artifacts.

## Architecture

### Harbor Evaluator Contract

Real evaluations should call Harbor directly from `evaluator/engines/harbor.sh`:

```sh
harbor run -p "$EVOLVE_HARBOR_TASKS" \
  --agent "$EVOLVE_HARBOR_AGENT" \
  --jobs-dir "$jobs_dir" \
  --n-attempts 1 \
  -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" \
  -y -q
```

`EVOLVE_HARBOR_AGENT` should be either:

- A Harbor built-in agent name, when the evolved target is configuration,
  prompts, or another artifact that the built-in agent explicitly consumes.
- A Harbor custom import path, when the evolved target is source code.

This matches Harbor's native contract. Harbor custom agents implement
`BaseAgent`, installed agents use `BaseInstalledAgent` which extends
`BaseAgent`, and Harbor's agent factory treats `--agent module.path:ClassName`
as a custom import path.

For MiniSWE source-code evolution, the recipe must use the target's Harbor
wrapper as a custom import path:

```env
EVOLVE_HARBOR_AGENT=target.harbor_agent:MiniSweSourceAgent
```

`harbor.sh` already sets `PYTHONPATH="$PWD:$PYTHONPATH"`, so Harbor can import
the candidate wrapper from `target/` while the evaluator tree remains pinned to
`gen/0`.

`templates/evaluator/checkout_agent.py` should not be the default real path. It
may be deleted or kept only as a compatibility shim for old workspaces, but real
recipes must not depend on it.

### MiniSWE Target Layout and Wrapper

When the evolved target is MiniSWE source code, `target/` should be a normal
MiniSWE source checkout plus a thin Harbor wrapper:

```text
target/
  pyproject.toml
  mini_swe_agent/
  harbor_agent.py
```

`target/harbor_agent.py` should implement Harbor's `BaseAgent` interface
directly, or use `BaseInstalledAgent` when the source should be installed into
the task container before running. For MiniSWE, `BaseInstalledAgent` is the
natural fit because Harbor's own MiniSWE integration is an installed agent.

The wrapper should stay small:

1. Upload the candidate `target/` source tree into the Harbor task container with
   `environment.upload_dir(...)`.
2. Install the uploaded source inside the container, for example with
   `uv tool install --force /installed-agent/miniswe-source` if the source is a
   CLI package, or the equivalent editable/package install command required by
   MiniSWE.
3. Reuse Harbor's MiniSWE run behavior where practical so model env handling,
   trajectory conversion, cost parsing, and ATIF support stay Harbor-native.
4. Fail fast if `target/` is not an installable MiniSWE source tree.

This is not a fallback path. It is Harbor's native custom-agent interface:
MiniSWE is just source code plus a Harbor-compatible wrapper, and when Evolve
modifies `target/`, Harbor imports and evaluates the modified target. Harbor
still owns tasks, environments, execution, parallelism, retries, logs, and score
parsing.

The recipe should include a candidate-liveness check: a mutation to MiniSWE
source must change the installed code path or version observed inside the task
container. This prevents a recipe from accidentally evaluating a global or
packaged MiniSWE install while claiming to evolve source.

### MiniSWE Wrapper Reuse Decision

The MiniSWE Harbor wrapper should be small. Harbor already has the right
MiniSWE runtime behavior: command construction, model environment forwarding,
config handling, trajectory conversion, cost parsing, ATIF support, and Harbor
logging. Evolve should reuse those pieces instead of reimplementing them.

The preferred implementation is:

```python
from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent


class MiniSweSourceAgent(MiniSweAgent):
    async def install(self, environment):
        source_dir = Path(__file__).resolve().parent
        await environment.upload_dir(source_dir, "/installed-agent/miniswe-source")
        await self.exec_as_agent(
            environment,
            command="uv tool install --force /installed-agent/miniswe-source",
        )
```

Only `install()` should change. Harbor's default MiniSWE install step installs a
published `mini-swe-agent` package, which is correct for benchmarking the
released agent but wrong for evolving local source. The overridden install step
should upload `Path(__file__).resolve().parent`, install that uploaded source
with `uv tool install --force`, and verify that the resulting `mini-swe-agent`
executable resolves to the uploaded candidate source.

If Harbor's `MiniSweAgent` becomes awkward to subclass, the target wrapper may
vendor the Harbor MiniSWE adapter as a narrow second choice. Vendoring should
copy only the Harbor MiniSWE adapter needed for compatibility and keep the same
single intended behavior change: candidate-source installation. Writing a fresh
MiniSWE Harbor agent from scratch is out of scope unless Harbor's adapter cannot
be reused safely.

This means the wrapper needs design discipline more than a large amount of code:
define the upload path, install command, verification command, and clear failure
messages. The rest should stay Harbor-native.

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

- Missing Harbor executable or Docker setup remains an `infra_failed` evaluator
  result.
- Missing `target.harbor_agent:MiniSweSourceAgent`, or a wrapper that does not
  satisfy Harbor's `BaseAgent` interface, fails during Harbor agent import or
  setup with an actionable error.
- Missing or non-installable MiniSWE source under `target/` fails the target
  wrapper setup with an actionable error.
- The MiniSWE target wrapper should verify that the in-container
  `mini-swe-agent` executable resolves to the uploaded candidate install, not to
  a previously installed global package.
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
- Harbor evaluator config passes target custom import paths through to
  `harbor run`, including `target.harbor_agent:MiniSweSourceAgent`.
- The MiniSWE target wrapper satisfies Harbor's `BaseAgent` or
  `BaseInstalledAgent` interface, uploads the candidate `target/` source,
  installs from that uploaded source, and fails if the source is missing or not
  installable.
- A candidate-liveness test proves Harbor evaluates the candidate MiniSWE source
  rather than Harbor's built-in package install.
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
3. Replace default real Harbor evaluation with explicit Harbor agent config:
   built-in agent names for config/prompt targets, target custom import paths
   for source-code targets.
4. Add `target/harbor_agent.py` to MiniSWE source recipes and point those
   recipes at `target.harbor_agent:MiniSweSourceAgent`.
5. Delete or de-default `CheckoutTargetAgent`; keep it only if needed for
   backward compatibility tests.
6. Split recipe directories into real and smoke names.
7. Move existing deterministic tests to smoke recipes or explicit `EVAL_STUB=1`
   setup.
8. Update README, DESIGN, glossary, and recipe docs to remove fake default
   claims.
9. Update `meta_eval` so real runs replay through the workspace evaluator
   instead of forcing the stub.

## Success Criteria

- A researcher can understand the system as:
  "Harbor runs the benchmark; `target/` contains the open-source target agent
  plus a Harbor `BaseAgent` wrapper; `run_agent(workspace, prompt)` runs
  mutation agents; `MutateOperator` adapts mutation into the evolve protocol."
- For MiniSWE source evolution, `target/` is MiniSWE source plus
  `target/harbor_agent.py`, and Harbor imports that wrapper, installs the
  candidate source, and runs it in each evaluation.
- Real recipes fail fast when live requirements are missing.
- Smoke behavior is never hidden behind a real recipe name.
- HyperAgents no longer claims same-generation mutation-workflow use where the
  driver cannot provide it.
- The unit suite remains fast by using explicit smoke paths.
