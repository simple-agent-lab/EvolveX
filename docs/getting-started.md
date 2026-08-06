# Getting started

## Requirements

- Python 3.12 or later
- [`uv`](https://docs.astral.sh/uv/)
- Git
- Docker and Harbor-compatible task data for real isolated experiments

## Install for development

```bash
git clone https://github.com/simple-agent-lab/simple-evolve-agent.git
cd simple-evolve-agent
uv sync --dev --locked
uv run --frozen evolve --help
```

## Run a deterministic baseline check

This path does not require a model or Docker:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-smoke-runtime"
export EVOLVE_HOME="/tmp/evolve-home"

uv run evolve init /tmp/evolve-demo
EVAL_STUB=1 /tmp/evolve-demo/evolve run /tmp/evolve-demo --max-generations 0
/tmp/evolve-demo/evolve status /tmp/evolve-demo
/tmp/evolve-demo/evolve verify /tmp/evolve-demo
```

This verifies workspace generation, baseline evaluation, and archive integrity.
It does not run a mutation round or measure agent quality.

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

- [Run preflight, smoke tests, and recovery commands](guides/operations.md)
- [Configure meta-agent execution](guides/meta-agents.md)
- [Use the trusted local Harbor backend](guides/local-environment.md)
- [Understand recipes in the source repository](https://github.com/simple-agent-lab/simple-evolve-agent/tree/main/recipes)
