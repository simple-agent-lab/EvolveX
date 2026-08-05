# Runtime Configuration Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ByteDance-specific locked runtime policy with provider-neutral declarative profiles, one project-root `.env`, explicit Codex/API authentication, simple proxy passthrough, strict local and registry dataset identity, and focused preflight modules.

**Architecture:** Local credentials and infrastructure settings come only from explicit process variables over the project-root `.env`; safe runtime policy comes from validated profile data and is frozen in `gen/0`. Authentication resolution, Harbor role templating, profile loading, preflight checks, dataset identity, and contract certification remain separate boundaries with typed errors and no persisted secrets.

**Tech Stack:** Python 3.12, PyYAML, python-dotenv, Typer, Harbor 0.18, pytest, Ruff, POSIX shell.

## Global Constraints

- Never discover `~/.codex/auth.json`; only `CODEX_AUTH_JSON_PATH` enables file authentication.
- Explicit process variables override the project-root `.env`; no caller or parent `.env` is loaded.
- `OPENAI_BASE_URL` is optional and an unset value identifies the official OpenAI endpoint.
- Literal credentials, auth paths, custom endpoints, and proxy values must not enter Git, receipts, contracts, logs, or persisted evidence.
- Standard `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` values pass through unchanged; core performs no host rewriting.
- Runtime profiles are provider-neutral data and contain no ByteDance-specific policy.
- Runtime images used by strict profiles must be immutable SHA-256 references.
- Keep `evaluation/contract.py` as one module and keep `evaluation/diagnostics.py` behavior unchanged.
- Preserve legacy `evaluator.k` reading and version 1 split-manifest reading.
- Generated `evaluator/eval.sh` is internal and fails clearly without prepared runtime inputs.
- Preserve unrelated user changes and keep the four existing focused fixes isolated from redesign commits.

---

## File map

**Create**

- `src/evolve/profiles/harbor-v1.yaml` — neutral Harbor runtime policy.
- `src/evolve/profiles/harbor-uv-v1.yaml` — neutral Harbor plus frozen UV candidate runtime.
- `src/evolve/runtime_auth.py` — typed API versus explicit Codex auth-json resolution.
- `src/evolve/preflight/__init__.py` — stable public exports.
- `src/evolve/preflight/models.py` — receipt/check types.
- `src/evolve/preflight/checks.py` — typed host and runtime checks.
- `src/evolve/preflight/runner.py` — orchestration and smoke integration.
- `tests/test_runtime_auth.py` — authentication coverage.

**Replace or modify substantially**

- Replace `src/evolve/preflight.py` with the `preflight/` package.
- Modify `runtime_profiles.py`, `runtime_environment.py`, `evaluator_config.py`, `workspace.py`, `cli.py`, `splits.py`, `evaluation/datasets.py`, and `evaluation/contract.py`.
- Modify the Harbor meta-agent runner and evaluator engine scaffold.
- Modify built-in recipes, public/scaffold documentation, and affected tests.

---

### Task 1: Land the existing focused correctness fixes

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `README.md`
- Modify: `scaffolds/evaluators/harbor/harbor_artifacts.py`
- Modify: `tests/test_harbor_artifacts.py`

**Interfaces:**
- Produces: deterministic fixture-based README/CI smoke setup.
- Produces: candidate error markers accepted only when matching `[a-z0-9_]{1,64}`.

- [ ] **Step 1: Inspect the existing unstaged changes**

```bash
git diff -- .github/workflows/test.yml README.md scaffolds/evaluators/harbor/harbor_artifacts.py tests/test_harbor_artifacts.py
```

Expected: only the fixture smoke setup and 64-character error boundary.

- [ ] **Step 2: Run the focused regression test**

```bash
uv run pytest tests/test_harbor_artifacts.py -q
uv run ruff check scaffolds/evaluators/harbor/harbor_artifacts.py tests/test_harbor_artifacts.py
git diff --check
```

Expected: all commands succeed.

- [ ] **Step 3: Commit only these four files**

```bash
git add .github/workflows/test.yml README.md scaffolds/evaluators/harbor/harbor_artifacts.py tests/test_harbor_artifacts.py
git commit -m "fix: keep smoke and Harbor errors deterministic"
```

---

### Task 2: Enforce one project-root environment file

