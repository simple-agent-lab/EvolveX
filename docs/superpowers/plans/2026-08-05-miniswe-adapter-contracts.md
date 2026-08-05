# MiniSWE Adapter Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clarify the two MiniSWE trust roles, make session metadata optional, make AHE target-neutral, and remove suffix-based agent behavior without building a general Harbor capability framework.

**Architecture:** Keep separate installed-runtime and candidate-runtime adapters with canonical role names and compatibility aliases. Centralize exact first-party identifiers and narrow role predicates in one integration module; ordinary Harbor agents remain generic, while only the installed MiniSWE adapter receives Evolve-owned meta-agent transport behavior. Preserve a generated prompt cache key for all OpenAI Responses calls, but add the custom session header only when the user supplies `EVOLVE_SESSION_ID`.

**Tech Stack:** Python 3.12, pytest, Harbor 0.18 agent adapters, YAML recipes, existing Evolve workspace/runtime contracts.

## Global Constraints

- `EVOLVE_SESSION_ID` is optional and used literally when non-empty.
- When `EVOLVE_SESSION_ID` is absent or empty, generate `prompt_cache_key` and omit the custom `extra` header.
- Installed and candidate MiniSWE execution remain separate trust roles.
- `CandidateMiniSweAgent` is evaluator-only; the meta-agent runner must not dispatch on it.
- No `endswith(":MiniSweSourceAgent")` or `endswith(":FileTaskMiniSweAgent")` behavior selection remains.
- Ordinary Harbor-supported agents retain the generic path without Evolve capability declarations.
- Recipe changes are limited to canonical adapter identifiers; experiment scripts are untouched.

---

### Task 1: Canonical Adapter Names and Exact Role Predicates

**Files:**
- Create: `src/evolve/integrations/harbor/agent_roles.py`
- Modify: `src/evolve/integrations/harbor/miniswe_task_file.py:40`
- Modify: `src/evolve/integrations/harbor/miniswe_candidate.py:318`
- Modify: `src/evolve/workspace.py:45-55, 580-650`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hill_climb/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/hyperagents/README.md`
- Test: `tests/test_harbor_file_agent.py`
- Test: `tests/test_miniswe_harbor_wrapper.py`
- Test: `tests/test_phase_e_recipes.py`
- Test: `tests/test_m9_ahe_recipe.py`
- Test: `tests/test_hyperagents_harbor_recipe.py`
- Test: `tests/test_recipe_composition.py`
- Test: `tests/test_hyperagents_meta_agent.py`
- Test: `tests/test_patching.py`

**Interfaces:**
- Produces: `INSTALLED_MINISWE_AGENT`, `LEGACY_INSTALLED_MINISWE_AGENT`, `CANDIDATE_MINISWE_AGENT`, and `LEGACY_CANDIDATE_MINISWE_AGENT` string constants.
- Produces: `is_installed_miniswe_agent(value: object) -> bool`, `is_candidate_miniswe_agent(value: object) -> bool`, and `uses_miniswe_submission(value: object) -> bool` using exact membership only.
- Produces: canonical classes `InstalledMiniSweAgent` and `CandidateMiniSweAgent`; legacy class names remain importable aliases.
- Consumes: no new configuration fields.

- [ ] **Step 1: Write failing adapter-name and exact-matching tests**

Add assertions equivalent to:

```python
def test_miniswe_adapters_expose_role_names_and_legacy_aliases(monkeypatch) -> None:
    installed = _load_installed_adapter(monkeypatch)
    candidate = _load_candidate_adapter(monkeypatch)

    assert installed.FileTaskMiniSweAgent is installed.InstalledMiniSweAgent
    assert candidate.MiniSweSourceAgent is candidate.CandidateMiniSweAgent


def test_agent_role_predicates_use_exact_identifiers() -> None:
    assert is_installed_miniswe_agent(INSTALLED_MINISWE_AGENT)
    assert is_installed_miniswe_agent(LEGACY_INSTALLED_MINISWE_AGENT)
    assert is_candidate_miniswe_agent(CANDIDATE_MINISWE_AGENT)
    assert is_candidate_miniswe_agent(LEGACY_CANDIDATE_MINISWE_AGENT)
    assert not is_installed_miniswe_agent("custom:FileTaskMiniSweAgent")
    assert not is_candidate_miniswe_agent("custom:MiniSweSourceAgent")
