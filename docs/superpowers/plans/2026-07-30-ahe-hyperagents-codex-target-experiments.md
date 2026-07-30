# AHE and HyperAgents Codex-Target Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the tested AHE/HyperAgents benchmark tooling with a frozen Codex-subscription target profile, run four isolated three-task/two-generation smokes, and prepare four verified but unlaunched production workspaces.

**Architecture:** Reuse the parameterized benchmark scripts from `codex/tau3-tb2-experiment-impl`, keeping recipe, target, and benchmark selection independent. The protected evaluator enforces Codex model/auth/reasoning controls, while tracked manifests and audit tools enforce task isolation, smoke completeness, and coexistence with active MiniSWE runs.

**Tech Stack:** Bash, Python 3.12, PyYAML, pytest, Git, Harbor, Docker Compose, `evolve`, SSH, and the existing DevBox/DevBoxS runtime environment.

## Global Constraints

- Do not modify, stop, restart, archive, or clean up any of the four active MiniSWE-target experiments.
- Do not overwrite an existing local or remote workspace.
- AHE keeps `surface.include: [target/**]`; HyperAgents keeps `surface.include: [target/**, operators/**]`.
- The Codex target seed is `builtin-codex`; the evaluator agent is `target.agent:HarborAgent`.
- Codex benchmark and meta-agents use the host subscription, `/home/zimuwang/.codex/auth.json`, the machine proxy, and model `gpt-5.4`.
- The protected evaluator enforces `reasoning_effort=high` for every Codex benchmark-agent evaluation.
- Codex meta-agents use model `gpt-5.4` with `reasoning_effort=xhigh`.
- Do not persist auth content, proxy values, API keys, or base URLs in Git, generated configuration, diagnostics, or audit reports.
- tau3 simulator values are `TAU2_USER_MODEL=openai/gpt-5.4-2026-03-05`, `TAU2_USER_REASONING_EFFORT=low`, and `TAU2_NL_ASSERTIONS_MODEL=openai/gpt-5.4-2026-03-05`.
- Production uses ten configured generations, one child, concurrency 25, one retry, setup multiplier 1, agent multiplier 2, and a final-only sealed anchor.
- Smoke uses exactly three tasks, two mutation generations, concurrency 3, no anchor, and one smoke process at a time across both hosts.
- tau3 smoke tasks are `tau3-airline-3`, `tau3-banking_knowledge-task-012`, and `tau3-retail-1`.
- Terminal-Bench 2 smoke tasks are `build-cython-ext`, `fix-git`, and `regex-log`.
- Prepare all four production workspaces after successful smoke audits, but do not launch them.

---

### Task 1: Import the tested generic benchmark tooling

**Files:**
- Create from existing branch: `scripts/setup_benchmark_experiment.sh`
- Create from existing branch: `scripts/run_benchmark_experiment.sh`
- Create from existing branch: `scripts/configure_benchmark_smoke.sh`
- Create from existing branch: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: committed files on `codex/tau3-tb2-experiment-impl`.
- Produces: the tested MiniSWE benchmark setup/run/smoke baseline that later tasks extend.

- [ ] **Step 1: Confirm the four destination paths are not tracked or present**

Run:

```bash
git status --short -- \
  scripts/setup_benchmark_experiment.sh \
  scripts/run_benchmark_experiment.sh \
  scripts/configure_benchmark_smoke.sh \
  tests/test_experiment_setup_scripts.py
```

Expected: no output. If any path appears, stop and inspect it instead of overwriting it.

- [ ] **Step 2: Restore the tested files from the implementation branch**

Run:

```bash
git restore --source=codex/tau3-tb2-experiment-impl -- \
  scripts/setup_benchmark_experiment.sh \
  scripts/run_benchmark_experiment.sh \
  scripts/configure_benchmark_smoke.sh \
  tests/test_experiment_setup_scripts.py
```

- [ ] **Step 3: Run the imported focused tests**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: all imported tests pass before Codex-target changes begin.

- [ ] **Step 4: Commit the imported baseline**

Run:

```bash
git add \
  scripts/setup_benchmark_experiment.sh \
  scripts/run_benchmark_experiment.sh \
  scripts/configure_benchmark_smoke.sh \
  tests/test_experiment_setup_scripts.py
git commit -m "feat: add parameterized benchmark experiment tooling"
```

### Task 2: Add frozen Harbor agent kwargs and subscription isolation

**Files:**
- Modify: `scaffolds/evaluators/harbor/engine.sh:145-247`
- Modify: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: optional protected workspace file `evaluator/agent.kwargs`, one `key=value` per line; optional protected `EVOLVE_HARBOR_CODEX_SUBSCRIPTION=1` in `evaluator/eval.env`.
- Produces: repeated Harbor `--agent-kwarg key=value` arguments and subscription-backed Codex execution that does not receive ambient `OPENAI_API_KEY`, `OPENAI_BASE_URL`, or `OPENAI_API_BASE`.

- [ ] **Step 1: Write a failing evaluator forwarding test**

Add this test beside the existing proxy-forwarding tests:

```python
def test_harbor_evaluator_forwards_protected_agent_kwargs() -> None:
    text = _eval_sh("harbor", "fixture")

    assert "if [ -f evaluator/agent.kwargs ]; then" in text
    assert 'set -- "$@" --agent-kwarg "$agent_kwarg"' in text
```

