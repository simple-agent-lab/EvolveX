# AHE and HyperAgents tau3/Terminal-Bench 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add minimal, tested scripts that prepare and run four train-only AHE/HyperAgents workspaces, verify them on DevBox and DevBoxS, complete a five-task/three-generation tau3 smoke run, and document the effective configurations in Lark.

**Architecture:** Two parameterized shell scripts own workspace preparation and execution. The setup script initializes from the current recipe, installs a frozen task manifest, and patches only workspace configuration; the run script validates and launches an existing workspace. Framework source, recipe source, and dataset manifests remain unchanged.

**Tech Stack:** Bash, embedded Python 3.12 with PyYAML, pytest, Git, Harbor, Docker Compose, `evolve`, Lark Docx tables.

## Global Constraints

- DevBox hosts AHE × tau3 and AHE × Terminal-Bench 2.
- DevBoxS hosts HyperAgents × tau3 and HyperAgents × Terminal-Bench 2.
- Evolution evaluates only the frozen `train` list; dataset `gate` tasks are unused.
- Final anchors evaluate only the frozen `sealed` list.
- tau3 uses 100 train, 100 unused gate, and 175 sealed tasks with seed 42.
- Terminal-Bench 2 uses 50 train, 19 unused gate, and 20 sealed tasks with seed 0.
- `experiment.budget_usd` must be absent.
- tau3 simulator values are `TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05`, `TAU2_USER_REASONING_EFFORT=low`, and `TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05`.
- The benchmark agent uses `openai/gpt-5.4-2026-03-05` with high reasoning.
- The Codex meta-agent uses GPT-5.4 with xhigh reasoning.
- Production runs use 10 generations, one child per generation, concurrency 25, setup multiplier 1, agent multiplier 2, one retry, and final-only anchors.
- No framework source, recipe source, or dataset manifest is modified.

---

### Task 1: Workspace setup script

**Files:**
- Create: `scripts/setup_benchmark_experiment.sh`
- Create: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: positional arguments `METHOD`, `BENCHMARK`, and `WORKSPACE_NAME`; optional `N_CONCURRENT`; environment paths `EVOLVE_EXPERIMENT_ROOT`, `EVOLVE_FRAMEWORK`, `TAU3_DATASET`, `TAU3_MANIFEST`, `TB2_DATASET`, and `TB2_MANIFEST`.
- Produces: a verified workspace at `$EVOLVE_EXPERIMENT_ROOT/workspaces/$WORKSPACE_NAME`.

- [ ] **Step 1: Write failing subprocess tests for validation and dry-run resolution**

Add tests that execute the real script with `--dry-run` and literal fixture
paths. Assert that:

```python
assert tau3["tasks_per_round"] == "100"
assert tau3["train_count"] == "100"
assert tau3["gate_count"] == "100"
assert tau3["sealed_count"] == "175"
assert tau3["simulator_model"] == "openai/gpt-5.4-2026-03-05"
assert tau3["simulator_effort"] == "low"
assert tb2["tasks_per_round"] == "50"
assert tb2["train_count"] == "50"
assert invalid.returncode == 2
```

The production change these tests catch is selecting the wrong benchmark
branch, count, model, or argument validation path.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: FAIL because `scripts/setup_benchmark_experiment.sh` does not exist.

- [ ] **Step 3: Implement argument/path resolution and dry-run behavior**

Create a Bash script with:

```text
usage: setup_benchmark_experiment.sh {ahe|hyperagents} \
       {tau3|terminal-bench-2} WORKSPACE_NAME [N_CONCURRENT] [--dry-run]
```

Resolve tau3 to 100/100/175 with seed 42 and Terminal-Bench 2 to 50/19/20
with seed 0. Print machine-readable `key=value` lines in dry-run mode without
creating files.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: all setup-script tests PASS.

- [ ] **Step 5: Add a failing integration test for rendered workspace behavior**

Use a temporary fake `evolve` executable that creates a minimal workspace from
fixture YAML and task manifests. Invoke the real setup script and assert on the
resulting parsed YAML and environment:

```python
assert "budget_usd" not in config["experiment"]
assert config["evaluator"]["evaluation_split"] == "train"
assert config["evaluator"]["sampling"] == "static"
assert config["evaluator"]["n_concurrent"] == 25
assert config["evaluator"]["agent_setup_timeout_multiplier"] == 1
assert config["evaluator"]["agent_timeout_multiplier"] == 2
assert config["evaluator"]["max_retries"] == 1
assert config["evaluator"]["anchor"] == {"final": True, "every_rounds": 0}
assert env["TAU2_USER_MODEL"] == "openai/gpt-5.4-2026-03-05"
assert env["TAU2_USER_REASONING_EFFORT"] == "low"
assert env["TAU2_NL_ASSERTIONS_MODEL"] == "openai/gpt-5.4-2026-03-05"
```

Also assert that tau3 train/gate/sealed lists remain exactly 100/100/175, the
evolution task file contains only the 100 train names, and the anchor task file
contains only the 175 sealed names.

- [ ] **Step 6: Run the integration test and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: FAIL because setup does not yet create and patch the workspace.

- [ ] **Step 7: Implement workspace initialization and patching**

The script must:

1. validate manifest counts, uniqueness, and membership in the dataset;
2. refuse to overwrite an existing workspace;
3. call the current framework's `evolve init` with the selected recipe;
4. copy the frozen manifest to `evaluator/splits.json`;
5. write `evaluator/tasks/train.txt` and `evaluator/tasks/sealed.txt`;
6. patch only the generated workspace YAML and evaluator environment;
7. remove `experiment.budget_usd` with `pop("budget_usd", None)`;
8. configure the Codex meta-agent and shared timeouts;
9. add tau3 simulator variables only for tau3;
10. preserve the selected recipe's operator variants; and
11. run `evolve verify` before reporting the workspace prepared.

- [ ] **Step 8: Run focused and relevant repository tests**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py tests/test_phase_e_recipes.py tests/test_m8_dataset_splits.py -q
```

Expected: all tests PASS.

- [ ] **Step 9: Commit the setup script**

```bash
git add scripts/setup_benchmark_experiment.sh tests/test_experiment_setup_scripts.py
git commit -m "feat: prepare benchmark experiment workspaces"
```

### Task 2: Workspace run script

**Files:**
- Create: `scripts/run_benchmark_experiment.sh`
- Modify: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: `WORKSPACE_NAME`, optional `MAX_GENERATIONS`, optional `--dry-run`, and the same experiment/framework root variables as the setup script.
- Produces: verification followed by `evolve run WORKSPACE --max-generations N`.

- [ ] **Step 1: Write failing subprocess tests**

Assert that dry-run resolves the exact workspace, framework executable, and
generation count; invalid names and zero generations return exit status 2; and
a missing workspace fails before launching the runner.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: FAIL because `scripts/run_benchmark_experiment.sh` does not exist.

- [ ] **Step 3: Implement the run script**

The script must validate inputs, load `evolve.env`, `proxy.env` when present,
and `runtime.env`, export the framework Python path, execute `evolve verify`,
then replace itself with:

```bash
evolve run "$workspace" --max-generations "$max_generations"
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: all script tests PASS.

- [ ] **Step 5: Commit the run script**

```bash
git add scripts/run_benchmark_experiment.sh tests/test_experiment_setup_scripts.py
git commit -m "feat: run prepared benchmark experiments"
```

### Task 3: Deploy current framework and prepare production workspaces

**Files:**
- Deploy: `scripts/setup_benchmark_experiment.sh`
- Deploy: `scripts/run_benchmark_experiment.sh`
- Deploy without modification: tau3 and Terminal-Bench 2 manifests/datasets.

**Interfaces:**
- Consumes: local branch based on `origin/main` commit `e23a847f2358ac22246372bff94a163903d71c7b`.
- Produces: a current framework installation and two verified production workspaces on each assigned host.

- [ ] **Step 1: Package the exact framework source state**

Build a Git bundle or archive from the committed branch, transfer it to both
hosts, and create a new versioned framework directory. Do not replace or mutate
the historical framework copies.

- [ ] **Step 2: Install the locked framework environment**

On each host, run the repository's locked `uv sync --frozen` workflow and
verify:

```bash
<framework>/.venv/bin/evolve --help
<framework>/.venv/bin/python -m pytest --version
```

- [ ] **Step 3: Transfer and validate immutable dataset artifacts**

Ensure both hosts have the 375 generated tau3 tasks, the 89 Terminal-Bench 2
tasks, and their frozen manifests. Compare counts and task-name membership
without rewriting either manifest.

- [ ] **Step 4: Prepare the four workspaces**

