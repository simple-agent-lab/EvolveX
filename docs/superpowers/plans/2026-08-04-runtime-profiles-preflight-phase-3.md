# Runtime Profiles and Preflight Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build framework-owned, immutable runtime profiles and mandatory typed preflight for future experiments, using ByteDance GPT-5.4 API-key authentication without touching existing or historical experiments.

**Architecture:** Two capability-based profiles resolve into canonical generation-zero JSON and feed the evaluation contract, a shared role-aware environment planner, ordinary preflight, and isolated smoke. Python owns identity, credential, proxy, dependency, and receipt policy; generated shell code only translates validated inputs into process arguments. Legacy workspaces remain explicitly unverified and retain their vendored behavior.

**Tech Stack:** Python 3.12, frozen dataclasses, Typer, PyYAML, Harbor, `uv`, Docker, POSIX shell, pytest, Ruff, and ty.

## Global Constraints

- This phase applies only to future generated workspaces; existing and historical experiment directories, scripts, commits, artifacts, and reports are never modified or migrated.
- Future model-backed execution uses the ByteDance GPT-5.4 OpenAI-compatible endpoint through `OPENAI_API_KEY` and `OPENAI_BASE_URL`.
- Codex `auth.json` is unavailable and is neither required, inspected, synthesized, nor used as a fallback.
- The strict profile names are exactly `harbor-bytedance-v1` and `harbor-bytedance-uv-v1`.
- `harbor-bytedance-uv-v1` uses a frozen `uv` project at `target` with Python `3.12` and offline trial execution.
- Ordinary preflight is read-only and makes no network request; smoke is separate, isolated, and may perform one minimal live model request.
- Secrets never enter contracts, profile files, receipts, diagnostics, command records, logs, or hashes.
- Raw endpoint and proxy values never appear in persisted artifacts; the normalized endpoint is used only to calculate the model-route digest and is then discarded.
- Shared runtime code never branches on `aevolve`, `ahe`, `gepa`, `hill_climb`, or `hyperagents`.
- Existing `evaluator.candidate_runtime` remains a named legacy compatibility input; strict future recipes write only `evaluator.runtime.profile`.
- New experiment-specific launchers, YAML patching, inline migration snippets, and hidden auth fallbacks are prohibited.
- `repetitions` remains configurable from `1` through `100` and defaults to `1`.
- Uncertainty-aware champion selection and statistical confidence intervals remain out of scope.

---

## File structure

Create three framework modules with one responsibility each:

- `src/evolve/runtime_profiles.py`: profile types, registry, route normalization, resolution, serialization, and hashing.
- `src/evolve/runtime_environment.py`: role-specific credential/proxy environment planning and safe Harbor templates.
- `src/evolve/preflight.py`: check execution, result schema, failure categories, receipt writing, and smoke delegation.

Keep candidate dependency installation in `src/evolve/uv_runtime.py`, candidate snapshot behavior in `src/evolve/candidate/smoke.py`, and evaluation orchestration in `src/evolve/evaluation/execution.py`. Those modules consume the new interfaces; they do not duplicate profile policy.

---

### Task 1: Define immutable runtime profiles and strict configuration normalization

**Files:**
- Create: `src/evolve/runtime_profiles.py`
- Modify: `src/evolve/evaluator_config.py:7-28`
- Modify: `src/evolve/workspace.py:588-595`
- Create: `tests/test_runtime_profiles.py`
- Modify: `tests/test_config_parser.py`

**Interfaces:**
- Consumes: `evaluator.runtime.profile`, `EVOLVE_RUNTIME_DIGEST`, `OPENAI_BASE_URL`, and canonical JSON hashing.
- Produces: `RuntimeProfileV1`, `ResolvedRuntimeProfileV1`, `RuntimeProfileResolutionError`, `runtime_profile(name: str) -> RuntimeProfileV1`, `normalize_model_route(url: str) -> str`, `model_route_digest(url: str) -> str`, `resolved_runtime_profile_payload(profile: ResolvedRuntimeProfileV1) -> dict[str, object]`, `resolve_runtime_profile(config: Mapping[str, object], runtime_digest: str, environment: Mapping[str, str]) -> ResolvedRuntimeProfileV1 | None`, and `load_resolved_runtime_profile(payload: object) -> ResolvedRuntimeProfileV1`.

- [ ] **Step 1: Write failing profile and route-identity tests**

```python
def test_strict_profiles_are_capability_based_and_versioned() -> None:
    basic = runtime_profile("harbor-bytedance-v1")
    uv = runtime_profile("harbor-bytedance-uv-v1")
    assert basic.candidate_runtime is None
    assert uv.candidate_runtime == CandidateRuntimePolicy("uv", "target", "3.12")
    assert basic.forbidden_credentials == ("CODEX_AUTH_JSON_PATH", "CODEX_FORCE_AUTH_JSON")


def test_route_digest_normalizes_equivalent_urls_without_persisting_url() -> None:
    first = model_route_digest("https://MODEL.EXAMPLE/v1/")
    second = model_route_digest("https://model.example/v1")
    assert first == second
    resolved = resolve_runtime_profile(
        strict_config("harbor-bytedance-v1"),
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert resolved is not None
    assert "model.example" not in json.dumps(resolved.to_dict())
    assert resolved.model_route_digest == first
```

Define the test configuration helper in the same file:

```python
def strict_config(profile: str) -> dict[str, object]:
    return {
        "experiment": {"id": "test"},
        "target": {"seed": "builtin-codex"},
        "surface": {"include": ["target/**"], "exclude": []},
        "operators": {"meta_agent": {"agent": "codex"}},
        "evaluator": {
            "engine": "harbor",
            "agent": "target.agent:HarborAgent",
            "runtime": {"profile": profile},
        },
    }
```

Also test rejection of userinfo, query strings, fragments, schemes other than HTTP/HTTPS, unknown profile names, unknown `runtime` fields, a strict profile combined with `candidate_runtime`, and credential/proxy keys embedded in either evaluator or meta-agent `agent_env`.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/test_runtime_profiles.py tests/test_config_parser.py -q`

Expected: FAIL because `evolve.runtime_profiles` and strict runtime normalization do not exist.

- [ ] **Step 3: Implement the profile types, registry, and route digest**

Use these public type names and values:

```python
class RuntimeProfileResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateRuntimePolicy:
    variant: str
    project: str
    python: str


@dataclass(frozen=True)
class RuntimeProfileV1:
    schema_version: int
    name: str
    engine: str
    model_route: str
    required_credentials_by_role: tuple[tuple[str, tuple[str, ...]], ...]
    forbidden_credentials: tuple[str, ...]
    required_tools: tuple[str, ...]
    candidate_runtime: CandidateRuntimePolicy | None
    dependency_policy: str
    cache_policy: str
    network_policy: str
    proxy_policy: str
    model_bypass_policy: str
    preflight_capabilities: tuple[str, ...]
    smoke_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedRuntimeProfileV1:
    profile: RuntimeProfileV1
    runtime_digest: str
    model_route_digest: str
    profile_digest: str

    def to_dict(self) -> dict[str, object]:
        return resolved_runtime_profile_payload(self)
