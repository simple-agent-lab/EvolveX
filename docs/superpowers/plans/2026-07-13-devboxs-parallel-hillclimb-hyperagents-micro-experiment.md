# DevBoxS Parallel Hill-Climb and HyperAgents Micro-Experiment Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run comparable three-generation hill-climb and HyperAgents MiniSWE experiments concurrently on DevBoxS, then evaluate each arm's newest runnable non-seed candidate on three held-out tasks and diagnose HyperAgents patch repetition.

**Architecture:** Transfer the unpushed local framework branch as a Git bundle, create an experiment-only derived framework commit containing only recipe/task-count overrides, and initialize two isolated training workspaces from that snapshot. Both arms share one copied, warmed uv cache but have separate archives, workspaces, jobs, logs, and process groups. After training, export each newest runnable generated candidate into a fresh evaluation-only workspace configured from a separate sealed-task framework checkout.

**Tech Stack:** Git bundles and worktrees, Bash, Python 3.11+, PyYAML, uv, Harbor 0.18.0, Docker, MiniSWE source agent, SWE-bench Pro registry.

## Global Constraints

- Run only on `DevBoxS` under `/data00/home/zimuwang/simple-evolve-agent-project`.
- Use local branch `codex/framework-hardening`; do not push it.
- Preserve unrelated local changes in `.superpowers/sdd/task-2-report.md` and `.superpowers/sdd/task-8-report.md`.
- Use three fixed training tasks, three generated candidates, one candidate per generation, `k=1`, and three Harbor workers per arm.
- Launch hill climb and HyperAgents concurrently against the identical training task file.
- Evaluate the newest runnable candidate from generations 3, 2, or 1 in that order; never substitute generation 0 and do not require the selected candidate to be the training winner.
- Keep the three held-out task names and all held-out artifacts outside both training workspaces and out of all meta-agent prompts.
- Treat `pyproject.toml` and `uv.lock` as an immutable-consistency pair during evaluation; never regenerate a lock silently.
- Use frozen candidate materialization and direct virtualenv Python execution; never repair a running trial interactively.
- Reuse one canonical warmed uv cache across both arms and both post-loop evaluations; do not prune it during the experiment.
- Installation may use the configured installation proxy. Remove uppercase and lowercase HTTP, HTTPS, and ALL proxy variables before meta-agent/model execution.
- Source `.env` silently. Never print `.env`, API credential values, or proxy values.
- The protected `./evolve candidate-smoke --full` command remains optional for the meta-agent.
- Do not remove or alter unrelated DevBoxS containers or processes.
- Do not claim long-run HyperAgents quality from this three-generation diagnostic.

---

### Task 1: Freeze and Transfer the Local Framework Snapshot

**Files:**
- Read: `.git` and the committed tree at `codex/framework-hardening`
- Create locally: `/tmp/framework-hardening-parallel-micro.bundle`
- Create locally: `/tmp/framework-hardening-parallel-micro.commit`
- Create remotely: `/data00/home/zimuwang/simple-evolve-agent-project/incoming/framework-hardening-parallel-micro.bundle`
- Create remotely: `/data00/home/zimuwang/simple-evolve-agent-project/framework/framework-hardening-parallel-micro-20260713`

**Interfaces:**
- Consumes: the local plan-bearing head of `codex/framework-hardening`, which contains runtime commit `4db6aa2` and the approved design.
- Produces: a fresh remote framework checkout whose head exactly matches the captured local source commit.

- [ ] **Step 1: Verify the local branch and preserve unrelated changes**

Run from `/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening`:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

Expected: branch `codex/framework-hardening`; history contains `4db6aa2` and
`3ad90a8`; only the two known `.superpowers/sdd/` files are modified.

- [ ] **Step 2: Create a branch-complete Git bundle without pushing**

```bash
git rev-parse HEAD > /tmp/framework-hardening-parallel-micro.commit
git bundle create /tmp/framework-hardening-parallel-micro.bundle codex/framework-hardening
git bundle verify /tmp/framework-hardening-parallel-micro.bundle
```

Expected: verification succeeds and lists `refs/heads/codex/framework-hardening`.

- [ ] **Step 3: Transfer the bundle to DevBoxS**

```bash
ssh DevBoxS 'mkdir -p /data00/home/zimuwang/simple-evolve-agent-project/incoming'
scp /tmp/framework-hardening-parallel-micro.bundle DevBoxS:/data00/home/zimuwang/simple-evolve-agent-project/incoming/framework-hardening-parallel-micro.bundle
```

Expected: both commands exit zero; no remote is pushed.

- [ ] **Step 4: Clone a fresh remote framework checkout**

First require the destination to be absent:

```bash
ssh DevBoxS 'test ! -e /data00/home/zimuwang/simple-evolve-agent-project/framework/framework-hardening-parallel-micro-20260713'
```

