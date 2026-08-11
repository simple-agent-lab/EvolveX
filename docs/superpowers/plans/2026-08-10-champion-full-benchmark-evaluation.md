# Champion Full-Benchmark Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run eight immutable champion agents once over four 89-task Terminal-Bench 2 evaluations and four 97-instance Tau3 Banking evaluations, after eight one-instance preflights, while enforcing the approved 75-worker DevBox and 25-worker DevBoxS limits.

**Architecture:** Build a one-off operational bundle locally, copy it to a new isolated evaluation root on each host, and use it to materialize corrected evaluation workspaces from audited rerun templates plus exact champion `target/` trees. Run a fail-closed preflight matrix, then two four-run waves, retrying only missing or infrastructure-owned failures once and producing merged task vectors with provenance.

**Tech Stack:** Python 3.12, Bash, Git, Evolve's deployed Python API, Harbor, Docker, SSH/SCP, JSON, YAML.

## Global Constraints

- Original experiment repositories, tags, archives, runs, mirrors, and corrected rerun workspaces are read-only inputs.
- Use exactly the eight champion tags and commits recorded in the approved design.
- Terminal-Bench 2 uses exactly 89 unique tasks per champion; Tau3 Banking uses exactly 97 unique instances per champion.
- Use one primary trial per task and no seed-agent baselines.
- Every Tau3 runtime call uses explicit simulator seed `626729`.
- Every full evaluation uses 25 workers.
- DevBox runs at most three evaluations concurrently; DevBoxS runs at most one; global maximum is 100 workers.
- Full launch is forbidden unless all eight one-instance preflights pass.
- Retry only missing or infrastructure-owned failures once; never replace a scoreable primary result.
- Never print or persist authentication tokens, API keys, proxy URLs, or `auth.json` contents.
- Keep all one-off generated files below `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/` on the remote hosts and `/private/tmp/champion-full-20260810/` locally.

---

### Task 1: Freeze the matrix and host readiness evidence

**Files:**
- Create locally: `/private/tmp/champion-full-20260810/matrix.json`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/audit/host-readiness-DevBox.json`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/audit/host-readiness-DevBoxS.json`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/manifests/tb2-all-89.txt`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/manifests/tau3-all-97.txt`

**Interfaces:**
- Consumes: the eight source repositories and commits in the approved design; both complete datasets; configured SSH hosts `DevBox` and `DevBoxS`.
- Produces: a canonical eight-row matrix, identical task manifests on both hosts, dataset hashes, and a redacted readiness decision.

- [ ] **Step 1: Write the canonical matrix**

Create `matrix.json` with one object per champion containing `id`, `host`, `benchmark`, `method`, `target_type`, `source`, `tag`, `commit`, `template`, `dataset`, `task_count`, `simulator_seed`, and `concurrency`. Use these row IDs:

```text
tb-ahe-miniswe
tb-hyper-miniswe
tb-ahe-codex
tb-hyper-codex
tau3-ahe-miniswe
tau3-hyper-miniswe
tau3-ahe-codex
tau3-hyper-codex
```

Use `task_count=89` and `simulator_seed=null` for TB2, `task_count=97` and `simulator_seed=626729` for Tau3, and `concurrency=25` for every row. Map source tags and commits exactly from the approved design. Use the matching corrected rerun workspace as `template`; never use a pending `partner-aligned` scaffold.

Use these template paths relative to the experiment root on the row's host:

```text
tb-ahe-miniswe       reruns/tb-ahe-miniswe-champ-evalfix
tb-hyper-miniswe     reruns/tb-hyper-miniswe-seed-evalfix
tb-ahe-codex         reruns/tb-codex-seed-evalfix
tb-hyper-codex       reruns/tb-hyper-codex-champ-evalfix
tau3-ahe-miniswe     reruns/ahe-miniswe-tau3-seed626729
tau3-hyper-miniswe   reruns/hyper-miniswe-tau3-seed626729
tau3-ahe-codex       reruns/ahe-codex-tau3-seed626729
tau3-hyper-codex     reruns/hyper-codex-tau3-champ-seed626729
```

Templates supply only the corrected evaluator/runtime shape. The preparation
step always replaces their `target/` tree with the champion tree and records a
new evaluated commit.

- [ ] **Step 2: Verify all champion identities without writing source repositories**

For every row, run:

```bash
git -C "$SOURCE" rev-parse "$TAG^{commit}"
git -C "$SOURCE" cat-file -e "$COMMIT^{commit}"
git -C "$SOURCE" diff --quiet "$COMMIT" "$TAG"
git -C "$SOURCE" ls-tree -d --name-only "$TAG" target
```

Expected: the resolved commit exactly equals the matrix commit and `target` exists.

