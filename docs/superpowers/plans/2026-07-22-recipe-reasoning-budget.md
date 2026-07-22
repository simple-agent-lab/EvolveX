# Recipe Reasoning and Budget Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the AHE and HyperAgents Terminal-Bench 2.0 recipes apply their intended reasoning-effort policy and remove all agent and experiment cost caps, while preserving a separate investigation of the remaining benchmark gap.

**Architecture:** Recipe YAML owns the policy: AHE uses `xhigh` for its meta-agent and `high` for its target agent; HyperAgents uses `high` for both. Both custom MiniSWE Harbor adapter templates forward the target-agent setting and share one embedded model-construction helper between model preflight and the real runner. The helper validates the effort, selects MiniSWE's Responses-backed model for OpenAI reasoning requests, and places reasoning under `model_kwargs.reasoning.effort`.

**Tech Stack:** Python 3.11+, pytest, PyYAML, Harbor, MiniSWEAgent, LiteLLM, OpenAI Responses API

---

## Guardrails

- Preserve the pre-existing `UV_LINK_MODE=copy` edits in both adapter templates and their test; they are unrelated user work.
- Do not infer that these configuration corrections explain the full accuracy gap. A clean post-change trajectory canary proves configuration delivery only.
- Do not launch a paid full-89 benchmark as part of implementation. Run the canary and broader parity audit as an explicitly authorized follow-up.
- Before every commit touching an already-dirty file, stage only the reasoning/budget hunks and inspect `git diff --cached`; leave the pre-existing UV hunks unstaged.

### Task 1: Encode and test recipe-level reasoning and no-cap policy

**Files:**
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_m9_ahe_recipe.py`
- Modify: `tests/test_hyperagents_harbor_recipe.py`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`

- [ ] **Step 1: Add failing policy assertions for the AHE recipe**

In `tests/test_phase_e_recipes.py`, import `yaml`, add a `_parsed_config(name)` helper using `yaml.safe_load`, then parse `recipes/ahe/evolve.yaml` and assert the structured values rather than matching loose text:

```python
meta_agent = recipe["operators"]["meta_agent"]
assert meta_agent["agent_kwargs"] == {
    "reasoning_effort": "xhigh",
    "cost_limit": 0,
}

agent_env = recipe["evaluator"]["agent_env"]
assert agent_env["MINISWE_REASONING_EFFORT"] == "high"
assert agent_env["MINISWE_COST_LIMIT"] == "0"
```

Update `tests/test_m9_ahe_recipe.py` so its expected initialized Harbor agent environment is exactly:

```text
MINISWE_COST_LIMIT=0
MINISWE_ENV_TIMEOUT=30
MINISWE_REASONING_EFFORT=high
MINISWE_STEP_LIMIT=100
```

- [ ] **Step 2: Add failing policy assertions for the HyperAgents recipe**

In `tests/test_phase_e_recipes.py`, assert:

```python
meta_agent = recipe["operators"]["meta_agent"]
assert meta_agent["agent_kwargs"] == {
    "reasoning_effort": "high",
    "cost_limit": 0,
}

assert "budget_usd" not in recipe["experiment"]
assert recipe["evaluator"]["agent_env"] == {
    "MINISWE_REASONING_EFFORT": "high",
    "MINISWE_COST_LIMIT": "0",
}
```

In `tests/test_hyperagents_harbor_recipe.py`, add or update the initialization assertion so the target-agent environment emitted by the recipe is:

```text
MINISWE_COST_LIMIT=0
MINISWE_REASONING_EFFORT=high
```

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py
```

Expected: failures show missing `agent_kwargs`, missing target reasoning variables, AHE's old `3.0` cap, and HyperAgents' old `budget_usd: 150` cap.

- [ ] **Step 4: Apply the smallest recipe changes**

In `recipes/ahe/evolve.yaml`, add to `operators.meta_agent`:

```yaml
agent_kwargs: {reasoning_effort: xhigh, cost_limit: 0}
```

Change the evaluator environment to:

```yaml
agent_env:
  MINISWE_STEP_LIMIT: "100"
  MINISWE_REASONING_EFFORT: "high"
  MINISWE_COST_LIMIT: "0"
  MINISWE_ENV_TIMEOUT: "30"
