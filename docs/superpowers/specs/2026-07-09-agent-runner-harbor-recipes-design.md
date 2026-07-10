# Agent Runner, Harbor Evaluation, and Real Recipes Design

## Context

The current framework mixes three concepts that should be separate:

- The evaluated target agent, which should run through Harbor.
- The meta-agent, which edits a local git checkout.
- Smoke scaffolding, which exists to make CI and local mechanism tests cheap.

Before the method-faithful HyperAgents replacement, this caused confusing
behavior. `CheckoutTargetAgent` could fall back to arbitrary scripts such as
`solve.sh` or `run.sh`; production recipe names still used deterministic
meta-agent edits; the HyperAgents scaffold exposed `operators/**` without a
method-faithful meta-agent; and `meta_eval` forced `EVAL_STUB=1` during
operator-surface admission replay.

## Goals

1. Make Harbor the only real benchmark execution interface.
2. Add a small, reusable primitive for running a local meta-agent:
   `run_meta_agent(workspace, prompt)`.
3. Keep `MetaAgentOperator` as the evolve protocol adapter, but make it call the
   simple meta-agent runner and patch builder instead of embedding runner and
   diff logic.
4. Split real recipes from smoke recipes. Real recipes should be structurally
   real and fail fast if required live agent or Harbor configuration is missing.
5. Make HyperAgents truthful: the V1 bounded meta-agent workflow is inherited
   by later generations, while gate and record remain fixed outside the
   mutable surface. The docs must say this plainly.
6. Stop real self-modification admission from using the stub evaluator unless a
   smoke or test run explicitly opts into `EVAL_STUB=1`.

## Non-Goals

- Do not build a new Harbor agent framework.
- Do not make the meta-agent a Harbor `BaseAgent`.
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
- **Meta-agent runner:** a local runner that receives a workspace
  path and a prompt, then edits files in that workspace.

`MetaAgentOperator` remains the framework protocol boundary. It builds the prompt,
calls the meta-agent runner, derives the patch from the modified checkout, and
writes evolve artifacts.

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

The recipe should include a candidate-liveness check: an edit to MiniSWE
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

### Checkout Terminology

`checkout` means the local git worktree for one candidate generation. The driver
creates it from the selected parent generation, then passes it to meta_agent. The
meta-agent edits files inside this checkout.

It is not the top-level Evolve project repo, and it is not the benchmark task
repo that Harbor creates during evaluation. For MiniSWE source evolution, the
checkout contains files such as:

```text
target/
  mini_swe_agent/
  harbor_agent.py
operators/
evolve.yaml
evaluator/
```

Patch creation should compare the modified checkout against a parent git ref,
usually `gen/{ctx.parent}`. It should not require a second physical parent
workspace.

### Meta-Agent Runner

Add `src/evolve/agent.py` with a small primitive. The meta-agent may call it
through a domain helper named `run_meta_agent`, but the concept is intentionally
simple:

```python
agent_run = run_meta_agent(
    workspace=checkout,
    prompt=prompt,
    config=ctx.config,
)
```

At this stage, a meta-agent is any configured program that receives a workspace
and a prompt, then edits files in that workspace. Its class shape, tool choices,
and provider-specific behavior can be designed later without changing
`MetaAgentOperator.run`.

`run_meta_agent` is responsible only for running that agent:

- Write the prompt to a temporary file.
- Resolve the configured command from `operators.meta_agent.command` or
  `EVOLVE_AGENT_COMMAND`.
- Run the command with `cwd=workspace`.
- Export `EVOLVE_PROMPT_FILE`.
- Capture stdout, stderr, return code, and wall time.
- Kill the process group on timeout.
- Return an `AgentRunResult`.

If no command is configured in a real recipe, meta-agent execution fails fast with a clear
message. The runner should not know about generation IDs, archive rows, surface
checks, patches, or meta-agent artifact files.

### Candidate Patch Builder

Add a helper that turns the edited checkout into the candidate patch record:

```python
patch = create_candidate_patch(
    checkout=checkout,
    parent_ref=patch_parent_ref(checkout, ctx),
    surface=load_surface_policy(checkout),
)
```

`create_candidate_patch` should:

- Compare the modified checkout against `parent_ref` using git.
- Compute changed paths and a diff.
- Apply surface validation and repair or reject invalid paths.
- Return a `CandidatePatch` object with `changed_paths`, `diff`, `surface_report`,
  and repair notes.

The patch helper owns git diff details. The meta-agent runner does not.

### Mutate Operator

Refactor `library/meta_agent/agent_command.py` so it becomes a thin protocol
adapter:

