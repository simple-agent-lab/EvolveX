# Harbor Smoke Fixes Implementation Plan

**Goal:** Fix the three infrastructure failures from the Terminal-Bench 2.0 smoke with minimal changes.

**Architecture:** Preserve the existing Harbor runners and validation. Add the MiniSWE completion contract at the AHE call site, place Harbor staging on the checkout filesystem, persist runner errors, and derive expected trial counts from selected tasks.

**Tech stack:** Python, shell evaluator template, pytest.

---

### Task 1: Make the AHE MiniSWE debugger submit correctly

**Files:** `library/trace_analyzer/ahe.py`, `tests/test_ahe_trace_analyzer.py`

1. Add a failing test that MiniSWE debugger prompts require the standalone completion Bash call while other agents are unchanged.
2. Add a small prompt adapter in `_run_debugger_job`.
3. Run `uv run pytest tests/test_ahe_trace_analyzer.py`.

### Task 2: Keep HyperAgents installation on one filesystem

**Files:** `library/meta_agent/runners/harbor.py`, `tests/test_harbor_meta_agent.py`

1. Add a failing assertion that bundle staging is beside the checkout and a failure-evidence test.
2. Pass `checkout.parent` to `tempfile.mkdtemp` and write a redacted `error.json` on runner failure.
3. Run `uv run pytest tests/test_harbor_meta_agent.py`.

### Task 3: Count the selected anchor trials

**Files:** `src/evolve/evaluator.py`, `tests/test_runtime.py`

1. Add a failing test for one selected sealed task with `k=2`.
2. Prefer effective task-set membership for Python expected counts.
3. Confirm the existing shell score parser already counts from the selected task file.
4. Run the targeted test file.

### Task 4: Verify and smoke

1. Run the full pytest, Ruff, and ty checks.
2. Commit the implementation.
3. Sync the commit to DevBoxS and rerun a small two-method Terminal-Bench 2.0 smoke with four workers.
4. Inspect AHE debugger reports, HyperAgents candidate import, and anchor evidence counts.