```

In `recipes/hyperagents/evolve.yaml`:

- remove `experiment.budget_usd`;
- add `agent_kwargs: {reasoning_effort: high, cost_limit: 0}` to `operators.meta_agent`;
- add:

```yaml
agent_env:
  MINISWE_REASONING_EFFORT: "high"
  MINISWE_COST_LIMIT: "0"
```

- [ ] **Step 5: Run the focused tests and confirm GREEN**

Run:

```bash
uv run pytest -q tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit only Task 1 changes**

```bash
git add recipes/ahe/evolve.yaml recipes/hyperagents/evolve.yaml tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py
git diff --cached --check
git diff --cached
git commit -m "fix: configure recipe reasoning and budgets"
```

### Task 2: Make target MiniSWE model construction honor reasoning effort

**Files:**
- Modify: `tests/test_miniswe_harbor_wrapper.py`
- Modify: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `templates/workspace/evolve_harbor_adapter/__init__.py`

- [ ] **Step 1: Parameterize adapter-template coverage**

Keep the existing workspace-template integration tests, and add a parametrized path fixture for the new equivalence tests so both source templates are covered:

```python
ADAPTER_TEMPLATES = (
    ROOT / "templates" / "target" / "harbor" / "miniswe_source_agent.py",
    ROOT / "templates" / "workspace" / "evolve_harbor_adapter" / "__init__.py",
)

@pytest.fixture(params=ADAPTER_TEMPLATES, ids=("target", "workspace"))
def adapter_path(request):
    return request.param
```

Each new test installs the existing fake Harbor modules and loads `adapter_path` with `_load(adapter_path)`. Retain the user's existing `UV_LINK_MODE == "copy"` assertion and the current workspace-template integration coverage unchanged.

- [ ] **Step 2: Add failing environment-forwarding tests**

Set `MINISWE_REASONING_EFFORT=high` in the source environment, instantiate `adapter_module.MiniSweSourceAgent`, call the agent's existing `_source_env()`, and assert:

```python
assert source_env["MINISWE_REASONING_EFFORT"] == "high"
```

Also assert that an absent variable remains absent, matching the current forwarding behavior.

- [ ] **Step 3: Add failing model-factory tests for both templates**

Install fake modules in `sys.modules` for:

- `minisweagent.models.litellm_model.LitellmModel`;
- `minisweagent.models.litellm_model.LitellmModelConfig` with representative `model_fields`;
- `minisweagent.models.litellm_response_model.LitellmResponseModel`.

Execute `adapter_module.MODEL_SETUP` into an isolated namespace and test its `build_model(config)` function.

For `MSWEA_MODEL_NAME=openai/gpt-5.4` and `MINISWE_REASONING_EFFORT=high`, assert:

```python
assert isinstance(model, FakeLitellmResponseModel)
assert model.kwargs["model_name"] == "openai/gpt-5.4"
assert model.kwargs["cost_tracking"] == "ignore_errors"
assert model.kwargs["model_kwargs"]["reasoning"] == {"effort": "high"}
assert "reasoning_effort" not in model.kwargs["model_kwargs"]
```

Pass a legacy `model_kwargs.reasoning_effort` in the input config so the final assertion proves it is removed rather than duplicated.

Add three more cases:

1. No `MINISWE_REASONING_EFFORT` selects `FakeLitellmModel` and preserves ordinary model kwargs.
2. A non-OpenAI model with a valid effort selects `FakeLitellmModel` without injecting OpenAI reasoning kwargs.
3. An invalid effort such as `maximum` raises `ValueError` containing the accepted values `none`, `low`, `medium`, `high`, and `xhigh`.

- [ ] **Step 4: Add failing preflight/runner construction-parity assertions**

Assert both embedded programs contain the same shared setup text and call the same factory:

```python
assert adapter_module.RUNNER.startswith(adapter_module.MODEL_SETUP)
assert adapter_module.MODEL_PREFLIGHT.startswith(adapter_module.MODEL_SETUP)
assert "model = build_model(config)" in adapter_module.RUNNER
assert "build_model(config)" in adapter_module.MODEL_PREFLIGHT
```

