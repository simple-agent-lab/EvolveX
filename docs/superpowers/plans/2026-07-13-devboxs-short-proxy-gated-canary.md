# Short Proxy-Gated Four-Arm Canary Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm the missing install proxy caused Harbor setup hangs, then run at most eight four-arm measurement trials within 30 minutes.

**Architecture:** Reuse the exact tested frameworks, task, and candidate trees from the completed pilot. A single proxy-enabled trial gates one required four-arm repetition and one optional repetition; any unusual condition stops the run.

**Tech Stack:** Bash, Git, Harbor, Docker, JSON, DevBoxS.

## Global Constraints

- DevBoxS only; existing experiment artifacts are read-only.
- Hard wall-clock limit: 30 minutes.
- Never print or persist proxy values.
- Use one task, one trial, and one worker per arm.
- Stop on setup timeout, identity mismatch, missing terminal evidence, ownership/cleanup failure, or any new workaround.
- Do not treat setup failure as a performance result.

---

### Task 1: Run the proxy causal gate

**Files:**
- Create remotely: `experiments/framework-hardening-short-canary-${RUN_TS}/causal/**`
- Read remotely: completed pilot workspaces and framework snapshots

**Interfaces:**
- Produces: `causal/gate.json` with `install_completed` and `runtime_boundary_reached`

- [ ] Allocate one new timestamped experiment root and record the 30-minute deadline.
- [ ] Clone the completed pilot's hardened-AHE canary workspace locally on DevBoxS, reset the new clone to `gen/0`, and verify task/candidate hashes.
- [ ] Load `.env` and `env/project-env.sh` silently, source `env/cache-proxy.sh`, copy `http_proxy`/`no_proxy` into `EVOLVE_INSTALL_HTTP_PROXY`/`EVOLVE_INSTALL_NO_PROXY`, then unset ordinary proxy variables.
- [ ] Run one hardened-AHE generation-0 trial with isolated `EVOLVE_HOME` and `EVOLVE_JOBS_DIR` and a 10-minute timeout.
- [ ] Pass only when `trial.log` proves the root package-install command completed and execution advanced to the subsequent candidate `uv run` setup/agent command. Record only proxy presence and configuration-file hashes, never values.
- [ ] Stop and report immediately if the gate fails or cleanup leaves an owned process/container.

### Task 2: Run the four-arm micro-comparison

**Files:**
- Create remotely: `arms/{ahe-old,ahe-hardened,hyper-old,hyper-hardened}/rep-{1,2}/**`
- Create remotely: `results/${arm}-rep-${rep}.json`

**Interfaces:**
- Consumes: passing `causal/gate.json`
- Produces: four required rep-1 results and four optional rep-2 results

- [ ] Clone fresh tracked workspaces from the completed pilot; verify AHE and HyperAgents target-tree equality, one identical task, one trial, one worker, and isolated jobs/state paths.
- [ ] Use generation 0 with `--force` for AHE and the already-validated unchanged generation-1 alias without `--force` for both HyperAgents arms.
- [ ] Launch all four rep-1 arms together with dedicated install proxy variables and per-arm process groups; capture start skew, return code, wall time, raw trial result, canonical hardened result, cost, and cleanup.
- [ ] Stop if any arm repeats `AgentSetupTimeoutError`, loses ownership, lacks terminal raw evidence, or requires an unplanned adaptation.
- [ ] Run rep 2 from fresh clones only if all four rep-1 arms reach the intended runtime boundary, finish normally, and at least 10 minutes remain before the deadline.

### Task 3: Verify and summarize

**Files:**
- Create remotely: `summary.json`, `summary.md`

**Interfaces:**
- Consumes: causal gate plus four or eight selected measurements
- Produces: scoped causal, correctness, and exploratory overhead conclusions

- [ ] Verify exact task/candidate/framework/environment fingerprints and unique attempt identities.
- [ ] Verify exception-first hardened semantics, reward/score eligibility, parent eligibility, artifact/cost propagation, and zero owned processes/containers.
- [ ] Report proxy causality separately from four-arm runtime correctness and exploratory wall time.
- [ ] State that one or two single-trial repetitions are diagnostic, not statistical benchmark evidence.
