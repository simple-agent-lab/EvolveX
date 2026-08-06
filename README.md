<p align="center">
  <img src="docs/evolve-mark.svg" width="112" alt="EvolveX selected lineage mark: a selected lineage rises past explored side branches to a verified generation.">
</p>

<h1 align="center">EvolveX</h1>

<p align="center">
  <strong>Build agents that improve — and keep the evidence.</strong>
</p>

<p align="center">
  A file-based framework for evaluator-driven evolution, reproducible candidate
  lineage, and controlled self-modification.
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
  <a href="#what-evolvex-does">What EvolveX Does</a> ·
  <a href="#how-evolvex-works">How It Works</a> ·
  <a href="#what-can-evolve">What Can Evolve</a> ·
  <a href="#recipes">Recipes</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#documentation">Documentation</a>
</p>

<p align="center">
  <a href="docs/evolve-lineage.svg">
    <img src="docs/evolve-lineage.svg" alt="A baseline branches into evaluated candidates. The selected lineage rises through successive generations to a verified improvement, while unselected candidates remain visible as evidence.">
  </a>
</p>

## What EvolveX Does

EvolveX gives an agent a controlled way to improve itself. It runs candidates
against a fixed evaluator, keeps the evidence for every generation, and carries
verified improvements forward without letting candidate code rewrite the rules
that score it.

| For agent builders | For researchers | Evidence built in |
| --- | --- | --- |
| Improve prompts, skills, harnesses, and agent code in a reusable experiment workspace. | Compare evolution strategies under fixed evaluation and mutation boundaries. | Connect every candidate to scores, artifacts, archive records, and Git lineage. |

## How EvolveX Works

Every recipe composes the same loop:

**select → evaluate → analyze → mutate → gate → record**

<p align="center">
  <a href="docs/assets/architecture.svg">
    <img src="docs/assets/architecture.svg" alt="EvolveX architecture: five built-in strategies and custom recipes compose a loop of select, rollout and evaluation, analyze, mutate, gate, and record. The target and selected operators occupy a declared mutable surface. The evaluator, runtime, surface check, and stamped evidence remain protected from candidate changes.">
  </a>
</p>

A recipe decides how parents are selected, how traces are analyzed, what may be
edited, and which evaluations admit a new generation. The framework owns the
mechanism that makes those decisions inspectable: clean candidate snapshots,
protected scoring, surface enforcement, Git tags, and stamped archive records.

## What Can Evolve

| Surface | Examples | Best fit |
| --- | --- | --- |
| prompts and skills | system prompts, task skills, reusable instructions | policy and behavior improvement |
| harnesses and target code | tools, orchestration, agent implementation | agent engineering |
| selected evolution operators | analysis or mutation policy chosen by a recipe | controlled co-evolution |

Each recipe declares its mutable paths. Evaluators, archive stamps, and the
vendored framework mechanism stay outside that surface.

## Recipes

| Choose this when you want to… | Recipe | Mutable surface |
| --- | --- | --- |
| improve one candidate from its current best parent | `hill_climb` | target |
| evolve prompts and reusable agent skills | `aevolve` | prompt and target skills |
| engineer the agent harness against evaluator feedback | `ahe` | target |
| balance multiple objectives with minibatch validation | `gepa` | prompt and task skill |
| co-evolve the target and selected evolution policy | `hyperagents` | target and selected operators |

See [the recipe guide](recipes/README.md) for each strategy’s workflow and configuration.

## Quick Start

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), and Git.

```bash
git clone https://github.com/simple-agent-lab/simple-evolve-agent.git
cd simple-evolve-agent
uv sync --dev --locked
uv run --frozen evolve --help
```

`evolve init` accepts an optional workspace path. When omitted, it creates the
workspace at `~/.evolve-workspace`; pass an explicit path for named or parallel
experiments.

Run a deterministic baseline smoke test without a model or Docker:

```bash
export EVOLVE_HOME="/tmp/evolve-home"

uv run evolve init /tmp/evolve-demo \
  --recipe-path tests/fixtures/recipes/hill_climb-smoke \
  --seed tests/fixtures/seeds/dummy
EVAL_STUB=1 /tmp/evolve-demo/evolve run /tmp/evolve-demo --max-generations 0
/tmp/evolve-demo/evolve status /tmp/evolve-demo
/tmp/evolve-demo/evolve verify /tmp/evolve-demo
```

This checks workspace generation, baseline evaluation, and archive integrity; it
does not run a mutation round or measure agent quality.

