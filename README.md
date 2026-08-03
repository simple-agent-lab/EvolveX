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
  <a href="#what-evolve-does">What Evolve does</a> ·
  <a href="#choose-your-starting-point">Start here</a> ·
  <a href="#evolve-the-built-in-codex-target">Codex</a> ·
  <a href="#evolve-the-miniswe-harness">MiniSWE</a> ·
  <a href="#bring-your-own-harbor-compatible-agent">Your agent</a> ·
  <a href="#inspect-the-result">Results</a>
</p>

## What Evolve does

Evolve repeatedly runs an agent on tasks, gives the failures and trajectories
to an editing agent, and evaluates the resulting candidate. It handles the
reusable mechanics around that loop: candidate snapshots, task splits, lineage,
trusted scores, and reports.

Each experiment is a separate Git repository. Candidate files can change;
the evaluator and score-writing mechanism cannot. The project is an active
research prototype for controlled agent-evolution experiments.

## How the pieces fit together

Four roles make up an experiment:

| Part | Role | Example |
| --- | --- | --- |
| Target | Candidate-owned files that may change between generations. | `target/prompt.md`, `target/skills/**`, or MiniSWE source under `target/`. |
| Evaluated Harbor agent | Runs one candidate on one Harbor task. It must load behavior from that candidate's `target/`. | `target.agent:HarborAgent` or `evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent`. |
| Evaluator | Frozen tasks and verifiers that produce the trusted score. | A local Harbor task directory plus its verifier. |
| Meta-agent | Reads training evidence and edits the next candidate. | Codex or MiniSWE running through the configured meta-agent operator. |

The evaluated Harbor agent and the meta-agent are different roles, even when
both happen to use Codex. The former executes a candidate and produces a task
trajectory; the latter reads trajectories and edits the next candidate.

<p align="center">
  <img src="docs/architecture.svg" alt="Evolve Framework architecture: evolution methods such as Hill Climb, A-Evolve, AHE, GEPA and HyperAgents plug into one loop of select, rollout, analyze, mutate, gate and record. The loop and the agent it improves sit inside a declared mutable surface, so the meta-agent can rewrite any stage. Only the substrate below stays frozen: the evaluator, the runtime, the surface check and the stamped evidence.">
</p>

## Choose your starting point

| Goal | Start with | Evolves |
| --- | --- | --- |
| Improve a Codex prompt and skills | `aevolve` with `builtin-codex` | `target/prompt.md` and `target/skills/**` |
| Improve the MiniSWE harness/source | `hill_climb` | the pinned MiniSWE repository under `target/**` |
| Improve your own Harbor-compatible agent | a copied recipe passed with `--recipe-path` | the seed repository vendored under `target/**` |

Start with the Codex or MiniSWE path once. A generated workspace makes the
custom integration contract concrete: `target/` is the candidate, `evolve.yaml`
defines what may change, and `evaluator/` remains frozen.

## Install

Requirements:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Git
- for a real run, Harbor's Docker environment or another configured Harbor
  environment, model credentials, and a local Harbor task dataset

```bash
git clone https://github.com/simple-agent-lab/simple-evolve-agent.git
cd simple-evolve-agent
uv sync --dev --frozen
uv run evolve --help
```

### Optional mechanism-only smoke test

This checks workspace generation, baseline evaluation, and archive integrity
without a model or Docker. It does not run a mutation generation or measure
agent quality.

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-smoke-runtime"
export EVOLVE_HOME="/tmp/evolve-home"