Then clone and verify:

```bash
ssh DevBoxS 'git clone --branch codex/framework-hardening /data00/home/zimuwang/simple-evolve-agent-project/incoming/framework-hardening-parallel-micro.bundle /data00/home/zimuwang/simple-evolve-agent-project/framework/framework-hardening-parallel-micro-20260713'
REMOTE_COMMIT=$(ssh DevBoxS 'git -C /data00/home/zimuwang/simple-evolve-agent-project/framework/framework-hardening-parallel-micro-20260713 rev-parse HEAD')
test "$REMOTE_COMMIT" = "$(cat /tmp/framework-hardening-parallel-micro.commit)"
```

Expected: the local and remote source commits match exactly.

---

### Task 2: Prepare the Fixed Task Sets and Experiment-Only Recipes

**Files:**
- Read remotely: `experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/tasks/train-30.txt`
- Read remotely: `experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/tasks/test-30.txt`
- Create remotely: `$EXP/inputs/train-3.txt`
- Create remotely: `$EXP/sealed/test-3.txt`
- Create locally then transfer: `/tmp/evolve-parallel-micro/configure_recipe.py`
- Modify remotely in the experiment checkout: `recipes/hill_climb/evolve.yaml`
- Modify remotely in the experiment checkout: `recipes/hyperagents/evolve.yaml`
- Create remotely in the experiment checkout: `recipes/{hill_climb,hyperagents}/evaluator/tasks/train-3.txt`

**Interfaces:**
- Consumes: validated 30-task training and sealed task lists.
- Produces: one three-task multi-image training list, one disjoint three-task held-out list, and a remote-only derived framework commit used to initialize clean generation-0 tags.

- [ ] **Step 1: Create a timestamped experiment root**

Use this fixed, one-run path and require it to be absent:

```bash
PROJECT=/data00/home/zimuwang/simple-evolve-agent-project
EXP=$PROJECT/experiments/framework-hardening-parallel-micro-20260713
test ! -e "$EXP"
mkdir -p "$EXP/inputs" "$EXP/sealed" "$EXP/hillclimb" "$EXP/hyperagents" "$EXP/tools"
chmod 700 "$EXP/sealed"
printf '%s\n' "$EXP"
```

Expected: one new experiment root is printed. Record it locally before continuing.

- [ ] **Step 2: Select three varied training images and three held-out images without printing the held-out names**

Use positions 1, 13, and 24 from each validated list. These positions span Ansible, Flipt, and OpenLibrary-style benchmark images in the training list.

```bash
sed -n '1p;13p;24p' "$PROJECT/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/tasks/train-30.txt" > "$EXP/inputs/train-3.txt"
sed -n '1p;13p;24p' "$PROJECT/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/tasks/test-30.txt" > "$EXP/sealed/test-3.txt"
chmod 600 "$EXP/sealed/test-3.txt"
```

Expected: no task names are printed.

- [ ] **Step 3: Validate counts, uniqueness, and disjointness using only safe summaries**

```bash
python3 - "$EXP/inputs/train-3.txt" "$EXP/sealed/test-3.txt" <<'PY'
import hashlib
import sys
from pathlib import Path

train = [line.strip() for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
test = [line.strip() for line in Path(sys.argv[2]).read_text().splitlines() if line.strip()]
assert len(train) == len(set(train)) == 3
assert len(test) == len(set(test)) == 3
assert set(train).isdisjoint(test)
print("train_count=3")
print("test_count=3")
print("disjoint=true")
print("train_sha256=" + hashlib.sha256(("\n".join(train) + "\n").encode()).hexdigest())
print("test_sha256=" + hashlib.sha256(("\n".join(test) + "\n").encode()).hexdigest())
PY
```

Expected: counts are 3, `disjoint=true`, and only hashes—not held-out names—are printed.

- [ ] **Step 4: Create the recipe configuration helper locally**

First run `mkdir -p /tmp/evolve-parallel-micro`. Then create
`/tmp/evolve-parallel-micro/configure_recipe.py` with `apply_patch` using this
complete content:

```python
#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", type=Path, required=True)
    parser.add_argument("--recipe", choices=("hill_climb", "hyperagents"), required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--task-source", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    args = parser.parse_args()

    recipe_root = args.framework / "recipes" / args.recipe
    config_path = recipe_root / "evolve.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["experiment"]["id"] = args.experiment_id
    config["experiment"]["max_generations"] = 3
    config["experiment"]["children_per_gen"] = 1
    evaluator = config["evaluator"]
    evaluator["dataset"] = "swebenchpro@1.0"
    evaluator["dataset_mode"] = "registry"
    evaluator["task_file"] = "evaluator/tasks/" + args.task_name
    evaluator["tasks_per_round"] = 3
    evaluator["k"] = 1
    evaluator["n_concurrent"] = 3
    destination = recipe_root / "evaluator" / "tasks" / args.task_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.task_source, destination)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))


if __name__ == "__main__":
    main()
```