- [ ] **Step 5: Run the focused test and confirm RED**

Run:

```bash
uv run pytest -q tests/test_miniswe_harbor_wrapper.py
```

Expected: failures show that reasoning is not forwarded, `MODEL_SETUP` does not exist, and runner/preflight still instantiate `LitellmModel` separately.

- [ ] **Step 6: Add the shared model setup to both adapter templates**

In each adapter template, define one embedded source string before `RUNNER`:

```python
MODEL_SETUP = r'''
import os

from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

VALID_REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh")


def _filtered(values, allowed):
    return {key: value for key, value in (values or {}).items() if key in allowed}


def _reasoning_effort():
    effort = os.environ.get("MINISWE_REASONING_EFFORT", "").strip().lower()
    if not effort:
        return None
    if effort not in VALID_REASONING_EFFORTS:
        accepted = ", ".join(VALID_REASONING_EFFORTS)
        raise ValueError(
            f"Invalid MINISWE_REASONING_EFFORT={effort!r}; expected one of: {accepted}"
        )
    return effort


def build_model(config):
    model_name = os.environ["MSWEA_MODEL_NAME"]
    effort = _reasoning_effort()
    model_kwargs = _filtered(config.get("model"), LitellmModelConfig.model_fields)
    model_kwargs["model_name"] = model_name
    model_kwargs["cost_tracking"] = "ignore_errors"

    model_class = LitellmModel
    if model_name.startswith("openai/") and effort is not None:
        from minisweagent.models.litellm_response_model import LitellmResponseModel

        nested_kwargs = dict(model_kwargs.get("model_kwargs") or {})
        nested_kwargs.pop("reasoning_effort", None)
        nested_kwargs["reasoning"] = {"effort": effort}
        model_kwargs["model_kwargs"] = nested_kwargs
        model_class = LitellmResponseModel

    return model_class(**model_kwargs)
'''.strip()
```

Compose both programs from this string without formatting it:

```python
RUNNER = (MODEL_SETUP + r'''
# existing runner body
''').strip()

MODEL_PREFLIGHT = (MODEL_SETUP + r'''
# existing preflight body
''').strip()
```

In `RUNNER`, replace the direct `LitellmModel(...)` construction with:

```python
model = build_model(config)
agent = DefaultAgent(model, LocalEnvironment(**env_kwargs), **agent_kwargs)
```

In `MODEL_PREFLIGHT`, call `build_model(config)` instead of rebuilding kwargs independently. Remove imports and helper definitions made redundant by `MODEL_SETUP`.

- [ ] **Step 7: Forward the target reasoning variable in both adapters**

Add `MINISWE_REASONING_EFFORT` to the existing forwarded-variable tuple:

```python
for key in (
    "MINISWE_STEP_LIMIT",
    "MINISWE_COST_LIMIT",
    "MINISWE_ENV_TIMEOUT",
    "MINISWE_REASONING_EFFORT",
):
```

- [ ] **Step 8: Run the focused test and confirm GREEN**

Run:

```bash
uv run pytest -q tests/test_miniswe_harbor_wrapper.py
```

Expected: both template variants pass every forwarding, model-selection, validation, and parity case.

- [ ] **Step 9: Stage only reasoning-related hunks and commit**

Because all three files contain pre-existing UV-link edits, use patch staging and decline every UV-only hunk:

```bash
git add -p templates/target/harbor/miniswe_source_agent.py
git add -p templates/workspace/evolve_harbor_adapter/__init__.py
git add -p tests/test_miniswe_harbor_wrapper.py
git diff --cached --check
git diff --cached
git commit -m "fix: propagate MiniSWE reasoning effort"
```

The cached diff must contain only reasoning/model-factory changes. Verify the UV changes remain in `git diff` after the commit.

### Task 3: Verify initialization, regression safety, and policy consistency

**Files:**
- Verify: `recipes/ahe/evolve.yaml`
- Verify: `recipes/hyperagents/evolve.yaml`
- Verify: `templates/target/harbor/miniswe_source_agent.py`
- Verify: `templates/workspace/evolve_harbor_adapter/__init__.py`
- Verify: `tests/`