```

Normalize routes by lowercasing scheme and hostname, removing a trailing slash from the path, rejecting username/password/query/fragment, accepting only HTTP or HTTPS, and hashing the normalized string with SHA-256. Build `profile_digest` from canonical JSON containing the profile payload, runtime digest, and model-route digest. Do not retain the normalized URL on either dataclass.

Configure both profiles with roles `agent` and `meta_agent`, required names `OPENAI_API_KEY` and `OPENAI_BASE_URL`, forbidden names `CODEX_AUTH_JSON_PATH` and `CODEX_FORCE_AUTH_JSON`, model route `bytedance-openai-compatible`, proxy policy `dependency-proxy-model-bypass`, and smoke capability `one-model-request`. Add `candidate_runtime` only to the UV profile.

- [ ] **Step 4: Normalize evaluator configuration structurally**

Extend `normalize_evaluator_config()` to validate `runtime` as a mapping containing only a non-empty string `profile`, preserve it in rendered YAML, reject the strict/legacy conflict, and keep omitted runtime configuration as legacy compatibility. Extend `_validate_evaluator_config()` to invoke the same validator before target preparation.

- [ ] **Step 5: Run the profile and parser tests**

Run: `uv run pytest tests/test_runtime_profiles.py tests/test_config_parser.py -q`

Expected: PASS.

- [ ] **Step 6: Run static checks for the new module**

Run: `uv run ruff check src/evolve/runtime_profiles.py src/evolve/evaluator_config.py tests/test_runtime_profiles.py`

Run: `uv run ty check src/evolve/runtime_profiles.py src/evolve/evaluator_config.py`

Expected: both commands pass.

- [ ] **Step 7: Commit the profile boundary**

```bash
git add src/evolve/runtime_profiles.py src/evolve/evaluator_config.py src/evolve/workspace.py tests/test_runtime_profiles.py tests/test_config_parser.py
git commit -m "feat: define immutable runtime profiles"
```

---

### Task 2: Generate resolved profiles automatically and migrate future recipes

**Files:**
- Modify: `src/evolve/workspace.py:175-286,543-588`
- Create: `scaffolds/workspace/operators/preflight.sh`
- Modify: `recipes/aevolve/evolve.yaml`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/gepa/evolve.yaml`
- Modify: `recipes/hill_climb/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `tests/conftest.py:29-34`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_phase_e_recipes.py:184-191`
- Modify: `tests/test_contract_recipe_conformance.py`

**Interfaces:**
- Consumes: `resolve_runtime_profile()` from Task 1.
- Produces: committed `evaluator/runtime-profile.json`, matching `evaluator/runtime.pin`, executable generated `operators/preflight.sh`, shared test helpers `write_identity_dataset(root: Path, count: int = 10) -> Path` and `init_recipe_with_local_inputs(tmp_path: Path, recipe: str) -> Path`, and pytest fixtures `strict_workspace` and `legacy_workspace`.

- [ ] **Step 1: Write failing workspace-generation tests**

```python
@pytest.mark.parametrize(
    ("recipe", "profile"),
    [
        ("aevolve", "harbor-bytedance-v1"),
        ("ahe", "harbor-bytedance-uv-v1"),
        ("gepa", "harbor-bytedance-v1"),
        ("hill_climb", "harbor-bytedance-uv-v1"),
        ("hyperagents", "harbor-bytedance-uv-v1"),
    ],
)
def test_init_generates_canonical_resolved_runtime_profile(tmp_path: Path, recipe: str, profile: str) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, recipe)
    payload = json.loads((workspace / "evaluator/runtime-profile.json").read_text())
    assert payload["name"] == profile
    assert payload["runtime_digest"] == "sha256:test-runtime"
    assert payload["profile_digest"]
    assert "model.example" not in json.dumps(payload)
    assert git(workspace, "show", "gen/0:evaluator/runtime-profile.json")
```

Add a compatibility test proving a custom recipe with no `runtime.profile` gets `runtime.pin` but no `runtime-profile.json`. Add a shell test proving generated `operators/preflight.sh` contains only root discovery and `exec "$ROOT/evolve" preflight "$ROOT" "$@"`.

Add these helpers to `tests/conftest.py` so all profile/conformance tests use the same local inputs:

```python
UV_SOURCE_RECIPES = {"ahe", "hill_climb", "hyperagents"}


def write_identity_dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def init_recipe_with_local_inputs(tmp_path: Path, recipe: str) -> Path:
    dataset = write_identity_dataset(tmp_path / f"{recipe}-tasks")
    seed = (
        write_locked_miniswe_seed(tmp_path / f"{recipe}-seed")
        if recipe in UV_SOURCE_RECIPES
        else None
    )
    workspace = tmp_path / f"workspace-{recipe}"
    create_workspace(
        InitOptions(
            workspace=workspace,
            recipe=recipe,
            seed=str(seed) if seed is not None else None,
            dataset=str(dataset),
        )
    )
    return workspace


@pytest.fixture
def strict_workspace(tmp_path: Path) -> Path:
    return init_recipe_with_local_inputs(tmp_path, "aevolve")


@pytest.fixture
def legacy_workspace(tmp_path: Path) -> Path:
    return init_fixture_workspace(tmp_path / "legacy-workspace")
```

- [ ] **Step 2: Run generation tests and verify failure**

Run: `uv run pytest tests/test_m0_init.py tests/test_phase_e_recipes.py tests/test_contract_recipe_conformance.py -q`

Expected: FAIL because no resolved profile file is generated and recipes still use legacy candidate runtime fields.

- [ ] **Step 3: Resolve and write the profile in one workspace operation**

In `_write_files()`, resolve the profile once from the complete configuration, `EVOLVE_RUNTIME_DIGEST`, and current environment. Add `evaluator/runtime-profile.json` only when resolution returns a strict profile. Serialize with `json.dumps(resolved.to_dict(), indent=2, sort_keys=True) + "\n"`. Keep `runtime.pin` and assert its text equals the resolved payload's runtime digest.

Replace the placeholder preflight shell source with `scaffolds/workspace/operators/preflight.sh`:

```sh
#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/.." && pwd)
exec "$ROOT/evolve" preflight "$ROOT" "$@"
```

- [ ] **Step 4: Migrate only source recipes**

Write `runtime: {profile: harbor-bytedance-v1}` for AEvolve and GEPA. Write `runtime: {profile: harbor-bytedance-uv-v1}` for AHE, hill-climb, and HyperAgents. Remove `candidate_runtime` from those five source recipes. Do not edit any file under `experiments/`, `analysis_artifacts/`, `analysis_selected/`, or `scripts/`.

- [ ] **Step 5: Give tests a non-secret route identity**

Extend the autouse fixture in `tests/conftest.py`:

```python
if os.environ.get("EVOLVE_LIVE_BYTEDANCE_SMOKE") != "1":
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.example/v1")
monkeypatch.delenv("CODEX_AUTH_JSON_PATH", raising=False)
monkeypatch.delenv("CODEX_FORCE_AUTH_JSON", raising=False)
```

Update recipe assertions to check profile names and absence of `candidate_runtime`.

- [ ] **Step 6: Run workspace and recipe tests**

Run: `uv run pytest tests/test_m0_init.py tests/test_phase_e_recipes.py tests/test_contract_recipe_conformance.py -q`

Expected: PASS.

- [ ] **Step 7: Commit automatic profile generation**

```bash
git add src/evolve/workspace.py scaffolds/workspace/operators/preflight.sh recipes tests/conftest.py tests/test_m0_init.py tests/test_phase_e_recipes.py tests/test_contract_recipe_conformance.py
git commit -m "feat: generate resolved runtime profiles"
```

---

### Task 3: Bind Evaluation Contract v1 to the resolved runtime policy

**Files:**
- Modify: `src/evolve/evaluation/contract.py:116-175,220-247,300-350`
- Modify: `src/evolve/uv_runtime.py:108-135`
- Modify: `tests/conftest.py`
- Modify: `tests/test_evaluation_contract.py`
- Modify: `tests/test_evaluation_contract_execution.py`
- Modify: `tests/test_locked_runtime.py`

**Interfaces:**
- Consumes: trusted generation-zero `runtime-profile.json` and `load_resolved_runtime_profile()`.
- Produces: contract runtime/profile fields derived from the complete resolved payload, model route name/digest, profile-derived candidate dependency identity, and test helper `contract_for_gen0(workspace: Path) -> EvaluationContractV1`.

- [ ] **Step 1: Write failing contract-binding tests**

