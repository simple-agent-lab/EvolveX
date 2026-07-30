# AHE and HyperAgents Codex-Target Experiment Design

## Goal

Prepare and smoke-test four new experiments that compare AHE and
HyperAgents while evolving the repository's built-in lightweight Codex
wrapper:

| Recipe | Benchmark | Production host | Production workspace |
| --- | --- | --- | --- |
| AHE | tau3 | DevBox | `ahe-codex-tau3` |
| AHE | Terminal-Bench 2 | DevBox | `ahe-codex-terminal-bench-2` |
| HyperAgents | tau3 | DevBoxS | `hyperagents-codex-tau3` |
| HyperAgents | Terminal-Bench 2 | DevBoxS | `hyperagents-codex-terminal-bench-2` |

The four active MiniSWE-target experiments remain untouched. The new
workspaces use the same frozen task partitions and shared experiment
parameters so their results can be compared with the AEvolve and GEPA
experiments being prepared separately.

The production workspaces are prepared and verified but not launched. Full
production execution requires user approval after the smoke audit.

## Experiment Axes

The setup treats three concerns as independent axes:

- recipe: `ahe` or `hyperagents`;
- target: `codex`; and
- benchmark: `tau3` or `terminal-bench-2`.

The recipe owns selection, rollout, trace analysis, mutation, validation,
gate, record, and mutable-surface behavior. The target profile owns the
candidate agent contract. The benchmark profile owns dataset paths, frozen
partitions, simulator configuration, and task counts.

This design extends the existing parameterized benchmark setup tooling with
an explicit target selector. It does not add duplicate `ahe_codex` or
`hyperagents_codex` recipes.

## Codex Target Contract

The Codex target profile initializes the existing `builtin-codex` seed and
applies this contract:

- `target.seed: builtin-codex`;
- `evaluator.agent: target.agent:HarborAgent`;
- evaluator model `gpt-5.4`, authenticated through the host Codex
  subscription;
- meta-agent prompt path `target/prompt.md`;
- meta-agent skills directory `target/skills`;
- no MiniSWE candidate runtime;
- no `MINISWE_*` evaluator environment;
- no MiniSWE source prompt, memory, or tools paths; and
- no target lock generation, because the built-in wrapper is not a Python
  candidate project.

The AHE mutable surface remains `target/**`. The HyperAgents mutable surface
remains `target/**` plus `operators/**`. Their recipe-specific operator
variants and settings remain unchanged.

The wrapper's initial `codex.toml` may describe model and reasoning defaults,
but model and reasoning are controlled by the frozen evaluator for comparison
fairness. Harbor receives `--model gpt-5.4` and the protected evaluator passes
`--agent-kwarg reasoning_effort=high`. The target wrapper's `setdefault`
behavior makes the evaluator-owned argument authoritative. Persisted Harbor
job configurations are audited to require effective high reasoning for every
canonical evaluation.

Other wrapper behavior, including prompt, skills, web-search policy, context
policy, and compaction settings, remains evolvable within each recipe's
surface.

## Authentication, Proxy, and Model Separation

Both DevBox and DevBoxS have a non-empty `/home/zimuwang/.codex/auth.json`
owned by the experiment user with mode `0600`.

The run path loads:

1. the shared `evolve.env`;
2. the shared `proxy.env`;
3. the shared `runtime.env`; and
4. the workspace's benchmark-specific `simulator.env`, when present.

It exports `CODEX_FORCE_AUTH_JSON=1`. Uppercase and lowercase HTTP, HTTPS, and
no-proxy variables are propagated into evaluator and meta-agent containers.
No proxy value or authentication material is copied into or committed within
a workspace. Logs and diagnostics report only variable presence, never
values.

Codex benchmark agents and Codex meta-agents use the host subscription,
`auth.json`, the machine proxy, model `gpt-5.4`, and fixed high reasoning.
Driver-level OpenAI API endpoints must not replace Codex's subscription-backed
provider.

tau3's simulated user and natural-language assertion judge remain separate.
They use:

- `TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05`;
- `TAU2_USER_REASONING_EFFORT=low`; and
- `TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05`.

Terminal-Bench 2 does not receive tau3 simulator configuration.

## Shared Production Configuration

All four production workspaces use:

- driver mode and experiment seed 0;
- ten configured generations and one child per generation;
- Harbor evaluation with static sampling and `k: 1`;
- 25 concurrent trials;
- setup-timeout multiplier 1;
- agent-timeout multiplier 2;
- one retry;
- partial floor 0.8;
- no `experiment.budget_usd`;
- 12-hour rollout and gate timeouts;
- method-appropriate trace-analyzer timeouts;
- two-hour Codex meta-agent timeout;
- Codex meta-agent model `gpt-5.4` with `xhigh` reasoning; and
- final-only sealed anchors.

The AHE trace analyzer processes the complete active training task set. The
HyperAgents trace browser retains its recipe settings.

## Dataset Invariants

The existing frozen manifests are immutable inputs.

For tau3:

- the 100-task train partition is the production evolution set;
- the 100-task gate partition is unused by AHE and HyperAgents evolution; and
- the 175-task sealed partition is used only by the final anchor.

For Terminal-Bench 2:

- the 50-task train partition is the production evolution set;
- the 19-task gate partition is unused by AHE and HyperAgents evolution; and
- the 20-task sealed partition is used only by the final anchor.

Setup validates counts, disjointness, dataset membership, and hashes. The
operator named `gate` certifies an already evaluated candidate; it does not
evaluate the dataset's gate partition. Gate and sealed task identifiers and
results remain unavailable to meta-agent feedback.