**Files:**
- Modify: `src/evolve/cli.py:34-49`
- Modify: `tests/test_m0_run_resume.py:87-130`
- Modify: `tests/test_m0_init.py:450-465`
- Modify: `scaffolds/workspace/AGENTS.md:25-28`
- Modify: `scaffolds/workspace/README.md`

**Interfaces:**
- Produces: `_workspace_environment(workspace: Path) -> Iterator[None]` loading only `workspace/.env` and restoring only variables it added.

- [ ] **Step 1: Replace the caller-fallback test with this failing test**

```python
def test_run_does_not_load_caller_dotenv_for_separate_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = tmp_path / "framework"
    caller.mkdir()
    (caller / ".env").write_text("OPENAI_BASE_URL=https://caller.example/v1\n")
    workspace = tmp_path / "experiment"
    workspace.mkdir()
    monkeypatch.chdir(caller)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    captured: dict[str, str | None] = {}

    def fake_run(_options) -> None:
        captured["base_url"] = os.environ.get("OPENAI_BASE_URL")

    monkeypatch.setattr(cli, "driver_run", fake_run)
    cli.run(workspace, max_generations=0)
    assert captured["base_url"] is None
```

Also assert generated `.gitignore` contains `.env` and `.env.*`.

- [ ] **Step 2: Verify the caller-ignore test fails**

```bash
uv run pytest tests/test_m0_run_resume.py::test_run_does_not_load_caller_dotenv_for_separate_workspace -q
```

Expected: FAIL because the current CLI loads the caller `.env`.

- [ ] **Step 3: Implement one-file loading**

```python
@contextmanager
def _workspace_environment(workspace: Path) -> Iterator[None]:
    added: list[str] = []
    try:
        for name, value in dotenv_values(workspace.resolve() / ".env").items():
            if value is not None and name not in os.environ:
                os.environ[name] = value
                added.append(name)
        yield
    finally:
        for name in reversed(added):
            os.environ.pop(name, None)
```

Update scaffold docs to say “project-root `.env`” and remove caller fallback.

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/test_m0_run_resume.py tests/test_m0_init.py -q
git add src/evolve/cli.py tests/test_m0_run_resume.py tests/test_m0_init.py scaffolds/workspace/AGENTS.md scaffolds/workspace/README.md
git commit -m "fix: load only the project environment file"
```

Expected: tests pass; explicit process variables still win.

---

### Task 3: Load neutral declarative runtime profiles

**Files:**
- Create: `src/evolve/profiles/harbor-v1.yaml`
- Create: `src/evolve/profiles/harbor-uv-v1.yaml`
- Modify: `src/evolve/runtime_profiles.py`
- Modify: `src/evolve/evaluator_config.py`
- Modify: `src/evolve/workspace.py`
- Modify: `recipes/aevolve/evolve.yaml`, `recipes/ahe/evolve.yaml`, `recipes/gepa/evolve.yaml`, `recipes/hill_climb/evolve.yaml`, `recipes/hyperagents/evolve.yaml`
- Modify: `tests/test_runtime_profiles.py`, `tests/test_config_parser.py`, `tests/test_runtime_profile_recipe_conformance.py`, `tests/test_phase_e_recipes.py`, `tests/test_m0_init.py`

**Interfaces:**
- Produces: `runtime_profile(name: str, environment: Mapping[str, str] | None = None) -> RuntimeProfileV1`.
- Produces: `profile_search_paths(environment: Mapping[str, str]) -> tuple[Path, ...]` using `os.pathsep`.
- Produces: `normalize_model_endpoint(url: str | None) -> str` and `model_endpoint_digest(url: str | None) -> str`.
- Produces: `ResolvedRuntimeProfileV1(profile, runtime_digest, endpoint_digest, profile_digest)`.
- Produces: `RuntimeProfileErrorCode` values `PROFILE_NOT_FOUND`, `PROFILE_AMBIGUOUS`, `PROFILE_INVALID`, `ENDPOINT_INVALID`, and `RUNTIME_IMAGE_MUTABLE`; `RuntimeProfileResolutionError.code` carries one of them.
- Preserves: `resolve_runtime_profile(config, runtime_digest, environment) -> ResolvedRuntimeProfileV1 | None`.

- [ ] **Step 1: Write failing loader tests**

```python
IMMUTABLE_IMAGE = "sha256:" + "a" * 64
PRIVATE_PROFILE_YAML = """\
schema_version: 1
name: private-harbor-v1
engine: harbor
required_tools: [docker, harbor]
candidate_runtime: null
dependency_policy: agent-owned
cache_policy: none
network_policy: model-endpoint
preflight_capabilities: [configuration, evaluation-contract, runtime-image]
smoke_capabilities: [one-model-request]
"""