```

Update recipe assertions to require the canonical identifiers:

```python
assert "agent: evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent" in config
assert "agent: evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent" in config
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q \
  tests/test_harbor_file_agent.py \
  tests/test_miniswe_harbor_wrapper.py \
  tests/test_phase_e_recipes.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_hyperagents_harbor_recipe.py \
  tests/test_recipe_composition.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_patching.py
```

Expected: failures because canonical classes, role predicates, and recipe identifiers do not exist yet.

- [ ] **Step 3: Implement canonical classes, aliases, and role predicates**

Create the focused identifier module with exact sets:

```python
INSTALLED_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent"
LEGACY_INSTALLED_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent"
CANDIDATE_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent"
LEGACY_CANDIDATE_MINISWE_AGENT = "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent"

_INSTALLED = frozenset({INSTALLED_MINISWE_AGENT, LEGACY_INSTALLED_MINISWE_AGENT})
_CANDIDATE = frozenset({CANDIDATE_MINISWE_AGENT, LEGACY_CANDIDATE_MINISWE_AGENT})
_MINISWE_SUBMISSION = frozenset({"mini-swe-agent", *_INSTALLED})

def is_installed_miniswe_agent(value: object) -> bool:
    return str(value or "") in _INSTALLED

def is_candidate_miniswe_agent(value: object) -> bool:
    return str(value or "") in _CANDIDATE

def uses_miniswe_submission(value: object) -> bool:
    return str(value or "") in _MINISWE_SUBMISSION
```

Rename class definitions and add aliases after each definition:

```python
FileTaskMiniSweAgent = InstalledMiniSweAgent
MiniSweSourceAgent = CandidateMiniSweAgent
```

Replace workspace initialization's exact candidate constant with the centralized candidate predicate. Change only adapter names in recipes and their explanatory README text. Update recipe-composition and generated-wrapper assertions to expect canonical identifiers and class definitions; keep separate, explicit assertions that both legacy aliases remain importable and that legacy identifier constants still satisfy their exact role predicates.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/evolve/integrations/harbor/agent_roles.py \
  src/evolve/integrations/harbor/miniswe_task_file.py \
  src/evolve/integrations/harbor/miniswe_candidate.py \
  src/evolve/workspace.py \
  recipes/ahe/evolve.yaml recipes/hyperagents/evolve.yaml \
  recipes/hill_climb/evolve.yaml recipes/ahe/README.md \
  recipes/hyperagents/README.md \
  tests/test_harbor_file_agent.py tests/test_miniswe_harbor_wrapper.py \
  tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py \
  tests/test_hyperagents_harbor_recipe.py tests/test_recipe_composition.py \
  tests/test_hyperagents_meta_agent.py tests/test_patching.py
git commit -m "refactor: clarify MiniSWE adapter roles"
```

### Task 2: Remove Candidate Adapter Dispatch from the Meta-Agent Runner

**Files:**
- Modify: `src/evolve/meta_agent_budget.py:35-68`
- Modify: `library/meta_agent/runners/harbor.py:35-45, 554-563, 832-864, 1030-1033, 1084-1104, 1244-1256`
- Modify: `library/trace_analyzer/ahe.py:333-344`
- Modify: `library/trace_analyzer/trajectory_only.py:100-116`
- Test: `tests/test_harbor_meta_agent.py`
- Test: `tests/test_m5_operator_runner.py`
- Test: `tests/test_ahe_trace_analyzer.py`
- Test: `tests/test_trajectory_only_trace_analyzer.py`

**Interfaces:**
- Consumes: Task 1's `is_installed_miniswe_agent()` and `uses_miniswe_submission()`.
- Produces: meta-agent config-command, mounted-file, submission, artifact, and timeout decisions based only on exact installed-agent identities.
- Removes: candidate-source meta-agent dispatch and candidate-source outer retry budget.