```python
def test_contract_hashes_complete_resolved_runtime_profile(strict_workspace: Path) -> None:
    contract = contract_for_gen0(strict_workspace)
    profile = json.loads(git(strict_workspace, "show", "gen/0:evaluator/runtime-profile.json"))
    assert contract.runtime_profile == profile["name"]
    assert contract.runtime_profile_digest == profile["profile_digest"]
    assert contract.runtime_digest == profile["runtime_digest"]
    assert contract.model_identity["route"] == "bytedance-openai-compatible"
    assert contract.model_identity["route_digest"] == profile["model_route_digest"]


def test_contract_mode_is_legacy_without_resolved_profile(legacy_workspace: Path) -> None:
    assert evaluation_contract_mode(legacy_workspace) is ContractMode.LEGACY_UNVERIFIED
```

Add mismatch cases for profile digest, route digest, and `runtime.pin`, plus a test that UV candidate dependency identity is derived from profile policy when the YAML has no `candidate_runtime`.

Define the shared contract helper in `tests/conftest.py`:

```python
def contract_for_gen0(workspace: Path) -> evaluation_package.EvaluationContractV1:
    commit = git(workspace, "rev-parse", "gen/0^{commit}")
    return evaluation_package.resolve_evaluation_contract(
        evaluation_package.ContractResolutionContext(
            workspace=workspace,
            candidate_commit=commit,
            purpose="candidate",
            generation="0",
        )
    )
```

Import it from `conftest` in contract and conformance tests.

Update the file's existing `_strict_workspace()` configuration to select `harbor-bytedance-v1` and remove `OPENAI_API_KEY` from `agent_env`; keep only non-protected `STEP_LIMIT` there. Read credentials from the autouse environment fixture.

- [ ] **Step 2: Run contract tests and verify failure**

Run: `uv run pytest tests/test_evaluation_contract.py tests/test_evaluation_contract_execution.py tests/test_locked_runtime.py -q`

Expected: FAIL because contract resolution still hashes only `legacy-pin` and `runtime.pin`.

- [ ] **Step 3: Replace legacy profile inference in strict contract resolution**

Add a trusted Git reader for `gen/0:evaluator/runtime-profile.json`, parse it with `load_resolved_runtime_profile()`, and verify:

```python
if profile.runtime_digest != runtime_digest:
    raise EvaluationContractResolutionError("runtime_digest", "runtime.pin does not match resolved profile")
```

Use `profile.profile.name`, `profile.profile_digest`, and `profile.runtime_digest` directly. Add route and route digest to `model_identity`. Make `evaluation_contract_mode()` strict only when both dataset content identity and a valid resolved profile exist.

- [ ] **Step 4: Derive candidate runtime config from the profile**

Change `candidate_runtime_config()` to load `checkout/evaluator/runtime-profile.json` when present and translate its `CandidateRuntimePolicy` into `UvRuntimeConfig`. Retain the current YAML path only when the profile file is absent. Reject a strict file plus a legacy YAML block.

- [ ] **Step 5: Run contract and runtime tests**

Run: `uv run pytest tests/test_evaluation_contract.py tests/test_evaluation_contract_execution.py tests/test_locked_runtime.py -q`

Expected: PASS.

- [ ] **Step 6: Commit contract/profile binding**

```bash
git add src/evolve/evaluation/contract.py src/evolve/uv_runtime.py tests/conftest.py tests/test_evaluation_contract.py tests/test_evaluation_contract_execution.py tests/test_locked_runtime.py
git commit -m "feat: bind contracts to runtime profiles"
```

---

### Task 4: Centralize role-specific endpoint and proxy planning

**Files:**
- Create: `src/evolve/runtime_environment.py`
- Create: `tests/test_runtime_environment.py`
- Modify: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: `ResolvedRuntimeProfileV1`, source environment, non-protected recipe agent/verifier settings.
- Produces: `RuntimeRole`, `RuntimeEnvironmentPlan`, `resolve_runtime_environment(profile, environment, *, agent_overrides=None, verifier_overrides=None) -> RuntimeEnvironmentPlan`, and `write_harbor_environment_inputs(run_dir: Path, plan: RuntimeEnvironmentPlan) -> None`.

- [ ] **Step 1: Write failing environment-planner tests**

```python
def test_environment_plan_uses_safe_templates_and_normalized_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    source = {
        "OPENAI_API_KEY": "sensitive-key-value",
        "OPENAI_BASE_URL": "https://model.example/v1",
        "HTTPS_PROXY": "http://user:password@proxy.example:8118",
        "NO_PROXY": "pypi.org,.internal.example",
    }
    plan = resolve_runtime_environment(resolved_profile(), source)
    assert plan.agent_env()["OPENAI_API_KEY"].startswith("${EVOLVE_RUNTIME_AGENT_")
    assert plan.agent_env()["OPENAI_BASE_URL"].startswith("${EVOLVE_RUNTIME_AGENT_")
    assert "model.example" in plan.process_env()["EVOLVE_RUNTIME_AGENT_NO_PROXY"]
    assert "pypi.org" not in plan.process_env()["EVOLVE_RUNTIME_AGENT_NO_PROXY"]
    serialized = json.dumps(plan.persisted_payload())
    assert "sensitive-key-value" not in serialized
    assert "model.example" not in serialized
    assert "password" not in serialized
```

Define the profile helper in the same test module:

```python
def resolved_profile() -> ResolvedRuntimeProfileV1:
    result = resolve_runtime_profile(
        {
            "experiment": {"id": "test"},
            "target": {"seed": "builtin-codex"},
            "surface": {"include": ["target/**"], "exclude": []},
            "operators": {"meta_agent": {"agent": "codex"}},
            "evaluator": {
                "engine": "harbor",
                "agent": "target.agent:HarborAgent",
                "runtime": {"profile": "harbor-bytedance-v1"},
            },
        },
        "sha256:runtime",
        {"OPENAI_BASE_URL": "https://model.example/v1"},
    )
    assert result is not None
    return result
```

Test identical upper/lowercase proxy values, configured model bypass, missing required names, forbidden Codex auth variables, invalid route digest, verifier separation, and output files containing templates only.

- [ ] **Step 2: Run the planner tests and verify failure**

Run: `uv run pytest tests/test_runtime_environment.py tests/test_harbor_evaluator_template.py -q`

Expected: FAIL because the shared planner does not exist.

- [ ] **Step 3: Implement immutable plan types**

```python
class RuntimeRole(StrEnum):
    AGENT = "agent"
    VERIFIER = "verifier"
    META_AGENT = "meta_agent"


@dataclass(frozen=True)
class RuntimeEnvironmentPlan:
    process_environment: tuple[tuple[str, str], ...]
    agent_environment: tuple[tuple[str, str], ...]
    verifier_environment: tuple[tuple[str, str], ...]
    meta_agent_environment: tuple[tuple[str, str], ...]
    evidence: tuple[tuple[str, object], ...]

    def process_env(self) -> dict[str, str]:
        return dict(self.process_environment)

    def agent_env(self) -> dict[str, str]:
        return dict(self.agent_environment)

    def verifier_env(self) -> dict[str, str]:
        return dict(self.verifier_environment)

    def meta_agent_env(self) -> dict[str, str]:
        return dict(self.meta_agent_environment)

    def persisted_payload(self) -> dict[str, object]:
        return {
            "agent_environment": self.agent_env(),
            "verifier_environment": self.verifier_env(),
            "meta_agent_environment": self.meta_agent_env(),
            "evidence": dict(self.evidence),
        }
```

For every actual value, place the value only in `process_environment` under a deterministic internal name such as `EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY`. Put `${EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY}` in the Harbor-facing mapping. Use the same pattern for endpoint and proxy values so persisted Harbor configurations contain templates, not raw values.

Remove `astral.sh`, `download.pytorch.org`, `files.pythonhosted.org`, `github.com`, `objects.githubusercontent.com`, and `pypi.org` from inherited bypass entries. Add the model hostname. Normalize uppercase and lowercase proxy names to the same value.