uv run evolve init /tmp/evolve-demo --recipe hill_climb
EVAL_STUB=1 /tmp/evolve-demo/evolve run /tmp/evolve-demo --max-generations 0
/tmp/evolve-demo/evolve status /tmp/evolve-demo
/tmp/evolve-demo/evolve verify /tmp/evolve-demo
```

## Evolve the built-in Codex target

This is the shortest path from a Harbor task dataset to a real mutation round.
The initial candidate contains:

```text
target/
├── agent.py       Harbor adapter that runs this candidate
├── codex.toml     model and Codex settings
├── prompt.md      task prompt template
└── skills/        candidate-owned skills
```

Before running, authenticate on the host with `codex login`. Authentication is
runtime state: it is injected into the Harbor task and is never copied into
`target/`.

Set `EVOLVE_RUNTIME_DIGEST` to the immutable digest of the evaluator image used
by your environment; the value below is deliberately a value you must replace.
The task directory must contain Harbor tasks with their verifiers.

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable-evaluator-image-digest>"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"

uv run evolve init /tmp/evolve-codex \
  --recipe aevolve \
  --seed builtin-codex \
  --dataset "$HARBOR_TASKS"

cd /tmp/evolve-codex
./evolve run . --max-generations 1 --verbose
./evolve status .
./evolve report .
```

`aevolve` runs the candidate on training tasks, analyzes its retained
trajectories, and lets the meta-agent improve the prompt and skills. Canonical
evaluation then scores the resulting Git snapshot on the frozen gate tasks.

## Evolve the MiniSWE harness

Use this path when the harness source itself is the candidate. The `hill_climb`
recipe pins a MiniSWE Git revision, generates its `uv.lock`, places the source
under `target/`, and evaluates it through the framework-owned
`MiniSweSourceAgent` Harbor adapter.

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable-evaluator-image-digest>"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"

uv run evolve init /tmp/evolve-miniswe \
  --recipe hill_climb \
  --dataset "$HARBOR_TASKS"