- [ ] **Step 1: Replace legacy expectations with failing boundary tests**

Delete or rewrite tests that expect `CandidateMiniSweAgent` to run as a meta-agent. Add boundary tests equivalent to:

```python
@pytest.mark.parametrize(
    "agent",
    [
        "custom:FileTaskMiniSweAgent",
        "custom:MiniSweSourceAgent",
        CANDIDATE_MINISWE_AGENT,
    ],
)
def test_non_installed_agents_use_generic_meta_agent_command(tmp_path, monkeypatch, agent) -> None:
    # Arrange the existing fake Harbor runner.
    ctx.config["agent"] = agent
    runner.run_agent(checkout, "evidence", ctx)
    command = json.loads((run_dir / "meta_agent/harbor/command.json").read_text())
    assert command[command.index("harbor") : command.index("harbor") + 2] == ["harbor", "exec"]
    assert "--config" not in command


def test_candidate_agent_does_not_receive_miniswe_meta_timeout_budget() -> None:
    config = {"runner": "harbor", "agent": CANDIDATE_MINISWE_AGENT, "max_retries": 1}
    assert _operator_deadline_s("meta_agent", config, 3600) == 3600


def test_suffix_sharing_debugger_agent_does_not_receive_submission_prompt() -> None:
    prompt = module._debugger_runner_prompt(job, {"agent": "custom:FileTaskMiniSweAgent"})
    assert prompt == module._debugger_prompt(job)
```

Retain explicit tests proving canonical and legacy installed identifiers still receive config transport, per-attempt timeout, artifact validation, and submission instructions.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q \
  tests/test_harbor_meta_agent.py \
  tests/test_m5_operator_runner.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_trajectory_only_trace_analyzer.py
```

Expected: candidate and suffix-sharing agents still enter MiniSWE-specific branches.

- [ ] **Step 3: Centralize installed-agent dispatch and delete source-agent branches**

Implement these focused substitutions:

- `harbor_agent_supports_per_attempt_timeout()` delegates to `is_installed_miniswe_agent()`.
- `_instruction_transport()` uses `is_installed_miniswe_agent()` and never checks a suffix.
- `_build_command()` uses the installed predicate for the config-command path and gives errors in role-neutral installed-agent language.
- `run_readonly_agent()` removes the `CandidateMiniSweAgent` config-command branch.
- submission and debugger/judge prompts use `uses_miniswe_submission()`.
- candidate adapters and arbitrary suffix-sharing names follow `_base_command()` in the meta-agent runner.

Run:

```bash
rg -n 'endswith\(.*(MiniSweSourceAgent|FileTaskMiniSweAgent)' src library
```

Expected: no matches.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/evolve/meta_agent_budget.py library/meta_agent/runners/harbor.py \
  library/trace_analyzer/ahe.py library/trace_analyzer/trajectory_only.py \
  tests/test_harbor_meta_agent.py tests/test_m5_operator_runner.py \
  tests/test_ahe_trace_analyzer.py tests/test_trajectory_only_trace_analyzer.py
git commit -m "refactor: make MiniSWE runner dispatch explicit"
```

### Task 3: Make Session Metadata Optional and Literal

**Files:**
- Modify: `src/evolve/integrations/harbor/miniswe_task_file.py:5-10, 61-75`
- Modify: `src/evolve/integrations/harbor/miniswe_candidate.py:64-116, 499-528`
- Test: `tests/test_harbor_file_agent.py`
- Test: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: optional `EVOLVE_SESSION_ID` from Harbor agent environment.
- Produces: literal configured `prompt_cache_key` plus `extra.session_id`, or generated cache key without `extra_headers`.
- Preserves: existing reasoning configuration, encrypted reasoning inclusion, and output-token defaults.

- [ ] **Step 1: Write failing installed-agent session tests**

Split the existing always-on session assertion into two tests:

```python
def test_installed_miniswe_uses_configured_session_id(monkeypatch) -> None:
    module = _load(monkeypatch)
    agent = module.InstalledMiniSweAgent(extra_env={"EVOLVE_SESSION_ID": "experiment-42"})
    environment = Environment()
    asyncio.run(agent.run("evidence", environment, object()))
    kwargs = _uploaded_model_kwargs(environment, module.RESPONSES_CONFIG_PATH)
    assert kwargs["prompt_cache_key"] == "experiment-42"
    assert json.loads(kwargs["extra_headers"]["extra"]) == {"session_id": "experiment-42"}


def test_installed_miniswe_omits_session_header_when_unset(monkeypatch) -> None:
    module = _load(monkeypatch)
    environment = Environment()
    asyncio.run(module.InstalledMiniSweAgent().run("evidence", environment, object()))
    kwargs = _uploaded_model_kwargs(environment, module.RESPONSES_CONFIG_PATH)
    assert kwargs["prompt_cache_key"].startswith("evolve-")
    assert "extra_headers" not in kwargs
```

- [ ] **Step 2: Write failing candidate-runtime session tests**

Add tests around the existing `MODEL_SETUP` execution helper:

```python
def test_candidate_miniswe_uses_literal_session_id(adapter_path, monkeypatch) -> None:
    _, build_model, (_, ResponseModel) = _load_model_factory(adapter_path, monkeypatch)
    monkeypatch.setenv("MSWEA_MODEL_NAME", "openai/gpt-5.4")
    monkeypatch.setenv("EVOLVE_SESSION_ID", "experiment-42")
    model = build_model({"model": {}})
    kwargs = model.kwargs["model_kwargs"]
    assert kwargs["prompt_cache_key"] == "experiment-42"
    assert json.loads(kwargs["extra_headers"]["extra"]) == {"session_id": "experiment-42"}


def test_candidate_miniswe_omits_session_header_when_unset(adapter_path, monkeypatch) -> None:
    _, build_model, _ = _load_model_factory(adapter_path, monkeypatch)
    monkeypatch.setenv("MSWEA_MODEL_NAME", "openai/gpt-5.4")
    monkeypatch.delenv("EVOLVE_SESSION_ID", raising=False)
    model = build_model({"model": {}})
    kwargs = model.kwargs["model_kwargs"]
    assert kwargs["prompt_cache_key"].startswith("evolve-")
    assert "extra_headers" not in kwargs
```

Extend `_source_env()` coverage to assert an adapter-provided `EVOLVE_SESSION_ID` is forwarded and absence stays absent.

- [ ] **Step 3: Run session tests and verify RED**

Run:

```bash
pytest -q tests/test_harbor_file_agent.py tests/test_miniswe_harbor_wrapper.py
```

Expected: current code generates a UUID and always emits `extra_headers`.

- [ ] **Step 4: Implement literal optional session handling**

In both paths, implement the same state transition:

```python
session_id = configured_session_id.strip()
cache_key = session_id or f"evolve-{uuid.uuid4().hex}"
model_kwargs["prompt_cache_key"] = cache_key
if session_id:
    model_kwargs["extra_headers"] = {
        "extra": json.dumps({"session_id": session_id}, separators=(",", ":"))
    }
```

For the installed adapter, read through `self._get_env("EVOLVE_SESSION_ID")`. For the candidate adapter, read `os.environ` inside `MODEL_SETUP` and add `EVOLVE_SESSION_ID` to `_source_env()` only when supplied through the Harbor agent environment.

- [ ] **Step 5: Run session tests and verify GREEN**

Run the Step 3 command. Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/evolve/integrations/harbor/miniswe_task_file.py \
  src/evolve/integrations/harbor/miniswe_candidate.py \
  tests/test_harbor_file_agent.py tests/test_miniswe_harbor_wrapper.py