- [ ] **Step 2: Write a failing subscription-isolation integration test**

Create an evaluator fixture using the existing fake `uv` and fake `harbor`
helpers. Write:

```python
(evaluator / "agent.kwargs").write_text("reasoning_effort=high\n")
```

Set:

```python
env.update(
    {
        "EVOLVE_HARBOR_CODEX_SUBSCRIPTION": "1",
        "CODEX_FORCE_AUTH_JSON": "1",
        "OPENAI_API_KEY": "not-for-codex",
        "OPENAI_BASE_URL": "http://model-bridge.invalid/v1",
        "HTTP_PROXY": "http://proxy.invalid:8118",
        "HTTPS_PROXY": "http://proxy.invalid:8118",
    }
)
```

After the fake evaluator runs, assert:

```python
assert args[args.index("--agent-kwarg") + 1] == "reasoning_effort=high"
agent_environment = [
    args[index + 1]
    for index, value in enumerate(args)
    if value == "--ae"
]
assert "OPENAI_API_KEY=not-for-codex" not in agent_environment
assert "OPENAI_BASE_URL=http://model-bridge.invalid/v1" not in agent_environment
assert "CODEX_FORCE_AUTH_JSON=1" in agent_environment
assert "HTTP_PROXY=http://proxy.invalid:8118" in agent_environment
assert "HTTPS_PROXY=http://proxy.invalid:8118" in agent_environment
```

- [ ] **Step 3: Run both tests and verify RED**

Run:

```bash
uv run pytest \
  tests/test_harbor_evaluator_template.py::test_harbor_evaluator_forwards_protected_agent_kwargs \
  tests/test_harbor_evaluator_template.py::test_harbor_evaluator_isolates_codex_subscription_from_ambient_api_credentials \
  -q
```

Expected: both tests fail because `engine.sh` does not read agent kwargs or isolate Codex credentials.

- [ ] **Step 4: Implement protected agent-kwarg forwarding**

Insert after environment kwargs are read:

```sh
if [ -f evaluator/agent.kwargs ]; then
  while IFS= read -r agent_kwarg || [ -n "$agent_kwarg" ]; do
    [ -n "$agent_kwarg" ] && set -- "$@" --agent-kwarg "$agent_kwarg"
  done < evaluator/agent.kwargs
fi
```

Replace unconditional credential forwarding with:

```sh
if [ "${EVOLVE_HARBOR_CODEX_SUBSCRIPTION:-0}" = "1" ]; then
  set -- "$@" --ae "CODEX_FORCE_AUTH_JSON=${CODEX_FORCE_AUTH_JSON:-1}"
else
  for credential_name in OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE; do
    eval "credential_value=\${$credential_name-}"
    if [ -n "$credential_value" ]; then
      set -- "$@" --ae "$credential_name=$credential_value"
    fi
  done
fi
```

Do not unset the ambient credentials in the Harbor process: tau3 Docker
Compose interpolation still needs the simulator endpoint. Only omit them from
the Codex agent's `--ae` values.

- [ ] **Step 5: Run the evaluator tests**

Run:

```bash
uv run pytest tests/test_harbor_evaluator_template.py -q
```

Expected: all evaluator-template tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add scaffolds/evaluators/harbor/engine.sh tests/test_harbor_evaluator_template.py
git commit -m "feat: freeze Harbor agent reasoning controls"
```

### Task 3: Add the Codex target profile to benchmark setup

**Files:**
- Modify: `scripts/setup_benchmark_experiment.sh`
- Modify: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: `METHOD TARGET BENCHMARK WORKSPACE_NAME [N_CONCURRENT] [--dry-run]`, where `TARGET` is `miniswe` or `codex`.
- Produces: a verified workspace whose recipe operators come from `METHOD`, target/evaluator contract comes from `TARGET`, and task/simulator configuration comes from `BENCHMARK`.

- [ ] **Step 1: Update dry-run tests to require a target axis**

Change calls such as:

```python
_run_setup("ahe", "tau3", "ahe-tau3", "25", "--dry-run")
```

to:

```python
_run_setup("ahe", "miniswe", "tau3", "ahe-tau3", "25", "--dry-run")
```

Add:

```python
def test_codex_dry_run_resolves_explicit_target_profile() -> None:
    values = _values(
        _run_setup(
            "hyperagents",
            "codex",
            "terminal-bench-2",
            "hyperagents-codex-terminal-bench-2",
            "25",
            "--dry-run",
        )
    )

    assert values["target"] == "codex"
    assert values["workspace"].endswith(
        "/workspaces/hyperagents-codex-terminal-bench-2"
    )
