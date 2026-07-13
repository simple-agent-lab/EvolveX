# DevBoxS Four-Arm Runtime Canary Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a gated 80-trial DevBoxS comparison of old and hardened AHE/HyperAgents runtime correctness and overhead.

**Architecture:** Transfer the exact hardened commit into an immutable remote snapshot and create fresh workspaces for every arm and repetition. Old and hardened arms within each recipe receive identical generation-zero candidate source and task inputs. Four sequential canaries gate four paired, high-concurrency measurement phases; all evidence is append-only under one timestamped root.

**Tech Stack:** Bash, Git archives, `uv`, Python 3, Harbor, Docker, JSON/JSONL, SHA-256, DevBoxS.

## Global Constraints

- All benchmark work runs on `DevBoxS`.
- Test hardened commit `a785ee7`, old AHE `ab4fc2384fef473c598843b82b80eefa920d2cac`, and old HyperAgents `7639e5c`.
- Use exactly five tasks, two trials, and two repetitions per arm: 80 measurement trials.
- Run one old/hardened pair at a time with eight workers per arm; fall back symmetrically to five workers.
- Existing experiments, framework snapshots, Harbor jobs, and global Docker state are read-only.
- Never print or retain expanded credentials or proxy values.
- Stop before measurement if a readiness canary fails.
- A pending job with no owning Harbor process is failed, never successful.

## Remote File Structure

```text
experiments/framework-hardening-runtime-canary-${RUN_TS}/
  design.json
  tasks/runtime-5.txt
  snapshots/hardened-a785ee7/
  arms/${arm}/{canary,rep-1,rep-2}/workspace/
  logs/
  pids/
  results/
  summary.json
  summary.md
  reproduce.sh
```

Every workspace has its own `EVOLVE_HOME` and `EVOLVE_JOBS_DIR`.

### Task 1: Create and verify the hardened snapshot

**Files:**
- Read: `.worktrees/framework-hardening/**`
- Create remotely: `snapshots/hardened-a785ee7/**`
- Create remotely: `logs/hardened-{sync,tests}.log`

**Interfaces:**
- Consumes: local commit `a785ee7`
- Produces: tested remote snapshot with source marker `a785ee7`

- [ ] **Step 1: Verify the local source**

```bash
git -C /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening rev-parse a785ee7^{commit}
git -C /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening status --short
```

Expected: the commit resolves and status is empty.

- [ ] **Step 2: Allocate a unique remote root**

```bash
RUN_TS=$(date +%Y%m%d-%H%M%S)
EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-runtime-canary-$RUN_TS
ssh DevBoxS "test ! -e '$EXP' && mkdir -p '$EXP'/{snapshots/hardened-a785ee7,arms,logs,pids,results,tasks}"
```

Expected: exit code 0.

- [ ] **Step 3: Transfer and test the exact commit**

```bash
git -C /Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening archive --format=tar a785ee7 | ssh DevBoxS "tar -xf - -C '$EXP/snapshots/hardened-a785ee7'"
ssh DevBoxS "printf '%s\n' a785ee7 > '$EXP/snapshots/hardened-a785ee7/git-source-commit'"
ssh DevBoxS "cd '$EXP/snapshots/hardened-a785ee7' && uv sync --frozen --all-groups > '$EXP/logs/hardened-sync.log' 2>&1 && uv run --frozen pytest -q > '$EXP/logs/hardened-tests.log' 2>&1"
ssh DevBoxS "tail -5 '$EXP/logs/hardened-tests.log'"
```

Expected: `214 passed`. Stop otherwise.

### Task 2: Freeze task and candidate identities

**Files:**
- Create remotely: `tasks/runtime-5.txt`
- Create remotely: `design.json`

**Interfaces:**
- Produces: immutable task hash plus AHE and HyperAgents target-tree hashes

- [ ] **Step 1: Write the approved task list**

```bash
ssh DevBoxS "printf '%s\n' \
'instance_ansible__ansible-0ea40e09d1b35bcb69ff4d9cecf3d0defa4b36e8-v30a923fb5c164d6cd18280c02422f75e611e8fb2' \
'instance_ansible__ansible-11c1777d56664b1acb56b387a1ad6aeadef1391d-v0f01c69f1e2528b935359cfe578530722bca2c59' \
'instance_flipt-io__flipt-05d7234fa582df632f70a7cd10194d61bd7043b9' \
'instance_future-architect__vuls-73f0adad95c4d227e2ccfa876c85cc95dd065e13' \
'instance_internetarchive__openlibrary-f8cc11d9c1575fdba5ac66aee0befca970da8d64-v13642507b4fc1f8d234172bf8129942da2c2ca26' \
> '$EXP/tasks/runtime-5.txt'"
```