An outer coding agent can also orchestrate a generation while reusing the
framework's operators:

```bash
/tmp/evolve-demo/evolve operator list /tmp/evolve-demo
/tmp/evolve-demo/evolve operator run /tmp/evolve-demo select --genid 1
```

The agent reads the retained operator artifacts, forks and edits the selected
parent, then uses `commit`, `eval`, and `finalize`. This keeps the agent in
control of the harness change while the mechanism still owns evaluation,
configured admission checks, gating, recording, and lineage. Validation and
novelty results are tied to the exact candidate tree, so editing afterward
requires rerunning them. See the generated workspace's `program.md` and
`skills/evolve-agent/SKILL.md` for the complete sequence and method guidance.

For a reproducible Terminal-Bench 2.0 run, prepare the shared pinned dataset and
the selected recipe's image once, then use the short execution script:

```bash
./scripts/setup_terminal_bench.sh ahe
./scripts/run_recipe_demo.sh ahe
```

The scripts support A-Evolve, AHE, GEPA, Hill Climb, and HyperAgents, including
their Codex profiles. Common execution overrides are `WORKSPACE`, `TASKS`,
`GENERATIONS`, `ENV_FILE`, and `EVOLVE_ASSET_DIR`. Preflight validates the
selected runtime's authentication before any experiment generation runs.

Initialization resolves each recipe's inline runtime block into
`evaluator/runtime.json` and generates the certified evaluation inputs.
Evaluator repetitions default to one. Workspace preflight performs offline,
cacheless validation and writes a redacted receipt; `--smoke` additionally makes
one real model request against a detached candidate snapshot.

Workspace commands load only `WORKSPACE/.env`; explicitly exported variables
override it, and caller or parent `.env` files are ignored. API-key
authentication is the default. Codex agents may instead use an explicit
`CODEX_AUTH_JSON_PATH`, with no automatic home-directory lookup. Explicitly
supplied standard proxy variables are inherited as optional host transport for
dependency downloads; the configured model endpoint is added to `NO_PROXY`,
and users without a proxy need no proxy setup. Recipes may still declare a
required proxy policy for environments that must fail closed.
Secrets, endpoint URLs, auth paths, and proxy values are excluded from resolved
runtime configuration and evaluation contracts.

Inspect a run with `evolve status`, `evolve report`, `git tag --list 'gen/*'`,
and the generated `archive.jsonl`. Run `evolve --help` for the complete CLI.

## Trustworthy by Construction

EvolveX separates evolvable policy from the mechanism that judges it:

1. **The evaluator is frozen.** Candidates cannot change the scoring contract.
2. **Mutation is bounded.** Each recipe declares which target and operator paths may change.
3. **Evaluation is canonical.** New generations are scored from clean candidate snapshots.
4. **Evidence is durable.** Reports recompute results from stamped `archive.jsonl` records and Git generation tags.

Operators run as subprocesses rather than being imported into the framework
process. See [the design guide](docs/concepts/design.md) for the complete ownership model and invariants.

## Project Status

EvolveX is an active prototype for research and controlled experimentation. The
current focus is reliable experiment mechanics, local-first workflows, and
composable strategies for different agent-evolution scenarios.

Benchmark results will be added only with a reproducible evaluation setup and
supporting artifacts.

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
| [Documentation site](https://simple-agent-lab.github.io/simple-evolve-agent/) | Installation, operation, concepts, guides, and reference. |
| [Design](docs/concepts/design.md) | System model, ownership boundaries, and invariants. |
| [Architecture](ARCHITECTURE.md) | Enforced source-module map and line budgets. |
| [Recipes](recipes/README.md) | Supported evolution strategies. |
| [Evaluation assets](evals/README.md) | Skill behavior/routing evaluation cases and result snapshots. |
| [Meta-agents](docs/guides/meta-agents.md) | Trusted-host and isolated meta-agent runners. |
| [Trace analysis](docs/reference/trace-analyzers.md) | Trace retention and analyzer variants. |
| [Local environment](docs/guides/local-environment.md) | Docker-free trusted local execution. |
| [Operations](docs/guides/operations.md) | Doctor profiles, runtime setup, full-loop smoke, and recovery. |
| [Contributing](CONTRIBUTING.md) | Development setup and repository conventions. |
| [Releasing](RELEASING.md) | Source, artifact, and publication checklist. |

## License

EvolveX is licensed under [Apache-2.0](LICENSE). See
[NOTICE](NOTICE) for required attributions.