- [ ] **Step 4: Write safe Harbor input files**

Write `runtime-agent.env`, `runtime-verifier.env`, and `runtime-environment-evidence.json` atomically under `run_dir`. Environment files contain sorted `KEY=${INTERNAL_KEY}` assignments only. Reject newlines, equals signs in names, and any value that is not a single Harbor environment template.

- [ ] **Step 5: Run planner and security tests**

Run: `uv run pytest tests/test_runtime_environment.py tests/test_harbor_evaluator_template.py -q`

Expected: PASS.

- [ ] **Step 6: Run static checks**

Run: `uv run ruff check src/evolve/runtime_environment.py tests/test_runtime_environment.py`

Run: `uv run ty check src/evolve/runtime_environment.py`

Expected: both pass.

- [ ] **Step 7: Commit shared runtime environment planning**

```bash
git add src/evolve/runtime_environment.py tests/test_runtime_environment.py tests/test_harbor_evaluator_template.py
git commit -m "feat: centralize runtime environment policy"
```

---

### Task 5: Move future Codex execution to supported API-key authentication

**Files:**
- Modify: `seeds/codex/agent.py:1-90`
- Modify: `seeds/codex/README.md`
- Modify: `library/meta_agent/runners/harbor.py:57-69,606-677,1136-1205`
- Modify: `tests/test_m7_codex_seed.py:73-124`
- Modify: `tests/test_harbor_meta_agent.py:40-115,175-186`

**Interfaces:**
- Consumes: `load_resolved_runtime_profile()` and `resolve_runtime_environment()`.
- Produces: future Codex target/meta-agent execution through Harbor's existing API-key mode, with no local auth-file override, plus runner helper `_runtime_environment_plan(checkout: Path, config: Mapping[str, object]) -> RuntimeEnvironmentPlan`.

- [ ] **Step 1: Replace auth-file expectations with failing API-key tests**

```python
def test_builtin_codex_wrapper_inherits_harbor_api_key_mode(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_target_agent(workspace / "target/agent.py")
    assert "_resolve_auth_json_path" not in module.HarborAgent.__dict__
    agent = module.HarborAgent(logs_dir=workspace / "logs")
    assert agent._resolve_auth_json_path() is None


def test_codex_meta_agent_uses_shared_endpoint_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _harbor_runner_module()
    checkout = init_recipe_with_local_inputs(tmp_path, "aevolve")
    plan = runner._runtime_environment_plan(checkout, {"agent": "codex"})
    assert plan.meta_agent_env()["OPENAI_API_KEY"].startswith("${EVOLVE_RUNTIME_META_AGENT_")
    assert "CODEX_FORCE_AUTH_JSON" not in plan.process_env()
```

Add a command-record canary proving the key, endpoint, and proxy literal are absent while templates are present.
Extend the test `FakeCodex` with an inherited-behavior stand-in so the assertion
models the installed Harbor interface:

```python
def _resolve_auth_json_path(self) -> None:
    return None
```

- [ ] **Step 2: Run Codex wrapper tests and verify failure**

Run: `uv run pytest tests/test_m7_codex_seed.py tests/test_harbor_meta_agent.py -q`

Expected: FAIL because the seed forces an auth file and the meta-agent strips OpenAI-compatible endpoint variables.

- [ ] **Step 3: Remove the seed override and document API-key mode**

Delete only the built-in wrapper's `_resolve_auth_json_path()` method and unused `Path.home()` dependency. Keep prompt, skills, compaction, model, and agent semantics unchanged. Update the seed README to require `OPENAI_API_KEY` and `OPENAI_BASE_URL` and state that auth files are unsupported for new workspaces.

- [ ] **Step 4: Replace meta-agent auth/proxy logic with the shared plan**

For strict workspaces, load `evaluator/runtime-profile.json`, resolve the plan, append template assignments to the Harbor command, and merge `plan.process_env()` into the Harbor parent process environment. Delete strict behavior that forces `CODEX_FORCE_AUTH_JSON` or removes `OPENAI_*` for Codex. Retain the old helper as `_legacy_agent_env()` only for newly generated legacy/unverified custom recipes; existing historical workspaces already carry their vendored code.

- [ ] **Step 5: Run Codex and meta-agent tests**

Run: `uv run pytest tests/test_m7_codex_seed.py tests/test_harbor_meta_agent.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the API-key migration**

```bash
git add seeds/codex/agent.py seeds/codex/README.md library/meta_agent/runners/harbor.py tests/test_m7_codex_seed.py tests/test_harbor_meta_agent.py
git commit -m "feat: route Codex agents through endpoint API keys"
```

---

### Task 6: Implement typed ordinary preflight and predefined receipts

**Files:**
- Create: `src/evolve/preflight.py`
- Create: `tests/test_preflight.py`
- Modify: `src/evolve/evaluation/__init__.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: trusted config/profile/contract resolvers, `uv`, Docker image inspection, and `resolve_runtime_environment()`.
- Produces: `PreflightMode`, `PreflightStatus`, `PreflightCheckStatus`, `PreflightFailureCategory`, `ArtifactReferenceV1`, `PreflightCheckV1`, `PreflightResultV1`, `PreflightResultV1.to_dict() -> dict[str, object]`, `PreflightResultV1.write() -> Path`, `PreflightResultV1.failed(mode: PreflightMode, profile_name: str, profile_digest: str, runtime_digest: str, model_route_digest: str, checks: tuple[PreflightCheckV1, ...], category: PreflightFailureCategory, message: str, receipt_path: Path | None = None) -> PreflightResultV1`, and `run_preflight(workspace: Path, *, mode: PreflightMode = PreflightMode.ORDINARY, candidate_commit: str | None = None, receipt_path: Path | None = None, environment: Mapping[str, str] | None = None) -> PreflightResultV1`.

- [ ] **Step 1: Write failing receipt and ordinary-check tests**

```python
def test_ordinary_preflight_is_typed_atomic_and_non_mutating(strict_workspace: Path, monkeypatch) -> None:
    before_tree = git(strict_workspace, "write-tree")
    before_cache = snapshot(strict_workspace / "runs/runtime")
    allow_local_runtime(monkeypatch)
    result = run_preflight(strict_workspace)
    assert result.status is PreflightStatus.PASSED
    assert result.mode is PreflightMode.ORDINARY
    assert result.receipt_path is not None
    assert json.loads(result.receipt_path.read_text())["profile_name"] == "harbor-bytedance-v1"
    assert git(strict_workspace, "write-tree") == before_tree
    assert snapshot(strict_workspace / "runs/runtime") == before_cache
```

Use `init_recipe_with_local_inputs(tmp_path, "aevolve")` for the
`strict_workspace` fixture. Define the cache snapshot helper locally:

```python
def snapshot(root: Path) -> tuple[tuple[str, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        (path.relative_to(root).as_posix(), path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
```

Add this shared local-runtime stand-in to `tests/conftest.py`:

```python
def allow_local_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from evolve import preflight as preflight_module

    monkeypatch.setattr(preflight_module, "_image_available", lambda digest, env: True)
    monkeypatch.setattr(preflight_module, "_tool_available", lambda name, env: True)
```

Add one test per failure category: invalid config, invalid profile, unavailable runtime, invalid lock, missing tool, missing credential, forbidden credential, invalid endpoint, unavailable image, network failure, and model smoke failure. Add secret/endpoint/proxy canaries against serialized receipts and bounded messages.

- [ ] **Step 2: Run preflight tests and verify failure**

Run: `uv run pytest tests/test_preflight.py -q`

Expected: FAIL because typed preflight does not exist.

- [ ] **Step 3: Implement result types and atomic serialization**

