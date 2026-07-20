# AHE MiniSWE Debugger Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AHE MiniSWE debugger submit its Markdown analysis through Harbor's standard `/logs/artifacts` collection without reading MiniSWE's private trajectory format.

**Architecture:** The AHE prompt gives MiniSWE one explicit file-and-sentinel submission contract. The read-only Harbor runner resolves the standard artifact through `manifest.json`, validates it remains inside the trial, and uses its non-empty contents as the debugger output; other agents retain normalized trajectory extraction.

**Tech Stack:** Python 3.12+, pytest, Harbor, MiniSWE-Agent.

## Global Constraints

- Keep MiniSWE as the AHE debugger.
- Do not add strict AHE report-schema validation.
- Do not change HyperAgents, evaluator execution, retries, or surface gates.
- Keep the implementation limited to the existing prompt and runner modules.

---

### Task 1: MiniSWE report submission prompt

**Files:**
- Modify: `library/trace_analyzer/ahe.py`
- Test: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: `_debugger_prompt(job: TaskAnalysisJob) -> str`
- Produces: `_debugger_runner_prompt(job: TaskAnalysisJob, config: dict[str, Any]) -> str` containing `/logs/artifacts/ahe-debugger-response.md` and the standalone completion sentinel.

- [ ] **Step 1: Change the prompt test to require artifact submission**

Assert the MiniSWE prompt requires Bash tool calls, writes `/logs/artifacts/ahe-debugger-response.md`, and runs `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`; assert it no longer requests prose before the tool call.

- [ ] **Step 2: Run the prompt test and verify RED**

Run: `uv run pytest -q tests/test_ahe_trace_analyzer.py::test_ahe_miniswe_debugger_prompt_includes_submission_protocol`

Expected: FAIL because the current prompt does not name the report artifact and still asks for reasoning prose first.

- [ ] **Step 3: Implement the minimal prompt contract**

Replace the contradictory prose-first instructions with: inspect evidence through Bash as needed; every response must include a Bash call; write the complete report to `/logs/artifacts/ahe-debugger-response.md`; then run the standalone completion sentinel.

- [ ] **Step 4: Run the prompt test and verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 2: Authoritative Harbor report artifact

**Files:**
- Modify: `library/meta_agent/runners/harbor.py`
- Test: `tests/test_harbor_meta_agent.py`

**Interfaces:**
- Consumes: Harbor trial `artifacts/manifest.json` entry with `source == "/logs/artifacts"`.
- Produces: `_readonly_artifact_output(trial_dir: Path) -> str`, returning the non-empty contents of `ahe-debugger-response.md` or raising `RuntimeError`.

- [ ] **Step 1: Write failing artifact extraction tests**

Cover a valid collected report, a missing report, and a manifest destination that escapes the trial. Remove the MiniSWE trajectory-fallback test.

- [ ] **Step 2: Run the new runner tests and verify RED**

Run: `uv run pytest -q tests/test_harbor_meta_agent.py -k 'readonly_artifact or readonly_agent_returns'`

Expected: FAIL because `_readonly_artifact_output` does not exist and `run_readonly_agent` still reads trajectories.

- [ ] **Step 3: Implement extraction and wire the read-only runner**

Resolve the `/logs/artifacts` manifest destination beneath the trial directory, require `status == "ok"`, read `ahe-debugger-response.md`, reject missing or empty content, and make `run_readonly_agent` prefer this contract for `mini-swe-agent` or `evolve_harbor_agent:FileTaskMiniSweAgent`. Leave `_agent_output` as normalized Harbor trajectory extraction only.

- [ ] **Step 4: Run the runner tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Run necessary regression tests**

Run: `uv run pytest -q tests/test_harbor_meta_agent.py tests/test_ahe_trace_analyzer.py tests/test_harbor_file_agent.py`

Expected: all tests PASS.

- [ ] **Step 6: Commit and validate remotely**

Commit the implementation, deploy the two modified modules to DevBoxS, and run one AHE debugger job against existing rollout evidence. Success requires a non-empty collected `ahe-debugger-response.md` and generated AHE analysis artifacts.