Expected: the helper exists only under `/tmp`; it does not modify the repository yet.

- [ ] **Step 5: Transfer and run the helper for both training recipes**

```bash
EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-parallel-micro-20260713
scp /tmp/evolve-parallel-micro/configure_recipe.py DevBoxS:"$EXP/tools/configure_recipe.py"
```

On DevBoxS:

```bash
PROJECT=/data00/home/zimuwang/simple-evolve-agent-project
EXP=$PROJECT/experiments/framework-hardening-parallel-micro-20260713
FRAMEWORK=$PROJECT/framework/framework-hardening-parallel-micro-20260713
uv run --project "$FRAMEWORK" --frozen python "$EXP/tools/configure_recipe.py" --framework "$FRAMEWORK" --recipe hill_climb --experiment-id hillclimb-parallel-20260713 --task-source "$EXP/inputs/train-3.txt" --task-name train-3.txt
uv run --project "$FRAMEWORK" --frozen python "$EXP/tools/configure_recipe.py" --framework "$FRAMEWORK" --recipe hyperagents --experiment-id hyperagents-parallel-20260713 --task-source "$EXP/inputs/train-3.txt" --task-name train-3.txt
```

Expected: both commands exit zero without resolving a new framework lock.

- [ ] **Step 6: Commit only the experiment recipe overrides in the remote checkout**

```bash
git -C "$FRAMEWORK" diff --check
git -C "$FRAMEWORK" add recipes/hill_climb/evolve.yaml recipes/hill_climb/evaluator/tasks/train-3.txt recipes/hyperagents/evolve.yaml recipes/hyperagents/evaluator/tasks/train-3.txt
git -C "$FRAMEWORK" commit -m "experiment: configure parallel three-task run"
git -C "$FRAMEWORK" rev-parse HEAD > "$EXP/framework-training-commit.txt"
git -C "$FRAMEWORK" diff --quiet
```

Expected: a remote-only derived commit is recorded and the checkout is clean. Nothing is pushed.

---

### Task 3: Initialize and Verify Both Training Workspaces

**Files:**
- Create remotely: `$EXP/hillclimb/hillclimb-workspace`
- Create remotely: `$EXP/hyperagents/hyperagents-workspace`
- Create remotely: `$EXP/runtime/uv-cache`
- Create remotely: per-arm `evolve-home`, `logs`, and `pids` directories

**Interfaces:**
- Consumes: the remote derived framework commit, local MiniSWE seed, fixed training task file, and verified warm cache.
- Produces: clean generation-0 tags whose evaluator trees already contain the final three-task configuration.

- [ ] **Step 1: Copy the verified warm cache into an experiment-owned canonical cache**

```bash
WARM=/data00/home/zimuwang/canaries/framework-hardening-runtime-workspace-74a9028/runs/runtime/uv-cache
mkdir -p "$EXP/runtime/uv-cache"
rsync -a "$WARM/" "$EXP/runtime/uv-cache/"
du -sh "$EXP/runtime/uv-cache"
```

Expected: approximately 670 MiB is present.

- [ ] **Step 2: Initialize both workspaces from the same MiniSWE seed**

```bash
SEED=$PROJECT/sources/mini-swe-agent
HC_WS=$EXP/hillclimb/hillclimb-workspace
HA_WS=$EXP/hyperagents/hyperagents-workspace
mkdir -p "$EXP/hillclimb/evolve-home" "$EXP/hillclimb/logs" "$EXP/hillclimb/pids"
mkdir -p "$EXP/hyperagents/evolve-home" "$EXP/hyperagents/logs" "$EXP/hyperagents/pids"
EVOLVE_HOME="$EXP/hillclimb/evolve-home" uv run --project "$FRAMEWORK" --frozen evolve init "$HC_WS" --recipe hill_climb --seed "$SEED"
EVOLVE_HOME="$EXP/hyperagents/evolve-home" uv run --project "$FRAMEWORK" --frozen evolve init "$HA_WS" --recipe hyperagents --seed "$SEED"
```

Expected: both initializations succeed, preserve `target/uv.lock`, and create `gen/0`.

- [ ] **Step 3: Attach both workspaces to the same canonical cache**

```bash
mkdir -p "$HC_WS/runs/runtime" "$HA_WS/runs/runtime"
ln -s "$EXP/runtime/uv-cache" "$HC_WS/runs/runtime/uv-cache"
ln -s "$EXP/runtime/uv-cache" "$HA_WS/runs/runtime/uv-cache"
```

Expected: both symlinks resolve to the identical canonical directory.

