# Getting started

## Requirements

- Python 3.12 or later
- [`uv`](https://docs.astral.sh/uv/)
- Git
- Docker and Harbor-compatible task data for real isolated experiments

## Install for development

```bash
git clone https://github.com/simple-agent-lab/EvolveX.git
cd EvolveX
uv sync --dev --locked
uv run --frozen evolve --help
```

## Run a deterministic baseline check

From the repository root, use the bundled local task fixtures for a check that
does not require a model, Docker, or access to the Harbor dataset registry:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-smoke-runtime"
export EVOLVE_HOME="/tmp/evolve-home"

uv run --frozen evolve init /tmp/evolve-demo \
  --dataset "$PWD/tests/fixtures/tasks-local"
EVAL_STUB=1 /tmp/evolve-demo/evolve run /tmp/evolve-demo --max-generations 0
/tmp/evolve-demo/evolve status /tmp/evolve-demo
/tmp/evolve-demo/evolve verify /tmp/evolve-demo
```

This verifies workspace generation, baseline evaluation, and archive integrity.
It does not run a mutation round or measure agent quality. The first run may
download the workspace's locked Python dependencies.

## Download a Harbor dataset

After installing the development dependencies, use Harbor's downloader to
export a benchmark dataset as local task directories. For example:

```bash
uv run --frozen harbor download terminal-bench@2.0 \
  --export \
  -o /absolute/path/to/terminal-bench-2
```

The output path can then be passed to `evolve preflight` and `evolve init` with
`--dataset`. For the repository's reproducible Terminal-Bench subset, prefer
the setup script below: it downloads Terminal-Bench 2.0, verifies and
materializes the pinned task subset, and builds the selected recipe's
meta-agent image.

```bash
./scripts/setup_terminal_bench.sh ahe
./scripts/run_recipe_demo.sh ahe
```

## Prepare a real experiment

Run the read-only preflight before initialization:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-evaluator-digest"

uv run evolve preflight /tmp/evolve-harbor \
  --recipe aevolve \
  --dataset /absolute/path/to/harbor/tasks

uv run evolve init /tmp/evolve-harbor \
  --recipe aevolve \
  --dataset /absolute/path/to/harbor/tasks

evolve doctor /tmp/evolve-harbor --profile experiment
evolve smoke /tmp/evolve-harbor --profile experiment
/tmp/evolve-harbor/evolve run /tmp/evolve-harbor --max-generations 5
```

`evolve preflight` accepts the same initialization inputs, writes nothing, and
reports unmet preconditions as one checklist.

## Next steps

- [Create a custom recipe](guides/custom-recipes.md)
- [Initialize a workspace and launch an experiment](guides/recipe-to-experiment.md)
- [Configure credentials and runtime environment](reference/environment-variables.md)
- [Choose operators and variants](reference/operators.md)
- [Run preflight, smoke tests, and recovery commands](guides/operations.md)
- [Configure meta-agent execution](guides/meta-agents.md)
- [Use the trusted local Harbor backend](guides/local-environment.md)
- [Understand recipes in the source repository](https://github.com/simple-agent-lab/EvolveX/tree/main/recipes)