def test_builtin_profiles_are_neutral_and_data_backed() -> None:
    basic = runtime_profile("harbor-v1", {})
    uv = runtime_profile("harbor-uv-v1", {})
    assert basic.candidate_runtime is None
    assert uv.candidate_runtime == CandidateRuntimePolicy("uv", "target", "3.12")
    assert "bytedance" not in json.dumps(profile_payload(basic)).lower()

def test_private_profile_directory_is_loaded_by_name(tmp_path: Path) -> None:
    (tmp_path / "private-harbor-v1.yaml").write_text(PRIVATE_PROFILE_YAML)
    profile = runtime_profile(
        "private-harbor-v1",
        {"EVOLVE_RUNTIME_PROFILE_PATH": str(tmp_path)},
    )
    assert profile.name == "private-harbor-v1"

def test_duplicate_profile_name_is_rejected(tmp_path: Path) -> None:
    built_in = resources.files("evolve").joinpath("profiles/harbor-v1.yaml").read_text()
    (tmp_path / "duplicate.yaml").write_text(built_in)
    with pytest.raises(RuntimeProfileResolutionError, match="multiple runtime profiles"):
        runtime_profile("harbor-v1", {"EVOLVE_RUNTIME_PROFILE_PATH": str(tmp_path)})
```

Add parameterized rejection for `ubuntu:latest`, `sha256:short`, and whitespace-containing image references.

- [ ] **Step 2: Run tests and observe failure**

```bash
uv run pytest tests/test_runtime_profiles.py tests/test_config_parser.py -q
```

Expected: FAIL because neutral data-backed profiles and optional endpoints do not exist.

- [ ] **Step 3: Add the profile data**

`harbor-v1.yaml`:

```yaml
schema_version: 1
name: harbor-v1
engine: harbor
required_tools: [docker, harbor]
candidate_runtime: null
dependency_policy: agent-owned
cache_policy: none
network_policy: model-endpoint
preflight_capabilities: [configuration, evaluation-contract, runtime-image]
smoke_capabilities: [one-model-request]
```

`harbor-uv-v1.yaml` uses the same fields with:

```yaml
name: harbor-uv-v1
required_tools: [docker, harbor, uv]
candidate_runtime: {variant: uv, project: target, python: "3.12"}
dependency_policy: uv-frozen
cache_policy: content-addressed-shared
network_policy: prepare-online-trial-offline
preflight_capabilities: [configuration, evaluation-contract, runtime-image, dependency-lock]
```

- [ ] **Step 4: Implement profile discovery and immutable resolution**

Remove credential, provider-route, proxy, and bypass fields from `RuntimeProfileV1`. Load packaged and configured YAML/JSON files, validate exact fields, and reject duplicate names. Raise `RuntimeProfileResolutionError` with a `RuntimeProfileErrorCode` instead of requiring callers to inspect its message.

```python
_OFFICIAL_OPENAI_ENDPOINT = "https://api.openai.com/v1"
_IMMUTABLE_IMAGE = re.compile(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}")

def model_endpoint_digest(url: str | None) -> str:
    normalized = normalize_model_endpoint(url or _OFFICIAL_OPENAI_ENDPOINT)
    return hashlib.sha256(normalized.encode()).hexdigest()

def _immutable_runtime_digest(value: str) -> str:
    normalized = value.strip().lower()
    if _IMMUTABLE_IMAGE.fullmatch(normalized) is None:
        raise RuntimeProfileResolutionError(
            "EVOLVE_RUNTIME_DIGEST must be an immutable SHA-256 image reference"
        )
    return normalized