- [ ] **Step 3: Generate full task manifests on both hosts**

For TB2, enumerate direct child directories containing `task.toml` under:

```text
/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/terminal-bench-2-full89
```

For Tau3, enumerate direct child directories containing `task.toml` under:

```text
/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/datasets/tau3-banking-97-codex-safe-health-v033-1d244f5dca42944b67a379b44bfeb9f5748f189d-seed626729-r1
```

Sort with bytewise `C` locale and write one directory name per line. Require 89/89 and 97/97 unique lines respectively.

- [ ] **Step 4: Compare cross-host manifest hashes**

Run `sha256sum` for both normalized manifests on both hosts. Expected: the TB2 hash matches across hosts and the Tau3 hash matches across hosts. Stop on any mismatch.

- [ ] **Step 5: Record redacted host readiness**

Record only booleans or non-secret measurements for Docker availability, CPU count, memory, `/data00` free space, required image presence, framework interpreter presence, Codex auth-file existence/mode, required environment-variable presence, current Evolve/Harbor process count, and current container count. Require at least 200 GiB free on each host and no active evaluation launch that would exceed the approved host limit.

- [ ] **Step 6: Review the readiness evidence**

Expected: DevBox is approved for 75 workers, DevBoxS for 25, both datasets have exact cardinality and matching hashes, and no secret values appear in JSON.

---

### Task 2: Build and validate isolated evaluation workspaces

**Files:**
- Create locally: `/private/tmp/champion-full-20260810/prepare_eval.py`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/bin/prepare_eval.py`
- Create remotely per row: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/workspaces/<row-id>/`
- Create remotely per row: `workspaces/<row-id>/evaluation-provenance.json`

**Interfaces:**
- Consumes: `matrix.json`, normalized manifests, corrected rerun templates, and exact champion tags.
- Produces: eight independent Git repositories whose HEAD contains the corrected evaluator configuration and exact champion `target/` tree.

- [ ] **Step 1: Implement fail-closed workspace preparation**

`prepare_eval.py` must:

1. Refuse an existing destination.
2. Resolve and compare the champion tag to the expected full commit.
3. Clone the corrected template with `--no-hardlinks`.
4. Remove the cloned `target/` from the index and checkout only `target/` from the champion commit.
5. Set a unique experiment ID equal to `champion-full-20260810-<row-id>`.
6. Set evaluator dataset to the matrix dataset, `evaluation_split: train`, `sampling: static`, `tasks_per_round` to 89 or 97, `k: 1`, `n_concurrent: 25`, and disable final anchors.
7. Rewrite `evaluator/splits.json` as version 1 with every manifest task in `train`, empty `gate` and `sealed`, static sampling, counts `89/0/0` or `97/0/0`, and SHA-256 membership digests.
8. Write `evaluator/tasks/train.txt` from the exact manifest and empty `gate.txt` and `sealed.txt`.
9. Update `evaluator/eval.env` with the exact dataset, expected-trial count, task file, and concurrency without copying credentials.
10. For Tau3 only, require the explicit-seed dataset and set the runtime seed to `626729`; for TB2, remove Tau3-only simulator configuration.
11. Commit all changes with local-only identity `Champion Full Evaluation <champion-eval@local>` and tag the candidate `eval/primary`.
12. Write `evaluation-provenance.json` outside Git containing source path, source tag, source commit, template path, evaluated commit, task-manifest hash, dataset, task count, and simulator seed.

- [ ] **Step 2: Add preparation self-checks**

Before returning success, require:

```text
git status --porcelain == empty
git rev-parse eval/primary == evaluated commit
git diff --quiet source-tag:target evaluated-commit:target
split train count == task_count
split gate count == 0
split sealed count == 0
task file count == task_count
configured concurrency == 25
```

For Tau3 additionally require every generated task runtime to carry effective seed `626729`; for TB2 require no Tau3 simulator variables.

- [ ] **Step 3: Test preparation on disposable copies**

Run `prepare_eval.py --check` for all rows without creating destinations, then prepare one TB2 MiniSWE row and one Tau3 Codex row in a disposable directory. Inspect their Git trees, configs, split manifests, and provenance. Remove only the disposable test destinations after inspection.

- [ ] **Step 4: Prepare all eight production evaluation workspaces**

Run the script on the matrix rows assigned to each host. Expected: eight clean repositories, exact candidate-tree matches, and unique experiment IDs.

- [ ] **Step 5: Verify the candidate-source boundary**

Use the prepared evaluator's candidate-runtime preparation in install-only mode and inspect the redacted receipt. Require the imported or mounted candidate path to be the detached evaluation checkout. Stop if it resolves to `EVOLVE_WORKSPACE`, a shared seed, the template, or the source repository's current checkout.