- [ ] **Step 4: Verify configuration, evaluator-tree cleanliness, and task hashes**

```bash
uv run --project "$FRAMEWORK" --frozen python - "$HC_WS" "$HA_WS" <<'PY'
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

hashes = []
for raw in sys.argv[1:]:
    workspace = Path(raw)
    config = yaml.safe_load((workspace / "evolve.yaml").read_text())
    evaluator = config["evaluator"]
    assert config["experiment"]["max_generations"] == 3
    assert config["experiment"]["children_per_gen"] == 1
    assert evaluator["dataset"] == "swebenchpro@1.0"
    assert evaluator["dataset_mode"] == "registry"
    assert evaluator["task_file"] == "evaluator/tasks/train-3.txt"
    assert evaluator["tasks_per_round"] == evaluator["n_concurrent"] == 3
    assert evaluator["k"] == 1
    assert (workspace / "target" / "uv.lock").is_file()
    assert subprocess.check_output(["git", "-C", str(workspace), "status", "--porcelain"], text=True) == ""
    task_bytes = (workspace / "evaluator" / "tasks" / "train-3.txt").read_bytes()
    hashes.append(hashlib.sha256(task_bytes).hexdigest())
assert len(set(hashes)) == 1
print("workspace_config=true")
print("workspace_clean=true")
print("training_task_hash_match=true")
PY
```

Expected: all three safe booleans print `true`.

- [ ] **Step 5: Verify the external meta-agent command without making a model request**

Source `.env` silently and run only the helper's `--check` path:

```bash
set -a
. "$PROJECT/.env"
set +a
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
"$SEED/.venv/bin/python" "$FRAMEWORK/tools/miniswe_source_agent_command.py" --check
```

Expected: `miniswe-source-agent-ok` and a model name are printed; no credential value or model request appears.

---

### Task 4: Launch Both Training Arms Concurrently

**Files:**
- Create locally then transfer: `/tmp/evolve-parallel-micro/launch_arm.sh`
- Create remotely: per-arm `logs/top.log`, `pids/top.pid`, and `started-at.txt`

**Interfaces:**
- Consumes: initialized workspaces, `.env`, `cache-proxy.sh`, and the validated source-agent command.
- Produces: two independently owned process groups running generations 0 through 3 concurrently.

- [ ] **Step 1: Create the shared launch wrapper locally**

Create `/tmp/evolve-parallel-micro/launch_arm.sh` with `apply_patch` using:

```bash
#!/usr/bin/env bash
set -euo pipefail

ARM_ROOT=$1
WORKSPACE=$2
FRAMEWORK=$3
SEED=$4
PROJECT=$5

set -a
. "$PROJECT/.env"
set +a
. "$PROJECT/env/cache-proxy.sh"

install_proxy=${HTTPS_PROXY:-${HTTP_PROXY:-${https_proxy:-${http_proxy:-}}}}
install_no_proxy=${NO_PROXY:-${no_proxy:-}}
test -n "$install_proxy"
export EVOLVE_INSTALL_HTTP_PROXY=$install_proxy
export EVOLVE_INSTALL_NO_PROXY=$install_no_proxy
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

export EVOLVE_HOME="$ARM_ROOT/evolve-home"
export EVOLVE_AGENT_COMMAND="$SEED/.venv/bin/python $FRAMEWORK/tools/miniswe_source_agent_command.py"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ARM_ROOT/started-at.txt"
exec "$WORKSPACE/evolve" run "$WORKSPACE" --max-generations 3
```

Expected: the wrapper contains no secret or proxy value.

- [ ] **Step 2: Transfer the wrapper and make it executable**

```bash
EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-parallel-micro-20260713
scp /tmp/evolve-parallel-micro/launch_arm.sh DevBoxS:"$EXP/tools/launch_arm.sh"
ssh DevBoxS "chmod 700 '$EXP/tools/launch_arm.sh'"
```

Expected: transfer and chmod succeed.

- [ ] **Step 3: Start both process groups within the same minute**

On DevBoxS:

```bash
setsid "$EXP/tools/launch_arm.sh" "$EXP/hillclimb" "$HC_WS" "$FRAMEWORK" "$SEED" "$PROJECT" > "$EXP/hillclimb/logs/top.log" 2>&1 &
HC_PID=$!
printf '%s\n' "$HC_PID" > "$EXP/hillclimb/pids/top.pid"
setsid "$EXP/tools/launch_arm.sh" "$EXP/hyperagents" "$HA_WS" "$FRAMEWORK" "$SEED" "$PROJECT" > "$EXP/hyperagents/logs/top.log" 2>&1 &
HA_PID=$!
printf '%s\n' "$HA_PID" > "$EXP/hyperagents/pids/top.pid"
printf 'hillclimb_pid=%s\nhyperagents_pid=%s\n' "$HC_PID" "$HA_PID"
```