```python
class PreflightMode(StrEnum):
    ORDINARY = "ordinary"
    SMOKE = "smoke"


class PreflightStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class PreflightCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class PreflightFailureCategory(StrEnum):
    CONFIGURATION_INVALID = "configuration_invalid"
    RUNTIME_PROFILE_INVALID = "runtime_profile_invalid"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    DEPENDENCY_LOCK_INVALID = "dependency_lock_invalid"
    DEPENDENCY_TOOL_UNAVAILABLE = "dependency_tool_unavailable"
    CREDENTIAL_MISSING = "credential_missing"
    CREDENTIAL_FORBIDDEN = "credential_forbidden"
    ENDPOINT_INVALID = "endpoint_invalid"
    CONTAINER_IMAGE_UNAVAILABLE = "container_image_unavailable"
    NETWORK_UNAVAILABLE = "network_unavailable"
    MODEL_SMOKE_FAILED = "model_smoke_failed"


@dataclass(frozen=True)
class ArtifactReferenceV1:
    path: str
    sha256: str


@dataclass(frozen=True)
class PreflightCheckV1:
    name: str
    status: PreflightCheckStatus
    failure_category: PreflightFailureCategory | None = None
    message: str = ""
    artifact: ArtifactReferenceV1 | None = None


@dataclass(frozen=True)
class PreflightResultV1:
    schema_version: int
    status: PreflightStatus
    profile_name: str
    profile_digest: str
    runtime_digest: str
    model_route_digest: str
    mode: PreflightMode
    checks: tuple[PreflightCheckV1, ...]
    required_credential_names_by_role: tuple[tuple[str, tuple[str, ...]], ...]
    failure_category: PreflightFailureCategory | None = None
    failure_message: str | None = None
    receipt_path: Path | None = field(default=None, compare=False)
```

Make `receipt_path` an operational property omitted from `to_dict()`. Atomically write `to_dict()` to either the supplied path or the next `runs/preflight/attempt-N/preflight.json` path.

Implement `PreflightResultV1.failed()` as a typed constructor taking
`mode`, `profile_name`, `profile_digest`, `runtime_digest`, completed checks,
failure category, bounded message, and optional receipt path. Tests and
evaluation orchestration use this constructor rather than manually assembling
receipt dictionaries.

- [ ] **Step 4: Implement ordered ordinary checks**

Validate config/profile and route first, contract prerequisites second, tools and local image third, UV lock fourth, and role environment planning last. Use `docker image inspect <runtime_digest>` without pulling. Use `uv lock --check --project <target>` without sync/install. Return the first failure plus all already completed checks; do not raise expected preflight failures to the CLI.

- [ ] **Step 5: Run preflight tests and static checks**

Run: `uv run pytest tests/test_preflight.py -q`

Run: `uv run ruff check src/evolve/preflight.py tests/test_preflight.py`

Run: `uv run ty check src/evolve/preflight.py`

Expected: all pass.

- [ ] **Step 6: Commit typed ordinary preflight**

```bash
git add src/evolve/preflight.py src/evolve/evaluation/__init__.py tests/conftest.py tests/test_preflight.py
git commit -m "feat: add typed runtime preflight"
```

---

### Task 7: Make ordinary preflight mandatory for strict evaluation and expose the CLI

**Files:**
- Modify: `src/evolve/cli.py:110-150`
- Modify: `src/evolve/evaluation/execution.py:37-220,321-365`
- Modify: `src/evolve/evaluation/results.py:55-104`
- Modify: `src/evolve/archive.py:10-48`
- Modify: `tests/test_m0_run_resume.py`
- Modify: `tests/test_evaluation_contract_execution.py`
- Modify: `tests/test_evaluation_records.py`

**Interfaces:**
- Consumes: `run_preflight()` and generated preflight wrapper.
- Produces: `evolve preflight WORKSPACE`, `EvaluationRecord.preflight_receipt`, and fail-closed strict evaluation before candidate preparation or trials.

- [ ] **Step 1: Write failing CLI and evaluation-gate tests**

```python
def test_preflight_cli_prints_receipt_and_returns_zero(strict_workspace: Path, monkeypatch) -> None:
    allow_local_runtime(monkeypatch)
    result = CliRunner().invoke(app, ["preflight", str(strict_workspace)])
    assert result.returncode == 0
    assert "preflight: passed" in result.stdout
    assert "preflight.json" in result.stdout


def test_strict_evaluation_stops_before_runtime_and_trials_when_preflight_fails(strict_workspace: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        execution_module,
        "run_preflight",
        lambda *args, **kwargs: failed_preflight(Path(kwargs["receipt_path"])),
    )
    monkeypatch.setattr(execution_module, "prepare_candidate_runtime", lambda *args, **kwargs: calls.append("runtime"))
    record = evaluate(strict_workspace, "gen/0", "0")
    assert calls == []
    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.preflight_receipt is not None
    assert all(trial.outcome is Outcome.MISSING for trial in record.trials)
```

Define the test helpers in the same modules:

```python
def failed_preflight(path: Path) -> PreflightResultV1:
    result = PreflightResultV1.failed(
        mode=PreflightMode.ORDINARY,
        profile_name="harbor-bytedance-v1",
        profile_digest="a" * 64,
        runtime_digest="sha256:test-runtime",
        model_route_digest="b" * 64,
        checks=(),
        category=PreflightFailureCategory.CREDENTIAL_MISSING,
        message="required credential is missing",
        receipt_path=path,
    )
    result.write()
    return result
```

The receipt helper ensures the evaluation reference points to a real predefined
receipt rather than an in-memory stand-in.

- [ ] **Step 2: Run CLI/evaluation tests and verify failure**

Run: `uv run pytest tests/test_m0_run_resume.py tests/test_evaluation_contract_execution.py tests/test_evaluation_records.py -q`

Expected: FAIL because the command, record field, and mandatory gate do not exist.

- [ ] **Step 3: Add the thin CLI command**

Add a Typer command with `workspace: Path` and `--smoke` boolean. Load `.env` through `_workspace_environment()`, call `run_preflight()`, print status and receipt path, exit `1` for ordinary failure and `2` for smoke failure.

- [ ] **Step 4: Gate strict evaluation and attach the receipt**

After the attempt directory and base record fields are established but before `prepare_candidate_runtime()`, call ordinary preflight with the candidate commit and `run_dir / "preflight.json"`. Store a relative path/SHA-256 reference in `base["preflight_receipt"]`. On failure, classify infrastructure failure with strict materialized missing trials and freeze diagnostics.

Add `preflight_receipt: dict[str, str] | None = None` to `EvaluationRecord`, omit it from legacy serialization when absent, and protect it in `STAMPED_FIELDS`.

- [ ] **Step 5: Run the focused evaluation tests**

Run: `uv run pytest tests/test_m0_run_resume.py tests/test_evaluation_contract_execution.py tests/test_evaluation_records.py -q`

Expected: PASS.

- [ ] **Step 6: Commit mandatory preflight integration**

```bash
git add src/evolve/cli.py src/evolve/evaluation/execution.py src/evolve/evaluation/results.py src/evolve/archive.py tests/test_m0_run_resume.py tests/test_evaluation_contract_execution.py tests/test_evaluation_records.py
git commit -m "feat: require preflight before strict evaluation"
```

---

### Task 8: Bind candidate runtime receipts to the strict profile

**Files:**
- Modify: `src/evolve/uv_runtime.py:84-430`
- Modify: `src/evolve/evaluation/contract.py:220-247`
- Modify: `tests/test_locked_runtime.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: profile-derived `UvRuntimeConfig`, profile name/digest, and contract ID.
- Produces: candidate runtime receipt schema version `3` with profile identity and no strict `EVAL_STUB` certification.

- [ ] **Step 1: Write failing strict runtime-receipt tests**

```python
def test_strict_uv_receipt_contains_profile_identity(strict_uv_checkout: Path) -> None:
    result = prepare_candidate_runtime(
        strict_uv_checkout,
        run_dir,
        runtime_root,
        candidate_commit,
        evaluator,
        contract_id=contract_id,
    )
    payload = json.loads(result.receipt_path.read_text())
    assert payload["schema_version"] == 3
    assert payload["runtime_profile"] == "harbor-bytedance-uv-v1"
    assert payload["runtime_profile_digest"] == resolved_profile.profile_digest


