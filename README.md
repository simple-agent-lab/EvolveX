<h1 align="center">Evolve Framework</h1>

<p align="center">
  <strong>Traceable, evaluator-driven evolution for AI agents.</strong>
</p>

<p align="center">
  <a href="https://github.com/simple-agent-lab/simple-evolve-agent/actions/workflows/test.yml">
    <img alt="Tests" src="https://github.com/simple-agent-lab/simple-evolve-agent/actions/workflows/test.yml/badge.svg">
  </a>
  <a href="https://www.python.org/">
    <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&amp;logoColor=white">
  </a>
  <a href="LICENSE">
    <img alt="Apache-2.0 License" src="https://img.shields.io/badge/License-Apache--2.0-blue.svg">
  </a>
</p>

<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#features">Features</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#concepts">Concepts</a> ·
  <a href="#recipes">Recipes</a> ·
  <a href="#result">Result</a> ·
  <a href="#documentation">Documentation</a>
</p>

## Overview

Evolve is a file-based framework for running agent-evolution experiments without
rebuilding the mechanics for candidate snapshots, evaluation, lineage, and
reporting. It provides composable recipes inspired by systems such as A-Evolve,
AHE, GEPA, and HyperAgents.

Each experiment is a separate Git repository. Generation tags identify
candidates, `archive.jsonl` records outcomes, and the evaluator stays outside the
candidate's mutable surface. The project is an active prototype intended for
research and controlled experimentation.

## Features

- **Composable loops:** select, rollout, trace analysis, editing, validation,
  gating, and recording are independent operators.
- **Reproducible workspaces:** generated projects include a locked Python runtime,
  frozen evaluator configuration, and vendored framework mechanism.
- **Controlled self-modification:** each recipe declares exactly which target and
  operator paths may evolve.
- **Traceable outcomes:** Git lineage, evaluation artifacts, and stamped archive
  records connect every candidate to its evidence.

## Structure

<p align="center">
  <img src="docs/architecture.svg" alt="Evolve Framework architecture: evolution methods such as Hill Climb, A-Evolve, AHE, GEPA and HyperAgents plug into one loop of select, rollout, analyze, mutate, gate and record. The loop and the agent it improves sit inside a declared mutable surface, so the meta-agent can rewrite any stage. Only the substrate below stays frozen: the evaluator, the runtime, the surface check and the stamped evidence.">
</p>

Every recipe runs the same loop: select a parent, run the tasks, analyze the
traces, edit, gate, record. Each stage is an operator rather than a fixed step,
and a recipe decides which of them the meta-agent may rewrite along with the
target. The evaluator, runtime, surface check, and evidence stamps stay outside
that surface.

## Quick Start

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Git.

```bash
git clone https://github.com/simple-agent-lab/simple-evolve-agent.git
cd simple-evolve-agent
uv sync --dev --frozen
uv run evolve --help
```

Run a deterministic baseline smoke test without a model or Docker:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-smoke-runtime"
export EVOLVE_HOME="/tmp/evolve-home"

uv run evolve init /tmp/evolve-demo --recipe hill_climb
EVAL_STUB=1 /tmp/evolve-demo/evolve run /tmp/evolve-demo --max-generations 0
/tmp/evolve-demo/evolve status /tmp/evolve-demo
/tmp/evolve-demo/evolve verify /tmp/evolve-demo
```

This checks workspace generation, baseline evaluation, and archive integrity; it
does not run a mutation round or measure agent quality.

For a real Harbor run, provide an immutable evaluator digest and a local task
dataset:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-evaluator-digest"

uv run evolve init /tmp/evolve-harbor \
  --recipe aevolve \
  --dataset /absolute/path/to/harbor/tasks
/tmp/evolve-harbor/evolve run /tmp/evolve-harbor --max-generations 5
```

Inspect a run with `evolve status`, `evolve report`, `git tag --list 'gen/*'`,
and the generated `archive.jsonl`. Run `evolve --help` for the complete CLI.

For future experiments, the complete startup path is intentionally short:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://your-bytedance-openai-compatible-endpoint/v1"
export EVOLVE_RUNTIME_DIGEST="sha256:..."

evolve init WORKSPACE --recipe ahe --dataset DATASET
WORKSPACE/evolve preflight WORKSPACE
WORKSPACE/evolve preflight WORKSPACE --smoke
WORKSPACE/evolve run WORKSPACE
```

Initialization generates the immutable runtime profile and all evaluation
contract inputs automatically. Evaluator repetitions default to one. Ordinary
preflight performs offline, cacheless validation and writes a receipt without
changing tracked source or preparing dependencies. `--smoke` adds one real
model request against a detached candidate snapshot. The agent and meta-agent
receive the ByteDance-compatible endpoint through `OPENAI_API_KEY` and
`OPENAI_BASE_URL`; credential files are neither required nor supported.
Runtime policy is resolved by the framework, so recipe and experiment scripts
only declare the profile they need.

## Concepts

| Concept | Meaning |
| --- | --- |
| workspace | A generated experiment repository. |
| target | The code or agent being improved. |
| operator | One step in the evolution loop. |
| evaluator | A pinned black-box scoring contract. |
| archive | Stamped outcomes in `archive.jsonl` plus generation tags. |
| mutable surface | The paths a proposal is allowed to change. |

The generated `.evolve/` runtime and evaluator are protected from candidate
edits. Operators run as subprocesses instead of being imported into the
framework process.

## Recipes

| Recipe | Search shape | Mutable surface |
| --- | --- | --- |
| `hill_climb` | single-parent improvement | target |
| `aevolve` | prompt and skill evolution | prompt and target skills |
| `ahe` | harness engineering | target |
| `gepa` | Pareto selection with minibatch validation | prompt and task skill |
| `hyperagents` | target and meta-agent co-evolution | target and selected operators |

See [the recipe guide](recipes/README.md) for the workflow and configuration of
each recipe.

## Trust Boundaries

Evolve enforces three core rules:

1. Scores and statuses are written by the mechanism, not workspace operators.
2. Canonical evaluation runs on clean candidate snapshots against a frozen
   evaluator.
3. Reports are recomputed from stamped archive records rather than mutable
   operator claims.

See [DESIGN.md](DESIGN.md) for the complete model and invariants.

## Result

> **TODO:** Add reproducible benchmark results and supporting artifacts once
> the evaluation setup and reporting protocol are finalized.

## Roadmap

- **Scenario-oriented recipes:** compose the current operator library into
  opinionated recipes for different agent-evolution use cases.
- **Local-first workflows:** make lightweight, Docker-free iteration a
  first-class path for trusted local agents, prompts, skills, and small features.
- **More method integrations:** add evolution and search methods while preserving
  the shared evaluator, lineage, and evidence contracts.

## Documentation

| Document | Purpose |
| --- | --- |
| [Design](DESIGN.md) | System model, ownership boundaries, and invariants. |
| [Architecture](ARCHITECTURE.md) | Enforced source-module map and line budgets. |
| [Recipes](recipes/README.md) | Supported evolution strategies. |
| [Meta-agents](META_AGENTS.md) | Trusted-host and isolated meta-agent runners. |
| [Trace analysis](TRACE_ANALYZER.md) | Trace retention and analyzer variants. |
| [Local environment](LOCAL_ENVIRONMENT.md) | Docker-free trusted local execution. |
| [Contributing](CONTRIBUTING.md) | Development setup and repository conventions. |

## License

Evolve Framework is licensed under [Apache-2.0](LICENSE). See
[NOTICE](NOTICE) for required attributions.