Expected: two different PIDs are printed and both commands return immediately.

- [ ] **Step 4: Verify immediate liveness and six-worker configuration**

```bash
ps -o pid,pgid,stat,etime,command -p "$(cat "$EXP/hillclimb/pids/top.pid")" -p "$(cat "$EXP/hyperagents/pids/top.pid")"
grep -E '^(EVOLVE_HARBOR_N_CONCURRENT|EVOLVE_HARBOR_ATTEMPTS|EVOLVE_HARBOR_EXPECTED_TRIALS)=' "$HC_WS/evaluator/eval.env"
grep -E '^(EVOLVE_HARBOR_N_CONCURRENT|EVOLVE_HARBOR_ATTEMPTS|EVOLVE_HARBOR_EXPECTED_TRIALS)=' "$HA_WS/evaluator/eval.env"
```

Expected per arm: concurrency 3, attempts 1, expected trials 3. Do not inspect process command lines after credentials could have been added as arguments; the launch design keeps credentials in the environment only.

---

### Task 5: Monitor Training Through Generation 3

**Files:**
- Read remotely: per-arm `archive.jsonl`, `runs/`, top logs, and Harbor jobs
- Create remotely: `$EXP/monitoring.log`

**Interfaces:**
- Consumes: two live process groups and their structured framework artifacts.
- Produces: bounded liveness evidence and terminal status for every attempted generation.

- [ ] **Step 1: Poll structured progress at intervals no longer than five minutes**

Use the framework status command for each arm, appending only safe summaries:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ >> "$EXP/monitoring.log"
EVOLVE_HOME="$EXP/hillclimb/evolve-home" "$HC_WS/evolve" status "$HC_WS" >> "$EXP/monitoring.log" 2>&1
EVOLVE_HOME="$EXP/hyperagents/evolve-home" "$HA_WS/evolve" status "$HA_WS" >> "$EXP/monitoring.log" 2>&1
```

Expected: generation state advances or a live meta-agent/Harbor job remains attributable. Do not dump full environments or process arguments.

- [ ] **Step 2: Check first materialization evidence once generation-0 jobs appear**

Inspect collected `evolve-runtime.json` files and sanitized Harbor results. Require these flags where the schema provides them:

```text
frozen_sync=true
direct_virtualenv_python=true
plain_uv_run=false
model_proxy_vars_present=false
miniswe_import=true
litellm_model_init=true
```

Expected: no `missing_lock`, `stale_lock`, `materialization_failed`, missing FastAPI, or LiteLLM build failure. Report categories and booleans only; do not copy raw environments.

- [ ] **Step 3: Apply arm-local and shared stop rules**

Continue the other arm after an arm-local invalid proposal or candidate failure. Stop both process groups only when structured evidence shows a shared infrastructure failure: bad runtime identity, Docker/Harbor failure, corrupted shared cache behavior, credential failure affecting both arms, lost process ownership, or model proxy contamination.

To stop a confirmed failed arm, signal only that arm's recorded process group.
Use exactly one of these commands, matching the affected arm:

```bash
kill -- -"$(cat "$EXP/hillclimb/pids/top.pid")"
kill -- -"$(cat "$EXP/hyperagents/pids/top.pid")"
```

Never run both stop commands unless the shared stop rule is satisfied. Never use
broad `pkill`, container-wide cleanup, or commands affecting unrelated jobs.

- [ ] **Step 4: Require terminal evidence after both top-level processes exit**

```bash
EVOLVE_HOME="$EXP/hillclimb/evolve-home" "$HC_WS/evolve" verify "$HC_WS"
EVOLVE_HOME="$EXP/hyperagents/evolve-home" "$HA_WS/evolve" verify "$HA_WS"
EVOLVE_HOME="$EXP/hillclimb/evolve-home" "$HC_WS/evolve" status "$HC_WS"
EVOLVE_HOME="$EXP/hyperagents/evolve-home" "$HA_WS/evolve" status "$HA_WS"
```

Expected: archive integrity passes and each attempted generation has a terminal framework status. A failed generation remains evidence; do not rewrite it.

---

### Task 6: Select and Export the Newest Runnable Non-Seed Candidate

**Files:**
- Create locally then transfer: `/tmp/evolve-parallel-micro/select_candidate.py`
- Create remotely: per-arm `selected-generation.txt`, `selected-candidate/`, and `candidate-provenance.json`

**Interfaces:**
- Consumes: merged archive rows, evaluation artifacts, tags, and candidate trees.
- Produces: one exact generated candidate per successful arm, choosing 3 then 2 then 1 without consulting score rank or `valid_parent`.

- [ ] **Step 1: Create the selection helper locally**

Create `/tmp/evolve-parallel-micro/select_candidate.py` with `apply_patch`:

```python
#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