def test_eval_stub_cannot_certify_strict_candidate_runtime(strict_uv_checkout: Path) -> None:
    result = prepare_candidate_runtime(strict_uv_checkout, run_dir, runtime_root, "abc", evaluator, env={"EVAL_STUB": "1"})
    assert result.ready is False
    assert result.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert "strict runtime preparation" in result.reason
```

- [ ] **Step 2: Run runtime tests and verify failure**

Run: `uv run pytest tests/test_locked_runtime.py tests/test_m1_evaluator_invariants.py -q`

Expected: FAIL because receipts remain schema version 2 and strict stubs skip preparation.

- [ ] **Step 3: Upgrade strict runtime receipts**

Load the resolved profile once in `prepare_candidate_runtime()`. Add profile name and digest to every ready/failure receipt. Keep schema version 2 only for legacy YAML runtime compatibility. Update `verify_candidate_runtime_receipt()` to require schema version 3 and the contract's profile identity for strict UV contracts.

- [ ] **Step 4: Fail closed for strict stubs**

When `EVAL_STUB=1` and a resolved strict profile exists, write an infrastructure-failure receipt explaining that strict runtime preparation was not observed. Preserve the existing no-receipt shortcut only when no resolved profile file exists. Update strict execution tests to inject a fake runtime adapter explicitly instead of using this legacy shortcut.

- [ ] **Step 5: Run runtime and contract tests**

Run: `uv run pytest tests/test_locked_runtime.py tests/test_m1_evaluator_invariants.py tests/test_evaluation_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit strict runtime receipts**

```bash
git add src/evolve/uv_runtime.py src/evolve/evaluation/contract.py tests/test_locked_runtime.py tests/test_m1_evaluator_invariants.py tests/test_evaluation_contract.py
git commit -m "feat: certify runtime preparation against profiles"
```

---

### Task 9: Make the Harbor evaluator consume the shared environment plan

**Files:**
- Modify: `src/evolve/evaluation/execution.py:321-365`
- Modify: `scaffolds/evaluators/harbor/engine.sh:145-260`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: `resolve_runtime_environment()` and `write_harbor_environment_inputs()`.
- Produces: safe template-only Harbor `--ae`/`--ve` arguments and removal of duplicate shell proxy/auth policy.

- [ ] **Step 1: Write failing evaluator-plan tests**

```python
def test_eval_runner_writes_templates_and_keeps_literals_only_in_process_env(strict_workspace: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    run_dir = strict_workspace / "runs" / "environment-plan-test"
    run_dir.mkdir(parents=True)

    def fake_run_owned(command, *, cwd, env, timeout_s=None):
        captured.update({"command": command, "cwd": cwd, "env": env, "timeout_s": timeout_s})
        return OwnedResult(0, "", "", 0.01, False)

    monkeypatch.setattr(execution_module, "run_owned", fake_run_owned)
    execution_module._run_eval_script(
        strict_workspace,
        run_dir,
        "0",
        1,
        "candidate",
        "gate",
        CandidateRuntimeResult(None, None),
    )
    agent_text = (run_dir / "runtime-agent.env").read_text()
    assert "${EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY}" in agent_text
    assert "sensitive-key-value" not in agent_text
    assert "model.example" not in agent_text
    assert captured["env"]["EVOLVE_RUNTIME_AGENT_OPENAI_API_KEY"] == "sensitive-key-value"


def test_harbor_shell_contains_no_proxy_or_credential_policy_engine() -> None:
    text = (ROOT / "scaffolds/evaluators/harbor/engine.sh").read_text()
    assert "dependency_hosts =" not in text
    assert "for credential_name in" not in text
    assert "model_base=" not in text
    assert "runtime-agent.env" in text
```

- [ ] **Step 2: Run evaluator tests and verify failure**

Run: `uv run pytest tests/test_harbor_evaluator_template.py tests/test_m1_evaluator_invariants.py -q`

Expected: FAIL because the shell still owns proxy and credential policy.

- [ ] **Step 3: Resolve the plan before launching the evaluator**

In `_run_eval_script()`, load the resolved profile, build the plan from the clean host environment plus allowed non-protected agent/verifier settings, write safe input files, and merge actual internal values into the process environment. For a new legacy custom workspace, call an explicitly named `resolve_legacy_runtime_environment()` that preserves existing forwarding without file auth.

- [ ] **Step 4: Reduce the shell to validated translation**

Delete credential discovery, endpoint parsing, dependency-host filtering, and proxy normalization from `engine.sh`. Loop over `runtime-agent.env` and `runtime-verifier.env`, passing each already validated template assignment through `--ae` or `--ve`. Keep candidate runtime mounts/env, task selection, retry, timeout, cleanup, Harbor launch, and score parsing unchanged.

- [ ] **Step 5: Run Harbor template and evaluator tests**

Run: `uv run pytest tests/test_harbor_evaluator_template.py tests/test_m1_evaluator_invariants.py tests/test_miniswe_source_agent_command.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the Harbor policy extraction**

```bash
git add src/evolve/evaluation/execution.py scaffolds/evaluators/harbor/engine.sh tests/test_harbor_evaluator_template.py tests/test_m1_evaluator_invariants.py tests/test_miniswe_source_agent_command.py
git commit -m "refactor: drive Harbor from runtime environment plans"
```

---

### Task 10: Add isolated one-request profile smoke

**Files:**
- Modify: `src/evolve/preflight.py`
- Modify: `src/evolve/candidate/smoke.py:15-130`
- Modify: `src/evolve/cli.py`
- Modify: `scaffolds/evaluators/harbor/engine.sh:80-145,235-280`
- Modify: `src/evolve/integrations/harbor/miniswe_candidate.py:380-535`
- Modify: `seeds/codex/agent.py`
- Modify: `tests/test_candidate_smoke.py`
- Modify: `tests/test_miniswe_harbor_wrapper.py`
- Modify: `tests/test_m7_codex_seed.py`
- Modify: `tests/test_preflight.py`

**Interfaces:**
- Consumes: ordinary preflight, detached candidate snapshot, real selected evaluator agent, and ByteDance environment plan.
- Produces: `SmokeMode`, `run_candidate_smoke(checkout: Path, *, workspace: Path, mode: SmokeMode = SmokeMode.INSTALL) -> SmokeResult`, and `run_preflight(workspace: Path, mode=PreflightMode.SMOKE)` with one model request.

- [ ] **Step 1: Write failing smoke-isolation tests**

```python
def test_smoke_runs_ordinary_checks_then_one_model_agent_request(strict_workspace: Path, monkeypatch) -> None:
    calls: list[str] = []
    allow_local_runtime(monkeypatch)
    smoke = passed_smoke(strict_workspace / "runs" / "fake-smoke")
    monkeypatch.setattr(
        preflight_module,
        "run_candidate_smoke",
        lambda *args, **kwargs: calls.append(kwargs["mode"].value) or smoke,
    )
    result = run_preflight(strict_workspace, mode=PreflightMode.SMOKE)
    assert calls == ["model"]
    assert result.checks[0].name == "configuration"
    assert result.checks[-1].name == "model_agent_request"
    assert result.status is PreflightStatus.PASSED