Expected: five unique lines.

- [ ] **Step 2: Verify membership in both historical training sets**

```bash
ssh DevBoxS "while read -r task; do grep -Fxq \"\$task\" /data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/tasks/train-30.txt && grep -Fxq \"\$task\" /data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hyperagents-30x30-20260711-020208/tasks/train-30.txt || exit 1; done < '$EXP/tasks/runtime-5.txt'"
```

Expected: exit code 0.

- [ ] **Step 3: Write `design.json`**

```bash
ssh DevBoxS "python3 - '$EXP' <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
exp = Path(sys.argv[1])
ahe = Path('/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/workspace')
hyper = Path('/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hyperagents-30x30-20260711-020208/workspace')
tree = lambda path: subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'gen/0:target'], text=True).strip()
task_bytes = (exp / 'tasks/runtime-5.txt').read_bytes()
payload = {
    'hardened_commit': 'a785ee7',
    'old_ahe_commit': 'ab4fc2384fef473c598843b82b80eefa920d2cac',
    'old_hyper_commit': '7639e5c',
    'task_sha256': hashlib.sha256(task_bytes).hexdigest(),
    'tasks': task_bytes.decode().splitlines(),
    'ahe_target_tree': tree(ahe),
    'hyper_target_tree': tree(hyper),
    'trials_per_task': 2,
    'repetitions': 2,
    'workers_per_arm': 8,
    'fallback_workers_per_arm': 5,
    'wall_time_overhead_limit': 0.15,
}
(exp / 'design.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
PY
python3 -m json.tool '$EXP/design.json' >/dev/null"
```

Expected: valid JSON with no credential fields.

### Task 3: Prepare twelve isolated workspaces

**Files:**
- Create remotely: `arms/{ahe-old,ahe-hardened,hyper-old,hyper-hardened}/{canary,rep-1,rep-2}/workspace/**`
- Create remotely: `results/workspace-identities.json`

**Interfaces:**
- Consumes: fixed task file, framework snapshots, old `gen/0` targets
- Produces: normalized workspaces with candidate equality within recipe

- [ ] **Step 1: Initialize all workspaces**

Use these framework/recipe pairs:

```text
ahe-old: /framework/ahe-ab4fc23-final-20260711, recipe ahe
ahe-hardened: $EXP/snapshots/hardened-a785ee7, recipe ahe
hyper-old: /framework/hyperagents-7639e5c46478-20260711, recipe hyperagents
hyper-hardened: $EXP/snapshots/hardened-a785ee7, recipe hyperagents
```

Run a remote Bash loop with explicit mappings:

```bash
declare -A FRAMEWORK RECIPE
FRAMEWORK[ahe-old]=/data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-ab4fc23-final-20260711
FRAMEWORK[ahe-hardened]=$EXP/snapshots/hardened-a785ee7
FRAMEWORK[hyper-old]=/data00/home/zimuwang/simple-evolve-agent-project/framework/hyperagents-7639e5c46478-20260711
FRAMEWORK[hyper-hardened]=$EXP/snapshots/hardened-a785ee7
RECIPE[ahe-old]=ahe
RECIPE[ahe-hardened]=ahe
RECIPE[hyper-old]=hyperagents
RECIPE[hyper-hardened]=hyperagents
for arm in ahe-old ahe-hardened hyper-old hyper-hardened; do
  for purpose in canary rep-1 rep-2; do
    EVOLVE_HOME=$EXP/arms/$arm/$purpose/evolve-home \
      "${FRAMEWORK[$arm]}/.venv/bin/evolve" init \
      "$EXP/arms/$arm/$purpose/workspace" --recipe "${RECIPE[$arm]}"
  done
done
```

Expected: twelve initialized workspaces.

- [ ] **Step 2: Normalize evaluator settings**

With PyYAML set `task_file: evaluator/tasks/runtime-5.txt`, `k: 2`, and
`n_concurrent: 8`. For canaries use a one-line task file, `k: 1`, and
`n_concurrent: 1`. Remove `evaluator.stage`; set `evaluator.anchor.final` false
when present. This normalization ensures one equivalent full evaluation per arm.

Run this for each initialized workspace:

```bash
PYTHON=${FRAMEWORK[$arm]}/.venv/bin/python
WORKSPACE=$EXP/arms/$arm/$purpose/workspace
"$PYTHON" - "$WORKSPACE" "$EXP/tasks/runtime-5.txt" "$purpose" <<'PY'
import sys, yaml
from pathlib import Path
workspace, source, purpose = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
config = yaml.safe_load((workspace / 'evolve.yaml').read_text())
evaluator = config['evaluator']
evaluator.pop('stage', None)
if isinstance(evaluator.get('anchor'), dict):
    evaluator['anchor']['final'] = False
evaluator['task_file'] = 'evaluator/tasks/runtime-5.txt'
evaluator['k'] = 1 if purpose == 'canary' else 2
evaluator['n_concurrent'] = 1 if purpose == 'canary' else 8
tasks = source.read_text().splitlines()
selected = tasks[:1] if purpose == 'canary' else tasks
destination = workspace / 'evaluator/tasks/runtime-5.txt'
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text('\n'.join(selected) + '\n')
(workspace / 'evolve.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
PY
```

Expected: canaries bind one task/one trial; measurement workspaces bind five
tasks/two trials and eight workers.

- [ ] **Step 3: Copy identical candidate source**

Use `git archive gen/0 target` from the old AHE workspace for both AHE arms and
from the old HyperAgents workspace for both HyperAgents arms. Commit workspace
changes and force-update `gen/0`. Record all target hashes and assert equality
within each recipe and purpose before continuing.

```bash
AHE_SOURCE=/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/workspace
HYPER_SOURCE=/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hyperagents-30x30-20260711-020208/workspace
for arm in ahe-old ahe-hardened hyper-old hyper-hardened; do
  SOURCE=$AHE_SOURCE
  case "$arm" in hyper-*) SOURCE=$HYPER_SOURCE ;; esac
  for purpose in canary rep-1 rep-2; do
    WORKSPACE=$EXP/arms/$arm/$purpose/workspace
    git -C "$WORKSPACE" rm -r -q target
    git -C "$SOURCE" archive gen/0 target | tar -xf - -C "$WORKSPACE"
    git -C "$WORKSPACE" add target evaluator/tasks/runtime-5.txt evolve.yaml
    git -C "$WORKSPACE" commit -qm 'freeze runtime canary inputs'
    git -C "$WORKSPACE" tag -f gen/0
  done
done
for purpose in canary rep-1 rep-2; do
  test "$(git -C "$EXP/arms/ahe-old/$purpose/workspace" rev-parse gen/0:target)" = "$(git -C "$EXP/arms/ahe-hardened/$purpose/workspace" rev-parse gen/0:target)"
  test "$(git -C "$EXP/arms/hyper-old/$purpose/workspace" rev-parse gen/0:target)" = "$(git -C "$EXP/arms/hyper-hardened/$purpose/workspace" rev-parse gen/0:target)"
done
```

Expected: all six equality checks pass. Write the twelve hashes to
`results/workspace-identities.json` using `json.dumps(..., sort_keys=True)`.

### Task 4: Run four sequential readiness canaries

**Files:**
- Create remotely: `logs/${arm}-canary.{log,rc}`
- Create remotely: `results/${arm}-canary.json`
- Create remotely: `results/readiness.json`

**Interfaces:**
- Produces: hard gate `ready: true|false`

- [ ] **Step 1: Run each canary with a 45-minute timeout**

For each value of `arm` in `ahe-old ahe-hardened hyper-old hyper-hardened`, load `/data00/home/zimuwang/simple-evolve-agent-project/.env` and
`env/project-env.sh` without echoing them, unset ordinary proxy variables, set
arm-specific `EVOLVE_HOME` and `EVOLVE_JOBS_DIR`, then run:

```bash
FRAMEWORK_PATH=${FRAMEWORK[$arm]}
WORKSPACE=$EXP/arms/$arm/canary/workspace
timeout 2700 "$FRAMEWORK_PATH/.venv/bin/evolve" eval "$WORKSPACE" 0 --force
```

Capture start/end timestamps, PID, PGID, stdout/stderr, and return code.

- [ ] **Step 2: Validate terminal evidence**

Require one trial-level `result.json` (not the job-level result), terminal Harbor
state, parseable task vector, safe artifact index with resolving hashes, elapsed
time, and no active container owned by the finished canary. Hardened arms must
also retain `cost.json`. Write all fields to `$EXP/results/${arm}-canary.json`.

- [ ] **Step 3: Enforce the gate**

Write `readiness.json` with all four arm results and `ready` equal to their
logical conjunction. Exit 4 and stop if `ready` is not exactly true.

### Task 5: Run paired AHE repetitions

**Files:**
- Create remotely: `logs/ahe-{old,hardened}-rep-{1,2}.{log,rc}`
- Create remotely: `results/ahe-{old,hardened}-rep-{1,2}.json`

**Interfaces:**
- Produces: forty AHE measurement trials