```

`load_resolved_runtime_profile()` validates the frozen schema and digest without requiring the original private search path.

- [ ] **Step 5: Decouple syntax normalization and rename recipes**

`normalize_evaluator_config()` validates a nonempty `runtime.profile` string and engine/runtime shape but does not resolve the name. Rename `harbor-bytedance-v1` to `harbor-v1` and `harbor-bytedance-uv-v1` to `harbor-uv-v1`. Replace fake strict-test image strings with 64-hex immutable references.

- [ ] **Step 6: Run and commit**

```bash
uv run pytest tests/test_runtime_profiles.py tests/test_config_parser.py tests/test_runtime_profile_recipe_conformance.py tests/test_phase_e_recipes.py tests/test_m0_init.py -q
git add src/evolve/profiles src/evolve/runtime_profiles.py src/evolve/evaluator_config.py src/evolve/workspace.py recipes/aevolve/evolve.yaml recipes/ahe/evolve.yaml recipes/gepa/evolve.yaml recipes/hill_climb/evolve.yaml recipes/hyperagents/evolve.yaml tests/test_runtime_profiles.py tests/test_config_parser.py tests/test_runtime_profile_recipe_conformance.py tests/test_phase_e_recipes.py tests/test_m0_init.py
git commit -m "feat: load neutral declarative runtime profiles"
```

Expected: all tests pass and public profile payloads contain no ByteDance policy.

---

### Task 4: Resolve API and explicit Codex authentication

**Files:**
- Create: `src/evolve/runtime_auth.py`
- Create: `tests/test_runtime_auth.py`
- Modify: `seeds/codex/agent.py`
- Modify: `tests/test_m7_codex_seed.py`

**Interfaces:**
- Produces: `AuthenticationKind` values `API` and `CODEX_AUTH_JSON`.
- Produces: `AuthenticationErrorCode` values `CREDENTIAL_MISSING`, `AUTH_JSON_MISSING`, and `AUTH_JSON_UNSUPPORTED`.
- Produces: `resolve_authentication(agent_kind: str, environment: Mapping[str, str]) -> ResolvedAuthentication`.
- Produces: `ResolvedAuthentication.environment() -> dict[str, str]`.

- [ ] **Step 1: Create failing tests**

```python
def test_codex_prefers_explicit_auth_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {}}\n')
    result = resolve_authentication(
        "codex",
        {"CODEX_AUTH_JSON_PATH": str(auth), "OPENAI_API_KEY": "api-key"},
    )
    assert result.kind is AuthenticationKind.CODEX_AUTH_JSON
    assert result.environment() == {"CODEX_AUTH_JSON_PATH": str(auth.resolve())}

def test_codex_defaults_to_api_without_base_url() -> None:
    result = resolve_authentication("codex", {"OPENAI_API_KEY": "api-key"})
    assert result.kind is AuthenticationKind.API
    assert result.environment() == {"OPENAI_API_KEY": "api-key"}

def test_codex_does_not_discover_home_auth_json(tmp_path: Path) -> None:
    (tmp_path / "auth.json").write_text("{}\n")
    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("codex", {})
    assert excinfo.value.code is AuthenticationErrorCode.CREDENTIAL_MISSING

def test_non_codex_rejects_auth_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")
    with pytest.raises(RuntimeAuthenticationError) as excinfo:
        resolve_authentication("mini-swe-agent", {"CODEX_AUTH_JSON_PATH": str(auth)})
    assert excinfo.value.code is AuthenticationErrorCode.AUTH_JSON_UNSUPPORTED
```

Also test missing auth file, optional base URL in API mode, and no secret/path in exception text.

- [ ] **Step 2: Verify module absence**

```bash
uv run pytest tests/test_runtime_auth.py -q
```

Expected: collection FAIL because `evolve.runtime_auth` does not exist.

- [ ] **Step 3: Implement typed authentication**

```python
class AuthenticationKind(StrEnum):
    API = "api"
    CODEX_AUTH_JSON = "codex_auth_json"

@dataclass(frozen=True)
class ResolvedAuthentication:
    kind: AuthenticationKind
    values: tuple[tuple[str, str], ...]

    def environment(self) -> dict[str, str]:
        return dict(self.values)
