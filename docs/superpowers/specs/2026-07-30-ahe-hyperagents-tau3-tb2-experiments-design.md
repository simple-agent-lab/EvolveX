# AHE and HyperAgents tau3/Terminal-Bench 2 Experiment Design

## Goal

Prepare four reproducible experiment workspaces without changing framework
code:

| Host | Recipe | Benchmark |
| --- | --- | --- |
| DevBox | AHE | tau3 |
| DevBox | AHE | Terminal-Bench 2 |
| DevBoxS | HyperAgents | tau3 |
| DevBoxS | HyperAgents | Terminal-Bench 2 |

The setup must follow the shared parameters in the experiment comparison Lark
document while preserving each recipe's existing operators and method-specific
behavior.

## Dataset Use

The checked split manifests remain immutable audit artifacts.

For tau3:

- use the 100-task `train` partition for every evolutionary evaluation;
- leave the 100-task `gate` partition unused by AHE and HyperAgents; and
- use the 175-task `sealed` partition only for the final anchor evaluation.

For Terminal-Bench 2:

- use the 50-task `train` partition for every evolutionary evaluation;
- leave the 19-task `gate` partition unused by AHE and HyperAgents; and
- use the 20-task `sealed` partition only for the final anchor evaluation.

The recipe operator named `gate` remains in both recipes. It certifies an
already evaluated candidate and does not evaluate the dataset's `gate`
partition. Held-out task identities and results remain unavailable to the meta
agent.

## Shared Experiment Setup

All four workspaces use:

- driver mode, seed 0, 10 generations, and one child per generation;
- Harbor evaluation with static task assignments and `k: 1`;
- `openai/gpt-5.4-2026-03-05` for the benchmark agent;
- the Codex meta agent with GPT-5.4 and `xhigh` reasoning;
- Docker meta-agent execution using `evolve-meta-agent-app:ubuntu-latest`;
- 25 concurrent benchmark trials;
- setup-timeout multiplier 1 and agent-timeout multiplier 2;
- one retry;
- a 12-hour rollout/evaluation timeout and a 2-hour meta-agent timeout;
- MiniSWE step limit 100, cost limit 3.0, environment timeout 30, and maximum
  output length 10,000;
- no `budget_usd` field; and
- a final-only sealed anchor (`final: true`, `every_rounds: 0`).

The omission applies specifically to `experiment.budget_usd`: setup must not
write that key with a numeric or null value.

Dataset-specific evaluator sizes are:

| Benchmark | `evaluation_split` | `tasks_per_round` | Final anchor |
| --- | --- | ---: | ---: |
| tau3 | `train` | 100 | 175 sealed tasks |
| Terminal-Bench 2 | `train` | 50 | 20 sealed tasks |

## tau3 Simulator

Every tau3 trial must run the adapter's official text-mode user simulator
through the generated `tau3-runtime` MCP sidecar. The setup exports these
values into Harbor's task runtime:

- `TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05`;
- `TAU2_USER_REASONING_EFFORT=low`; and
- `TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05`.

The first two values configure the simulated user. The assertions model is set
to the same pinned model so tasks containing natural-language assertions do not
fall back to the adapter's default model. The task environment continues to
provide the adapter-required OpenAI API key and base URL. Terminal-Bench 2 does
not receive these tau3-only variables.

## Scripts and Workspaces

Implementation adds scripts only. A parameterized setup script accepts
`ahe|hyperagents` and `tau3|terminal-bench-2`, validates the frozen manifest,
initializes a workspace from the matching current recipe, applies the shared
settings, installs the exact task lists, and verifies the workspace.

A parameterized run script loads the existing machine runtime environment,
verifies the selected workspace, and launches the requested generation count.
It supports a dry-run mode and rejects missing or inconsistent artifacts before
launching Harbor.

The scripts create these production workspaces:

- DevBox: `ahe-tau3` and `ahe-terminal-bench-2`;
- DevBoxS: `hyperagents-tau3` and `hyperagents-terminal-bench-2`.

Existing workspaces are never overwritten. Setup stops with a clear error if a
target name already exists.

## Smoke Experiment

Before production handoff, run one AHE × tau3 smoke experiment on DevBox using
five tasks and three generations. The smoke workspace is separate from the
production workspace, disables the final sealed anchor, and uses only task IDs
from the tau3 training partition.

Success requires:

1. workspace verification succeeds;
2. all three generations complete;
3. each generation produces complete Harbor evaluation artifacts for five
   tasks; and
4. the experiment exits without exposing or evaluating gate/sealed tasks.

## Documentation

After the scripts and smoke experiment are verified, update the existing Lark
document in place. Append four columns to its current parameter tables:

- AHE × tau3;
- AHE × Terminal-Bench 2;
- HyperAgents × tau3; and
- HyperAgents × Terminal-Bench 2.

Existing columns and table structure remain unchanged. Each new column records
the effective workspace value, including recipe-specific differences, so the
document is the final auditable comparison of all experiment setups.

## Verification

Automated checks cover argument validation, exact dataset membership, train-only
evolution, sealed-only final anchors, effective parameter values, host/workspace
mapping, absence of `experiment.budget_usd`, tau3 simulator model/effort
configuration, and dry-run output. Verification then runs the relevant
repository test suite, remote workspace verification, and the
five-task/three-generation smoke experiment.
