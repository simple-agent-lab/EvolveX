# Terminal-Bench Subset Default Design

## Goal

Make future AHE and HyperAgents experiments use the repository's
`terminal-bench-2-10-10-10` dataset by default. The smaller dataset must retain
its intended, deterministic 10-task train, 10-task gate, and 10-task sealed
partitions so experiments run faster without mixing evaluation roles.

## Scope

This change applies to the `ahe` and `hyperagents` recipes. It does not change
the `hill_climb` recipe, smoke recipes, existing generated experiment
workspaces, or historical experiment reports.

## Configuration

Both affected recipe configurations will:

- set `evaluator.dataset` to the project-relative
  `terminal-bench-2-10-10-10` directory;
- use a static split with train, gate, and sealed ratios of one third each and
  seed 0;
- set `evaluator.tasks_per_round` to 10; and
- use the normal partitioned task scope rather than the current full-dataset
  `task_scope: full` and `evaluation_split: train` settings.

The path remains relative so a checkout is portable. `evolve init` already
resolves a local dataset relative to the caller's current directory and freezes
the resolved absolute path and split membership in the generated workspace.
Consequently, these recipes are intended to be initialized from the project
root, matching the repository's normal development workflow.

All other algorithm and runtime settings remain unchanged unless a setting is
explicitly tied to the former 89-task scope. AHE's trace-analysis task cap will
be reduced to 10 so its per-generation work matches the smaller active
partition.

## Data Flow and Validation

During `evolve init`, the existing split builder discovers the 30 local Harbor
tasks and deterministically assigns them using the configured ratios and seed.
It writes the authoritative membership to `evaluator/splits.json`. Rollout
consumes the train partition, canonical evaluation consumes the gate partition,
and sealed results remain isolated according to the existing runtime contracts.

Recipe tests will first be changed to express the new defaults and expected
partitioned semantics. They must fail against the old full-89 configuration.
After the recipe and documentation changes, the targeted recipe tests and the
dataset-split tests must pass. A generated AHE and HyperAgents workspace will
also be checked to confirm that each frozen partition contains exactly 10 tasks
and matches `terminal-bench-2-10-10-10/expected-splits.json`.

## Documentation

The AHE and HyperAgents recipe documentation and the root recipe guidance will
describe the smaller default dataset and 10/10/10 split. Historical reports
remain untouched because they describe completed full-89 experiments rather
than future defaults.

## Error Handling

No new error path is introduced. The documented initialization command runs
from the project root, where the dataset resolves and is frozen. If a caller
initializes elsewhere and the relative directory is unavailable, the manifest
is marked unresolved; the existing split-selection guard then rejects the
workspace before it can run a partitioned evaluation. The runtime does not
silently substitute another dataset.
