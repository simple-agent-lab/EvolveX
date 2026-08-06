# EvolveX

**Build agents that improve — and keep the evidence.**

EvolveX is a file-based framework for running agent-evolution experiments
without rebuilding candidate snapshots, evaluation, lineage, and reporting for
every method. It provides composable recipes inspired by A-Evolve, AHE, GEPA,
Hill Climb, and HyperAgents.

![EvolveX architecture](assets/architecture.svg)

## Start here

### Run an experiment

| Step | Guide |
| --- | --- |
| 1. Install EvolveX and verify the local setup | [Getting started](getting-started.md) |
| 2. Configure credentials and the host runtime | [Environment Variables](reference/environment-variables.md) |
| 3. Initialize a workspace and launch an experiment | [From recipe to experiment](guides/recipe-to-experiment.md) |
| 4. Check, monitor, and recover a real run | [Running Evolve reliably](guides/operations.md) |

### Build your own method

| Goal | Guide |
| --- | --- |
| Compose a custom experiment configuration | [Creating a custom recipe](guides/custom-recipes.md) |
| Choose stages and built-in variants | [Operator overview](reference/operators.md) |
| Configure the editing agent and isolation model | [Meta-agent execution](guides/meta-agents.md) |
| Run trusted local tasks without Docker isolation | [Local Harbor environment](guides/local-environment.md) |

For the framework model and vocabulary, see
[Framework design](concepts/design.md) and [Terminology](reference/terminology.md).

## What Evolve keeps fixed

Each experiment is a separate Git repository. Generation tags identify exact
candidates, `archive.jsonl` records stamped outcomes, and the evaluator stays
outside the candidate's mutable surface.

The mechanism enforces three core rules:

1. Scores and statuses are written by the mechanism, not workspace operators.
2. Canonical evaluation runs on clean candidate snapshots against a frozen evaluator.
3. Reports are recomputed from stamped archive records rather than mutable operator claims.

See the [design guide](concepts/design.md) for the complete model and invariants.

## Repository resources

- [Supported recipes](https://github.com/simple-agent-lab/simple-evolve-agent/tree/main/recipes)
- [Source architecture map](https://github.com/simple-agent-lab/simple-evolve-agent/blob/main/ARCHITECTURE.md)
- [Contributing guide](https://github.com/simple-agent-lab/simple-evolve-agent/blob/main/CONTRIBUTING.md)
- [GitHub repository](https://github.com/simple-agent-lab/simple-evolve-agent)
