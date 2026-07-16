# Sub-20-Second Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the default complete developer test loop from 57.32 seconds to less than 20 seconds while retaining fast contract tests and representative production-faithful lifecycle coverage.

**Architecture:** Register an `extended` pytest marker and exclude it in the default marker expression. A collection hook owns an exact, validated set of redundant lifecycle node IDs; five representative lifecycle scenarios remain unmarked and therefore run by default. Eight work-stealing workers avoid the contention caused by unbounded automatic worker discovery. The hook raises a collection error for stale configured IDs so the boundary cannot silently drift.

**Tech Stack:** Python 3.11+, pytest, pytest-xdist, uv.

## Global Constraints

- `uv run pytest -q` must pass in less than 20 seconds on the benchmark machine.
- At least five representative subprocess/worktree lifecycle scenarios remain in the default suite.
- All fast parsing, archive, validation, task-vector, configuration, SDK, and operator-contract tests remain in the default suite.
- Production code and behavior must not change.
- `uv run pytest -q -m extended` must collect and pass the extended scenarios.

---

### Task 1: Define and validate the extended boundary

**Files:**
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: pytest collection items and their stable node IDs.
- Produces: the `extended` marker assignment and a collection error for stale configured node IDs.

- [ ] **Step 1: Register the `extended` marker in `[tool.pytest.ini_options]`.**
- [ ] **Step 2: Extend `addopts` with `-m` and `not extended`.**
- [ ] **Step 3: Add `_EXTENDED_TESTS: frozenset[str]` containing every measured redundant lifecycle node ID.**
- [ ] **Step 4: Add `pytest_collection_modifyitems(items)` that compares both exact parameterized node IDs and their unparameterized base IDs, marks matches, and raises `pytest.UsageError` when any configured ID is stale.**
- [ ] **Step 5: Run `uv run pytest --collect-only -q` and expect collection to succeed with the default selection.**

### Task 2: Keep the timeout contract fast

**Files:**
- Modify: `tests/test_m5_operator_runner.py`
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `run_operator(..., timeout_s: float)`.
- Produces: the same timeout result assertion without a one-second fixed wait.

- [ ] **Step 1: Change the timeout test from `timeout_s=1` to `timeout_s=0.1`.**
- [ ] **Step 2: Give nested-child cleanup tests a one-second startup window so they remain deterministic under worker load.**
- [ ] **Step 3: Run `uv run pytest -q tests/test_m5_operator_runner.py tests/test_agent_runner.py tests/test_runtime.py -m "extended or not extended"` and expect all tests to pass.**

### Task 3: Verify both suites and update the PR

**Files:**
- Modify: `docs/superpowers/specs/2026-07-16-sub-20-second-test-suite-design.md`
- Modify: `docs/superpowers/plans/2026-07-16-sub-20-second-test-suite.md`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: benchmark evidence and an updated draft PR.

- [ ] **Step 1: Run `uv run ruff check tests/conftest.py tests/test_m5_operator_runner.py` and expect no errors.**
- [ ] **Step 2: Run `/usr/bin/time -p uv run pytest -q --durations=25` and expect all default tests to pass in less than 20 seconds.**
- [ ] **Step 3: Run `uv run pytest -q -m extended` and expect all extended tests to pass.**
- [ ] **Step 4: Run `uv run pytest --collect-only -q -m "extended or not extended"` and verify the union still collects 251 tests.**
- [ ] **Step 5: Commit the verified changes, push `codex/fast-test-suite`, and update draft PR #4 with the new coverage boundary and benchmark.**