- [ ] **Step 1: Run YAML and recipe initialization coverage**

```bash
uv run pytest -q tests/test_phase_e_recipes.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py tests/test_harbor_evaluator_config.py
```

Expected: all tests pass; initialized evaluator configuration contains the exact intended environment for each recipe.

- [ ] **Step 2: Run all adapter and source-agent coverage**

```bash
uv run pytest -q tests/test_miniswe_harbor_wrapper.py tests/test_miniswe_source_agent_command.py
```

Expected: all tests pass for both adapter templates, including the pre-existing UV-link behavior.

- [ ] **Step 3: Run the complete local test suite**

```bash
uv run pytest -q
```

Expected: full suite passes with no regressions.

- [ ] **Step 4: Perform static policy checks**

```bash
rg -n "reasoning_effort|MINISWE_REASONING_EFFORT|MINISWE_COST_LIMIT|budget_usd" recipes/ahe recipes/hyperagents templates/target/harbor/miniswe_source_agent.py templates/workspace/evolve_harbor_adapter/__init__.py
```

Confirm:

- AHE meta-agent is `xhigh` and target agent is `high`;
- HyperAgents meta-agent and target agent are `high`;
- both agent layers use zero cost limit;
- HyperAgents has no experiment-wide `budget_usd`;
- both target adapters forward and validate the same reasoning variable.

- [ ] **Step 5: Inspect final repository state**

```bash
git status --short
git log -3 --oneline
```

Expected: only the user's pre-existing UV-link changes remain unstaged; the reasoning/budget commits are present.

### Task 4: Run a paid trajectory canary and a separate benchmark-parity audit

**Files:**
- Inspect remotely: new AHE and HyperAgents canary run directories on DevBoxS
- Compare remotely: canonical prior runs and the independently configured Terminal-Bench 2.0 experiment
- Document findings in a new dated audit artifact only after the user authorizes execution

- [ ] **Step 1: Obtain explicit authorization for paid remote execution**

Confirm the desired canary size and whether to run one task per recipe or a small stratified subset. Do not start a benchmark before this confirmation.

- [ ] **Step 2: Deploy the committed configuration to an isolated DevBoxS checkout**

Use a new run directory and immutable commit identifier. Record the resolved recipe, framework commit, MiniSWEAgent version, Harbor version, model name, API base, and environment image digest before running.

- [ ] **Step 3: Run the smallest useful canary for both recipes**

For AHE, verify the meta-agent request uses `xhigh` and target requests use `high`. For HyperAgents, verify both layers use `high`. Verify no run stops because of agent or experiment cost caps.

- [ ] **Step 4: Inspect raw trajectories rather than relying on aggregate accuracy**

For every canary trajectory, verify:

- the recorded request or provider payload contains the intended reasoning effort;
- OpenAI target calls follow the Responses-backed model path;
- `reasoning_tokens` are recorded when the provider returns them;
- tool calls, command outputs, completion status, and grader results are intact;
- no silent fallback model or incompatible API mode was selected.

- [ ] **Step 5: Run the independent parity audit**

Compare the canary and the other correctly configured low-performing experiment against the closest official Codex + GPT-5.4 Terminal-Bench 2.0 setup across:

1. exact benchmark task set and dataset revision;
2. container/runtime image and task setup;
3. model snapshot, endpoint, API mode, and reasoning payload;
4. agent prompt, tool schema, command timeout, context handling, and step limits;
5. retry, failure classification, parser, and grader behavior;
6. per-task failure clusters: setup/infrastructure, timeout, tool misuse, premature completion, context exhaustion, and incorrect solution.

Treat the public leaderboard range as a comparison target, not as an acceptance test for this configuration patch.

- [ ] **Step 6: Produce two separate conclusions**

Report independently:

- **Configuration delivery:** whether the intended efforts and no-cap policy reached real requests.
- **Performance diagnosis:** which remaining parity differences and failure modes plausibly explain the accuracy gap, with counts and representative trajectories.