```

Also assert an unknown target returns exit code 2.

- [ ] **Step 2: Write failing rendered-workspace tests for both recipes**

Add `import pytest` to the test module. Parameterize the existing rendered
workspace fixture over `method` and expected mutable roots using:

```python
@pytest.mark.parametrize(
    ("method", "surface", "editable_roots"),
    [
        ("ahe", ["target/**"], ["target"]),
        (
            "hyperagents",
            ["target/**", "operators/**"],
            ["target", "operators"],
        ),
    ],
)
```

Inside `test_setup_renders_codex_target_contract`, use the existing
`_write_fake_evolve`, tau3 fixture, and `_run_setup` helpers to render
`f"{method}-codex-tau3"`. Parse `evolve.yaml`, `evaluator/eval.env`, and the
meta/evaluator mappings. Assert:

```python
assert config["target"] == {"seed": "builtin-codex"}
assert config["surface"]["include"] == surface
assert evaluator["agent"] == "target.agent:HarborAgent"
assert evaluator["model"] == "gpt-5.4"
assert "candidate_runtime" not in evaluator
assert evaluator["agent_env"] == {}
assert meta["prompt_path"] == "target/prompt.md"
assert meta["skills_dir"] == "target/skills"
assert meta["editable_roots"] == editable_roots
assert "memory_dir" not in meta
assert "tools_dir" not in meta
assert (workspace / "evaluator" / "agent.kwargs").read_text() == (
    "reasoning_effort=high\n"
)
assert eval_env["EVOLVE_HARBOR_CODEX_SUBSCRIPTION"] == "1"
assert eval_env["EVOLVE_HARBOR_MODEL"] == "gpt-5.4"
```

Assert AHE and HyperAgents retain their original `select`, `trace_analyzer`,
`validate`, `gate`, and `record` variants.

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: failures because setup has no target argument or Codex rendering branch.

- [ ] **Step 4: Add target argument validation and initialization**

Change the interface to:

```sh
usage: setup_benchmark_experiment.sh \
  {ahe|hyperagents} {miniswe|codex} \
  {tau3|terminal-bench-2} WORKSPACE_NAME [N_CONCURRENT] [--dry-run]
```

Parse and validate `target`. Print `target=<value>` during dry-run.

Build initialization arguments as:

```sh
init_args=(init "$workspace" --recipe "$method" --dataset "$dataset")
if [[ "$target" == "codex" ]]; then
  init_args+=(--seed builtin-codex)
elif [[ -n "${EVOLVE_TARGET_SEED:-}" ]]; then
  init_args+=(--seed "$EVOLVE_TARGET_SEED")
fi
```

Pass `EVOLVE_SETUP_TARGET="$target"` into the renderer.

- [ ] **Step 5: Implement the Codex renderer branch**

For `target == "codex"`:

```python
config["target"] = {"seed": "builtin-codex"}
meta["prompt_path"] = "target/prompt.md"
meta["skills_dir"] = "target/skills"
meta.pop("memory_dir", None)
meta.pop("tools_dir", None)

evaluator["agent"] = "target.agent:HarborAgent"
evaluator["model"] = "gpt-5.4"
evaluator.pop("candidate_runtime", None)
evaluator["agent_env"] = {}
```

Write:

```python
(evaluator_dir / "agent.kwargs").write_text("reasoning_effort=high\n")
eval_env["EVOLVE_HARBOR_CODEX_SUBSCRIPTION"] = "1"
eval_env["EVOLVE_HARBOR_MODEL"] = "gpt-5.4"
```

For `target == "miniswe"`, preserve the imported behavior and remove any
stale `agent.kwargs` or subscription flag.

- [ ] **Step 6: Run focused and recipe tests**

Run:

```bash
uv run pytest \
  tests/test_experiment_setup_scripts.py \
  tests/test_phase_e_recipes.py \
  tests/test_m7_codex_seed.py \
  tests/test_recipe_composition.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add scripts/setup_benchmark_experiment.sh tests/test_experiment_setup_scripts.py
git commit -m "feat: prepare Codex-target benchmark workspaces"
```

### Task 4: Make smoke task selection explicit and immutable

**Files:**
- Create: `experiments/codex-wrapper-smoke-tasks.json`
- Modify: `scripts/configure_benchmark_smoke.sh`
- Modify: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: `WORKSPACE TASK_MANIFEST BENCHMARK MAX_GENERATIONS N_CONCURRENT`.
- Produces: a smoke workspace using the exact tracked benchmark task list, with no anchor and with all unselected original train tasks moved into gate for privacy.

- [ ] **Step 1: Add the tracked smoke manifest**

Create:

```json
{
  "tau3": [
    "tau3-airline-3",
    "tau3-banking_knowledge-task-012",
    "tau3-retail-1"
  ],
  "terminal-bench-2": [
    "build-cython-ext",
    "fix-git",
    "regex-log"
  ]
}
```

- [ ] **Step 2: Replace selection tests with exact-manifest tests**

Add a fixture manifest containing three known names and invoke:

```python
configured = subprocess.run(
    [
        "bash",
        str(SMOKE),
        str(workspace),
        str(smoke_manifest),
        "tau3",
        "2",
        "3",
    ],
    cwd=ROOT,
    env={
        **os.environ,
        "EVOLVE_CLI": str(fake_evolve),
        "EVOLVE_PYTHON": sys.executable,
    },
    capture_output=True,
    text=True,
    check=False,
)
```

Assert:

```python
assert config["experiment"]["max_generations"] == 2
assert config["evaluator"]["task_names"] == approved_tasks
assert config["evaluator"]["tasks_per_round"] == 3
assert config["evaluator"]["n_concurrent"] == 3
assert config["evaluator"]["anchor"]["final"] is False
assert rendered["tasks"]["train"] == approved_tasks
assert set(approved_tasks).isdisjoint(rendered["tasks"]["gate"])
assert set(approved_tasks).isdisjoint(rendered["tasks"]["sealed"])
```

Add negative tests for:

- a task absent from original train;
- a task present in gate;
- a benchmark key absent from the task manifest;
- duplicate approved names; and
- a manifest with a count other than three.

- [ ] **Step 3: Run smoke tests and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -k smoke -q
```