def test_model_smoke_uses_detached_snapshot_without_workspace_mutation(checkout: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_owned(command, *, cwd, env, timeout_s=None):
        captured["env"] = env
        return SimpleNamespace(returncode=0, stdout="", stderr="", wall_s=0.01, timed_out=False)

    monkeypatch.setattr(candidate_smoke_module, "run_owned", fake_run_owned)
    before = git(checkout, "write-tree")
    result = run_candidate_smoke(checkout, workspace=checkout, mode=SmokeMode.MODEL)
    assert result.status == "passed"
    assert git(checkout, "write-tree") == before
    assert captured["env"]["EVOLVE_CANDIDATE_SMOKE_MODE"] == "model"
```

Define the passed smoke helper in `tests/test_preflight.py`:

```python
def passed_smoke(attempt: Path) -> SmokeResult:
    attempt.mkdir(parents=True)
    stdout = attempt / "stdout.log"
    stderr = attempt / "stderr.log"
    stdout.write_text("model response received\n")
    stderr.write_text("")
    (attempt / "result.json").write_text('{"schema_version": 1, "status": "passed"}\n')
    return SmokeResult("passed", attempt, "a" * 40, 0, stdout, stderr)
```

Add adapter tests proving both Codex and MiniSWE replace benchmark instructions with `Reply with exactly OK. Do not use tools.` only in model-smoke mode. Add a normal-run test proving instructions remain unchanged.

- [ ] **Step 2: Run smoke tests and verify failure**

Run: `uv run pytest tests/test_candidate_smoke.py tests/test_miniswe_harbor_wrapper.py tests/test_m7_codex_seed.py tests/test_preflight.py -q`

Expected: FAIL because model-smoke mode and delegation do not exist.

- [ ] **Step 3: Add explicit smoke modes**

```python
class SmokeMode(StrEnum):
    INSTALL = "install"
    MODEL = "model"
```

Keep the existing `candidate-smoke --full` behavior mapped to `INSTALL`. For preflight smoke, use `MODEL`. Pass the mode through `EVOLVE_CANDIDATE_SMOKE_MODE` without storing any endpoint value.

Set `EVOLVE_EVAL_SPLIT` from
`evaluation_split_name(evaluator, "candidate")` so full-scope AHE and
HyperAgents smoke their configured `train` split while split-based AEvolve,
GEPA, and hill-climb smoke `gate`.

- [ ] **Step 4: Make model smoke execute exactly one agent request**

In Harbor shell model mode, set tasks, attempts, and concurrency to `1`, pass the smoke mode to the agent, and do not use `--install-only`. In MiniSWE and built-in Codex wrappers, replace the received benchmark instruction with the exact smoke sentence only when the mode is `model`; then call the existing real `run()` implementation. This exercises installation, adapter initialization, API routing, response parsing, and runtime evidence while the detached snapshot absorbs any writes.

- [ ] **Step 5: Attach smoke evidence to the preflight receipt**

Run ordinary checks first. On success, invoke model smoke. Add a `model_agent_request` check with a relative path/SHA-256 reference to the smoke result and redacted logs. Map candidate smoke failure to `model_smoke_failed` unless its structured result identifies dependency/network infrastructure first.

- [ ] **Step 6: Run all smoke and adapter tests**

Run: `uv run pytest tests/test_candidate_smoke.py tests/test_miniswe_harbor_wrapper.py tests/test_m7_codex_seed.py tests/test_preflight.py -q`

Expected: PASS with no live endpoint call because subprocesses are faked.

- [ ] **Step 7: Commit isolated profile smoke**

```bash
git add src/evolve/preflight.py src/evolve/candidate/smoke.py src/evolve/cli.py scaffolds/evaluators/harbor/engine.sh src/evolve/integrations/harbor/miniswe_candidate.py seeds/codex/agent.py tests/test_candidate_smoke.py tests/test_miniswe_harbor_wrapper.py tests/test_m7_codex_seed.py tests/test_preflight.py
git commit -m "feat: add isolated runtime profile smoke"
```

---

### Task 11: Add four-method conformance and security gates

**Files:**
- Create: `tests/test_runtime_profile_recipe_conformance.py`
- Modify: `tests/test_contract_recipe_conformance.py`
- Modify: `tests/test_diagnostics_recipe_conformance.py`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`

**Interfaces:**
- Consumes: complete strict profile, preflight, contract, environment, and smoke local interfaces.
- Produces: AEvolve/AHE/GEPA/HyperAgents conformance proof and user-facing future workflow documentation.

- [ ] **Step 1: Write the failing conformance matrix**

```python
@pytest.mark.parametrize(
    ("recipe", "profile"),
    [
        ("aevolve", "harbor-bytedance-v1"),
        ("ahe", "harbor-bytedance-uv-v1"),
        ("gepa", "harbor-bytedance-v1"),
        ("hyperagents", "harbor-bytedance-uv-v1"),
    ],
)
def test_partner_recipe_runtime_profile_conformance(tmp_path: Path, recipe: str, profile: str, monkeypatch) -> None:
    workspace = init_recipe_with_local_inputs(tmp_path, recipe)
    allow_local_runtime(monkeypatch)
    result = run_preflight(workspace)
    contract = contract_for_gen0(workspace)
    assert result.status is PreflightStatus.PASSED
    assert result.profile_name == profile
    assert contract.runtime_profile == profile
    assert contract.runtime_profile_digest == result.profile_digest
```

Import `allow_local_runtime`, `contract_for_gen0`, and
`init_recipe_with_local_inputs` from `conftest`; do not duplicate their setup
logic in the matrix.

Add assertions for unchanged method operator bindings/surfaces, structured diagnostics availability, preflight receipt redaction, no method-name branches in the three new modules, and no auth-file path in generated workspaces.

- [ ] **Step 2: Run conformance tests and verify failures identify gaps**

Run: `uv run pytest tests/test_runtime_profile_recipe_conformance.py tests/test_contract_recipe_conformance.py tests/test_diagnostics_recipe_conformance.py tests/test_phase_e_recipes.py -q`

Expected: any missing integration fails with the exact recipe/profile mismatch; after Tasks 1-10 the remaining failures should be documentation or assertion alignment only.

- [ ] **Step 3: Complete conformance integration without method branches**

Fix shared profile/config behavior only. Do not add conditionals on recipe names. Keep AEvolve/GEPA Codex semantics and AHE/HyperAgents MiniSWE semantics in recipe/agent data. Include hill-climb in profile-generation coverage without making it a partner-method acceptance row.

- [ ] **Step 4: Document the short future workflow**

Document:

```bash
evolve init WORKSPACE --recipe ahe --dataset DATASET
WORKSPACE/evolve preflight WORKSPACE
WORKSPACE/evolve preflight WORKSPACE --smoke
WORKSPACE/evolve run WORKSPACE
```

Explain that profile/contract fields are automatic, repetitions default to one, ordinary preflight is read-only, smoke is isolated, ByteDance endpoint credentials come from environment variables, and source scripts no longer prepare runtime policy.

- [ ] **Step 5: Run conformance and documentation checks**

Run: `uv run pytest tests/test_runtime_profile_recipe_conformance.py tests/test_contract_recipe_conformance.py tests/test_diagnostics_recipe_conformance.py tests/test_phase_e_recipes.py -q`

Run: `uv run pytest tests/test_coherence.py tests/test_resource_layout.py -q`

Expected: profile conformance passes; only already documented unrelated dirty-tree resource-layout failures may remain, and their exact paths must be recorded without changing them.

- [ ] **Step 6: Commit conformance and docs**

```bash
git add tests/test_runtime_profile_recipe_conformance.py tests/test_contract_recipe_conformance.py tests/test_diagnostics_recipe_conformance.py tests/test_phase_e_recipes.py README.md ARCHITECTURE.md
git commit -m "test: enforce runtime profile conformance"
```

---

### Task 12: Run two opt-in live ByteDance profile smokes

**Files:**
- Create: `tests/test_live_runtime_profile_smoke.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: real ByteDance `OPENAI_API_KEY`/`OPENAI_BASE_URL`, locally available immutable evaluator runtime, Docker, Harbor, Codex, and pinned MiniSWE source.
- Produces: separate non-mutating live evidence for `harbor-bytedance-v1` and `harbor-bytedance-uv-v1` without starting an experiment run.

- [ ] **Step 1: Add an opt-in live smoke test with a synthetic Harbor dataset**

The test creates ten temporary tasks so split recipes have non-empty train/gate/sealed sets. Each task contains a pinned Ubuntu 24.04 Dockerfile, the instruction `Runtime profile smoke.`, and a verifier that writes reward `1`. The test initializes an AEvolve workspace with the built-in Codex seed and an AHE workspace with the pinned MiniSWE seed, then runs `run_preflight(workspace, mode=PreflightMode.SMOKE)`.

Use these exact helpers in the live test module:

```python
UBUNTU_DIGEST = "sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"


def write_model_smoke_dataset(root: Path) -> Path:
    root.mkdir()
    for index in range(10):
        task = root / f"model-smoke-{index}"
        (task / "environment").mkdir(parents=True)
        (task / "tests").mkdir()
        (task / "task.toml").write_text(
            'version = "1.0"\n\n'
            '[metadata]\n\n'
            '[verifier]\ntimeout_sec = 60.0\n\n'
            '[agent]\ntimeout_sec = 180.0\n\n'
            '[environment]\nbuild_timeout_sec = 300.0\n'
        )
        (task / "instruction.md").write_text("Runtime profile smoke.\n")
        (task / "environment" / "Dockerfile").write_text(
            f"FROM ubuntu:24.04@{UBUNTU_DIGEST}\nWORKDIR /app\n"
        )
        verifier = task / "tests" / "test.sh"
        verifier.write_text("#!/bin/sh\nset -eu\nprintf '1\\n' > /logs/verifier/reward.txt\n")
        verifier.chmod(0o755)
    return root


def build_live_smoke_workspace(tmp_path: Path, recipe: str) -> Path:
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "EVOLVE_RUNTIME_DIGEST"):
        if not os.environ.get(name):
            raise AssertionError(f"live profile smoke requires {name}")
    dataset = write_model_smoke_dataset(tmp_path / f"{recipe}-dataset")
    workspace = tmp_path / f"{recipe}-workspace"
    init_workspace(InitOptions(workspace=workspace, recipe=recipe, dataset=str(dataset)))
    return workspace