---

### Task 3: Run the eight-instance paid preflight matrix

**Files:**
- Create locally: `/private/tmp/champion-full-20260810/evaluate_row.py`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/bin/evaluate_row.py`
- Create remotely per row: `preflight/<row-id>/`
- Create remotely: `audit/preflight-summary.json`

**Interfaces:**
- Consumes: eight prepared workspaces and the host runtime environment loaders.
- Produces: one real, scoreable preflight result per champion plus a global pass/fail summary.

- [ ] **Step 1: Implement the row evaluator wrapper**

The wrapper accepts `--row`, `--purpose preflight|primary|retry`, `--task-file`, `--task-limit`, and `--concurrency`. It must load the existing host runtime environment without printing values, export the frozen framework Python, set the approved concurrency, and invoke the deployed Evolve evaluation API against `eval/primary` with `purpose="research"` and the requested task limit.

Reserve a purpose-specific output directory before execution and tee stdout/stderr to timestamped logs. Persist the returned record as JSON. Reject a task file whose IDs are not a subset of the canonical full manifest.

- [ ] **Step 2: Run dry-run validation for all rows**

For each row, print only row ID, host, candidate commit, task count, task-file hash, concurrency, model identity, reasoning level, and Tau3 seed. Compare these values to `matrix.json`. Expected: all eight match and no secret values appear.

- [ ] **Step 3: Select deterministic preflight tasks**

Use the first bytewise-sorted task from each canonical manifest. Each row's preflight task file contains exactly one ID. Record that ID and the full-manifest hash in the preflight provenance.

- [ ] **Step 4: Launch one real task for every champion**

Launch the eight preflights with no more than three simultaneous processes on DevBox and one on DevBoxS. Each evaluation itself receives `task_limit=1` and concurrency 1; its model, candidate adapter, reasoning configuration, dataset, and Tau3 seed remain identical to the full run.

- [ ] **Step 5: Audit every preflight artifact**

Require exactly one task in the returned task vector, a scoreable status, a complete indexed-artifact file, an evaluated candidate commit matching provenance, and a candidate-runtime receipt bound to the expected target tree. For Tau3, inspect persisted runtime evidence and require simulator seed `626729`.

- [ ] **Step 6: Gate the full launch**

Write `audit/preflight-summary.json` with eight rows and `all_passed`. Continue only when `all_passed` is true. If any row fails, retain artifacts, stop, and report the failing boundary instead of launching a full wave.

---

### Task 4: Launch and audit Wave 1 Terminal-Bench 2

**Files:**
- Create locally: `/private/tmp/champion-full-20260810/launch_wave.py`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/bin/launch_wave.py`
- Create remotely per TB2 row: `primary/<row-id>/`
- Create remotely: `audit/wave1-primary.json`

**Interfaces:**
- Consumes: passing preflight summary, four TB2 workspaces, and `tb2-all-89.txt`.
- Produces: four terminal primary evaluations and a per-task completeness audit.

- [ ] **Step 1: Implement host-capacity enforcement**

Before launch and every 30 seconds while starting jobs, count owned wave processes and Harbor trial containers. Refuse a fourth DevBox evaluation or a second DevBoxS evaluation. Use process IDs and unique row IDs, not broad process-name killing or cleanup.

- [ ] **Step 2: Launch the four TB2 evaluations**

Start concurrently:

```text
DevBox:  tb-ahe-miniswe, tb-ahe-codex, tb-hyper-codex
DevBoxS: tb-hyper-miniswe
```

Pass the complete 89-task manifest and concurrency 25 to each. Run under persistent remote sessions with PID files and timestamped logs so SSH disconnects do not terminate evaluations.

- [ ] **Step 3: Monitor without mutating live runs**

Poll process state, completed-task count, failed-task count, container health, disk space, and last-log timestamp at intervals no shorter than 60 seconds. Do not restart Docker, move tags, edit configs, or relaunch a row while its primary process is alive.

- [ ] **Step 4: Audit Wave 1 primary evidence**

After all four processes terminate, require the evaluated candidate commit and manifest hash to match provenance. Build an 89-ID table for every row classifying each ID as scoreable, infrastructure-failed, missing, or duplicate. Preserve the first scoreable primary result when duplicates exist.

- [ ] **Step 5: Decide whether Wave 2 may begin**

Wave 2 may begin after all four Wave 1 primary processes are terminal and the audit files are durable. Infrastructure retry work may be deferred until after both primary waves, but no ambiguous or still-running Wave 1 process may overlap Wave 2.

---

### Task 5: Launch and audit Wave 2 Tau3 Banking

