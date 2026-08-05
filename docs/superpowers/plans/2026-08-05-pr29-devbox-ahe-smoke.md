# PR 29 DevBox AHE 3x3 Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide and execute one clear Bash script that validates PR #29 with three AHE tasks and three evolved generations on DevBox.

**Architecture:** A single repository script creates an isolated timestamped DevBox run, sources existing private environment inputs, clones the PR branch, copies three immutable Harbor tasks into a fresh dataset, initializes AHE, and runs preflight plus three generations. Shell and `jq` assertions make success depend on the PR commit, certified three-trial evaluations, generation tags, and workspace integrity.

**Tech Stack:** Bash, Git, uv, Evolve CLI, Harbor, Docker, jq, SSH/SCP.

## Global Constraints

- Run AHE over exactly three tasks.
- Run three evolved generations, `gen/1` through `gen/3`, after genesis.
- Use only the generated workspace-root `.env` as the experiment's user-facing environment file.
- Never print, commit, or copy private values outside the isolated run.
- Never modify or delete existing DevBox experiments.
- Preserve the entire run directory and logs on success or failure.

---

### Task 1: Create the reusable smoke script

**Files:**
- Create: `scripts/devbox_pr29_ahe_smoke_3x3.sh`

**Interfaces:**
- Consumes: PR branch `codex/runtime-profiles-phase3`; DevBox model, runtime, and proxy env files; the immutable Tau3 banking Harbor dataset.
- Produces: a timestamped run root containing `repo/`, `dataset/`, `workspace/`, and `run.log`; exits zero only after all assertions pass.

- [ ] **Step 1: Write the script with fixed, overridable inputs**

Use `set -Eeuo pipefail`, `umask 077`, and these defaults:

```bash
PR_BRANCH=${PR_BRANCH:-codex/runtime-profiles-phase3}
RUN_ROOT=${RUN_ROOT:-/data00/home/zimuwang/pr29-ahe-3x3-$(date -u +%Y%m%dT%H%M%SZ)}
SOURCE_DATASET=${SOURCE_DATASET:-/data00/home/zimuwang/simple-evolve-agent-full89-20260724/datasets/tau3-banking-97-codex-safe-health-v033-1d244f5dca42944b67a379b44bfeb9f5748f189d}
MODEL_ENV=${MODEL_ENV:-/data00/home/zimuwang/modelhub-codex-smokes-20260804/evolve.env}
RUNTIME_ENV=${RUNTIME_ENV:-/data00/home/zimuwang/modelhub-codex-smokes-20260804/runtime.env}
PROXY_ENV=${PROXY_ENV:-/data00/home/zimuwang/modelhub-codex-smokes-20260804/proxy.env}
TASKS=3
GENERATIONS=3
```

The script must refuse an existing `RUN_ROOT`, verify `git`, `uv`, `docker`, `harbor`, and `jq`, source the three private files without output, capture the remote PR head with `git ls-remote`, and clone only the PR branch.

- [ ] **Step 2: Create the exact three-task dataset and root environment**

Copy the first three lexically sorted task directories containing `task.toml` into `$RUN_ROOT/dataset`. Initialize with:

```bash
uv run evolve init "$WORKSPACE" --recipe ahe --dataset "$DATASET"
cat "$MODEL_ENV" "$RUNTIME_ENV" "$PROXY_ENV" > "$WORKSPACE/.env"
chmod 600 "$WORKSPACE/.env"
```

Assert that the clone commit equals the captured PR head and that exactly three `task.toml` files exist in the copied dataset.

- [ ] **Step 3: Run preflight, evolution, and evidence assertions**

Execute:

```bash
"$WORKSPACE/evolve" preflight "$WORKSPACE"
"$WORKSPACE/evolve" preflight "$WORKSPACE" --smoke
"$WORKSPACE/evolve" run "$WORKSPACE" --max-generations "$GENERATIONS" --children-per-gen 1 --verbose
"$WORKSPACE/evolve" status "$WORKSPACE"
"$WORKSPACE/evolve" verify "$WORKSPACE"
```

Assert tags `gen/0` through `gen/3`. For genesis and each candidate generation, use `jq -e` over `archive.jsonl` to require `outcome == "benchmark_complete"`, `expected_trials == 3`, three task-set members, and `contract_certified == true`. Print only the run root, commit, status summary, and final success line.

- [ ] **Step 4: Verify the script locally**

Run:

```bash
bash -n scripts/devbox_pr29_ahe_smoke_3x3.sh
rg -n 'TASKS=3|GENERATIONS=3|max-generations|contract_certified|expected_trials|\.env' scripts/devbox_pr29_ahe_smoke_3x3.sh
```

Expected: Bash syntax exits zero and every required invariant is present.

- [ ] **Step 5: Commit the script**

```bash
git add scripts/devbox_pr29_ahe_smoke_3x3.sh
git commit -m "test: add DevBox AHE 3x3 smoke"
```

### Task 2: Execute and verify on DevBox

**Files:**
- Read: `scripts/devbox_pr29_ahe_smoke_3x3.sh`
- Produce remotely: `/data00/home/zimuwang/pr29-ahe-3x3-*/`

**Interfaces:**
- Consumes: the committed Task 1 script and DevBox private inputs.
- Produces: retained DevBox workspace, logs, receipts, contracts, and archive evidence.

- [ ] **Step 1: Copy the script to DevBox**

Run:

```bash
scp scripts/devbox_pr29_ahe_smoke_3x3.sh DevBox:/data00/home/zimuwang/devbox_pr29_ahe_smoke_3x3.sh
ssh DevBox 'chmod 700 /data00/home/zimuwang/devbox_pr29_ahe_smoke_3x3.sh'
```

- [ ] **Step 2: Execute the experiment with a durable log**

Run the script in a login shell and allow its timestamped run root to remain:

```bash
ssh DevBox 'bash -lc /data00/home/zimuwang/devbox_pr29_ahe_smoke_3x3.sh'
```

Expected: the process reaches the final `PASS` line. If it fails, inspect the printed run root and diagnose the preserved `run.log`, preflight receipts, archive, and evaluation artifacts before retrying with a new run root.

- [ ] **Step 3: Independently verify retained evidence**

From the run root printed by the script, run:

```bash
ssh DevBox 'RUN_ROOT=$(find /data00/home/zimuwang -maxdepth 1 -type d -name "pr29-ahe-3x3-*" -printf "%T@ %p\n" | sort -n | tail -n 1 | cut -d" " -f2-); git -C "$RUN_ROOT/repo" rev-parse HEAD; git -C "$RUN_ROOT/workspace" tag --list "gen/*"; jq -c "select(._evolve_mechanism_eval == true) | {genid,purpose,outcome,expected_trials,contract_certified}" "$RUN_ROOT/workspace/archive.jsonl"'
```

Expected: the PR head commit, tags `gen/0` through `gen/3`, and certified three-trial benchmark-complete evaluation records for genesis and generations 1–3.