- [ ] **Step 1: Launch repetition 1 as a paired phase**

Start old and hardened within the same second with separate `EVOLVE_HOME`, jobs,
logs, PIDs, and process groups. Each arm uses eight workers and a two-hour
timeout.

- [ ] **Step 2: Monitor every 60 seconds**

Record load, process ownership, active Harbor children, trial-level terminal
counts, and arm-specific containers. If no trial state changes for ten minutes
and no Harbor process owns the job, terminate only that experiment process group
and mark the pair invalid. Never count a job-level result as a completed trial.

- [ ] **Step 3: Run repetition 2 in fresh paths**

Require ten terminal trials per arm per repetition. Preserve rep-1 unchanged.

- [ ] **Step 4: Apply symmetric fallback if needed**

If load remains above 14 for five minutes or both arms repeatedly fail container
startup, retain the failed attempt and rerun both arms in new paths with five
workers each.

### Task 6: Run paired HyperAgents repetitions

**Files:**
- Create remotely: `logs/hyper-{old,hardened}-rep-{1,2}.{log,rc}`
- Create remotely: `results/hyper-{old,hardened}-rep-{1,2}.json`

**Interfaces:**
- Produces: forty HyperAgents measurement trials

- [ ] **Step 1: Launch both HyperAgents repetitions as paired phases**

For each repetition, start `hyper-old` and `hyper-hardened` within the same
second, each with eight workers, a two-hour timeout, separate workspace,
`EVOLVE_HOME`, `EVOLVE_JOBS_DIR`, log, PID, and process group. Monitor every 60
seconds. Stop only the current experiment process group if trial-level state is
unchanged for ten minutes and no Harbor process owns the job. If load remains
above 14 for five minutes or both arms repeatedly fail container startup,
retain the attempt and rerun both arms in fresh paths with five workers.

- [ ] **Step 2: Verify screening remains disabled**

```bash
find "$EXP/arms/hyper-hardened" -type d -name 'eval-stage' -print
find "$EXP/arms/hyper-hardened" -type d -name '*replay*' -print
```

Expected: no output and exactly ten trials per arm/repetition.

### Task 7: Aggregate correctness and overhead

**Files:**
- Create remotely: `summary.json`
- Create remotely: `summary.md`

**Interfaces:**
- Consumes: eight measurement JSON files and four canary files
- Produces: paired old-versus-hardened verdicts

- [ ] **Step 1: Validate identities and count**

Require exactly 80 measurement trial identities grouped by recipe, arm,
repetition, task, and trial index. Reject duplicates or missing trials; exclude
the four canaries.

- [ ] **Step 2: Compute paired metrics**

For each recipe/arm compute median and per-repetition wall time, setup latency,
trials/hour, total cost, cost/trial, terminal outcome counts, reward mean, and
artifact completeness. Compute hardened-minus-old absolute and percentage
differences only within recipe.

- [ ] **Step 3: Audit exception precedence and eligibility**

For hardened results, every exception or nonzero Harbor return must be
score-ineligible; every infrastructure failure must have no score and
`valid_parent: false`. Report old false completions without rewriting them.

- [ ] **Step 4: Write verdicts**

Set `runtime_correct` only when all hardened criteria pass. Set
`overhead_acceptable` only when paired median wall time is at most 15% slower and
cost has no systematic increase. State that two repetitions are a canary, not a
statistical performance claim.

### Task 8: Verify and report

**Files:**
- Create remotely: `reproduce.sh`
- Verify remotely: full experiment root

**Interfaces:**
- Produces: secret-free reproducibility record and user-facing result

- [ ] **Step 1: Write `reproduce.sh`**

Include exact snapshot, initialization, normalization, identity, canary,
paired-launch, monitor, and aggregation commands. Reference environment-loading
files but never expand their values into the script.

- [ ] **Step 2: Run integrity checks**

```bash
test "$(wc -l < "$EXP/tasks/runtime-5.txt")" -eq 5
test "$(find "$EXP/results" -name '*rep-*.json' | wc -l)" -eq 8
python3 -m json.tool "$EXP/design.json" >/dev/null
python3 -m json.tool "$EXP/results/readiness.json" >/dev/null
python3 -m json.tool "$EXP/summary.json" >/dev/null
```

Scan for credential patterns; require no matches. Do not scan or print the
external environment files themselves.

- [ ] **Step 3: Report limitations honestly**

Report experiment root, commits, task/candidate hashes, worker decisions,
readiness, trial counts, correctness, paired overhead, cost, and every stopped
attempt. Explicitly state that this does not validate unfinished
preflight/retry/process-ownership integration or evolutionary score quality.