```

```python
@pytest.mark.live_model
@pytest.mark.skipif(os.environ.get("EVOLVE_LIVE_BYTEDANCE_SMOKE") != "1", reason="live model smoke is opt-in")
@pytest.mark.parametrize("recipe", ["aevolve", "ahe"])
def test_live_profile_smoke_is_non_mutating(tmp_path: Path, recipe: str) -> None:
    assert "CODEX_AUTH_JSON_PATH" not in os.environ
    assert "CODEX_FORCE_AUTH_JSON" not in os.environ
    workspace = build_live_smoke_workspace(tmp_path, recipe)
    before = git(workspace, "write-tree")
    result = run_preflight(workspace, mode=PreflightMode.SMOKE)
    assert result.status is PreflightStatus.PASSED
    assert git(workspace, "write-tree") == before
    serialized = result.receipt_path.read_text()
    assert os.environ["OPENAI_API_KEY"] not in serialized
    assert os.environ["OPENAI_BASE_URL"] not in serialized
```

Register the `live_model` marker in `pyproject.toml`.

- [ ] **Step 2: Prove the live test is skipped by default**

Run: `uv run pytest tests/test_live_runtime_profile_smoke.py -q`

Expected: two skipped tests and zero model requests.

- [ ] **Step 3: Run the non-UV live smoke on a ByteDance-capable machine**

Run:

```bash
env -u CODEX_AUTH_JSON_PATH -u CODEX_FORCE_AUTH_JSON \
  EVOLVE_LIVE_BYTEDANCE_SMOKE=1 \
  uv run pytest tests/test_live_runtime_profile_smoke.py -k aevolve -v
```

Expected: PASS with one Codex model request, a passed redacted preflight receipt, and no tracked workspace change.

- [ ] **Step 4: Run the UV live smoke on the same endpoint**

Run:

```bash
env -u CODEX_AUTH_JSON_PATH -u CODEX_FORCE_AUTH_JSON \
  EVOLVE_LIVE_BYTEDANCE_SMOKE=1 \
  uv run pytest tests/test_live_runtime_profile_smoke.py -k ahe -v
```

Expected: PASS with one MiniSWE model request, frozen candidate preparation, a passed redacted preflight receipt, and no tracked workspace change.

- [ ] **Step 5: Inspect only the new smoke receipts**

Verify each receipt reports the expected profile name, route digest, runtime digest, successful `model_agent_request`, and no raw API key/base URL/proxy. Do not inspect or modify any current/historical experiment directory.

- [ ] **Step 6: Commit the opt-in smoke gate**

```bash
git add tests/test_live_runtime_profile_smoke.py pyproject.toml
git commit -m "test: add live ByteDance profile smoke"
```

---

### Task 13: Run Phase 3 regression, preservation, and security audit

**Files:**
- Modify only if a Phase 3-owned regression is found: files already listed in Tasks 1-12.

**Interfaces:**
- Consumes: all Phase 3 commits and the unchanged dirty worktree baseline.
- Produces: evidence that Phase 3 is locally correct, secret-safe, and preserves current/historical experiments.

- [ ] **Step 1: Run the complete Phase 3 focused gate**

Run:

```bash
uv run pytest \
  tests/test_runtime_profiles.py \
  tests/test_runtime_environment.py \
  tests/test_preflight.py \
  tests/test_evaluation_contract.py \
  tests/test_evaluation_contract_execution.py \
  tests/test_locked_runtime.py \
  tests/test_candidate_smoke.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_meta_agent.py \
  tests/test_runtime_profile_recipe_conformance.py \
  tests/test_contract_recipe_conformance.py \
  tests/test_diagnostics_recipe_conformance.py -q
```

Expected: PASS.

- [ ] **Step 2: Run repository static checks**

Run: `uv run ruff check .`

Run: `uv run ty check src`

Expected: both pass.

- [ ] **Step 3: Run the full local test suite**

Run: `uv run pytest -q`

Expected: all Phase 3-owned tests pass. If the two known unrelated dirty-tree failures remain, record them exactly: tracked legacy superpowers artifacts in `test_local_superpowers_artifacts_are_not_tracked` and untracked `templates/` ownership in `test_source_resources_have_one_owner`. Do not delete or rewrite those user-owned files.

- [ ] **Step 4: Run the secret and endpoint persistence scan**

Run targeted tests with canary key, URL, and proxy values, then search only tracked source and newly created temporary smoke receipts. Confirm canary literals appear nowhere outside ephemeral process environment. Do not inspect credential files or `.env` contents.

- [ ] **Step 5: Prove protected directories were untouched**

Run:

```bash
git diff --name-only 088d249..HEAD -- experiments scripts analysis_artifacts analysis_selected terminal-bench-2-50-19-20
```

Expected: no output.

Run: `git diff --check 088d249..HEAD`

Expected: PASS.

- [ ] **Step 6: Review the final Phase 3 diff by responsibility**

Confirm every new policy behavior lives in `runtime_profiles.py`, `runtime_environment.py`, or `preflight.py`; shell only translates validated files; no method-name branches or auth fallback were introduced; recipe changes are declarative; and no long experiment launcher was added.

- [ ] **Step 7: Commit any Phase 3-owned audit fixes**

If the audit required a source fix, stage only the Phase 3-owned files and commit:

```bash
git commit -m "fix: close runtime profile audit gaps"
```

If no fix was required, do not create an empty commit.

---

## Phase 3 completion evidence

Before moving to Phase 4, retain these concrete results in the handoff:

- Commit range containing Tasks 1-12.
- Focused pytest count and pass result.
- Full pytest result with any unrelated pre-existing failures named exactly.
- Ruff and ty pass results.
- One passed live receipt for each strict profile.
- Git preservation scan showing no current/historical experiment or script change.
- Secret/endpoint scan showing no persisted raw values.
- A concise list of any external Harbor behavior that required confirmation; no workaround is acceptable at such a boundary.