from evolve.archive import rows_by_genid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    rows = rows_by_genid(workspace)
    for genid in ("3", "2", "1"):
        row = rows.get(genid, {})
        reference = row.get("evaluation_artifacts")
        artifact_ok = isinstance(reference, dict) and isinstance(reference.get("path"), str)
        if artifact_ok:
            artifact_ok = (workspace / reference["path"]).is_file()
        tag_ok = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--verify", "--quiet", "refs/tags/gen/" + genid],
            check=False,
            stdout=subprocess.DEVNULL,
        ).returncode == 0
        if (
            row.get("status") == "complete"
            and row.get("outcome") == "benchmark_complete"
            and row.get("surface_violations") == []
            and artifact_ok
            and tag_ok
        ):
            print(genid)
            return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
```

Expected: the helper never selects generation 0 and never checks best score or gate admission.

- [ ] **Step 2: Transfer the helper and select independently for each arm**

```bash
EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-parallel-micro-20260713
scp /tmp/evolve-parallel-micro/select_candidate.py DevBoxS:"$EXP/tools/select_candidate.py"
HC_GEN=$(uv run --project "$FRAMEWORK" --frozen python "$EXP/tools/select_candidate.py" "$HC_WS")
HA_GEN=$(uv run --project "$FRAMEWORK" --frozen python "$EXP/tools/select_candidate.py" "$HA_WS")
printf '%s\n' "$HC_GEN" > "$EXP/hillclimb/selected-generation.txt"
printf '%s\n' "$HA_GEN" > "$EXP/hyperagents/selected-generation.txt"
```

Expected: each value is `1`, `2`, or `3`. If an arm returns exit 2, mark that arm unsuccessful and skip only its held-out evaluation.

- [ ] **Step 3: Export exact tagged candidates as detached worktrees**

```bash
git -C "$HC_WS" worktree add --detach "$EXP/hillclimb/selected-candidate" "gen/$HC_GEN"
git -C "$HA_WS" worktree add --detach "$EXP/hyperagents/selected-candidate" "gen/$HA_GEN"
```

Expected: both exports are clean and contain `target/pyproject.toml`, `target/uv.lock`, and the candidate source.

- [ ] **Step 4: Record candidate provenance without credentials or held-out names**

Record for each arm: original workspace, original generation, tag commit, target tree hash, `pyproject.toml` SHA-256, `uv.lock` SHA-256, training task hash, and framework training commit. Store these fields in `candidate-provenance.json` under each arm.

Expected: the target tree hashes differ from or are explicitly compared with generation 0; generation 0 is never the selected identity.

---

### Task 7: Build Separate Held-Out Evaluation Workspaces

**Files:**
- Create remotely: `$EXP/framework-test`
- Modify only in that checkout: `recipes/hill_climb/evolve.yaml`
- Create only in that checkout: `recipes/hill_climb/evaluator/tasks/test-3.txt`
- Create remotely: per-arm `test-workspace`

**Interfaces:**
- Consumes: sealed test file after training has ended and exported candidate targets.
- Produces: two evaluation-only workspaces that cannot feed another proposal.

- [ ] **Step 1: Clone a separate test framework from the unmodified bundle**

```bash
git clone --branch codex/framework-hardening "$PROJECT/incoming/framework-hardening-parallel-micro.bundle" "$EXP/framework-test"
git -C "$EXP/framework-test" rev-parse HEAD
```

Expected: the base commit matches `/tmp/framework-hardening-parallel-micro.commit`
from Task 1 when checked from the local controller.

- [ ] **Step 2: Configure the test-only hill-climb recipe after training is terminal**

```bash
uv run --project "$EXP/framework-test" --frozen python "$EXP/tools/configure_recipe.py" --framework "$EXP/framework-test" --recipe hill_climb --experiment-id heldout-eval-20260713 --task-source "$EXP/sealed/test-3.txt" --task-name test-3.txt
git -C "$EXP/framework-test" add recipes/hill_climb/evolve.yaml recipes/hill_climb/evaluator/tasks/test-3.txt
git -C "$EXP/framework-test" commit -m "experiment: configure held-out three-task evaluation"
git -C "$EXP/framework-test" rev-parse HEAD > "$EXP/framework-test-commit.txt"
```

Expected: the held-out task file enters only the evaluation-only framework after both training loops are over.

- [ ] **Step 3: Initialize one evaluation-only workspace per selected target**

```bash
HC_TEST_WS=$EXP/hillclimb/hillclimb-test-workspace
HA_TEST_WS=$EXP/hyperagents/hyperagents-test-workspace
mkdir -p "$EXP/hillclimb/test-evolve-home" "$EXP/hyperagents/test-evolve-home"
EVOLVE_HOME="$EXP/hillclimb/test-evolve-home" uv run --project "$EXP/framework-test" --frozen evolve init "$HC_TEST_WS" --recipe hill_climb --seed "$EXP/hillclimb/selected-candidate/target"
EVOLVE_HOME="$EXP/hyperagents/test-evolve-home" uv run --project "$EXP/framework-test" --frozen evolve init "$HA_TEST_WS" --recipe hill_climb --seed "$EXP/hyperagents/selected-candidate/target"
```

Expected: each evaluation workspace has its candidate as `gen/0`; this local evaluation generation is mapped back to the original generated identity in `candidate-provenance.json`.

- [ ] **Step 4: Attach both test workspaces to the same canonical cache and verify configuration**

```bash
mkdir -p "$HC_TEST_WS/runs/runtime" "$HA_TEST_WS/runs/runtime"
ln -s "$EXP/runtime/uv-cache" "$HC_TEST_WS/runs/runtime/uv-cache"
ln -s "$EXP/runtime/uv-cache" "$HA_TEST_WS/runs/runtime/uv-cache"
```

Run the same configuration assertions from Task 3, changing the expected task file to `evaluator/tasks/test-3.txt`. Print only test count, hash equality between arms, and safe booleans.

Expected: three held-out tasks, three workers, `k=1`, identical test hash, and clean Git state.

---

### Task 8: Run Both Held-Out Evaluations Concurrently

**Files:**
- Create locally then transfer: `/tmp/evolve-parallel-micro/run_eval.sh`
- Create remotely: per-arm `test.log`, `test.pid`, and held-out evaluation artifacts

**Interfaces:**
- Consumes: two evaluation-only workspaces and the same proxy/credential boundary as training.
- Produces: three held-out trials for each runnable generated candidate, with no later meta-agent call.

- [ ] **Step 1: Create the held-out evaluation wrapper locally**

Create `/tmp/evolve-parallel-micro/run_eval.sh` with `apply_patch`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ARM_ROOT=$1
WORKSPACE=$2
FRAMEWORK=$3
PROJECT=$4

set -a
. "$PROJECT/.env"
set +a
. "$PROJECT/env/cache-proxy.sh"
install_proxy=${HTTPS_PROXY:-${HTTP_PROXY:-${https_proxy:-${http_proxy:-}}}}
install_no_proxy=${NO_PROXY:-${no_proxy:-}}
test -n "$install_proxy"
export EVOLVE_INSTALL_HTTP_PROXY=$install_proxy
export EVOLVE_INSTALL_NO_PROXY=$install_no_proxy
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export EVOLVE_HOME="$ARM_ROOT/test-evolve-home"
exec "$WORKSPACE/evolve" eval "$WORKSPACE" 0 --force
```