Expected: failures because the current script selects tasks algorithmically.

- [ ] **Step 4: Implement exact task loading and validation**

Use this interface:

```sh
usage: configure_benchmark_smoke.sh \
  WORKSPACE TASK_MANIFEST {tau3|terminal-bench-2} \
  [MAX_GENERATIONS] [N_CONCURRENT]
```

Defaults are `MAX_GENERATIONS=2` and `N_CONCURRENT=3`.

In Python:

```python
approved = json.loads(task_manifest.read_text())[benchmark]
if len(approved) != 3 or len(set(approved)) != 3:
    raise SystemExit("smoke task manifest must contain exactly three unique tasks")
if not set(approved) <= set(original_train):
    raise SystemExit("smoke task manifest contains a task outside frozen train")
if set(approved) & (set(tasks["gate"]) | set(tasks["sealed"])):
    raise SystemExit("smoke task manifest overlaps gate or sealed")
```

Preserve every original task exactly once by setting train to `approved` and
prepending unselected original train tasks to gate. Remove MiniSWE-only
`MINISWE_STEP_LIMIT` mutation when the evaluator agent is
`target.agent:HarborAgent`. For AHE, cap trace analysis to the three smoke
tasks; HyperAgents retains `trace_browser`. Preserve the imported smoke
default
`EVOLVE_HARBOR_ENVIRONMENT_BUILD_TIMEOUT_MULTIPLIER=10` so Docker image
builds have the same contention tolerance as the existing benchmark tooling.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -q
```

Expected: all setup, run, and smoke tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add \
  experiments/codex-wrapper-smoke-tasks.json \
  scripts/configure_benchmark_smoke.sh \
  tests/test_experiment_setup_scripts.py
git commit -m "feat: configure exact Codex smoke tasks"
```

### Task 5: Add Codex auth/proxy preflight to the run path

**Files:**
- Modify: `scripts/run_benchmark_experiment.sh`
- Modify: `tests/test_experiment_setup_scripts.py`

**Interfaces:**
- Consumes: workspace `evaluator/eval.env`, root `evolve.env`, optional `proxy.env`, `runtime.env`, optional simulator env, and host Codex auth.
- Produces: verification plus `evolve candidate-smoke --full --checkout WORKSPACE` before a Codex-target run; emits only boolean/presence diagnostics.

- [ ] **Step 1: Extend the fake runner log**

Record these values without recording proxy values:

```python
{
    "args": sys.argv[1:],
    "force_auth": os.environ.get("CODEX_FORCE_AUTH_JSON"),
    "proxy_keys": sorted(
        name
        for name in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "no_proxy",
            "NO_PROXY",
        )
        if os.environ.get(name)
    ),
}
```

- [ ] **Step 2: Write failing Codex preflight tests**

Create a Codex workspace fixture with:

```text
EVOLVE_HARBOR_CODEX_SUBSCRIPTION=1
EVOLVE_HARBOR_N_CONCURRENT=3
```

Create mode-`0600` `auth.json` under a fake `HOME`, six proxy variables in
`proxy.env`, and assert runner calls occur in this order:

```python
assert calls[0]["args"] == ["verify", str(workspace)]
assert calls[1]["args"] == [
    "candidate-smoke",
    "--full",
    "--checkout",
    str(workspace),
]
assert calls[2]["args"] == [
    "run",
    str(workspace),
    "--max-generations",
    "2",
]
assert calls[2]["force_auth"] == "1"
assert calls[2]["proxy_keys"] == [
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
]
```

Add failure tests for missing auth, auth mode other than `0600`, and each
missing proxy variable. Assert stderr contains only the missing variable name,
not any configured proxy value.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py -k "run or preflight" -q
```

Expected: failures because the run script does not enforce Codex preconditions or call candidate smoke.

- [ ] **Step 4: Implement runtime-only preflight**

After environment loading, detect:

```sh
codex_subscription=$(
  sed -n 's/^EVOLVE_HARBOR_CODEX_SUBSCRIPTION=//p' \
    "$workspace/evaluator/eval.env" | tail -1
)
```

For `codex_subscription=1`:

1. resolve `${CODEX_AUTH_JSON_PATH:-$HOME/.codex/auth.json}`;
2. use `"$framework_python"` and `stat.S_IMODE(path.stat().st_mode)` to require
   a non-empty regular file with mode `0o600`;
3. require all six proxy variables;
4. export `CODEX_FORCE_AUTH_JSON=1`; and
5. run:

```sh
"$runner" candidate-smoke --full --checkout "$workspace"
```

Do not print auth size, auth contents, proxy values, or environment dumps.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_experiment_setup_scripts.py tests/test_candidate_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add scripts/run_benchmark_experiment.sh tests/test_experiment_setup_scripts.py
git commit -m "feat: preflight Codex auth and proxy runtime"
```