```python
class AgentCommandMetaAgent(MetaAgentOperator):
    def run(
        self,
        checkout: Path,
        observation: str,
        ctx: OperatorContext,
    ) -> MetaAgentResult:
        prompt = build_meta_agent_prompt(checkout, observation, ctx)
        agent_run = run_meta_agent(
            workspace=checkout,
            prompt=prompt,
            config=ctx.config,
        )
        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=patch_parent_ref(checkout, ctx),
            surface=load_surface_policy(checkout),
        )
        return write_meta_agent_result(ctx.run_dir, agent_run, patch)
```

`MetaAgentOperator` is not the meta-agent. It is the Evolve protocol adapter. Its
main method should remain this small: build the prompt, run the meta-agent in
the checkout, derive the patch from the modified checkout, and write meta-agent
artifacts.

Helper functions may handle prompt assembly, command resolution, process
management, git diffing, surface repair, rationale text, predicted fixes, usage,
and `changed.json`. Those details should not be braided into the main method.

## Recipe Policy

Real recipe names are reserved for real behavior:

- `hill_climb`
- `dgm`
- `ahe`
- `autoresearch`
- `hyperagents`
- `metaagent`

These recipes should use Harbor as their evaluator backend and a real
meta-agent adapter such as `agent_command`. They may require `EVOLVE_AGENT_COMMAND`,
Harbor, Docker, and model credentials. Missing live requirements should produce
clear failures rather than silently falling back to smoke behavior.

Smoke recipes should be explicitly named:

- `hill_climb-smoke`
- `dgm-smoke`
- `ahe-smoke`
- `autoresearch-smoke`
- `hyperagents-smoke`
- `metaagent-smoke`

Smoke recipes may use `EVAL_STUB=1`, deterministic target fixtures, and a
test-provided `EVOLVE_AGENT_COMMAND`. Tests that only verify framework
mechanics should use smoke recipes.

## HyperAgents Semantics

This section is superseded for the implemented V1 HyperAgents recipe by
`2026-07-10-method-faithful-hyperagents-recipe-design.md`. The old scaffold
used broad `operators/**` exposure; the implemented recipe uses the bounded
atomic genome `target/**`, `operators/meta_agent.py`, and
`operators/meta_agent.md`, with fixed selection, validation, gate, record,
evaluator, archive, and configuration.

The implemented driver semantics are:

- A changed `operators/meta_agent.py` cannot affect the same candidate edit that created
  it. It can affect future children forked from the accepted generation.
- `operators/gate.py`, `operators/record.py`, `operators/select.py`,
  `operators/rollout.py`, and validation remain fixed outside the V1 mutable
  surface.
- `program.md` is not executable under `./evolve run`. It should not be
  presented as an evolved workflow unless a later change adds an explicit
  agent-mode orchestrator that reads and follows it.

Real HyperAgents uses the `hyperagents` meta-agent, `score_child_prop`
selection, `hyperagents` validation/record variants, and the exact bounded
surface above. The deterministic mechanism test recipe is `hyperagents-smoke`.

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
- Missing meta-agent command fails the meta-agent operator with
  `operator_failed`, naming `EVOLVE_AGENT_COMMAND` and `operators.meta_agent.command`
  as the accepted configuration points.
- Agent timeout kills the agent process group and records timeout details in
  meta-agent rationale and usage.
- Surface violations are still repaired before the mechanism sees the candidate edit,
  using the existing surface repair behavior.

## Testing

Add or update tests for these behaviors:

- `run_meta_agent` runs a fake command in a temporary checkout, passes
  `EVOLVE_PROMPT_FILE`, captures output, records wall time, and handles timeout.
- `create_candidate_patch` compares a modified checkout to the parent git ref,
  reports changed paths and diff, and handles surface repair or rejection.
- `agent_command` meta-agent has a small main method that calls prompt builder,
  `run_meta_agent`, `create_candidate_patch`, and result writer while still
  writing valid meta-agent artifacts.
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

1. Introduce the meta-agent runner and candidate patch builder without changing
   recipe defaults.
2. Refactor `agent_command` so its main method delegates to prompt builder,
   `run_meta_agent`, `create_candidate_patch`, and result writer.
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
  plus a Harbor `BaseAgent` wrapper; `run_meta_agent(workspace, prompt)` edits a
  candidate checkout; `create_candidate_patch` derives the diff against the
  parent; `MetaAgentOperator` adapts candidate editing into the evolve protocol."
- For MiniSWE source evolution, `target/` is MiniSWE source plus
  `target/harbor_agent.py`, and Harbor imports that wrapper, installs the
  candidate source, and runs it in each evaluation.
- Real recipes fail fast when live requirements are missing.
- Smoke behavior is never hidden behind a real recipe name.
- HyperAgents no longer claims same-generation meta-agent workflow use where the
  driver cannot provide it.
- The unit suite remains fast by using explicit smoke paths.