## Tooling

The existing tested benchmark scripts are extended rather than replaced.

The setup interface becomes:

```text
setup_benchmark_experiment.sh \
  METHOD TARGET BENCHMARK WORKSPACE_NAME N_CONCURRENT [--dry-run]
```

where:

- `METHOD` is `ahe` or `hyperagents`;
- `TARGET` includes the new explicit `codex` profile;
- `BENCHMARK` is `tau3` or `terminal-bench-2`; and
- `N_CONCURRENT` is a positive integer.

The setup script:

1. validates arguments and resolves immutable inputs;
2. refuses to overwrite an existing workspace;
3. validates the complete frozen manifest against the dataset;
4. initializes the selected recipe and target;
5. applies shared, benchmark-specific, and target-specific settings;
6. writes normalized split and task files;
7. writes protected evaluator agent kwargs for fixed high reasoning;
8. commits the generation-zero configuration and retargets `gen/0`; and
9. runs `evolve verify`.

A tracked smoke-task manifest records the approved task IDs. The smoke
configurator validates that every selected task belongs to `train`, that none
belongs to gate or sealed, and that AHE and HyperAgents use identical task
lists for each benchmark.

The run script loads runtime environment files, validates auth and proxy
presence, checks workspace concurrency, exports the frozen framework Python,
runs `evolve verify`, performs the Codex install/auth/proxy preflight, and
then launches the requested generation count.

Smoke and production workspaces are initialized independently through the
same renderer. Smoke configuration is not produced by mutating a production
workspace.

## Smoke Matrix

Each smoke uses three tasks, two mutation generations, concurrency 3, and no
anchor. A successful smoke contains generation tags and canonical evaluations
for generation 0 through generation 2.

The exact task sets are:

### tau3

- `tau3-airline-3`;
- `tau3-banking_knowledge-task-012`; and
- `tau3-retail-1`.

### Terminal-Bench 2

- `build-cython-ext`;
- `fix-git`; and
- `regex-log`.

The four smoke runs execute sequentially:

| Order grouping | Host | Recipe | Benchmark |
| --- | --- | --- | --- |
| tau3 smokes | DevBoxS | AHE, then HyperAgents | tau3 |
| Terminal-Bench 2 smokes | DevBox | AHE, then HyperAgents | Terminal-Bench 2 |

Only one smoke runs at a time across both hosts.

## Coexistence with Active Production Runs

Smoke experiments may run while the four MiniSWE production experiments are
active, but must not modify or restart their resources.

Harbor assigns randomized Docker Compose project names per trial, and tau3's
port 8000 is internal-only. The smoke workflow nevertheless:

- uses unique workspace and experiment identifiers;
- caps smoke concurrency at 3;
- never restarts Docker or shared benchmark services;
- records existing Evolve processes and Docker container health before each
  smoke;
- checks those processes and containers after each smoke; and
- stops the smoke sequence if an existing process exits or an existing
  container becomes unhealthy.

On failure, cleanup is limited to Compose projects proven to belong to the
failed smoke. Pre-existing workspaces, processes, mirrors, archives,
containers, datasets, manifests, and caches are not altered.

## Preflight and Verification

Before each smoke, the workflow requires:

1. repository tests for the setup, smoke, run, evaluator, and Codex target
   paths;
2. successful workspace `evolve verify`;
3. exact smoke task membership and train/gate/sealed isolation;
4. non-empty mode-`0600` Codex auth;
5. presence of all required proxy variable forms;
6. an install-only Harbor/Codex compatibility check;
7. effective evaluator model `gpt-5.4`;
8. effective frozen evaluator reasoning `high`; and
9. complete tau3 simulator configuration for tau3 only.

A smoke passes only when:

- tags and archive records exist through generation 2;
- each canonical evaluation contains exactly three scoreable trials;
- no gate or sealed task is evaluated or exposed to feedback;
- mutations remain within the recipe's mutable surface;
- persisted Harbor jobs show evaluator reasoning `high`;
- the run exits successfully without an anchor evaluation; and
- the pre-existing production health snapshot remains satisfied.

Automated tests cover:

- valid and invalid method/target/benchmark combinations;
- exact Codex target transformation;
- removal of MiniSWE-only configuration;
- preservation of recipe-specific operators and surfaces;
- frozen model and reasoning enforcement;
- proxy and auth propagation without secret persistence or log exposure;
- exact smoke task selection and anchor disabling;
- full production train/sealed membership and final-only anchors;
- dry-run output and overwrite refusal; and
- run-script environment loading and verification-before-launch.

## Failure Handling

Setup fails before launch when an input, workspace, dataset, manifest, task
selection, auth file, proxy environment, simulator setting, frozen agent
argument, or verification check is invalid.

Any smoke failure stops the remaining sequence. The failure report retains
logs and artifacts and distinguishes:

- candidate failure;
- evaluator or verifier failure;
- Codex auth or proxy failure;
- benchmark-service failure;
- Docker isolation failure; and
- impact on an existing production run.

No production run is launched automatically. After four passing smoke audits,
the workflow prepares and verifies the four named production workspaces, then
stops and asks for user review.

## Deliverables

The implementation produces:

- tested parameterized setup, smoke, run, and audit behavior;
- the tracked six-task smoke manifest;
- four audited smoke workspaces and reports;
- four verified but unlaunched production workspaces;
- a configuration audit comparing effective values with the Lark source
  document; and
- a handoff that requires explicit approval before any production launch.
