# July 23 Handoff Consolidation and Shared Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the July 23 handoff changes on local `main`, run comparable AHE and HyperAgents experiments over the same 10-task optimization set, and monitor/recover them until inspectable artifacts are ready.

**Architecture:** Keep the framework's train/gate/sealed manifest disjoint but direct canonical evolution evaluation to `train`; `evaluation_replay` then makes those same retained trajectories the learning feedback. Freeze both recipes at 10-worker capacity while adding a runtime-only evaluator concurrency override, so generation 1 can smoke at five workers and the same workspace can continue at ten without changing evaluator identity. Run AHE trace analysis with ten workers, build a versioned expanded meta-agent image, and retain the proven July 18 image as fallback.

**Tech Stack:** Python 3.12+, pytest, YAML recipes, POSIX shell, Git, Docker, Harbor, MiniSWE Agent, OpenAI Responses, SSH/DevBoxS.

## Global Constraints

- Work directly on local `main` because the user explicitly requested local consolidation and the July 23 changes already share this working tree.
- Both recipes use dataset `terminal-bench-2-10-10-10`, split seed `0`, `evaluation_split: train`, `tasks_per_round: 10`, and `k: 1`.
- Candidate settings are reasoning `high`, step limit `100`, environment timeout `30`, cost limit `0`, and default Responses output budget `64000`.
- Smoke uses five evaluator workers; healthy full runs use ten from the same workspace.
- AHE trace analysis uses ten workers and must produce ten detail reports with `debugger_errors == 0`.
- Sealed tasks are neither selected nor evaluated.
- Prefer the newly built expanded image; preserve evidence and fall back to image ID `sha256:61b800306be7032671455fe02b60002dad7853ef2e8de1e3e772f91dcb059998` only if the new image cannot be made healthy promptly.
- Before stopping remote work, enumerate exact experiment controllers, process paths, tmux sessions, and task containers; do not touch unrelated services.
- If DevBoxS authentication expires, run `kinit` in the terminal and retry SSH before diagnosing network or experiment failure.
- Preserve failed workspaces, logs, archives, and image IDs.

---

### Task 1: Shared optimization and adaptive concurrency contract

**Files:**
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_m9_ahe_recipe.py`
- Modify: `tests/test_hyperagents_harbor_recipe.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/hyperagents/README.md`

**Interfaces:**
- Consumes: existing `evaluation_split_name()` behavior and frozen split manifests.
- Produces: identical train-set evaluation configuration for both recipes and runtime variable `EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE`.

- [ ] **Step 1: Write failing recipe-contract tests**

Change the real-recipe assertions to require:

```python
assert "evaluation_split: train" in config
assert "tasks_per_round: 10" in config
assert "k: 1" in config
assert "n_concurrent: 10" in config
```

Require both generated candidate environments to equal:

```python
{
    "MINISWE_COST_LIMIT": "0",
    "MINISWE_ENV_TIMEOUT": "30",
    "MINISWE_REASONING_EFFORT": "high",
    "MINISWE_STEP_LIMIT": "100",
    "OPENAI_BASE_URL": "https://aidp.bytedance.net/api/modelhub/online/responses/openai/responses",
}
```

Require the AHE operator config to contain `max_concurrent: 10`.

- [ ] **Step 2: Write a failing runtime-override test**

Add a template contract test that reads
`templates/evaluator/engines/harbor.sh` and requires the generated Harbor
command to prefer a validated runtime override:

```python
assert "EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" in contents
assert 'invalid EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE' in contents
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/test_phase_e_recipes.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_hyperagents_harbor_recipe.py
```

Expected: failures show the recipes still use gate evaluation, AHE still uses
`k=2`, concurrency is five, HyperAgents lacks the aligned candidate limits,
and the Harbor template lacks the override.

- [ ] **Step 4: Implement the runtime override**

Immediately after sourcing `evaluator/eval.env`, validate and apply:

```sh
if [ -n "${EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE:-}" ]; then
  case "$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" in
    *[!0-9]*|""|0)
      printf 'invalid EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=%s\n' \
        "$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE" >&2
      exit 3
      ;;
  esac
  EVOLVE_HARBOR_N_CONCURRENT=$EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE
