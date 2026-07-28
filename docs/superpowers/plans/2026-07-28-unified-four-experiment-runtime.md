# Unified Four-Experiment Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four AHE/HyperAgents × TB2/HLE recipes produce identical, auditable runtime-control settings while preserving all method- and benchmark-specific behavior.

**Architecture:** Treat the recipe as the canonical experiment contract, freeze that contract into each workspace, and prevent ambient launch variables from overriding controlled Harbor settings. Give AHE trace-debugger retries an explicit nonnegative retry interface so zero retries means exactly one whole-job attempt, independently of lower-level LLM/API transport retries.

**Tech Stack:** Python 3.12, pytest, YAML recipes, POSIX shell evaluator templates, Harbor 0.18, UV.

## Global Constraints

- Do not start, resume, stop, archive, or delete any experiment as part of implementation.
- Future launches use four new unique IDs and clean generation-0 workspaces.
- The benchmark agent remains `evolve_harbor_adapter:MiniSweSourceAgent` over the pinned mini-swe-agent revision `388da74aad620a384ab47669b17c52133e30e7c3`.
- Setup, agent, and verifier timeout multipliers are explicitly `1` in all four recipes; absolute task timeouts remain Harbor-native.
- Harbor benchmark retries and automatic driver re-evaluation remain `0`.
- Meta-agent timeout is 3,600 seconds per attempt with `max_retries: 1`, giving at most two total attempts.
- AHE trace-debugger whole-job retries are `0`, giving one total attempt; trace failure remains nonfatal.
- Existing LLM/API client transport retries are untouched.
- Partial-score floor is `0.9` in all four recipes.
- Models, datasets, splits, task counts, concurrency, UV scoping, Docker image, prompts, editable roots, and operator algorithms remain unchanged.
- Preflight remains an operator-run procedure outside candidate and benchmark code.

---

## File map

- `library/trace_analyzer/ahe.py`: interpret an explicit trace-debugger retry count and convert it to total attempts.
- `tests/test_ahe_trace_analyzer.py`: prove zero whole-job retries performs one call and remains nonfatal on failure.
- `recipes/ahe/evolve.yaml`: AHE/TB2 canonical runtime contract.
- `recipes/ahe_hle/evolve.yaml`: AHE/HLE canonical runtime contract.
- `recipes/hyperagents/evolve.yaml`: HyperAgents/TB2 canonical runtime contract.
- `recipes/hyperagents_hle/evolve.yaml`: HyperAgents/HLE canonical runtime contract.
- `tests/test_phase_e_recipes.py`: cross-recipe contract and unchanged-setting assertions.
- `templates/evaluator/eval-prefix.sh`: clear ambient values for frozen Harbor retry and timeout controls before sourcing workspace configuration.
- `tests/test_harbor_evaluator_template.py`: prove ambient runtime variables cannot override a neutral frozen workspace while nonneutral frozen values remain supported.
- `tests/test_harbor_evaluator_config.py`: prove neutral values do not emit positive override variables into `eval.env`.

### Task 1: Give AHE trace-debugger retries explicit zero-safe semantics

**Files:**
- Modify: `library/trace_analyzer/ahe.py`
- Modify: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: `OperatorContext.config["debugger_max_retries"]`
- Produces: `_run_debugger_job(...)` performs `debugger_max_retries + 1` total whole-job attempts.
- Preserves: `_debugger_runner_config(...)` continues setting the nested Harbor runner's `max_retries` to zero, so each trace-debugger attempt is itself not replayed by Harbor.

- [ ] **Step 1: Write the failing zero-retry unit test**

Add a counter-based test beside `test_ahe_debugger_retries_and_fails_visibly`:

```python
def test_ahe_debugger_zero_retries_means_one_total_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    ctx.config["debugger_max_retries"] = 0
    ctx.config.pop("retry_attempts", None)
    job = module._build_jobs([_case("task-a", "failed", 0)], 90)[0]
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AgentCommandError("failed", returncode=1)

    monkeypatch.setattr(module, "run_readonly_agent", fail_once)

    with pytest.raises(AgentCommandError, match="failed"):
        module._run_debugger_job(ctx.checkout, ctx, job)

    assert calls == 1
```

