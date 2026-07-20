# AHE MiniSWE Debugger Artifact Design

## Goal

Keep MiniSWE as AHE's read-only debugger while removing the dependency on MiniSWE's internal trajectory format. The debugger must return its report through an explicit Harbor artifact.

## Considered approaches

1. **Report artifact (selected).** MiniSWE reads the mounted evidence, writes the final Markdown report to `/logs/artifacts/ahe-debugger-response.md`, and then runs the normal completion sentinel. Harbor collects the file and the AHE runner reads it. This is explicit, small, and independent of trajectory schemas.
2. **Trajectory fallback.** Recover the last assistant message from `mini-swe-agent.trajectory.json`. This accepts a protocol failure and depends on MiniSWE internals, so it will be removed.
3. **Dedicated debugger runtime.** Port the official NexAU debugger. This is closer to the official implementation but adds another runtime and is outside the present smoke-test scope.

## Contract and data flow

- The existing Harbor Docker execution and mounted prompt/evidence remain unchanged.
- For MiniSWE only, the debugger prompt requires tool calls on every turn, permits Bash-based inspection, and requires the final report at `/logs/artifacts/ahe-debugger-response.md`.
- After writing a non-empty report, MiniSWE runs `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` as a standalone final command.
- Harbor's standard `/logs/artifacts` collection returns the report under the trial artifacts directory.
- `run_readonly_agent` reads the report artifact as the authoritative output. It raises a visible error if the file is missing, empty, or escapes the trial directory.
- Non-MiniSWE read-only agents retain the existing normalized Harbor trajectory output path.
- No strict AHE report schema is introduced.

## Scope

Only the AHE MiniSWE debugger prompt and read-only Harbor output collection change. HyperAgents, candidate artifact handling, evaluator execution, retries, and surface gates remain unchanged.

## Verification

- A prompt test verifies the report path, tool-call rule, and completion sentinel.
- Runner tests verify successful report extraction and missing/empty report failures.
- A regression test verifies non-MiniSWE trajectory output still works.
- Focused AHE/Harbor tests run locally, followed by one DevBoxS debugger smoke using existing rollout evidence.