### Task 6: Add deterministic workspace and smoke auditing

**Files:**
- Create: `scripts/audit_codex_experiment.py`
- Create: `tests/test_audit_codex_experiment.py`

**Interfaces:**
- Consumes: `WORKSPACE`, `--mode prepared|smoke`, optional `--expected-anchor final|none`, optional `--through-generation`, and optional `--output`.
- Produces: a secret-free JSON report with `ok`, `errors`, `experiment`, `tasks`, `lineage`, `reasoning`, and `anchor` keys; exits 0 only when all requested invariants pass.

- [ ] **Step 1: Write prepared-workspace audit tests**

Build a fixture containing `evolve.yaml`, `evaluator/splits.json`,
`evaluator/tasks/train.txt`, `evaluator/tasks/sealed.txt`,
`evaluator/agent.kwargs`, and `evaluator/eval.env`.

Call:

```python
result = subprocess.run(
    [
        sys.executable,
        str(AUDIT),
        str(workspace),
        "--mode",
        "prepared",
    ],
    text=True,
    capture_output=True,
)
```

Assert the report requires:

```python
assert report["ok"] is True
assert report["reasoning"] == {"reasoning_effort": "high"}
assert report["anchor"] == {"final": True, "every_rounds": 0}
assert report["tasks"]["train_count"] == expected_train_count
assert report["tasks"]["sealed_count"] == expected_sealed_count
```

Add one failure test each for MiniSWE evaluator agent, missing protected
reasoning, non-Codex model, and train/sealed membership mismatch.

Add a prepared-smoke fixture and call:

```python
result = subprocess.run(
    [
        sys.executable,
        str(AUDIT),
        str(workspace),
        "--mode",
        "prepared",
        "--expected-anchor",
        "none",
    ],
    text=True,
    capture_output=True,
)
```

Assert it requires exactly three train tasks, a disabled final anchor, and no
anchor cadence.

- [ ] **Step 2: Write smoke-lineage audit tests**

Create tags `gen/0`, `gen/1`, and `gen/2` and archive evaluation events with:

```python
{
    "_evolve_mechanism_eval": True,
    "purpose": "candidate",
    "generation": str(generation),
    "status": "complete",
    "selection_eligible": True,
    "expected_trials": 3,
    "task_set_members": approved_tasks,
}
```

Create one Harbor `config.json` per canonical evaluation whose agent kwargs
contain `reasoning_effort: high`. Assert `--mode smoke
--through-generation 2` passes.

Add failure tests for a missing generation, expected trials other than 3,
gate/sealed leakage, an anchor event, and effective reasoning other than high.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_audit_codex_experiment.py -q
```

Expected: failure because the audit script does not exist.

- [ ] **Step 4: Implement focused audit functions**

Define these exact public functions:

- `audit_prepared(workspace: Path) -> dict[str, object]`
- `audit_smoke(workspace: Path, through_generation: int) -> dict[str, object]`
- `write_report(report: dict[str, object], output: Path | None) -> None`
- `main(argv: list[str] | None = None) -> int`

`audit_prepared` validates the static Codex contract, exact split/task-file
agreement, protected high reasoning, and the requested anchor state.
`--expected-anchor final` is the default and requires the full production
final-only anchor. `--expected-anchor none` requires exactly three train
tasks, `anchor.final == false`, and `anchor.every_rounds == 0`.

`audit_smoke` additionally validates tags 0 through N, complete canonical
evaluation events, exactly three approved task members, no anchor events, no
private task identifiers in rollout/trace/feedback text files, allowed
surface mutations, and
`config["agent"]["kwargs"]["reasoning_effort"] == "high"` in persisted
canonical Harbor trial configs.

The report contains paths, task names, counts, booleans, and error messages.
It never contains environment values or file content from auth/proxy paths.

- [ ] **Step 5: Run audit and repository tests**

Run:

```bash
uv run pytest \
  tests/test_audit_codex_experiment.py \
  tests/test_experiment_setup_scripts.py \
  tests/test_harbor_evaluator_template.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add scripts/audit_codex_experiment.py tests/test_audit_codex_experiment.py
git commit -m "feat: audit Codex benchmark experiments"
```

### Task 7: Verify locally and deploy an immutable framework snapshot

**Files:**
- No source changes.
- Create remotely: `/data00/home/zimuwang/simple-evolve-agent-codex-target-20260730`

**Interfaces:**
- Consumes: the committed implementation branch and existing datasets/manifests on DevBox and DevBoxS.
- Produces: identical locked framework installations on both hosts without replacing historical checkouts.

- [ ] **Step 1: Run the complete relevant local test set**

Run:

```bash
uv run pytest \
  tests/test_experiment_setup_scripts.py \
  tests/test_audit_codex_experiment.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_candidate_smoke.py \
  tests/test_m7_codex_seed.py \
  tests/test_phase_e_recipes.py \
  tests/test_recipe_composition.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Record and verify the exact clean source state**

Run:

```bash
git diff --check
git status --short
git rev-parse HEAD
```

Expected: only the user's pre-existing unrelated untracked files remain; no
implementation file is modified or untracked.