git commit -m "fix: make MiniSWE session metadata optional"
```

### Task 4: Make the AHE Meta-Agent Prompt Target-Neutral

**Files:**
- Modify: `library/meta_agent/ahe.py:20-51`
- Test: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Consumes: existing `workspace_contract(checkout, ctx.config)` output and mutable surface.
- Produces: an AHE prompt that describes the configured candidate harness without MiniSWE, `DefaultAgent`, `mini`, or fixed target-path assumptions.
- Preserves: evidence-reading order, KEEP/REVISE/ROLLBACK decision, one coherent change, manifest requirements, and evaluation-boundary protections.

- [ ] **Step 1: Write the failing target-neutral prompt contract**

Replace MiniSWE-specific positive assertions with semantic positive and negative assertions:

```python
def test_ahe_prompt_is_target_neutral(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    prompt = module.build_prompt(checkout, "fallback", ctx)

    for required in (
        "configured candidate harness",
        "declared mutable surface",
        "Runtime prompt/config: `target/src/minisweagent/config/mini.yaml`",
        "KEEP",
        "REVISE",
        "ROLLBACK + PIVOT",
        "target/.ahe-change-manifest.json",
    ):
        assert required in prompt
    for forbidden in (
        "Improve the MiniSWE harness",
        "`DefaultAgent`",
        "`mini` configuration",
        "Make one coherent target/** change",
    ):
        assert forbidden not in prompt
```

Keep the existing assertions proving that evidence bodies and evolution-only context are not copied into the runtime prompt.

- [ ] **Step 2: Run the focused AHE tests and verify RED**

Run:

```bash
pytest -q tests/test_ahe_meta_agent.py
```

Expected: target-neutral assertions fail against the current MiniSWE-specific prompt.

- [ ] **Step 3: Rewrite only the permanent AHE instructions**

Change `AHE_PROMPT` so it:

- addresses the configured candidate harness;
- tells the editor to follow the workspace contract and declared mutable surface;
- asks it to identify the actual active execution path before editing;
- retains evidence-versus-causality and pivot guidance; and
- prohibits copying evolution-only artifacts into runtime files.

Do not add target-specific configuration or alter manifest parsing, patch creation, evidence paths, or runner behavior.

- [ ] **Step 4: Run the focused AHE tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git commit -m "refactor: make AHE prompt target-neutral"
```

### Task 5: Full Regression and Boundary Verification

**Files:**
- Verify only; modify implementation or tests only when a failing assertion exposes a regression in Tasks 1-4.

**Interfaces:**
- Consumes: all preceding task deliverables.
- Produces: evidence that framework tests, recipe initialization, static checks, and suffix-removal requirements hold together.

- [ ] **Step 1: Run all directly affected tests**

```bash
pytest -q \
  tests/test_harbor_file_agent.py \
  tests/test_miniswe_harbor_wrapper.py \
  tests/test_harbor_meta_agent.py \
  tests/test_m5_operator_runner.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_trajectory_only_trace_analyzer.py \
  tests/test_ahe_meta_agent.py \
  tests/test_phase_e_recipes.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_hyperagents_harbor_recipe.py \
  tests/test_recipe_composition.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_patching.py \
  tests/test_harbor_evaluator_config.py \
  tests/test_harbor_evaluator_template.py
```

Expected: all selected tests pass with no warnings introduced by these changes.

- [ ] **Step 2: Run the complete test suite**

```bash
pytest -q
```

Expected: zero failures.

- [ ] **Step 3: Run lint and hardcoding boundary checks**

```bash
ruff check src library tests
rg -n 'endswith\(.*(MiniSweSourceAgent|FileTaskMiniSweAgent)' src library
rg -n 'Improve the MiniSWE harness|DefaultAgent.*mini configuration' library/meta_agent/ahe.py
git diff --check
```

Expected: Ruff succeeds; both searches return no matches; `git diff --check` succeeds.

- [ ] **Step 4: Review the final diff for scope**

```bash
git diff --stat HEAD~4..HEAD
git diff HEAD~4..HEAD -- recipes scripts
```

Expected: only identifier/name changes appear under `recipes/`; no `scripts/` changes appear.

- [ ] **Step 5: Record any verification-only correction**

If Steps 1-4 required a correction, rerun the failing command and commit only that correction:

```bash
git add <corrected-files>
git commit -m "fix: close MiniSWE adapter contract regression"
```

If no correction was required, do not create an empty commit.