cd /tmp/evolve-miniswe
./evolve run . --max-generations 1 --verbose
./evolve status .
```

The mutable surface is `target/**`, so the meta-agent may change the pinned
MiniSWE candidate but not the evaluator or framework runtime. Your Harbor tasks
must be compatible with the selected agent and evaluator. Successful workspace
initialization verifies the experiment structure; it does not prove that an
arbitrary task dataset is compatible with MiniSWE.

For the opinionated Terminal-Bench 2.0 AHE workflow, see the
[AHE recipe guide](recipes/ahe/README.md).

## Bring your own Harbor-compatible agent

Your integration needs two related pieces:

1. a candidate repository that Evolve vendors into `target/`; and
2. an installable Harbor `BaseAgent` adapter that executes the candidate from
   the current checkout's `target/`.

That second condition is essential. An adapter that always invokes a fixed host
installation will keep evaluating the same program, no matter how `target/`
changes.

### 1. Copy the nearest recipe

Copy `recipes/aevolve/` when your genome is mainly prompts and skills. Copy
`recipes/hill_climb/` when the harness source is the genome. Keep the complete
recipe directory; the YAML below shows only the fields you normally replace:

```yaml
target:
  seed: /absolute/path/to/my-agent-repository

surface:
  include:
    - target/**
  exclude: []

evaluator:
  engine: harbor
  dataset: /absolute/path/to/harbor/tasks
  agent: package.module:ClassName
```

`target.seed` may also be a Git URL. `surface.include` is the genome boundary:
only matching candidate paths may change. Keep evaluator code and verifiers
outside that boundary.

`evaluator.agent` configures the candidate executor. It must name an importable
Harbor adapter as `package.module:ClassName`. By contrast,
`operators.meta_agent` configures the editor that proposes the next candidate.

### 2. Initialize from the custom recipe

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable-evaluator-image-digest>"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"

uv run evolve init /tmp/evolve-custom \
  --recipe-path /absolute/path/to/my-recipe \
  --dataset "$HARBOR_TASKS"
```

If the Harbor adapter lives in an external Python package, add that package to
the generated workspace's locked runtime before running:

```bash
cd /tmp/evolve-custom
uv add /absolute/path/to/my-harbor-adapter-package
git add pyproject.toml uv.lock
git commit -m "chore: add Harbor candidate adapter"
```

Direct `PYTHONPATH` or `sys.path` injection is intentionally unsupported. The
adapter and its dependencies must be reproducible from `pyproject.toml` and
`uv.lock`.

### 3. Run one generation and inspect it

```bash
./evolve run . --max-generations 1 --verbose
./evolve status .
./evolve report .
```

Before a longer run, confirm that the adapter imports candidate behavior from
this workspace's `target/`, the verifier score changes when candidate behavior
changes, and `./evolve surface-check .` reports no out-of-surface edits.

## What one generation does

Every recipe composes the same basic stages:

1. **Select** a parent from the recorded population.
2. **Roll out** that candidate on training tasks.
3. **Analyze** retained failures and trajectories.
4. **Edit** a child inside the declared mutable surface.
5. **Evaluate** a clean Git snapshot with the frozen evaluator.
6. **Gate and record** the result, lineage, and next eligible parent.

The exact selection, analysis, editing, and gating strategies come from the
recipe. The mechanism owns candidate commits, evaluator isolation, and stamped
outcomes in every recipe.

## Inspect the result

From a generated workspace:

```bash
./evolve status .
./evolve report .
./evolve verify .
git tag --list 'gen/*'
```

Useful retained state includes:

| Path | Contains |
| --- | --- |
| `archive.jsonl` | append-only lineage and stamped candidate outcomes |
| `gen/*` Git tags | exact candidate snapshots |
| `runs/gen-N/` | rollout, trace, editing, evaluation, and gate artifacts |
| `artifacts/generations/N/` | optional durable meta-agent handoff context |

Runs print stage-level progress by default. `--verbose` streams operator and
Harbor output while retaining logs under `runs/`.

## Recipes

| Recipe | Search shape | Mutable surface |
| --- | --- | --- |
| `hill_climb` | single-parent MiniSWE source improvement | target |
| `aevolve` | Codex prompt and skill evolution | prompt and target skills |
| `ahe` | debugger-guided harness engineering | target |
| `gepa` | Pareto selection with minibatch validation | prompt and task skill |
| `hyperagents` | target and meta-agent co-evolution | target and selected operators |

See the [recipe guide](recipes/README.md) for each workflow's configuration and
evidence contract.

## Trust boundaries

Evolve enforces three core rules:

1. Scores and statuses are written by the mechanism, not workspace operators.
2. Canonical evaluation runs on clean candidate snapshots against a frozen
   evaluator.
3. Reports are recomputed from stamped archive records rather than mutable
   operator claims.

The generated `.evolve/` runtime and `evaluator/` are protected from candidate
edits. See [DESIGN.md](DESIGN.md) for the complete model and invariants.

## Current limitations

- Evolve is an active research prototype, not a production orchestration
  service.
- Real Harbor experiments need model credentials and an execution environment;
  Linux is preferred for long-running Docker workloads.
- Deterministic task splitting currently requires a materialized local Harbor
  task directory.
- Credentials are runtime inputs and must never be committed under `target/`.
- Reproducible benchmark results have not yet been published.

For short trusted runs against an agent already installed on the host, see the
[local environment guide](LOCAL_ENVIRONMENT.md). It removes Docker overhead but
does not provide a sandbox.

## Documentation

| Document | Purpose |
| --- | --- |
| [Design](DESIGN.md) | System model, ownership boundaries, and invariants. |
| [Architecture](ARCHITECTURE.md) | Enforced source-module map and budgets. |
| [Recipes](recipes/README.md) | Supported evolution strategies. |
| [Meta-agents](META_AGENTS.md) | Trusted-host and isolated editing-agent runners. |
| [Trace analysis](TRACE_ANALYZER.md) | Trace retention and analyzer variants. |
| [Local environment](LOCAL_ENVIRONMENT.md) | Docker-free trusted local execution. |
| [Contributing](CONTRIBUTING.md) | Development setup and repository conventions. |

## Project information

Read the [security policy](SECURITY.md) to report vulnerabilities privately,
the [Code of Conduct](CODE_OF_CONDUCT.md) for community expectations, and
[support guidance](SUPPORT.md) for public issue routing and support boundaries.

## License

Evolve Framework is licensed under [Apache-2.0](LICENSE). See
[NOTICE](NOTICE) for required attributions.