- [ ] **Step 3: Create and transfer an immutable Git bundle**

Run:

```bash
git bundle create /tmp/simple-evolve-agent-codex-target-20260730.bundle HEAD
scp /tmp/simple-evolve-agent-codex-target-20260730.bundle \
  DevBox:/data00/home/zimuwang/
scp /tmp/simple-evolve-agent-codex-target-20260730.bundle \
  DevBoxS:/data00/home/zimuwang/
```

- [ ] **Step 4: Refuse overwrite and clone on both hosts**

Run on each host:

```bash
test ! -e /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730
git clone \
  /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730.bundle \
  /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730
```

Expected: the destination did not exist and clone succeeds.

- [ ] **Step 5: Install and verify the locked environment on each host**

Run:

```bash
cd /data00/home/zimuwang/simple-evolve-agent-codex-target-20260730
uv sync --frozen
.venv/bin/evolve --help
.venv/bin/python -m pytest \
  tests/test_experiment_setup_scripts.py \
  tests/test_audit_codex_experiment.py \
  tests/test_harbor_evaluator_template.py \
  -q
```

Expected: dependency sync is frozen and all remote focused tests pass.

### Task 8: Prepare and run the four sequential smoke experiments

**Files:**
- Create remotely on DevBoxS:
  - `workspaces/ahe-codex-tau3-smoke-3x2`
  - `workspaces/hyperagents-codex-tau3-smoke-3x2`
- Create remotely on DevBox:
  - `workspaces/ahe-codex-terminal-bench-2-smoke-3x2`
  - `workspaces/hyperagents-codex-terminal-bench-2-smoke-3x2`
- Create remotely: one JSON audit report per smoke.

**Interfaces:**
- Consumes: deployed framework, shared environment files, frozen datasets/manifests, tracked smoke manifest, existing production health baseline.
- Produces: four passing generation-0-through-2 smoke lineages; stops immediately on any smoke or isolation failure.

- [ ] **Step 1: Capture the initial active-production inventory**

On each host, record:

```bash
pgrep -af '[/]evolve run ' > /tmp/codex-smoke-baseline-processes.txt
docker ps --format '{{json .}}' > /tmp/codex-smoke-baseline-containers.jsonl
docker ps --format '{{.ID}}' > /tmp/codex-smoke-baseline-container-ids.txt
```

This inventory establishes which production runs existed before the entire
sequence. Refresh the same three files immediately before every individual
smoke, as shown below, so a production run that finishes normally between
smokes is not misclassified as smoke interference.

Do not use `docker compose down`, `docker stop`, `docker restart`, or Docker
prune commands.

- [ ] **Step 2: Prepare the two tau3 smoke workspaces on DevBoxS**

With:

```bash
export EVOLVE_EXPERIMENT_ROOT=/data00/home/zimuwang/simple-evolve-agent-full89-20260724
export EVOLVE_FRAMEWORK=/data00/home/zimuwang/simple-evolve-agent-codex-target-20260730
export TAU3_DATASET="$EVOLVE_EXPERIMENT_ROOT/datasets/tau3-bench-375"
export TAU3_MANIFEST="$EVOLVE_EXPERIMENT_ROOT/manifests/tau3-bench-100-100-175.json"
```

Run:

```bash
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  ahe codex tau3 ahe-codex-tau3-smoke-3x2 3
"$EVOLVE_FRAMEWORK/scripts/configure_benchmark_smoke.sh" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/ahe-codex-tau3-smoke-3x2" \
  "$EVOLVE_FRAMEWORK/experiments/codex-wrapper-smoke-tasks.json" \
  tau3 2 3

"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  hyperagents codex tau3 hyperagents-codex-tau3-smoke-3x2 3
"$EVOLVE_FRAMEWORK/scripts/configure_benchmark_smoke.sh" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/hyperagents-codex-tau3-smoke-3x2" \
  "$EVOLVE_FRAMEWORK/experiments/codex-wrapper-smoke-tasks.json" \
  tau3 2 3
```

- [ ] **Step 3: Prepare the two Terminal-Bench 2 smoke workspaces on DevBox**

Set:

```bash
export EVOLVE_EXPERIMENT_ROOT=/data00/home/zimuwang/simple-evolve-agent-full89-20260724
export EVOLVE_FRAMEWORK=/data00/home/zimuwang/simple-evolve-agent-codex-target-20260730
export TB2_DATASET="$EVOLVE_EXPERIMENT_ROOT/datasets/terminal-bench-2-50-19-20"
export TB2_MANIFEST="$EVOLVE_EXPERIMENT_ROOT/manifests/terminal-bench-2-50-19-20.json"
```

Run:

```bash
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  ahe codex terminal-bench-2 \
  ahe-codex-terminal-bench-2-smoke-3x2 3
"$EVOLVE_FRAMEWORK/scripts/configure_benchmark_smoke.sh" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/ahe-codex-terminal-bench-2-smoke-3x2" \
  "$EVOLVE_FRAMEWORK/experiments/codex-wrapper-smoke-tasks.json" \
  terminal-bench-2 2 3

"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  hyperagents codex terminal-bench-2 \
  hyperagents-codex-terminal-bench-2-smoke-3x2 3
"$EVOLVE_FRAMEWORK/scripts/configure_benchmark_smoke.sh" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/hyperagents-codex-terminal-bench-2-smoke-3x2" \
  "$EVOLVE_FRAMEWORK/experiments/codex-wrapper-smoke-tasks.json" \
  terminal-bench-2 2 3
```