```

Treat shipped `codex` and `target.agent:HarborAgent` adapters as Codex-capable. Treat known MiniSWE and unknown custom selectors as API-only. Validate explicit paths with `expanduser().resolve()` and `is_file()`. Never inspect `Path.home()`. Include `OPENAI_BASE_URL` only when set.

- [ ] **Step 4: Keep the seed neutral**

Keep `seeds/codex/agent.py` relying on Harbor’s explicit path/API behavior. Add a seed test proving smoke instruction rewriting does not modify authentication variables.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/test_runtime_auth.py tests/test_m7_codex_seed.py -q
git add src/evolve/runtime_auth.py tests/test_runtime_auth.py seeds/codex/agent.py tests/test_m7_codex_seed.py
git commit -m "feat: support explicit Codex and API authentication"
```

---

### Task 5: Simplify runtime environment planning

**Files:**
- Modify: `src/evolve/runtime_environment.py`
- Modify: `tests/test_runtime_environment.py`
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `tests/test_harbor_meta_agent.py`
- Modify: `src/evolve/evaluation/execution.py`
- Modify: `src/evolve/candidate/smoke.py`
- Modify: `tests/test_m1_evaluator_invariants.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_candidate_smoke.py`

**Interfaces:**
- Consumes: `ResolvedAuthentication.environment()`.
- Produces: `resolve_runtime_environment(profile, environment, *, agent_kind, meta_agent_kind=None, agent_overrides=None, verifier_overrides=None) -> RuntimeEnvironmentPlan`.
- Preserves: `RuntimeEnvironmentPlan` accessors and `write_harbor_environment_inputs()`.

- [ ] **Step 1: Replace host-rewriting tests with exact passthrough tests**

```python
def test_standard_proxy_values_pass_through_unchanged() -> None:
    environment = {
        "OPENAI_API_KEY": "sensitive-key-value",
        "HTTPS_PROXY": "http://proxy.example:8118",
        "NO_PROXY": "pypi.org,.internal.example",
    }
    plan = resolve_runtime_environment(
        resolved_profile(),
        environment,
        agent_kind="codex",
        meta_agent_kind="codex",
    )
    process = plan.process_env()
    assert process["EVOLVE_RUNTIME_AGENT_HTTPS_PROXY"] == environment["HTTPS_PROXY"]
    assert process["EVOLVE_RUNTIME_AGENT_NO_PROXY"] == environment["NO_PROXY"]
```

Add API-without-base, auth-json, no dependency-host filtering, proxy equality, and persisted-value redaction tests.

Add a profile-less workspace compatibility test that calls `resolve_legacy_runtime_environment()` with API credentials and unchanged standard proxies, and a Codex legacy test that accepts an explicit existing `CODEX_AUTH_JSON_PATH`. Both must use the same generic templating and must not restore automatic home lookup or proxy rewriting.

- [ ] **Step 2: Verify old policy fails**

```bash
uv run pytest tests/test_runtime_environment.py tests/test_harbor_meta_agent.py -q
```

Expected: FAIL on the old base-URL requirement, forbidden auth-json behavior, and `NO_PROXY` rewriting.

- [ ] **Step 3: Reduce environment planning to generic transport**

Remove dependency hosts, model-host parsing, automatic bypass changes, ByteDance overrides, and file-auth rejection.

```python
authentication = resolve_authentication(agent_kind, source)
for name, value in authentication.environment().items():
    _add_value(process, role_values[RuntimeRole.AGENT], RuntimeRole.AGENT, name, value)

for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
    if source.get(name):
        value = _single_line_value(name, source[name])
        for role in RuntimeRole:
            _add_value(process, role_values[role], role, name, value)
```

Safe scalar overrides remain, but credentials, auth paths, endpoints, and proxy names are configured only by process environment/project `.env`, not `agent_env`.

- [ ] **Step 4: Update all callers**

The evaluator passes its shipped agent selector, the meta-agent runner passes `config["agent"]`, and smoke uses evaluator configuration. Keep real values in private process variables and Harbor templates in `--ae`/`--ve`.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/test_runtime_environment.py tests/test_harbor_meta_agent.py tests/test_m1_evaluator_invariants.py tests/test_harbor_evaluator_template.py tests/test_candidate_smoke.py -q
git add src/evolve/runtime_environment.py library/meta_agent/runners/harbor.py src/evolve/evaluation/execution.py src/evolve/candidate/smoke.py tests/test_runtime_environment.py tests/test_harbor_meta_agent.py tests/test_m1_evaluator_invariants.py tests/test_harbor_evaluator_template.py tests/test_candidate_smoke.py
git commit -m "refactor: isolate generic Harbor runtime inputs"
```

Expected: no serialized artifact contains a literal key, auth path, custom endpoint, or proxy value.

---

### Task 6: Certify local and registry dataset contents

**Files:**
- Modify: `src/evolve/evaluation/datasets.py`
- Modify: `src/evolve/splits.py`
- Modify: `src/evolve/workspace.py`
- Modify: `tests/test_evaluation_datasets.py`
- Modify: `tests/test_m8_dataset_splits.py`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_contract_recipe_conformance.py`

