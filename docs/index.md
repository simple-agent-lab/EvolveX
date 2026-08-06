# EvolveX

**Build agents that improve — and keep the evidence.**

EvolveX is a file-based framework for running agent-evolution experiments
without rebuilding candidate snapshots, evaluation, lineage, and reporting for
every method. It provides composable recipes inspired by A-Evolve, AHE, GEPA,
Hill Climb, and HyperAgents.

![EvolveX architecture](assets/architecture.svg)

## Start here

| Goal | Guide |
| --- | --- |
| Install the framework and run a deterministic check | [Quick start](getting-started.md) |
| Prepare and recover a real experiment | [Running Evolve reliably](guides/operations.md) |
| Configure a trusted local Harbor environment | [Local Harbor environment](guides/local-environment.md) |
| Configure the editing agent | [Meta-agent execution](guides/meta-agents.md) |
| Understand the system boundaries | [Framework design](concepts/design.md) |
| Look up framework terms | [Terminology](reference/terminology.md) |
| Choose trace evidence for the meta agent | [Trace analyzer](reference/trace-analyzers.md) |

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
