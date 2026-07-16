# Sub-20-Second Test Suite Design

## Goal

Make the default `uv run pytest -q` developer loop complete in less than 20 seconds while retaining fast contract coverage and a small representative set of real CLI, subprocess, evaluator, and Git-worktree lifecycle tests.

## Current Evidence

PR #4 reduced the suite from 254.45 seconds serial to 57.32 seconds with work-stealing workers and smaller generation counts. Static analysis still finds 56 test functions that invoke the CLI or driver lifecycle. Those tests repeatedly exercise the same process-isolation machinery, so worker parallelism cannot reduce the default loop below the desired target by itself.

## Approaches Considered

1. **Recommended: essential default plus extended lifecycle suite.** Keep all fast tests and five representative lifecycle tests in the default command. Mark redundant lifecycle variants `extended` and exclude them by default. This is reversible, preserves audit coverage, and makes the intended coverage boundary explicit.
2. **Delete redundant lifecycle tests.** This minimizes repository size but permanently removes useful forensic cases and makes later coverage audits harder.
3. **Add production test hooks to bypass subprocesses and worktrees.** This preserves test names but makes them exercise behavior different from production and adds mechanism complexity solely for tests.

## Default Coverage Boundary

The default suite uses eight work-stealing workers, avoiding the process and filesystem contention observed when automatic discovery launched eighteen workers. It retains representative end-to-end coverage for:

- initialization plus one complete generation;
- population formatting and selection through direct contract tests, with full fan-out retained in the extended suite;
- Hyperagents self-modification taking effect in a later generation;
- evaluator retry on the same candidate commit;
- terminal gate/record protection against malicious output;
- the AHE recipe operator chain;

All pure parsing, archive merging, validation, task-vector, configuration, SDK, and operator-contract unit tests remain in the default suite.

## Extended Coverage

Redundant full-lifecycle failure variants receive `@pytest.mark.extended`. They can be run with:

```bash
uv run pytest -q -m extended
```

The complete union can be run with:

```bash
uv run pytest -q -m "extended or not extended"
```

Pytest registers the marker so collection produces no warnings. CI continues to use the default essential suite on every PR; the extended suite is available for explicit audits without slowing every commit.

## Acceptance Criteria

- `uv run pytest -q` passes in less than 20 seconds on the same development machine used for the 57.32-second benchmark.
- At least five representative subprocess/worktree lifecycle tests remain in the default suite.
- All fast contract tests remain in the default suite.
- `uv run pytest -q -m extended` collects and passes the extended tests.
- Ruff passes for every modified Python test file.

## Non-goals

- Changing production code or behavior.
- Making the extended audit suite complete in less than 20 seconds.
- Adding fake in-process execution paths to the mechanism.

## Verified Result

- Default essential suite: 188 passed in 16.27 seconds.
- Extended lifecycle suite: 63 passed in 46.28 seconds.
- Complete union: 251 tests collected.
- Original merged baseline: 255 passed in 254.45 seconds.