**Interfaces:**
- Produces: `DatasetContentIdentity.task_digests: tuple[tuple[str, str], ...]`.
- Produces: `DatasetContentIdentity.task_digest_map() -> dict[str, str]`.
- Produces: `dataset_content_identity(dataset: str, *, base_dir: Path, client: RegistryMetadataClient | None = None) -> DatasetContentIdentity`.
- Produces: `build_manifest(..., registry_client: RegistryMetadataClient | None = None) -> dict[str, Any]` as the deterministic test seam used only when the dataset is not local.
- Produces: verified version 2 manifests for local and registry sources.

- [ ] **Step 1: Add failing single-pass and registry tests**

```python
def test_build_manifest_hashes_each_local_task_once(tmp_path: Path, monkeypatch) -> None:
    dataset = make_dataset(tmp_path, ("task-a", "task-b"))
    calls: list[str] = []
    real = datasets.local_task_content_digest

    def counted(root: Path, member: str) -> str:
        calls.append(member)
        return real(root, member)

    monkeypatch.setattr(datasets, "local_task_content_digest", counted)
    manifest = build_manifest(
        str(dataset), SPLIT, base_dir=tmp_path, sampling="static", gate_limit=1
    )
    assert sorted(calls) == ["task-a", "task-b"]
    assert manifest["identity_status"] == "verified"
```

Add a fake registry client test asserting version 2, `source == "registry"`, immutable resolved reference, per-task digests, and deterministic split membership. Add mutable Git/package rejection cases.

- [ ] **Step 2: Verify current integration fails**

```bash
uv run pytest tests/test_evaluation_datasets.py tests/test_m8_dataset_splits.py -q
```

Expected: FAIL because registry identities are test-only and local tasks are hashed twice.

- [ ] **Step 3: Return reusable per-task digests**

```python
@dataclass(frozen=True)
class DatasetContentIdentity:
    source: str
    digest: str
    members: tuple[str, ...]
    resolved_reference: str
    task_digests: tuple[tuple[str, str], ...]

    def task_digest_map(self) -> dict[str, str]:
        return dict(self.task_digests)
```

For registry tasks, hash each canonical immutable task payload. Build the aggregate identity from source plus sorted `{name, digest}` entries.

- [ ] **Step 4: Build verified manifests for both sources**

Resolve a local dataset path first; otherwise query registry metadata. Assign splits from `identity.members` and reuse `identity.task_digest_map()`. Accept `local` and `registry` in v2 parsing. Fail initialization if the registry cannot provide immutable references; retain version 1 as `legacy_unverified`.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/test_evaluation_datasets.py tests/test_m8_dataset_splits.py tests/test_m0_init.py tests/test_contract_recipe_conformance.py -q
git add src/evolve/evaluation/datasets.py src/evolve/splits.py src/evolve/workspace.py tests/test_evaluation_datasets.py tests/test_m8_dataset_splits.py tests/test_m0_init.py tests/test_contract_recipe_conformance.py
git commit -m "feat: certify local and registry dataset contents"
```

---

### Task 7: Update the contract and split preflight responsibilities

**Files:**
- Modify: `src/evolve/evaluation/contract.py`
- Delete: `src/evolve/preflight.py`
- Create: `src/evolve/preflight/__init__.py`
- Create: `src/evolve/preflight/models.py`
- Create: `src/evolve/preflight/checks.py`
- Create: `src/evolve/preflight/runner.py`
- Modify: `tests/test_evaluation_contract.py`
- Modify: `tests/test_evaluation_contract_execution.py`
- Modify: `tests/test_preflight.py`
- Modify: `tests/test_live_runtime_profile_smoke.py`
- Modify: `tests/test_selection_certification.py`

**Interfaces:**
- Contract consumes `ResolvedRuntimeProfileV1.endpoint_digest` and preserves all existing public contract functions.
- Preflight preserves imports for `PreflightMode`, `PreflightStatus`, `PreflightCheckStatus`, `PreflightFailureCategory`, `ArtifactReferenceV1`, `PreflightCheckV1`, `PreflightResultV1`, `run_preflight`, and `artifact_reference`.
- Typed failure categories include `credential_missing`, `auth_json_missing`, `auth_json_unsupported`, `endpoint_invalid`, `profile_not_found`, `profile_ambiguous`, and `runtime_image_unavailable`.
- Typed profile and authentication exceptions are mapped by their `.code` fields; runtime environment errors gain the same typed-code pattern where preflight needs to distinguish invalid overrides from endpoint mismatch.

- [ ] **Step 1: Add contract privacy tests**

```python
def test_contract_binds_endpoint_digest_without_persisting_url(strict_workspace: Path) -> None:
    contract = resolve_evaluation_contract(
        _context(strict_workspace, candidate_commit(strict_workspace))
    )
    serialized = json.dumps(contract.to_dict())
    assert contract.endpoint_digest == model_endpoint_digest(
        "https://private.example/v1"
    )
    assert "private.example" not in serialized
