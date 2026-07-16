# Fast Essential Test Suite Design

## Goal

Reduce the wall-clock time of the default `uv run pytest -q` suite while preserving coverage of every distinct mechanism contract.

## Baseline

On the merged `origin/main` baseline, 255 tests pass in 254.45 seconds. The slow tests repeatedly execute the complete evolution lifecycle, where each generated child creates several Git worktrees and launches operator and evaluator subprocesses. Running the unchanged suite with pytest-xdist work stealing reduces it to 66.53 seconds on the development machine.

## Design

The default suite remains the complete suite; no slow tests are hidden behind markers or a second command. Add pytest-xdist as a development dependency and configure pytest to use automatic worker discovery with work stealing.

Prune only repetition that does not exercise a new transition:

- One generation is sufficient to verify lineage, mirror synchronization, mutation tracking, and repository cleanliness.
- A one-generation run followed by a two-generation resume is sufficient to verify continuation and duplicate prevention.
- One generation with two children is sufficient to verify population fan-out and sibling lineage.
- One generated row is sufficient to verify that status and report ignore an unstamped malicious override.
- Record-field validation should exercise every forbidden field through the in-process API and retain one CLI call to cover command wiring.
- Lifecycle outcome parameterization should keep one representative later-generation terminal retry because genesis and evaluator tests already cover the individual outcome classifications.

Tests that require two generations for their meaning remain unchanged, including static parent selection and Hyperagents self-modification taking effect in the following generation.

## Acceptance Criteria

- `uv run pytest -q` passes without extra flags.
- The default suite runs with pytest-xdist work stealing.
- Every distinct mechanism listed above retains coverage.
- The suite is at least 70% faster than the 254.45-second serial baseline on the same machine.
- Ruff passes for all modified Python files.

## Non-goals

- Changing production behavior.
- Mocking Git or operator isolation in the remaining end-to-end tests.
- Creating a separate nightly suite or excluding tests from the default command.