- [ ] **Step 4: Audit all four prepared smoke workspaces before launch**

Run for each workspace:

```bash
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$workspace" --mode prepared --expected-anchor none
"$EVOLVE_FRAMEWORK/.venv/bin/evolve" verify "$workspace"
```

Expected: all prepared audits and verifications pass.

- [ ] **Step 5: Run the AHE tau3 smoke and monitor it**

On DevBoxS:

```bash
pgrep -af '[/]evolve run ' > /tmp/codex-smoke-baseline-processes.txt || true
docker ps --format '{{json .}}' > /tmp/codex-smoke-baseline-containers.jsonl
docker ps --format '{{.ID}}' > /tmp/codex-smoke-baseline-container-ids.txt
"$EVOLVE_FRAMEWORK/scripts/run_benchmark_experiment.sh" \
  ahe-codex-tau3-smoke-3x2 2
```

While active, report progress at least every 60 seconds using tag/archive
counts and the smoke-owned Harbor log. Do not poll or modify production
containers.

- [ ] **Step 6: Audit AHE tau3 and compare production health**

Run:

```bash
mkdir -p "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730"
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/ahe-codex-tau3-smoke-3x2" \
  --mode smoke --through-generation 2 \
  --output "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730/ahe-codex-tau3-smoke-3x2.json"
```

Confirm every baseline Evolve PID is still alive:

```bash
awk '{print $1}' /tmp/codex-smoke-baseline-processes.txt |
while IFS= read -r production_pid; do
  kill -0 "$production_pid" ||
    { echo "production process exited: $production_pid" >&2; exit 1; }
done
```

For baseline containers that still exist, reject unhealthy state:

```bash
while IFS= read -r container_id; do
  docker inspect "$container_id" >/dev/null 2>&1 || continue
  container_health=$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "$container_id"
  )
  test "$container_health" != unhealthy ||
    { echo "production container unhealthy: $container_id" >&2; exit 1; }
done < /tmp/codex-smoke-baseline-container-ids.txt
```

Missing baseline containers are allowed because a production trial may finish
normally. If a baseline process exits or a surviving baseline container is
unhealthy, stop the sequence and report an isolation failure.

- [ ] **Step 7: Run and audit HyperAgents tau3**

On DevBoxS, run:

```bash
pgrep -af '[/]evolve run ' > /tmp/codex-smoke-baseline-processes.txt || true
docker ps --format '{{json .}}' > /tmp/codex-smoke-baseline-containers.jsonl
docker ps --format '{{.ID}}' > /tmp/codex-smoke-baseline-container-ids.txt
"$EVOLVE_FRAMEWORK/scripts/run_benchmark_experiment.sh" \
  hyperagents-codex-tau3-smoke-3x2 2
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/hyperagents-codex-tau3-smoke-3x2" \
  --mode smoke --through-generation 2 \
  --output "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730/hyperagents-codex-tau3-smoke-3x2.json"
```

Do not begin until the AHE tau3 audit and health comparison pass. Re-run the
exact `kill -0` and `docker inspect` loops from Step 6 after this audit.

- [ ] **Step 8: Run and audit AHE Terminal-Bench 2**

On DevBox, run:

```bash
pgrep -af '[/]evolve run ' > /tmp/codex-smoke-baseline-processes.txt || true
docker ps --format '{{json .}}' > /tmp/codex-smoke-baseline-containers.jsonl
docker ps --format '{{.ID}}' > /tmp/codex-smoke-baseline-container-ids.txt
"$EVOLVE_FRAMEWORK/scripts/run_benchmark_experiment.sh" \
  ahe-codex-terminal-bench-2-smoke-3x2 2
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/ahe-codex-terminal-bench-2-smoke-3x2" \
  --mode smoke --through-generation 2 \
  --output "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730/ahe-codex-terminal-bench-2-smoke-3x2.json"
```

Do not begin until both tau3 smokes pass. Re-run the exact `kill -0` and
`docker inspect` loops from Step 6 after this audit.

- [ ] **Step 9: Run and audit HyperAgents Terminal-Bench 2**

On DevBox, run:

```bash
pgrep -af '[/]evolve run ' > /tmp/codex-smoke-baseline-processes.txt || true
docker ps --format '{{json .}}' > /tmp/codex-smoke-baseline-containers.jsonl
docker ps --format '{{.ID}}' > /tmp/codex-smoke-baseline-container-ids.txt
"$EVOLVE_FRAMEWORK/scripts/run_benchmark_experiment.sh" \
  hyperagents-codex-terminal-bench-2-smoke-3x2 2
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$EVOLVE_EXPERIMENT_ROOT/workspaces/hyperagents-codex-terminal-bench-2-smoke-3x2" \
  --mode smoke --through-generation 2 \
  --output "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730/hyperagents-codex-terminal-bench-2-smoke-3x2.json"
```

Do not begin until the AHE Terminal-Bench 2 smoke passes. Re-run the exact
`kill -0` and `docker inspect` loops from Step 6 after this audit.

