# Target-Required HyperAgents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stopped operator-focused run with a fresh broad-surface HyperAgents experiment whose prompt requires a substantive `target/**` edit in every proposal.

**Architecture:** Clone the verified framework into a new immutable experiment root, change only the HyperAgents strategy prompt, and scaffold fresh smoke/full workspaces from that recipe. A 3-task/3-generation smoke is the gate: all three candidates must edit `target/**`; otherwise stop without adding framework logic.

**Tech Stack:** Python 3.12, evolve CLI, Git, Harbor/SWE-bench Pro, Bash launch wrappers, DevBoxS, 10-worker full evaluation.

## Global Constraints

- New experiment root: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715`.
- Preserve editable surface exactly as `target/**` and `operators/**`.
- Behavioral change is limited to `recipes/hyperagents/operators/meta_agent.md`.
- Start from the verified seed commit `7cee6331e94c0c6b132724dd10e29d33377dc385`.
- Reuse the fixed train-list hash `5da1bad49642d737fe276db3338b6fe3df910c92218fe59fca0eeb72bdb22186` and sealed-test hash `8171064f410d01a22a58b53300a86c6a823a5d0122fb9b215fb7ec5629c93988`.
- Smoke uses three fixed tasks, three generations, one child per generation.
- Full run uses 30 train tasks, 20 generations, one child per generation, and 10 workers.
- Do not open the sealed test list before recording the selected training candidate.
- If any smoke generation is operator-only, stop and report; do not add a validation gate automatically.

---

### Task 1: Create the clean prompt-only experiment seed

**Files:**
- Create: remote experiment directory `/data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/`
- Modify: remote `framework/recipes/hyperagents/operators/meta_agent.md`
- Copy unchanged: setup helper, proxy environment, fixed task lists, and runtime cache references from the stopped experiment

**Interfaces:**
- Consumes: verified framework commit `26cbbb556ace9812dc401c6d0c7553a00483bfea` and stopped-run Gen0 recipe text.
- Produces: a clean framework commit containing exactly one behavioral file change.

- [ ] **Step 1: Clone the verified framework and create experiment directories**

Run on DevBoxS:

```bash
git clone --no-hardlinks /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-broad-overnight-20260714-212317/framework-full /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/framework
mkdir -p /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/{inputs,sealed,private,status,logs,tools,runtime}
```

Expected: cloned framework HEAD is `26cbbb556ace9812dc401c6d0c7553a00483bfea` and the destination was previously absent.

- [ ] **Step 2: Copy immutable experiment inputs**

Copy the old experiment's `inputs/smoke-train-3.txt`, `inputs/train-30.txt`, `sealed/test-30.txt`, `private/proxy.env`, and `tools/configure_broad_hyperagents.py` into the corresponding new directories. Preserve `sealed/test-30.txt` mode `0600`.

Expected hashes:

```text
train-30.txt  5da1bad49642d737fe276db3338b6fe3df910c92218fe59fca0eeb72bdb22186
test-30.txt   8171064f410d01a22a58b53300a86c6a823a5d0122fb9b215fb7ec5629c93988
```

- [ ] **Step 3: Apply the one-file prompt change**

Use this complete strategy text:

```markdown
# HyperAgents Self-Improvement

Improve downstream task performance by making one coherent repository change.
The benchmark directly evaluates the agent implementation under `target/**`.
Every proposal must therefore include at least one substantive change under
`target/**` that is intended to improve benchmark performance. Re-evaluating an
unchanged target cannot demonstrate improvement.

The allowed surface remains exactly `target/**` and `operators/**`. You may also
improve any part of the active improvement process, including your own behavior,
selection, rollout, validation, admission, or recording, but operator changes
must accompany rather than replace the substantive target improvement.

Inspect prior generations and evaluation artifacts before editing. Make one
coherent repository change; descendants inherit the complete patch. An operator
cannot change the invocation already running. Do not modify the fixed evaluator,
authoritative archive, experiment configuration, or outer driver.
```

- [ ] **Step 4: Verify and commit the prompt-only seed**

Run:

```bash
git -C /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/framework diff --check
git -C /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/framework diff --name-only HEAD
```

Expected sole output path:

```text
recipes/hyperagents/operators/meta_agent.md
```

Commit with message `recipe: require substantive target edits` and record the resulting commit SHA in `status/framework-commit.txt`.

### Task 2: Scaffold and verify the 3×3 smoke

**Files:**
- Create: remote `smoke-workspace/`
- Create: remote `tools/run_smoke.sh`
- Create: smoke logs and status artifacts

**Interfaces:**
- Consumes: Task 1's prompt-only framework commit and `inputs/smoke-train-3.txt`.
- Produces: a fresh three-generation archive whose changed-path records can be audited.

- [ ] **Step 1: Configure the recipe for smoke**

Run `tools/configure_broad_hyperagents.py` with:

```text
--framework /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/framework
--seed /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-smoke-bbb2ca4-20260714-202801/seed
--task-source /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/inputs/smoke-train-3.txt
--task-name smoke-train-3.txt
--experiment-id target-required-smoke
--generations 3
--tasks 3
--workers 3
```

- [ ] **Step 2: Scaffold a fresh workspace**

Run from the new framework virtual environment:

```bash
python -m evolve init /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/smoke-workspace --recipe hyperagents
```

Expected: empty archive lineage except genesis, prompt contains `Every proposal must`, and surface includes both approved globs.

- [ ] **Step 3: Run preflight verification**

Run `./evolve doctor`, `./evolve candidate-smoke --full`, and `./evolve surface-check` from `smoke-workspace` with the verified runtime digest and proxy environment.

Expected: doctor healthy, candidate smoke exits 0, and surface report has no violations.

- [ ] **Step 4: Run three smoke generations**

Launch synchronously:

```bash
./evolve run . --max-generations 3 --children-per-gen 1
```

Preserve stdout/stderr and the exit code under `logs/` and `status/`.

- [ ] **Step 5: Audit the smoke gate**

For Gens1–3, inspect `meta_agent/changed.json`, `meta_agent/surface-check.json`, `validate/result.json`, canonical evaluation records, and Git target-tree hashes.

Expected for every generation:

```text
changed.json contains at least one target/** path
surface-check ok == true
validate accept == true
canonical evaluation completed
target tree differs from its parent
```

Stop here if any expectation fails.

### Task 3: Launch the fresh full experiment after a passing smoke

**Files:**
- Create: remote `full-workspace/`
- Create: remote `tools/run_full.sh` and `tools/monitor_full.sh`
- Create: full-run logs, status, and heartbeat automation

**Interfaces:**
- Consumes: the same prompt-only framework commit proven by Task 2, fixed 30-task train list, and sealed 30-task test list.
- Produces: durable 20-generation training artifacts and a monitored runner.

- [ ] **Step 1: Reconfigure and scaffold the full workspace**

Configure the recipe with `train-30.txt`, experiment id `target-required-full`, 20 generations, 30 tasks, and 10 workers; then run `python -m evolve init /data00/home/zimuwang/simple-evolve-agent-project/experiments/hyperagents-target-required-20260715/full-workspace --recipe hyperagents`.

- [ ] **Step 2: Verify split integrity and full candidate smoke**

Verify train/test hashes, counts of 30, zero overlap without printing sealed members, sealed mode `0600`, config values, prompt checksum, `doctor`, and `candidate-smoke --full`.

- [ ] **Step 3: Launch a durable full runner**

Launch `./evolve run . --max-generations 20 --children-per-gen 1` under a new session with stdout/stderr/status files and record PID, process group, start time, framework commit, workspace genesis commit, and prompt hash.

- [ ] **Step 4: Create a low-frequency heartbeat**

Create one 10-minute heartbeat scoped to the new experiment root. It must audit generation-scale progress, leave healthy evaluations undisturbed, and after Gen20 record selection before opening sealed data.

### Task 4: Select and evaluate the held-out result

**Files:**
- Create: remote selection manifest
- Create: isolated held-out workspace and evaluation artifacts
- Create: final integrity report

**Interfaces:**
- Consumes: completed canonical training archive from Task 3.
- Produces: exactly one sealed 30-task held-out result and a requirement-by-requirement audit.

- [ ] **Step 1: Record the selected training candidate**

Select the valid candidate with highest canonical training score, using later generation as the tie-break. Record generation, candidate commit, target-tree hash, score, task-set hash, and selection timestamp before reading the sealed list.

- [ ] **Step 2: Run exactly one isolated held-out evaluation**

Export the selected candidate into a fresh evaluation-only workspace, configure the sealed 30-task list and 10 workers, disable mutation, and run one genesis evaluation. Permit only the framework's single infrastructure retry; never rerun for quality.

- [ ] **Step 3: Audit and report**

Verify 30 scoreable held-out trials, split secrecy and non-overlap, selected target identity, runtime fingerprint, archive integrity, costs, and all smoke/full target-edit invariants. Delete the heartbeat only after the audit is complete.