```

Also test that a changed endpoint rejects the frozen profile and an absent base URL uses the official endpoint identity.

- [ ] **Step 2: Add preflight typed-error and exact-environment tests**

```python
def test_local_probe_uses_exact_supplied_environment(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(preflight_checks.subprocess, "run", fake_run)
    assert local_command_succeeds(["tool"], {"PATH": "/controlled/bin"})
    assert captured == {"PATH": "/controlled/bin"}
```

Assert typed failure categories directly for missing API credentials, missing auth file, unsupported auth file, invalid endpoint, missing profile, ambiguous profile, and missing image.

- [ ] **Step 3: Verify the new tests fail**

```bash
uv run pytest tests/test_evaluation_contract.py tests/test_preflight.py tests/test_evaluation_contract_execution.py -q
```

Expected: FAIL on old route fields, message-based classification, and ambient environment merging.

- [ ] **Step 4: Update the single contract module**

Add a module docstring explaining trusted `gen/0` Git inputs. Replace provider route fields with endpoint digest while retaining agent and model:

```python
model_identity={
    "agent": _optional_string(evaluator.get("agent")),
    "model": _optional_string(evaluator.get("model")),
    "endpoint_digest": resolved_profile.endpoint_digest,
}
```

Do not add auth mode, auth path, credential, or proxy data.

- [ ] **Step 5: Move preflight code by responsibility**

Move enums/dataclasses and serialization to `models.py`; typed host/runtime probes to `checks.py`; ordering, short-circuiting, smoke calls, redaction, and receipt writing to `runner.py`. Re-export the stable API from `__init__.py`. Map typed domain error codes, not message strings. Pass exactly `dict(environment)` to subprocess probes.

- [ ] **Step 6: Run and commit**

```bash
uv run pytest tests/test_evaluation_contract.py tests/test_evaluation_contract_execution.py tests/test_contract_recipe_conformance.py tests/test_selection_certification.py tests/test_preflight.py tests/test_live_runtime_profile_smoke.py tests/test_runtime_profile_recipe_conformance.py -q
uv run python -c "from evolve.preflight import PreflightMode, PreflightResultV1, run_preflight"
uv run ruff check src/evolve/preflight src/evolve/evaluation/contract.py
git add src/evolve/evaluation/contract.py src/evolve/preflight.py src/evolve/preflight tests/test_evaluation_contract.py tests/test_evaluation_contract_execution.py tests/test_selection_certification.py tests/test_preflight.py tests/test_live_runtime_profile_smoke.py tests/test_runtime_profile_recipe_conformance.py
git commit -m "refactor: certify runtime and separate preflight checks"
```

Expected: all commands succeed and public imports remain stable.

---

### Task 8: Make evaluator internals explicit, document behavior, and verify the branch

**Files:**
- Modify: `scaffolds/evaluators/harbor/engine.sh`
- Modify: `scaffolds/workspace/evaluator/stub_eval.py`
- Modify: `src/evolve/candidate/smoke.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_candidate_smoke.py`
- Modify: `README.md`
- Modify: `scaffolds/workspace/README.md`
- Modify: `scaffolds/workspace/AGENTS.md`
- Modify: `library/README.md`
- Modify: remaining tests with stale public profile names.

**Interfaces:**
- Produces: clear failure when internal evaluator runtime inputs are missing.
- Documents: one project-root `.env`, auth precedence, optional endpoint, proxy passthrough, profile search, neutral profiles, registry certification, and internal evaluator status.

- [ ] **Step 1: Add a failing direct-invocation test**

```python
def test_engine_rejects_direct_invocation_without_prepared_runtime_inputs(
    tmp_path: Path,
) -> None:
    completed = run_generated_engine(tmp_path, create_runtime_inputs=False)
    assert completed.returncode != 0
    assert "internal evaluator runtime inputs are missing" in completed.stderr
```

Run it:

```bash
uv run pytest tests/test_harbor_evaluator_template.py::test_engine_rejects_direct_invocation_without_prepared_runtime_inputs -q
```

Expected: FAIL because current shell silently skips missing files.

- [ ] **Step 2: Require internal runtime inputs**

After the `EVAL_STUB=1` prefix has had an opportunity to exit, require prepared files:

```sh
for required_input in runtime-agent.env runtime-verifier.env candidate-runtime.env; do
  if [ ! -f "$EVOLVE_RUN_DIR/$required_input" ]; then
    echo "evolve: internal evaluator runtime inputs are missing: $required_input" >&2
    exit 1
  fi
done
```

- [ ] **Step 3: Document stub and smoke roles**

Add module documentation stating:

- `stub_eval.py` runs only under `EVAL_STUB=1`; `# FAIL task-N` emits an observed failure and `# MISSING task-N` omits evidence.
- `candidate/smoke.py` serves `evolve candidate-smoke` and `preflight --smoke`, not ordinary evaluation rounds.

- [ ] **Step 4: Update public documentation**

Show the minimal API setup:

```dotenv
OPENAI_API_KEY=...
```

Show optional `OPENAI_BASE_URL`, explicit `CODEX_AUTH_JSON_PATH`, `EVOLVE_RUNTIME_PROFILE_PATH`, and standard proxy variables. State auth-json precedence, no home lookup, no caller `.env`, private value exclusion, neutral profile names, registry identity guarantees, and internal `evaluator/eval.sh` status.

- [ ] **Step 5: Scan for stale public policy**

```bash
rg -n "harbor-bytedance|ByteDance|EVOLVE_HARBOR_.*PROXY|caller.*\.env|CODEX_FORCE_AUTH_JSON|dependency-proxy-model-bypass" README.md docs src library scaffolds recipes tests --glob '!docs/superpowers/**'
```

Expected: no public runtime-policy occurrence. A historical migration assertion is acceptable only when its test name explains the retained legacy input.

- [ ] **Step 6: Run focused architecture suites**

```bash
uv run pytest tests/test_runtime_auth.py tests/test_runtime_profiles.py tests/test_runtime_environment.py tests/test_preflight.py tests/test_evaluation_datasets.py tests/test_evaluation_contract.py tests/test_evaluation_diagnostics.py -q
uv run pytest tests/test_runtime_profile_recipe_conformance.py tests/test_contract_recipe_conformance.py tests/test_diagnostics_recipe_conformance.py tests/test_harbor_meta_agent.py tests/test_harbor_evaluator_template.py tests/test_candidate_smoke.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Run complete verification**

```bash
uv run ruff check .
uv run pytest -q
git diff --check
```

Expected: Ruff and all tests succeed with no whitespace errors.

- [ ] **Step 8: Commit final docs and integration changes**

```bash
git add scaffolds/evaluators/harbor/engine.sh scaffolds/workspace/evaluator/stub_eval.py src/evolve/candidate/smoke.py tests/test_harbor_evaluator_template.py tests/test_candidate_smoke.py README.md scaffolds/workspace/README.md scaffolds/workspace/AGENTS.md library/README.md tests/test_live_runtime_profile_smoke.py
git commit -m "docs: explain portable runtime configuration"
```

- [ ] **Step 9: Review branch scope**

```bash
git status --short
git diff origin/main...HEAD --stat
git log --oneline origin/main..HEAD
```

Expected: clean worktree, cohesive commits, no unrelated files, and every approved review concern represented in code, tests, or documentation.