fi
```

This changes scheduling only; task identities, attempts, and evaluator
fingerprints remain frozen.

- [ ] **Step 5: Implement the shared recipe settings**

For both recipes add `evaluation_split: train`, set `k: 1`, set
`n_concurrent: 10`, and align the five candidate environment variables.
Set AHE `trace_analyzer.max_concurrent: 10`.

- [ ] **Step 6: Update recipe documentation**

Describe the train partition as the shared 10-task optimization set, state that
the configured gate partition is unused during evolution, and state that
sealed tasks remain untouched. Document `k=1`, five-worker smoke override, and
ten-worker full capacity.

- [ ] **Step 7: Run tests and verify GREEN**

Run the command from Step 3.

Expected: all selected tests pass.

### Task 2: Verify and repair the inherited July 23 handoff integration

**Files:**
- Modify: `tests/test_phase_e_recipes.py`
- Verify: `containers/meta-agent/Dockerfile`
- Verify: `library/meta_agent/runners/__init__.py`
- Verify: `library/meta_agent/runners/harbor.py`
- Verify: `library/trace_analyzer/ahe.py`
- Verify: `templates/target/harbor/miniswe_source_agent.py`
- Verify: `templates/workspace/evolve_harbor_adapter/__init__.py`
- Verify: `templates/workspace/evolve_harbor_agent/__init__.py`
- Verify: `tests/test_ahe_trace_analyzer.py`
- Verify: `tests/test_harbor_file_agent.py`
- Verify: `tests/test_harbor_meta_agent.py`
- Verify: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: the four `handoff-0723-21/*.md` records and current uncommitted working-tree changes.
- Produces: one coherent, test-covered Responses/file-evidence/image integration.

- [ ] **Step 1: Repair the failing Dockerfile assertion**

Replace the formatting-dependent assertion:

```python
assert "python3 python-is-python3" in contents
```

with package-presence assertions:

```python
assert "\n        python3 \\" in contents
assert "\n        python-is-python3 \\" in contents
```

- [ ] **Step 2: Run focused handoff verification**

Run:

```bash
uv run pytest -q \
  tests/test_ahe_trace_analyzer.py \
  tests/test_harbor_file_agent.py \
  tests/test_harbor_meta_agent.py \
  tests/test_miniswe_harbor_wrapper.py \
  tests/test_phase_e_recipes.py
```

Expected: all selected tests pass, proving mounted debugger evidence,
fail-soft accounting, Responses routing/session configuration, 64k default
and override behavior, file-task transport, and expanded image contents.

- [ ] **Step 3: Review the integration diff**

Run:

```bash
git diff --check
git diff --stat
git diff -- \
  containers/meta-agent/Dockerfile \
  library/meta_agent/runners \
  library/trace_analyzer/ahe.py \
  recipes/ahe \
  recipes/hyperagents \
  templates/target/harbor/miniswe_source_agent.py \
  templates/workspace/evolve_harbor_adapter \
  templates/workspace/evolve_harbor_agent \
  tests
```

Expected: no whitespace errors and no unrelated source changes.

### Task 3: Full local verification and main consolidation

**Files:**
- Include: all verified July 23 handoff source, recipes, tests, Dockerfile, documentation, and `handoff-0723-21/*.md`
- Exclude: ignored local datasets, rendered trace tools, experiment output, caches, and unrelated worktree state.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: one verified local `main` commit used as the remote source fingerprint.

- [ ] **Step 1: Run the full suite**

Run:

```bash
uv run pytest -q
```

Expected: 395 or more tests pass with zero failures.

- [ ] **Step 2: Run repository checks**

Run:

```bash
git diff --check
git status --short
git branch --contains HEAD
```

Expected: only the intended integration files are modified/untracked, and the
current branch is `main`.

- [ ] **Step 3: Commit the consolidated integration**

Stage the exact reviewed files and commit:

```bash
git commit -m "feat: consolidate shared optimization experiments"
```

- [ ] **Step 4: Verify the committed source**

Run:

```bash
git status --short --branch
git show --stat --oneline --decorate HEAD
uv run pytest -q
```

Expected: local `main` is clean except intentionally ignored local artifacts,
the commit contains the reviewed integration, and the full suite passes again.

### Task 4: Prepare and clean DevBoxS

**Files:**
- Create remotely: `/data00/home/zimuwang/simple-evolve-agent-shared-opt-20260723/`
- Create remotely: `/data00/home/zimuwang/simple-evolve-agent-shared-opt-20260723/experiments/STATUS.md`

**Interfaces:**
- Consumes: the exact local `main` commit from Task 3.
- Produces: a clean remote source tree, idle experiment capacity, recorded proxy/runtime/image state.

- [ ] **Step 1: Verify SSH and recover credentials if necessary**

Run:

```bash
ssh DevBoxS 'hostname; date; pwd'
```

If authentication is expired, run `kinit` interactively in the terminal and
retry the exact SSH command. Do not print ticket or proxy secrets.

- [ ] **Step 2: Inventory remote state**

Collect:

```bash
ssh DevBoxS 'tmux ls 2>/dev/null || true; ps -eo pid,ppid,pgid,etime,args; docker ps --no-trunc; free -h; df -h /data00; uptime'
```

Identify all active experiment controllers and experiment-owned task
containers by exact command path and job label.

- [ ] **Step 3: Stop active experiments**

Terminate only the enumerated experiment process groups/sessions and matching
task containers. Re-run the inventory and verify no active experiment
controller or task container remains.

- [ ] **Step 4: Inspect proxy configuration safely**

Check only whether relevant proxy variables and helper scripts are present;
redact values. Record which mechanism will be used for Docker build, APT, UV,
and Python downloads.

- [ ] **Step 5: Transfer the committed source**

Create a `git archive` of the Task 3 commit, securely copy it to DevBoxS,
extract it into the new source root, create its virtual environment with the
configured UV binary, and verify the remote source fingerprint against the
local commit recorded in `STATUS.md`.

### Task 5: Build and smoke the expanded meta-agent image

**Files:**
- Consume remotely: `containers/meta-agent/Dockerfile`
- Update remotely: `experiments/STATUS.md`

**Interfaces:**
- Consumes: Task 4 source and proxy state.
- Produces: versioned tag `evolve-meta-agent-app:20260723-pr15` and exact image ID, or a documented fallback decision.

- [ ] **Step 1: Build the new image**

Build with the discovered safe proxy mechanism and tag:

```bash
docker build -t evolve-meta-agent-app:20260723-pr15 containers/meta-agent
```

- [ ] **Step 2: Verify required tools**

Run the image and require successful versions/lookups for:

```text
bash, git, jq, rg, rsync, tree, python3, pip, uv, mini-swe-agent
```

Record `docker image inspect --format '{{.Id}}'` in `STATUS.md`.

- [ ] **Step 3: Apply the experiment tag**

Use a remote experiment-only recipe copy that replaces
`evolve-meta-agent-app:ubuntu-latest` with
`evolve-meta-agent-app:20260723-pr15`. Do not change the committed local recipe
solely for a host-local tag.

- [ ] **Step 4: Fallback only on reproduced image failure**

If the new image fails a real Harbor launch, preserve build output and smoke
logs, diagnose once, and repair/rebuild when bounded. If it remains unhealthy,
record the reason and switch both recipes to the proven July 18 image ID.

### Task 6: Initialize and verify comparable real workspaces

**Files:**
- Create remotely: `experiments/tb2-ahe-sharedopt-k1-10gen-20260723-v1/`
- Create remotely: `experiments/tb2-hyperagents-sharedopt-k1-10gen-20260723-v1/`
- Update remotely: `experiments/STATUS.md`

**Interfaces:**
- Consumes: the same remote source commit, runtime digest, image, dataset, and environment.
- Produces: two frozen comparable workspaces ready for generation-1 smoke.

- [ ] **Step 1: Initialize both workspaces**

Source `/data00/home/zimuwang/simple-evolve-agent-project/.env`, set:

```bash
EVOLVE_RUNTIME_DIGEST=tb2-10x3-runtime-20260722-v3
EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv
```

Initialize one AHE and one HyperAgents workspace from the same source root.

- [ ] **Step 2: Verify frozen equality**

Parse both frozen `gen/0:evolve.yaml` and `gen/0:evaluator/splits.json`.
Require:

```text
evaluation_split=train
tasks_per_round=10
k=1
n_concurrent=10
candidate reasoning=high
candidate step limit=100
candidate environment timeout=30
candidate cost limit=0
same ordered train task list
same ordered sealed task list
no sealed evaluation selection
```

Require AHE `trace_analyzer.max_concurrent=10`.

- [ ] **Step 3: Seed immutable runtime caches**

Reuse only the immutable UV/Python runtime caches from previous workspaces.
Do not copy archives, task results, candidates, or analyzer artifacts.

### Task 7: Run and gate generation-1 smokes

**Files:**
- Update remotely: both experiment workspaces and `experiments/STATUS.md`

**Interfaces:**
- Consumes: Task 6 frozen workspaces.
- Produces: two generation-1 smoke verdicts over real tasks.

- [ ] **Step 1: Launch durable smoke controllers**

Launch both workspaces concurrently with:

```bash
EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=5
python -u -m evolve run <workspace> --max-generations 1 --verbose
```

Wrap each controller with PID, exit-code, start-time, and unbuffered log files.

- [ ] **Step 2: Monitor smoke health**

At each heartbeat inspect controller/process/container liveness, archive
records, ten expected trials, trace freshness, API/formatting errors, host
pressure, and candidate outputs.

- [ ] **Step 3: Enforce the promotion rubric**

Require both genesis and generation 1 archived; ten trials per evaluation;
valid Responses endpoint/reasoning/64k/tool calls; non-empty installable
candidates; and no unexplained controller, archive, API, truncation, format, or
container error. Additionally require AHE ten detail reports and
`debugger_errors == 0`.

- [ ] **Step 4: Recover failed smokes**

Resume consistent archives after controller loss. Preserve and replace corrupt
or misconfigured workspaces. Apply shared fairness changes to both and restart
both. Keep all failed evidence and record every recovery in `STATUS.md`.

### Task 8: Promote, monitor, and preserve full experiments

**Files:**
- Update remotely: both experiment workspaces and `experiments/STATUS.md`

**Interfaces:**
- Consumes: Task 7 passing workspaces.
- Produces: full generation-10 archives or healthy continuing runs with complete inspectable state.

- [ ] **Step 1: Promote the same workspaces**

Stop the smoke controllers after clean exit and continue both workspaces with:

```bash
python -u -m evolve run <workspace> --max-generations 10 --verbose
```

Omit the five-worker override so frozen ten-worker capacity applies.

- [ ] **Step 2: Monitor comprehensively**

Use the active goal and ten-minute thread heartbeat. Inspect all rubric health
signals and make meaningful recovery progress on every wake.

- [ ] **Step 3: Maintain artifact pointers**

Keep `STATUS.md` current with source commit, task-set hashes and members,
runtime digest, image tag/ID, controller PIDs and exit states, generation
progress, failures/recoveries, and direct paths to archives, summaries, traces,
logs, and candidates.

- [ ] **Step 4: Verify completion artifacts**

When both runs finish, verify generation 10 is durably archived, expected
evaluation/analyzer artifacts exist, no task containers remain, and all paths
in `STATUS.md` resolve. Do not run sealed evaluation.

- [ ] **Step 5: End monitoring**

Only after the completion audit succeeds, mark the active goal complete and
delete the heartbeat automation.
