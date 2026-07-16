# Fast Essential Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the complete default pytest suite materially faster without dropping distinct mechanism coverage.

**Architecture:** Run independent tests concurrently with pytest-xdist work stealing, then shorten only end-to-end scenarios whose extra generations repeat the same transition. Replace the most expensive repeated CLI validation with direct API validation plus one CLI wiring check.

**Tech Stack:** Python 3.11+, pytest, pytest-xdist, uv, Git worktrees.

## Global Constraints

- The default `uv run pytest -q` command must continue to run every retained test.
- Do not change production behavior.
- Preserve at least one end-to-end test for each distinct lifecycle contract.
- Achieve at least a 70% wall-clock reduction from the 254.45-second serial baseline on the same machine.

---

### Task 1: Parallel default execution

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: the existing pytest configuration and development dependency group.
- Produces: `uv run pytest -q` automatically using xdist work stealing.

- [ ] **Step 1: Add `pytest-xdist>=3.8` to the development dependency group.**
- [ ] **Step 2: Configure pytest with `addopts = ["-n", "auto", "--dist", "worksteal"]`.**
- [ ] **Step 3: Refresh `uv.lock` with `uv lock`.**
- [ ] **Step 4: Run `uv run pytest -q` and expect all tests to pass using workers.**

### Task 2: Remove redundant lifecycle repetitions

**Files:**
- Modify: `tests/test_m0_run_resume.py`
- Modify: `tests/test_m3_population_self_reference.py`
- Modify: `tests/test_m4_presets_bootstrap.py`

**Interfaces:**
- Consumes: existing CLI helpers and archive assertions.
- Produces: the same lineage, resume, fan-out, and reporting guarantees with the minimum generations needed.

- [ ] **Step 1: Change the lineage test from five generations to one and update expected rows and tags.**
- [ ] **Step 2: Change the resume test from `2 -> 5` generations to `1 -> 2` and retain prefix and duplicate assertions.**
- [ ] **Step 3: Change population fan-out from two generations to one generation with two sibling children.**
- [ ] **Step 4: Change the status/report test from three generated rows to one and update the malicious row and row count.**
- [ ] **Step 5: Run the four modified test modules and expect all tests to pass.**

### Task 3: Keep record validation coverage without repeated CLI startup

**Files:**
- Modify: `tests/test_m5_record_verb.py`

**Interfaces:**
- Consumes: `evolve.driver.record_fields(workspace, genid, fields)` and the `evolve record` CLI.
- Produces: exhaustive forbidden-field API validation and one end-to-end CLI rejection check.

- [ ] **Step 1: Initialize a workspace without generating a child and target generation zero.**
- [ ] **Step 2: Assert one forbidden field is rejected through the CLI.**
- [ ] **Step 3: Assert every forbidden field raises `RuntimeError` through `record_fields`.**
- [ ] **Step 4: Assert the archive is unchanged and run the focused test.**

### Task 4: Collapse duplicate later-terminal integration cases

**Files:**
- Modify: `tests/test_evaluation_lifecycle.py`

**Interfaces:**
- Consumes: existing genesis classification coverage and later-generation retry lifecycle.
- Produces: one representative later-terminal retry integration test while retaining separate evaluator classification tests.

- [ ] **Step 1: Replace the three-way later retry terminal parameterization with the representative `timeout` outcome.**
- [ ] **Step 2: Replace the three-way immediate later terminal parameterization with the representative `candidate_invalid` outcome.**
- [ ] **Step 3: Run `tests/test_evaluation_lifecycle.py` and expect all tests to pass.**

### Task 5: Verify and publish

**Files:**
- Verify all modified files.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: a benchmarked branch and draft GitHub pull request.

- [ ] **Step 1: Run `uv run ruff check` on the modified Python test files and expect no errors.**
- [ ] **Step 2: Run `/usr/bin/time -p uv run pytest -q --durations=25` and expect all retained tests to pass in less than 76.34 seconds.**
- [ ] **Step 3: Inspect the complete diff and confirm only test-speed work and its design/plan are present.**
- [ ] **Step 4: Commit, push `codex/fast-test-suite`, and open a draft PR against `main`.**
