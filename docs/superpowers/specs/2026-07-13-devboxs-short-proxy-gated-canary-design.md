# Short Proxy-Gated Four-Arm Canary

## Purpose

Determine quickly whether the dedicated install proxy removes the Harbor agent-setup hang, then compare old and hardened AHE/HyperAgents only if execution reaches the intended agent-runtime boundary.

## Fixed inputs

- DevBoxS only.
- Reuse hardened `a785ee7`, old AHE `ab4fc2384fef473c598843b82b80eefa920d2cac`, and old HyperAgents `7639e5c`.
- Reuse the exact candidate trees and first task from the completed pilot.
- Source `env/cache-proxy.sh`, copy its proxy/no-proxy values into `EVOLVE_INSTALL_HTTP_PROXY` and `EVOLVE_INSTALL_NO_PROXY`, then unset ordinary proxy variables. Never record proxy values.
- HyperAgents uses the already-validated `gen/1` alias of the unchanged `gen/0` candidate.

## Stage 1: causal gate

Run one fresh hardened-AHE trial with the dedicated install proxy enabled. The prior no-proxy trial is the control: it hung in `apt-get` and timed out after 360 seconds.

Pass only if the trial log proves that the root package-install command completed and execution advanced to the candidate `uv run` setup/agent boundary. A benchmark reward is not required. Stop immediately if package installation still hangs, ownership is lost, cleanup fails, or a new workaround is needed.

## Stage 2: four-arm micro-comparison

Only after Stage 1 passes, launch AHE old/hardened and HyperAgents old/hardened from fresh workspaces. Each arm uses one identical task, one trial, one worker, isolated state/jobs paths, and a synchronized paired start. Run one repetition. Run a second fresh repetition only if all four first-repetition arms reach the intended runtime boundary and finish normally within the remaining budget.

Primary observations:

- furthest runtime phase reached;
- raw exception and reward presence;
- hardened canonical outcome, score eligibility, and parent eligibility;
- wall time and cost;
- artifact and cleanup completeness.

Legacy evidence remains explicitly uncertified where the old framework lacks the new contract.

## Limits and stopping rules

- Hard wall-clock budget: 30 minutes for both stages.
- Stop the entire experiment on repeated setup timeout, identity mismatch, missing terminal evidence, lost process ownership, cleanup failure, or any unplanned compatibility change.
- Do not reinterpret a setup failure as a valid performance measurement.
- One or two single-trial repetitions are diagnostic evidence, not a statistical benchmark-quality claim.