Run:

```bash
# DevBox
setup_benchmark_experiment.sh ahe tau3 ahe-tau3 25
setup_benchmark_experiment.sh ahe terminal-bench-2 ahe-terminal-bench-2 25

# DevBoxS
setup_benchmark_experiment.sh hyperagents tau3 hyperagents-tau3 25
setup_benchmark_experiment.sh hyperagents terminal-bench-2 hyperagents-terminal-bench-2 25
```

- [ ] **Step 5: Audit effective configuration**

Parse each generated `evolve.yaml`, `evaluator/eval.env`,
`evaluator/tasks/train.txt`, and `evaluator/tasks/sealed.txt`. Assert the global
constraints, exact host mapping, and absence of `experiment.budget_usd`.

### Task 4: Run and audit the tau3 smoke experiment

**Files:**
- Create remotely: DevBox workspace `ahe-tau3-smoke-5x3`.

**Interfaces:**
- Consumes: DevBox's prepared AHE × tau3 configuration and the first five
frozen tau3 train task names.
- Produces: three completed evolution generations with five Harbor trials per
canonical evaluation and no anchor run.

- [ ] **Step 1: Prepare the isolated smoke workspace**

Use the setup script with smoke overrides `tasks_per_round=5`,
`max_generations=3`, and `anchor.final=false`. Copy exactly the first five
names from the frozen train list; do not sample from gate or sealed.

- [ ] **Step 2: Verify before launch**

Run `evolve verify`, parse the five-name task file, and confirm the names are a
subset of `tasks.train` with empty intersection against gate and sealed.

- [ ] **Step 3: Launch and monitor the smoke run**

Run:

```bash
run_benchmark_experiment.sh ahe-tau3-smoke-5x3 3
```

Monitor until the process exits; report intermediate status at least every
60 seconds while active.

- [ ] **Step 4: Audit smoke artifacts**

Require generation records through generation 3, complete Harbor result
artifacts for five selected tasks per canonical evaluation, no anchor
evaluation, and no gate/sealed task identifiers in evaluator or meta-agent
feedback artifacts.

### Task 5: Append effective experiment columns to Lark

**Files:**
- Modify in place: Lark Docx `DJnmdL1B3oywtbxNSuzcUfXOnGe`.

**Interfaces:**
- Consumes: audited effective values from the four production workspaces.
- Produces: four appended columns in every applicable existing parameter table.

- [ ] **Step 1: Refetch the latest document revision and table block IDs**

Fetch the document in full and identify each existing parameter table. Preserve
all current rows and columns.

- [ ] **Step 2: Append four columns**

Append, in order:

1. AHE × tau3
2. AHE × Terminal-Bench 2
3. HyperAgents × tau3
4. HyperAgents × Terminal-Bench 2

Populate values from the audited workspace configs, not from intended defaults.
For `experiment.budget_usd`, record `omitted`. For tau3 simulator rows, record
the pinned model and low effort; mark those rows not applicable for
Terminal-Bench 2.

- [ ] **Step 3: Refetch and verify**

Refetch the edited document and confirm every applicable table has all four
headers, unchanged pre-existing cells, and values matching the remote
workspaces.

### Task 6: Final verification and handoff

**Files:**
- No new files.

**Interfaces:**
- Consumes: local tests, remote workspaces, smoke artifacts, and refetched Lark
document.
- Produces: evidence-backed handoff with exact paths and launch commands.

- [ ] **Step 1: Run the full local test suite**

Run:

```bash
uv run pytest -q
```

Expected: zero failures.

- [ ] **Step 2: Run shell syntax checks**

Run:

```bash
bash -n scripts/setup_benchmark_experiment.sh
bash -n scripts/run_benchmark_experiment.sh
```

Expected: both exit 0.

- [ ] **Step 3: Re-audit all remote workspaces**

Run each workspace's `evolve verify`, compare frozen task-file digests, confirm
the host mapping, and confirm no production experiment has started.

- [ ] **Step 4: Review repository changes**

Run:

```bash
git status --short
git diff --check
git log --oneline origin/main..HEAD
```

Confirm only the design, plan, new scripts, and focused tests are committed;
preserve unrelated untracked user artifacts.

- [ ] **Step 5: Report handoff**

Provide the four workspace paths, smoke result path and status, exact launch
commands, Lark document link, test counts, and any remaining operational
requirements.