- [ ] **Step 10: Collect reports and produce a combined smoke summary**

Create the local report directory and retrieve the four JSON reports:

```bash
mkdir -p \
  /Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730
scp \
  DevBoxS:/data00/home/zimuwang/simple-evolve-agent-full89-20260724/audits/codex-target-20260730/ahe-codex-tau3-smoke-3x2.json \
  DevBoxS:/data00/home/zimuwang/simple-evolve-agent-full89-20260724/audits/codex-target-20260730/hyperagents-codex-tau3-smoke-3x2.json \
  /Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730/
scp \
  DevBox:/data00/home/zimuwang/simple-evolve-agent-full89-20260724/audits/codex-target-20260730/ahe-codex-terminal-bench-2-smoke-3x2.json \
  DevBox:/data00/home/zimuwang/simple-evolve-agent-full89-20260724/audits/codex-target-20260730/hyperagents-codex-terminal-bench-2-smoke-3x2.json \
  /Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730/
```

Create
`/Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730/summary.md`
containing, for each smoke:

- host and workspace;
- exact three tasks;
- generation tags 0, 1, and 2;
- canonical evaluation status and score for each generation;
- effective model and high reasoning evidence;
- mutation paths and surface-policy result;
- absence of anchor/private-task leakage;
- pre/post production health result; and
- audit-report path.

The summary must not contain proxy values, auth content, API keys, or base URLs.

### Task 9: Prepare and audit four production workspaces without launching

**Files:**
- Create remotely on DevBox:
  - `workspaces/ahe-codex-tau3`
  - `workspaces/ahe-codex-terminal-bench-2`
- Create remotely on DevBoxS:
  - `workspaces/hyperagents-codex-tau3`
  - `workspaces/hyperagents-codex-terminal-bench-2`
- Create remotely: one prepared-workspace audit report per production workspace.

**Interfaces:**
- Consumes: four passing smoke audits and the same deployed framework/dataset manifests.
- Produces: four verified production workspaces with no running Evolve process.

- [ ] **Step 1: Require all four passing smoke reports**

Parse the four JSON reports collected under
`/Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730`
and require:

```python
assert all(report["ok"] is True for report in reports)
```

If any report is absent or false, do not prepare production workspaces.

- [ ] **Step 2: Prepare AHE production workspaces on DevBox**

Run:

```bash
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  ahe codex tau3 ahe-codex-tau3 25
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  ahe codex terminal-bench-2 ahe-codex-terminal-bench-2 25
```

- [ ] **Step 3: Prepare HyperAgents production workspaces on DevBoxS**

Run:

```bash
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  hyperagents codex tau3 hyperagents-codex-tau3 25
"$EVOLVE_FRAMEWORK/scripts/setup_benchmark_experiment.sh" \
  hyperagents codex terminal-bench-2 \
  hyperagents-codex-terminal-bench-2 25
```

- [ ] **Step 4: Audit and verify every production workspace**

For each workspace, run:

```bash
mkdir -p "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730"
"$EVOLVE_FRAMEWORK/.venv/bin/python" \
  "$EVOLVE_FRAMEWORK/scripts/audit_codex_experiment.py" \
  "$workspace" --mode prepared \
  --output "$EVOLVE_EXPERIMENT_ROOT/audits/codex-target-20260730/$(basename "$workspace")-prepared.json"
"$EVOLVE_FRAMEWORK/.venv/bin/evolve" verify "$workspace"
```

Require:

- 100/100/175 tau3 split counts or 50/19/20 TB2 split counts;
- complete train and sealed task files;
- train-only canonical evaluation configuration;
- final-only sealed anchor;
- model `gpt-5.4`;
- frozen reasoning `high`;
- subscription auth flag;
- concurrency 25;
- correct recipe surfaces and operator variants; and
- tau3 simulator settings only in tau3 workspaces.

Create
`/Users/bytedance/Desktop/simple-evolve-agent/reports/codex-target-smoke-20260730/configuration-comparison.md`.
For each of the four production workspaces, compare the effective values
above with the Lark experiment source and record `match` or the exact
non-secret mismatch. Include recipe, benchmark, task counts, concurrency,
generation count, children, retry and timeout multipliers, evaluator model
and reasoning, meta-agent model and reasoning, mutable surface, anchor
policy, and tau3 simulator settings. Do not include environment values,
credentials, proxy endpoints, API keys, or base URLs.

- [ ] **Step 5: Prove no production workspace was launched**

Run on both hosts:

```bash
for workspace_name in \
  ahe-codex-tau3 \
  ahe-codex-terminal-bench-2 \
  hyperagents-codex-tau3 \
  hyperagents-codex-terminal-bench-2; do
  if pgrep -af "[e]volve run .*$workspace_name"; then
    echo "unexpected production launch: $workspace_name" >&2
    exit 1
  fi
done
```

Expected: no matching process.

- [ ] **Step 6: Hand off for user review**

Report:

- the four smoke summaries and audit paths;
- the four production workspace paths and prepared-audit paths;
- the deployed framework commit;
- confirmation that active MiniSWE runs remained healthy; and
- confirmation that no Codex production run was launched.

Stop and wait for explicit user approval before any production launch.