- [ ] **Step 2: Run the test and verify the old semantics fail**

Run:

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py::test_ahe_debugger_zero_retries_means_one_total_attempt
```

Expected: FAIL because the existing code ignores `debugger_max_retries` and performs three attempts.

- [ ] **Step 3: Add a nonnegative integer parser and convert retries to attempts**

Add:

```python
def _nonnegative_int(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
```

Change `_run_debugger_job` from:

```python
attempts = _positive_int(ctx.config.get("retry_attempts"), 3)
```

to:

```python
max_retries = _nonnegative_int(ctx.config.get("debugger_max_retries"), 0)
attempts = max_retries + 1
```

Do not change `run_readonly_agent`, the model client, or any LLM transport configuration.

- [ ] **Step 4: Update the existing multi-attempt test to use retry counts**

In `_ctx`, replace:

```python
"retry_attempts": 3,
```

with:

```python
"debugger_max_retries": 2,
```

Keep the existing assertion `attempts == 3`; it now proves two retries yield three total attempts.

- [ ] **Step 5: Prove a failed single trace attempt remains nonfatal**

Extend `test_ahe_debugger_stage_keeps_all_tasks_when_individual_jobs_fail` or add a focused test that calls `_run_debugger_job_safe`:

```python
def test_ahe_debugger_safe_wrapper_records_single_attempt_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    ctx = _ctx(tmp_path)
    ctx.config["debugger_max_retries"] = 0
    job = module._build_jobs([_case("task-a", "failed", 0)], 90)[0]
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AgentCommandError("debugger unavailable", returncode=1)

    monkeypatch.setattr(module, "run_readonly_agent", fail_once)
    result = module._run_debugger_job_safe(ctx.checkout, ctx, job)

    assert calls == 1
    assert result.error == "debugger unavailable"
    assert result.response.startswith("ANALYSIS UNAVAILABLE:")
```

- [ ] **Step 6: Run the complete trace-analyzer test module**

Run:

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit the trace retry semantics**

Review and stage only the named files:

```bash
git diff -- library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "fix: make trace debugger retries explicit"
```

### Task 2: Encode the complete four-recipe runtime contract

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/ahe_hle/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hyperagents_hle/evolve.yaml`
- Modify: `tests/test_phase_e_recipes.py`

**Interfaces:**
- Consumes: the recipe schema loaded by `evolve.config.load_config`.
- Produces: four recipes whose evaluator and operator blocks satisfy the approved configuration table.
- Preserves: all dataset, split, task, model, target, operator-variant, concurrency, and UV settings not named in the contract change.

- [ ] **Step 1: Replace obsolete assertions with one four-recipe contract test**

Replace `test_shared_optimization_recipes_double_candidate_agent_timeout` and update method-specific `max_retries: 2` string assertions. Add:

```python
@pytest.mark.parametrize(
    "name",
    ["ahe", "ahe_hle", "hyperagents", "hyperagents_hle"],
)
def test_four_experiment_recipes_share_runtime_contract(name: str) -> None:
    recipe = _parsed_config(name)
    evaluator = recipe["evaluator"]
    meta_agent = recipe["operators"]["meta_agent"]

    assert evaluator["agent_setup_timeout_multiplier"] == 1
    assert evaluator["agent_timeout_multiplier"] == 1
    assert evaluator["verifier_timeout_multiplier"] == 1
    assert evaluator["max_retries"] == 0
    assert evaluator["k"] == 1
    assert evaluator["benchmark_timeout_is_zero"] is True
    assert evaluator["partial_floor"] == 0.9
    assert meta_agent["timeout_s"] == 3600
    assert meta_agent["max_retries"] == 1


@pytest.mark.parametrize("name", ["ahe", "ahe_hle"])
def test_ahe_recipes_disable_trace_debugger_whole_job_retries(name: str) -> None:
    trace = _parsed_config(name)["operators"]["trace_analyzer"]

    assert trace["debugger_max_retries"] == 0
    assert "retry_attempts" not in trace
```

Retain the existing tests for the fixed datasets, splits, mini-swe-agent revision, image, judge model, task counts, concurrency, reasoning settings, and UV runtime.

- [ ] **Step 2: Run the new contract tests and verify failure**

Run:

```bash
uv run pytest -q \
  tests/test_phase_e_recipes.py::test_four_experiment_recipes_share_runtime_contract \
  tests/test_phase_e_recipes.py::test_ahe_recipes_disable_trace_debugger_whole_job_retries
```

Expected: FAIL on the current timeout multipliers, meta-agent retries/timeouts, and AHE trace retry key.

- [ ] **Step 3: Update the two AHE recipes**

In both `recipes/ahe/evolve.yaml` and `recipes/ahe_hle/evolve.yaml`:

- replace trace `retry_attempts: 3` with `debugger_max_retries: 0`;
- set meta-agent `max_retries: 1`;
- keep meta-agent `timeout_s: 3600`;
- set evaluator `agent_setup_timeout_multiplier: 1`;
- set evaluator `agent_timeout_multiplier: 1`;
- set evaluator `verifier_timeout_multiplier: 1`;
- retain evaluator `max_retries: 0`;
- retain `partial_floor: 0.9`.

The resulting controlled fields must be equivalent to:

```yaml
operators:
  trace_analyzer:
    debugger_max_retries: 0
  meta_agent:
    max_retries: 1
    timeout_s: 3600
evaluator:
  agent_setup_timeout_multiplier: 1
  agent_timeout_multiplier: 1
  verifier_timeout_multiplier: 1
  max_retries: 0
  benchmark_timeout_is_zero: true
  partial_floor: 0.9
```

- [ ] **Step 4: Update the two HyperAgents recipes**

In both `recipes/hyperagents/evolve.yaml` and `recipes/hyperagents_hle/evolve.yaml`:

- keep the `trace_browser` block unchanged;
- set meta-agent `max_retries: 1`;
- change meta-agent `timeout_s` from `21600` to `3600`;
- add explicit evaluator `agent_setup_timeout_multiplier: 1`;
- set evaluator `agent_timeout_multiplier: 1`;
- add explicit evaluator `verifier_timeout_multiplier: 1`;
- retain evaluator `max_retries: 0`;
- retain `partial_floor: 0.9`.

- [ ] **Step 5: Run all recipe tests**

Run:

```bash
uv run pytest -q tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py
```

Expected: all tests pass after updating any AHE recipe fixture that still expects `retry_attempts: 3`.

- [ ] **Step 6: Verify unchanged settings mechanically**

Run:

```bash
git diff -- \
  recipes/ahe/evolve.yaml \
  recipes/ahe_hle/evolve.yaml \
  recipes/hyperagents/evolve.yaml \
  recipes/hyperagents_hle/evolve.yaml
```

Confirm the diff changes only the approved retry, timeout-multiplier, meta-agent, and explicit-neutral fields.

- [ ] **Step 7: Commit the recipe contract**

```bash
git add \
  recipes/ahe/evolve.yaml \
  recipes/ahe_hle/evolve.yaml \
  recipes/hyperagents/evolve.yaml \
  recipes/hyperagents_hle/evolve.yaml \
  tests/test_phase_e_recipes.py \
  tests/test_m9_ahe_recipe.py
git commit -m "config: unify four experiment runtime limits"
```

### Task 3: Prevent ambient launch variables from overriding frozen Harbor controls

**Files:**
- Modify: `templates/evaluator/eval-prefix.sh`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_harbor_evaluator_config.py`

**Interfaces:**
- Consumes: frozen `evaluator/eval.env`.
- Produces: an evaluator process in which timeout multipliers and benchmark retries come only from the frozen workspace configuration.
- Preserves: the explicit `EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE`, credential forwarding, proxy forwarding, candidate runtime environment, and LLM/API behavior.

- [ ] **Step 1: Add a failing behavioral test for hostile ambient values**

In `tests/test_harbor_evaluator_template.py`, create a neutral one-task evaluator with the existing `_write_executable`, `_write_fake_uv`, `_write_evaluator_helpers`, `_eval_sh`, and `_eval_env` helpers. Launch it with hostile ambient values:

```python
def test_harbor_evaluator_ignores_ambient_frozen_control_overrides(tmp_path: Path) -> None:
    evaluator = tmp_path / "evaluator"
    evaluator.mkdir()
    _write_executable(evaluator / "eval.sh", _eval_sh("harbor", "fixture"))
    (evaluator / "eval.env").write_text(
        _eval_env(
            "experiment",
            "fixture",
            n_concurrent=1,
            tasks_per_round=1,
            trials=1,
            partial_floor=0.9,
            agent="custom:Agent",
            setup_timeout_multiplier=1,
            agent_timeout_multiplier=1,
            verifier_timeout_multiplier=1,
            max_retries=0,
        )
    )
    (evaluator / "agent.env").write_text("")
    (evaluator / "verifier.env").write_text("")
    (evaluator / "environment.kwargs").write_text("")
    (evaluator / "splits.json").write_text('{"resolved":false}\n')
    _write_evaluator_helpers(evaluator)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_uv(fake_bin)
    _write_executable(
        fake_bin / "harbor",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$HARBOR_ARGS_CAPTURE"\n'
        "jobs_dir=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--jobs-dir" ]; then shift; jobs_dir=$1; fi\n'
        "  shift || true\n"
        "done\n"
        'mkdir -p "$jobs_dir/trial"\n'
        'printf \'%s\\n\' \'{"task_name":"task","trial_name":"trial","verifier_result":{"rewards":{"reward":1}}}\' > "$jobs_dir/trial/result.json"\n",
    )
    _write_executable(fake_bin / "docker", "#!/bin/sh\nexit 0\n")

    args_capture = tmp_path / "args"
    run_dir = tmp_path / "run"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HARBOR_ARGS_CAPTURE": str(args_capture),
        "EVOLVE_RUN_DIR": str(run_dir),
        "EVOLVE_ATTEMPT_ID": "ambient-override-test",
        "EVOLVE_FRAMEWORK_PYTHON": sys.executable,
        "EVOLVE_CANDIDATE_RUNTIME_ENV_JSON": "{}",
        "EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON": "[]",
        "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER": "9",
        "EVOLVE_HARBOR_MAX_RETRIES": "9",
    }

    result = subprocess.run(
        [str(evaluator / "eval.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    args = args_capture.read_text().splitlines()
    assert "--agent-setup-timeout-multiplier" not in args
    assert "--agent-timeout-multiplier" not in args
    assert "--verifier-timeout-multiplier" not in args
    assert "--max-retries" not in args
```

- [ ] **Step 2: Run the behavioral test and verify failure**

Run:

```bash
uv run pytest -q tests/test_harbor_evaluator_template.py::test_harbor_evaluator_ignores_ambient_frozen_control_overrides
```

Expected: FAIL because the current shell inherits and forwards all four hostile values.

- [ ] **Step 3: Clear only frozen control variables before sourcing `eval.env`**

Immediately before `. evaluator/eval.env` in `templates/evaluator/eval-prefix.sh`, add:

```sh
unset \
  EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER \
  EVOLVE_HARBOR_MAX_RETRIES
. evaluator/eval.env
```

Replace the existing direct `. evaluator/eval.env` line rather than sourcing the file twice. Do not unset `EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE` or any credential, proxy, model-client, or LLM retry variable.

- [ ] **Step 4: Prove nonneutral frozen configurations still render**

Add to `tests/test_harbor_evaluator_config.py`:

```python
def test_eval_env_omits_neutral_harbor_controls() -> None:
    env = _eval_env(
        "exp",
        "terminal-bench-2",
        n_concurrent=1,
        tasks_per_round=1,
        trials=1,
        partial_floor=0.9,
        agent="custom:Agent",
        setup_timeout_multiplier=1,
        agent_timeout_multiplier=1,
        verifier_timeout_multiplier=1,
        max_retries=0,
    )

    assert "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER" not in env
    assert "EVOLVE_HARBOR_AGENT_TIMEOUT_MULTIPLIER" not in env
    assert "EVOLVE_HARBOR_VERIFIER_TIMEOUT_MULTIPLIER" not in env
    assert "EVOLVE_HARBOR_MAX_RETRIES" not in env
```

Retain the existing tests proving configured multipliers greater than one are emitted. This preserves other recipes that intentionally use nonneutral values.

- [ ] **Step 5: Run evaluator configuration and shell tests**

Run:

```bash
uv run pytest -q \
  tests/test_harbor_evaluator_config.py \
  tests/test_harbor_evaluator_template.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit evaluator precedence isolation**

```bash
git diff -- \
  templates/evaluator/eval-prefix.sh \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_evaluator_config.py
git add \
  templates/evaluator/eval-prefix.sh \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_evaluator_config.py
git commit -m "fix: freeze harbor runtime controls"
```

### Task 4: Run integrated verification without launching experiments

**Files:**
- Verify only; no new production files.
- Reference: `docs/superpowers/specs/2026-07-28-unified-four-experiment-runtime-design.md`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: fresh test evidence and a line-by-line contract audit suitable for later deployment and launch.

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
uv run pytest -q \
  tests/test_ahe_trace_analyzer.py \
  tests/test_phase_e_recipes.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_harbor_evaluator_config.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_evaluation_lifecycle.py
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run the broader evaluator and runtime suite**

Run:

```bash
uv run pytest -q \
  tests/test_candidate_smoke.py \
  tests/test_evaluation_lifecycle.py \
  tests/test_evaluation_records.py \
  tests/test_harbor_artifacts.py \
  tests/test_locked_runtime.py \
  tests/test_m5_operator_runner.py \
  tests/test_m6_per_round_sampling.py \
  tests/test_selection_certification.py
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Audit the four parsed recipes**

Run:

```bash
uv run python -c '
from pathlib import Path
from evolve.config import load_config

for name in ("ahe", "ahe_hle", "hyperagents", "hyperagents_hle"):
    config = load_config(Path("recipes") / name / "evolve.yaml")
    evaluator = config["evaluator"]
    meta = config["operators"]["meta_agent"]
    print(
        name,
        "setup", evaluator["agent_setup_timeout_multiplier"],
        "agent", evaluator["agent_timeout_multiplier"],
        "verifier", evaluator["verifier_timeout_multiplier"],
        "harbor_retries", evaluator["max_retries"],
        "partial_floor", evaluator["partial_floor"],
        "meta_timeout", meta["timeout_s"],
        "meta_retries", meta["max_retries"],
    )
'
```

Expected for every row:

```text
setup 1 agent 1 verifier 1 harbor_retries 0 partial_floor 0.9 meta_timeout 3600 meta_retries 1
```

- [ ] **Step 4: Confirm only approved files and values changed**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Compare the final recipe values against the complete table in the approved design specification. Preserve unrelated pre-existing worktree changes.

- [ ] **Step 5: Record implementation completion**

If Tasks 1–3 were committed separately, do not create an empty final commit. Report:

- commit IDs;
- exact test commands and pass counts;
- confirmation that no experiment was launched;
- the remaining launch-time procedure: synchronize verified source, allocate four new IDs, scaffold clean workspaces, perform the manual preflight, inspect actual Harbor arguments, then continue only if all four match.