Expected: no meta-agent command is invoked and no test evidence can influence training.

- [ ] **Step 2: Transfer and launch both held-out evaluations**

```bash
EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-parallel-micro-20260713
scp /tmp/evolve-parallel-micro/run_eval.sh DevBoxS:"$EXP/tools/run_eval.sh"
ssh DevBoxS "chmod 700 '$EXP/tools/run_eval.sh'"
```

On DevBoxS:

```bash
setsid "$EXP/tools/run_eval.sh" "$EXP/hillclimb" "$HC_TEST_WS" "$EXP/framework-test" "$PROJECT" > "$EXP/hillclimb/test.log" 2>&1 &
printf '%s\n' "$!" > "$EXP/hillclimb/test.pid"
setsid "$EXP/tools/run_eval.sh" "$EXP/hyperagents" "$HA_TEST_WS" "$EXP/framework-test" "$PROJECT" > "$EXP/hyperagents/test.log" 2>&1 &
printf '%s\n' "$!" > "$EXP/hyperagents/test.pid"
```

Expected: both test evaluators run concurrently with three workers each.

- [ ] **Step 3: Verify terminal held-out evidence**

After both PIDs exit:

```bash
EVOLVE_HOME="$EXP/hillclimb/test-evolve-home" "$HC_TEST_WS/evolve" verify "$HC_TEST_WS"
EVOLVE_HOME="$EXP/hyperagents/test-evolve-home" "$HA_TEST_WS/evolve" verify "$HA_TEST_WS"
```

Expected: each successful arm has exactly three held-out trial artifacts and a complete or explicitly classified terminal evaluation. No generation 1 exists in either test workspace.

---

### Task 9: Analyze Runtime Reproducibility and HyperAgents Repetition

**Files:**
- Read remotely: training/test archives, meta-agent prompts/outputs/patches, validation records, runtime evidence, and sanitized Harbor results
- Create remotely: `$EXP/report.md`
- Create remotely: `$EXP/summary.json`
- Create remotely: `$EXP/safe-scan.json`

