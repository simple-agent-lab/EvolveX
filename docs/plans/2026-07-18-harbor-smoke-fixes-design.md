# Harbor Smoke Fixes Design

## Goal

Remove the three infrastructure failures exposed by the Terminal-Bench 2.0 smoke while preserving the current HyperAgents and AHE experiment semantics.

## Design

### AHE debugger submission

The AHE debugger remains a Harbor read-only trial and continues to return free-form text under the existing headings. When the configured agent is MiniSWE, the debugger prompt will include the agent's required submission protocol: put the report in the response text and issue the standalone completion Bash command. Other Harbor agents are unchanged. No report-schema validation is added.

### HyperAgents candidate installation

The disposable workspace staging directory will be created beside the host checkout rather than in the system temporary directory. The replacement and checkout will therefore be on the same filesystem, preserving the existing atomic rename and rollback logic on DevBoxS. Failures will also persist their redacted exception message next to the existing Harbor artifacts.

### Anchor trial count

Evaluation classification will use the number of tasks actually selected for the effective task set when that membership is known. The Harbor evaluator shell will likewise recompute `EVOLVE_HARBOR_EXPECTED_TRIALS` after split selection from the selected task file and `k`. Thus one sealed task with `k=2` expects two trials, independent of the configured gate task count.

## Verification

Add focused regression tests for the MiniSWE prompt contract, cross-filesystem-safe staging location and failure evidence, and sealed-task count with `k=2`. Run the targeted tests, full unit suite, lint/type checks, then repeat a small DevBoxS smoke.