**Files:**
- Create remotely per Tau3 row: `primary/<row-id>/`
- Create remotely: `audit/wave2-primary.json`

**Interfaces:**
- Consumes: Wave 1 terminal-state audit, four Tau3 workspaces, and `tau3-all-97.txt`.
- Produces: four terminal Tau3 primary evaluations with explicit seed evidence and a per-instance completeness audit.

- [ ] **Step 1: Recheck explicit Tau3 seed immediately before launch**

For every row, inspect the selected dataset task runtime and the generated evaluation environment. Require the runtime call site and persisted prospective receipt to use `626729`; reject null, 42-only, or implicit/default seed behavior.

- [ ] **Step 2: Launch the four Tau3 evaluations**

Start concurrently:

```text
DevBox:  tau3-ahe-miniswe, tau3-hyper-miniswe, tau3-ahe-codex
DevBoxS: tau3-hyper-codex
```

Pass the complete 97-instance manifest and concurrency 25 to each. Use the same persistent-session, PID, logging, and capacity controls as Wave 1.

- [ ] **Step 3: Monitor Wave 2 read-only**

Poll at intervals no shorter than 60 seconds. In addition to the Wave 1 health fields, sample persisted task receipts to confirm new trials continue to record seed `626729`.

- [ ] **Step 4: Audit Wave 2 primary evidence**

Build a 97-ID classification table per row and require candidate commit, manifest hash, dataset identity, and simulator seed to match provenance. Treat the legacy expected-trial-count defect as an audit concern: 97 scoreable task vectors are authoritative even if an old wrapper emits a stale status label.

---

### Task 6: Retry infrastructure gaps once and publish final results

**Files:**
- Create locally: `/private/tmp/champion-full-20260810/audit_results.py`
- Create remotely: `/data00/home/zimuwang/simple-agent-lab/RSIHub-full89-20260724/full-evals/champion-full-20260810/bin/audit_results.py`
- Create remotely per affected row: `retry/<row-id>/tasks.txt`
- Create remotely per row: `results/<row-id>/task_vector.json`
- Create remotely: `results/summary.json`
- Create remotely: `results/summary.md`

**Interfaces:**
- Consumes: primary task vectors and indexed artifacts from both waves.
- Produces: bounded retry manifests, provenance-preserving merged vectors, and the final eight-row report.

- [ ] **Step 1: Implement strict failure ownership classification**

Classify as retryable only missing task IDs or records whose owner/reason is infrastructure, service startup, auth transport, container runtime, or artifact collection. Do not retry valid zero rewards, verifier failures, candidate errors, benchmark-agent timeouts recorded as scoreable zero, or policy failures.

- [ ] **Step 2: Write and review retry manifests**

For each affected row, write sorted unique IDs and prove the file is a strict subset of the canonical manifest. Record the primary evidence that caused each ID to enter the retry set. If all rows are complete, write no retry manifests.

- [ ] **Step 3: Execute at most one retry per retryable ID**

Use the same candidate, dataset, model, reasoning, seed, and host limits. Set the evaluator task file to the retry manifest. Never start a retry while that row's primary process remains alive.

- [ ] **Step 4: Merge by task ID with immutable primary preference**

For each ID, select the scoreable primary record if present; otherwise select the single scoreable retry. Preserve both records and the selection reason in provenance. Mark IDs with no scoreable record after retry as unresolved.

- [ ] **Step 5: Verify final denominators and scores**

Require 89 unique merged records for every TB2 row and 97 for every Tau3 row. Compute numerator, denominator, mean score, status counts, total cost, and wall time from merged evidence. If unresolved IDs remain, mark that row incomplete and report the explicit denominator; do not silently divide by 89 or 97.

- [ ] **Step 6: Run final integrity checks**

Verify all indexed artifact paths and hashes, candidate commits, task-manifest hashes, Tau3 seed receipts, and cross-host matrix identity. Search logs and reports for credential-like values before handoff; report only presence booleans and redacted configuration.

- [ ] **Step 7: Present the final handoff**

Report the eight rows separately with benchmark, method/target, champion tag and commit, score, numerator/denominator, completeness, retries, cost, wall time, and remote evidence path. Do not aggregate TB2 and Tau3 into one metric.

---

## Execution Checkpoints

1. Stop after Task 1 if host readiness, cardinality, or hashes fail.
2. Stop after Task 2 if any candidate-source or workspace-integrity check fails.
3. Stop after Task 3 unless all eight paid preflights pass.
4. Start Wave 2 only after all Wave 1 primary runs are terminal and audited.
5. Retry only after both primary waves are terminal, unless an earlier wave must be completed before capacity can be released safely.
6. Claim completion only after Task 6 verifies all expected IDs or explicitly reports unresolved gaps.