**Interfaces:**
- Consumes: all structured terminal artifacts from Tasks 5 and 8.
- Produces: a concise causal report covering dependency behavior, cross-arm outcomes, parent selection, patch relationships, and held-out results.

- [ ] **Step 1: Build the per-generation comparison table**

For each arm and generations 0 through 3, record:

```text
generation
selected parent
terminal status and outcome
score
changed paths
normalized patch SHA-256
stable git patch-id
exact duplicate of earlier generation (boolean)
same selected-parent content already contained the change (boolean)
candidate runtime fingerprint
lock fingerprint
cache hit/miss and materialization duration
optional smoke attempts
```

Expected: every value links to a retained artifact path; missing evidence is reported as missing rather than inferred.

- [ ] **Step 2: Classify HyperAgents repetition causally**

Use these mutually understandable labels:

- `selection_driven_seed_repeat`: the selector chose generation 0 again and the proposal resembles an earlier child.
- `parent_already_contains_change`: a descendant reapplied behavior already present in its selected parent.
- `history_or_source_inspection_failure`: relevant prior artifacts/current code existed but the proposal ignored them.
- `workflow_activation_failure`: a selected parent's meta-agent workflow edit did not appear in or influence the later descendant.
- `runtime_feedback_unusable`: the available evidence was dominated by dependency/setup failure.
- `distinct_evidence_backed_proposal`: a valid behavioral change used a distinct hypothesis or new evidence, whether or not score improved.

Expected: cite parent IDs, patch hashes, changed paths, and prompt/artifact references. Do not describe a patch as meaningless only because its score failed to improve.

- [ ] **Step 3: Verify dependency/runtime success criteria**

Across all retained training and test trials, require and report:

```text
lock/project check passed
frozen synchronization passed
MiniSWE import passed
configured LiteLLM model initialization passed
direct virtualenv Python used
plain unresolved uv run absent
missing FastAPI absent
LiteLLM build failure absent
model proxy variables absent
explicit model configuration present
cache reused after the first materialization
```

Expected: any failure is attributed using the structured candidate/infrastructure outcome, not arbitrary traceback parsing.

- [ ] **Step 4: Perform a value-safe credential and proxy leak scan**

Load `.env` and `cache-proxy.sh` only inside a script, collect non-empty sensitive values, scan experiment text artifacts, and write only this schema:

```json
{
  "credential_value_found": false,
  "proxy_value_found": false,
  "files_scanned": 0
}
```

The script must never print matching values or matching lines. If either boolean is true, stop report publication, restrict the artifact permissions, and report only the boolean and affected file path.

- [ ] **Step 5: Write the final experiment report**

`report.md` must lead with:

1. whether both arms reproduced the locked runtime;
2. whether the historical missing-FastAPI/LiteLLM/setup-timeout symptoms recurred;
3. which generated candidates were selected for held-out evaluation;
4. the parent sequence and repetition classification for HyperAgents;
5. training and held-out scores with the three-task limitation stated clearly;
6. total wall time and reported model cost;
7. exact experiment paths and framework identities;
8. safe leak-scan booleans.

Expected: no API key, proxy value, `.env` content, or held-out task name appears in the report.

---

### Task 10: Final Verification and Handoff

**Files:**
- Read: all experiment deliverables and local Git status
- Do not modify or push the local branch

**Interfaces:**
- Consumes: completed report, summary, safe scan, archive verification, and process terminal states.
- Produces: an evidence-backed user handoff with no unrequested integration action.

- [ ] **Step 1: Confirm no experiment process remains unintentionally live**

Check only the four recorded PID files. A completed PID may no longer exist; an unexpectedly live process must be explained before handoff.

Expected: both training processes and both held-out evaluators are terminal, or any deliberately retained live process is clearly reported.

- [ ] **Step 2: Confirm experiment completeness**

Require:

- two verified training archives;
- generations 0 through 3 attempted in each arm;
- selected non-seed generation recorded for each successful arm;
- three held-out trials per successful arm;
- `report.md`, `summary.json`, and `safe-scan.json` present;
- framework base and derived commit IDs recorded;
- training and test task hashes recorded;
- shared cache reuse evidence recorded.

Expected: missing items are named explicitly and prevent a “complete” claim.

- [ ] **Step 3: Recheck the local worktree**

```bash
git status --short --branch
git log -3 --oneline
```

Expected: no experiment implementation changes were made locally beyond this committed plan; the two unrelated `.superpowers/sdd/` modifications remain untouched. No push occurred.

- [ ] **Step 4: Hand off results**

Report the experiment root, both workspace/job/log paths, selected candidate IDs, dependency outcome, HyperAgents repetition diagnosis, held-out scores, cost, wall time, and any limitation. Link local design and plan files. Do not imply statistical significance from three tasks.
