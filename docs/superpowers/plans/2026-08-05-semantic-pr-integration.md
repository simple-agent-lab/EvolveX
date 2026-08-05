# Semantic PR Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one clean draft PR on current remote `main` that preserves the final behavior of PRs #23, #26, #29, and #31 and passes local plus DevBox qualification.

**Architecture:** Current `main` remains the orchestration and reporting baseline. Certified evaluation and inline runtime configuration are added as cohesive framework services, then the later PR #31 contracts are applied at the task-selection and MiniSWE transport boundaries. Codex candidate binding is integrated independently so runtime work cannot regress it.

**Tech Stack:** Python 3.12, Bash, uv, pytest/pytest-xdist, Ruff, ty, Harbor 0.18.0, Docker, Git, SSH/DevBox.

## Global Constraints

- Start from a freshly fetched `origin/main`; exclude unrelated local commit `0ad0281`.
- PR #26 subsumes PR #23; do not restore removed experiment tooling.
- PR #31 wins over PR #29 for task limiting, MiniSWE role dispatch, candidate transport, session identity, and model-variable ownership.
- Public proxy behavior is optional and disabled by default; never commit DevBox endpoints, proxy values, credentials, bundles, or outputs.
- Downloads on DevBox may use its private proxies; model calls must be covered by `NO_PROXY` and `no_proxy`.
- Preserve current-main orchestration, Skill, reporting, release, and documentation behavior unless an approved contract requires an explicit change.
- Each production change begins with a failing regression test and ends with focused green tests before commit.

---

### Task 1: Bind Codex Trials to the Candidate Instance

**Files:**
- Modify: `scaffolds/evaluators/harbor/engine.sh`
- Modify: `seeds/codex/agent.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_m7_codex_seed.py`

**Interfaces:**
- Consumes: Harbor `extra_env`, `evaluator/agent.kwargs`, and `EVOLVE_HARBOR_CODEX_SUBSCRIPTION`.
- Produces: `_target_root(extra_env: object) -> Path`; per-instance `HarborAgent._target_root`; explicit `EVOLVE_CANDIDATE_SOURCE`; empty-value API credential shadowing.

- [ ] **Step 1: Add candidate-binding regressions**

Add tests equivalent to:

```python
def test_builtin_codex_wrapper_uses_candidate_source_from_extra_env(tmp_path, monkeypatch):
    candidate = _write_candidate_target(tmp_path / "candidate", model="candidate-model")
    module = _load_target_agent(SEED_AGENT)
    agent = module.HarborAgent(
        logs_dir=tmp_path / "logs",
        extra_env={"EVOLVE_CANDIDATE_SOURCE": str(candidate)},
    )
    assert agent.model_name == "candidate-model"
    assert agent.kwargs["prompt_template_path"] == candidate / "prompt.md"


def test_builtin_codex_wrapper_rejects_non_string_candidate(tmp_path, monkeypatch):
    module = _load_target_agent(SEED_AGENT)
    with pytest.raises(TypeError, match="EVOLVE_CANDIDATE_SOURCE must be a string"):
        module.HarborAgent(logs_dir=tmp_path, extra_env={"EVOLVE_CANDIDATE_SOURCE": 42})
```

Also cover per-instance isolation, missing/empty fallback, ambient-variable non-inheritance, skill upload source, protected agent kwargs, parent-process preservation, explicit proxy forwarding, and subscription-mode empty API values.

- [ ] **Step 2: Verify the regressions fail**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q \
  tests/test_m7_codex_seed.py tests/test_harbor_evaluator_template.py
```

Expected: candidate-path and subscription-isolation assertions fail on the current-main implementation.

- [ ] **Step 3: Implement per-instance candidate resolution and evaluator forwarding**

Implement this contract in `seeds/codex/agent.py`:

```python
def _target_root(extra_env: object) -> Path:
    if not isinstance(extra_env, Mapping) or "EVOLVE_CANDIDATE_SOURCE" not in extra_env:
        return MODULE_ROOT
    candidate_source = extra_env["EVOLVE_CANDIDATE_SOURCE"]
    if candidate_source == "":
        return MODULE_ROOT
    if not isinstance(candidate_source, str):
        raise TypeError("EVOLVE_CANDIDATE_SOURCE must be a string")
    return Path(candidate_source).expanduser().resolve()
```

Use the resolved root for config, prompt, and skills. Update `engine.sh` to pass `evaluator/agent.kwargs`, candidate source, and explicit empty OpenAI credential values in subscription mode without clearing the parent shell environment.

- [ ] **Step 4: Run focused validation**

Run the focused pytest command, `ruff check` on the changed Python files, and `bash -n scaffolds/evaluators/harbor/engine.sh`.

- [ ] **Step 5: Commit**

```bash
git add scaffolds/evaluators/harbor/engine.sh seeds/codex/agent.py \
  tests/test_harbor_evaluator_template.py tests/test_m7_codex_seed.py
git commit -m "fix: bind Codex trials to candidate source"
```

### Task 2: Add Inline Runtime, Authentication, and Environment Planning

**Files:**
- Create: `src/evolve/evaluator_config.py`
- Create: `src/evolve/runtime_config.py`
- Create: `src/evolve/runtime_auth.py`
- Create: `src/evolve/runtime_environment.py`
- Create: `tests/test_runtime_config.py`
- Create: `tests/test_runtime_auth.py`
- Create: `tests/test_runtime_environment.py`
- Modify: `src/evolve/config.py`
- Modify: `src/evolve/runtime.py`
- Modify: `src/evolve/workspace.py`
- Modify: `tests/test_config_parser.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Produces: `RuntimeConfigV1`, `ResolvedRuntimeV1`, `resolve_runtime`, `load_resolved_runtime`, `resolve_authentication`, `RuntimeEnvironmentPlan`, `resolve_runtime_environment`, and `write_harbor_environment_inputs`.
- Consumes: recipe `evaluator.runtime`, process environment, agent kind, protected evaluator values, and current workspace runtime pins.

- [ ] **Step 1: Add strict parser, digest, auth, and routing tests**

Cover exact field rejection, uv candidate project containment, Python `major.minor`, canonical endpoint normalization, secret-free runtime digests, API-key default auth, explicit Codex auth path, no home fallback, optional/required proxy modes, endpoint bypass in both `NO_PROXY` spellings, protected-name rejection, scalar validation, and atomic Harbor input files.

Representative assertions:

```python
resolved = resolve_runtime(
    {"proxy": {"mode": "optional", "model_endpoint": "bypass"}},
    engine="harbor",
    environment={"OPENAI_BASE_URL": "https://model.example/v1"},
)
assert "model.example" not in json.dumps(resolved.to_dict())
assert resolved.endpoint_digest == model_endpoint_digest("https://model.example/v1")

plan = resolve_runtime_environment(
    resolved,
    role=RuntimeRole.EVALUATOR,
    agent_kind="openai",
    environment={"OPENAI_API_KEY": "secret", "HTTPS_PROXY": "http://proxy"},
)
assert plan.agent_environment["OPENAI_API_KEY"] == "secret"
assert "model.example" in plan.process_environment["NO_PROXY"]
```

- [ ] **Step 2: Verify new tests fail because modules are absent**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q \
  tests/test_runtime_config.py tests/test_runtime_auth.py \
  tests/test_runtime_environment.py tests/test_config_parser.py tests/test_runtime.py
```

- [ ] **Step 3: Implement the runtime services**

Port the final PR #29 inline-runtime model, using these stable types:

```python
@dataclass(frozen=True)
class RuntimeConfigV1:
    candidate: CandidateRuntimeConfig | None = None
    proxy: ProxyRoutingConfig | None = None


@dataclass(frozen=True)
class ResolvedRuntimeV1:
    config: RuntimeConfigV1
    engine: str
    endpoint_digest: str
    digest: str
```

Keep raw credentials and proxy values outside `to_dict()` and canonical digest payloads. Integrate normalized runtime config into recipe parsing and workspace materialization without introducing a named profile registry.

- [ ] **Step 4: Run focused tests, Ruff, and ty**

Run the focused tests, `ruff check`/`ruff format --check` for new modules, and `ty check src/evolve`.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/evaluator_config.py src/evolve/runtime_config.py \
  src/evolve/runtime_auth.py src/evolve/runtime_environment.py \
  src/evolve/config.py src/evolve/runtime.py src/evolve/workspace.py \
  tests/test_runtime_config.py tests/test_runtime_auth.py \
  tests/test_runtime_environment.py tests/test_config_parser.py tests/test_runtime.py
git commit -m "feat: add inline evaluator runtime contracts"
```

### Task 3: Add Typed Preflight and Candidate Runtime Preparation

**Files:**
- Delete: `src/evolve/preflight.py`
- Create: `src/evolve/preflight/__init__.py`
- Create: `src/evolve/preflight/models.py`
- Create: `src/evolve/preflight/checks.py`
- Create: `src/evolve/preflight/runner.py`
- Create: `tests/test_preflight.py`
- Modify: `tests/test_candidate_smoke.py`
- Modify: `src/evolve/candidate/smoke.py`
- Modify: `src/evolve/cli.py`
- Modify: `src/evolve/uv_runtime.py`
- Modify: `tests/test_locked_runtime.py`
- Modify: `tests/test_m0_init.py`

**Interfaces:**
- Produces: typed preflight receipts and an opt-in one-request model smoke; locked candidate uv preparation tied to resolved runtime.
- Consumes: `ResolvedRuntimeV1`, authentication result, dataset/runtime availability, and recipe/workspace inputs.

- [ ] **Step 1: Add failing preflight and locked-runtime tests**

Test aggregated failures, stable error codes, read-only preflight, opt-in network smoke, host-independent cache paths, candidate lock mismatch, offline build backend availability, and no provider-specific public defaults.

```python
receipt = run_preflight(request)
assert receipt.schema_version == 1
assert {item.code for item in receipt.checks if not item.ok} == {
    PreflightCode.MODEL_AUTH_MISSING,
    PreflightCode.RUNTIME_UNAVAILABLE,
}
assert not workspace.exists()
```

- [ ] **Step 2: Confirm failures**

Run `pytest -q tests/test_preflight.py tests/test_candidate_smoke.py tests/test_locked_runtime.py tests/test_m0_init.py`.

- [ ] **Step 3: Implement preflight and runtime preparation**

Adapt PR #29's final preflight package to current-main CLI and workspace APIs. Preserve current `doctor` semantics: preflight is prospective and read-only; doctor remains workspace diagnostics. Candidate build/sync uses the locked workspace runtime and local uv cache without writing host-specific locations into receipts.

- [ ] **Step 4: Run focused tests and static checks**

Run the task tests, Ruff, formatting, and ty.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/preflight src/evolve/candidate/smoke.py src/evolve/cli.py \
  src/evolve/uv_runtime.py tests/test_preflight.py tests/test_candidate_smoke.py \
  tests/test_locked_runtime.py tests/test_m0_init.py
git commit -m "feat: add typed runtime preflight"
```

### Task 4: Certify Evaluation Inputs and Diagnostics

**Files:**
- Create: `src/evolve/evaluation/contract.py`
- Create: `src/evolve/evaluation/datasets.py`
- Create: `src/evolve/evaluation/diagnostics.py`
- Create: `tests/test_evaluation_contract.py`
- Create: `tests/test_evaluation_contract_execution.py`
- Create: `tests/test_evaluation_datasets.py`
- Create: `tests/test_evaluation_diagnostics.py`
- Create: `tests/test_diagnostics_recipe_conformance.py`
- Modify: `src/evolve/evaluation/__init__.py`
- Modify: `src/evolve/evaluation/evidence.py`
- Modify: `src/evolve/evaluation/results.py`
- Modify: `src/evolve/archive.py`
- Modify: `src/evolve/feedback.py`
- Modify: `src/evolve/frozen/interfaces.py`
- Modify: `src/evolve/frozen/sdk.py`

**Interfaces:**
- Produces: `EvaluationContractV1`, `ContractResolutionContext`, `resolve_evaluation_contract`, `evaluation_contract_mode`, `verify_candidate_runtime_receipt`, selected dataset identity, and typed diagnostics.
- Consumes: trusted `gen/0` evaluator/runtime inputs, exact candidate commit, effective task members, evaluator artifacts, and trial results.

- [ ] **Step 1: Add contract and diagnostic tests**

Assert canonical digest sensitivity and legacy behavior:

```python
contract = resolve_evaluation_contract(
    ContractResolutionContext(
        workspace=workspace,
        candidate_commit=candidate,
        purpose="candidate",
        generation="1",
        task_limit=1,
    )
)
assert contract.candidate_commit == candidate
assert len(contract.task_members) == 1
assert contract.contract_id == canonical_digest(contract.payload())
assert evaluation_contract_mode(legacy_workspace) is ContractMode.LEGACY_UNVERIFIED
```

Test dataset content changes, evaluator changes, endpoint normalization, dependency lock changes, retry changes, missing trials, candidate-invalid failures, verifier failures, infrastructure failures, and valid zero rewards.

- [ ] **Step 2: Verify failures**

Run the five new test modules plus `tests/test_evaluation_records.py`, `tests/test_task_vectors.py`, and `tests/test_selection_certification.py`.

- [ ] **Step 3: Implement contract, dataset identity, and diagnostics**

Port PR #29's final strict receipt implementation. Adapt imports and record fields to current-main evidence/replay APIs. Preserve replay verification from PR #28 and require both indexed artifacts and adjacent Harbor results to agree with the new contract.

- [ ] **Step 4: Run focused tests and static checks**

Run the task tests, Ruff, formatting, and ty.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/evaluation src/evolve/archive.py src/evolve/feedback.py \
  src/evolve/frozen tests/test_evaluation_contract.py \
  tests/test_evaluation_contract_execution.py tests/test_evaluation_datasets.py \
  tests/test_evaluation_diagnostics.py tests/test_diagnostics_recipe_conformance.py \
  tests/test_evaluation_records.py tests/test_task_vectors.py \
  tests/test_selection_certification.py
git commit -m "feat: certify evaluation inputs and diagnostics"
```

### Task 5: Make Effective Task Selection Authoritative End to End

**Files:**
- Modify: `src/evolve/splits.py`
- Modify: `src/evolve/evaluation/identity.py`
- Modify: `src/evolve/evaluation/execution.py`
- Modify: `scaffolds/evaluators/harbor/engine.sh`
- Modify: `scaffolds/evaluators/harbor/parse_score.py`
- Modify: `scaffolds/evaluators/harbor/harbor_artifacts.py`
- Modify: `tests/test_m8_dataset_splits.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_harbor_parse_score.py`
- Modify: `tests/test_harbor_artifacts.py`
- Modify: `tests/test_evaluation_contract_execution.py`

**Interfaces:**
- Produces: `effective_task_set_identity`, limit-aware `selected_task_names`, `write_runtime_task_file_selection`, and `_runtime_selection_matches`.
- Consumes: deterministic split manifest or task file, optional validated task limit, evaluator repetitions, and runtime selection artifacts.

- [ ] **Step 1: Add failing PR #31 precedence tests**

Cover one-task limit, oversized limit, multiple repetitions, task-file selection, host/runtime agreement, malformed/non-positive values, incomplete trials, and zero reward:

```python
identity = effective_task_set_identity(workspace, purpose="candidate", task_limit=1)
assert identity.members == (expected_first_task,)
assert expected_trials(evaluator, selected_tasks=len(identity.members)) == repetitions

record = evaluate(workspace, candidate, purpose="candidate", task_limit=1)
assert record.expected_trials == 1
assert record.completed_trials == 1
assert record.outcome is Outcome.BENCHMARK_COMPLETE
assert record.score == 0.0
```

- [ ] **Step 2: Confirm failures against Task 4 behavior**

Run the listed tests. Expected failures must demonstrate that task limiting is still applied at more than one boundary or that runtime selection is not authoritative.

- [ ] **Step 3: Implement the single effective-selection path**

Apply the task limit during deterministic selection, write the limited members and digest, pass the same members to Harbor, calculate expected trials once from members times repetitions, and reject runtime/host disagreement. Keep the PR #26 fallback only for datasets without a resolved selection artifact.

- [ ] **Step 4: Run focused tests and shell/static checks**

Run the listed tests, `bash -n` for changed scripts, Ruff, formatting, and ty.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/splits.py src/evolve/evaluation/identity.py \
  src/evolve/evaluation/execution.py scaffolds/evaluators/harbor \
  tests/test_m8_dataset_splits.py tests/test_harbor_evaluator_template.py \
  tests/test_harbor_parse_score.py tests/test_harbor_artifacts.py \
  tests/test_evaluation_contract_execution.py
git commit -m "fix: make limited task selection authoritative"
```

### Task 6: Clarify MiniSWE Roles and Install Candidate Archives Safely

**Files:**
- Create: `src/evolve/integrations/harbor/_agent_roles.py`
- Create: `src/evolve/integrations/harbor/_candidate_source.py`
- Create: `tests/test_harbor_agent_roles.py`
- Modify: `src/evolve/integrations/harbor/miniswe_candidate.py`
- Modify: `src/evolve/integrations/harbor/miniswe_task_file.py`
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `src/evolve/meta_agent_budget.py`
- Modify: `tests/test_miniswe_harbor_wrapper.py`
- Modify: `tests/test_harbor_file_agent.py`
- Modify: `tests/test_harbor_meta_agent.py`
- Modify: `tests/test_m5_operator_runner.py`

**Interfaces:**
- Produces: `InstalledMiniSweAgent`, `CandidateMiniSweAgent`, exact legacy aliases, role predicates, `candidate_source_archive(source: Path)`, and literal optional session identity.
- Consumes: reviewed candidate snapshot, Harbor environment upload/extract methods, mutable surface, and configured session ID.

- [ ] **Step 1: Add role and archive security regressions**

```python
assert is_installed_miniswe_agent(INSTALLED_CANONICAL)
assert is_candidate_miniswe_agent(CANDIDATE_LEGACY_ALIAS)
assert not uses_miniswe_submission("third.party.CustomMiniSweAgent")

with candidate_source_archive(source_0700) as archive:
    members = tarfile.open(archive).getmembers()
    assert all(member.mode & 0o600 == 0o600 for member in members if member.isfile())
assert stat.S_IMODE(source_0700.stat().st_mode) == 0o700
```

Also test absolute/traversal/escaping symlink rejection, runtime-user extraction command, no privileged/world-writable repair, transport cleanup ownership, exact aliases, optional/literal session IDs, and target-neutral AHE prompts.

- [ ] **Step 2: Verify focused failures**

Run the seven listed test modules plus `tests/test_ahe_meta_agent.py` and `tests/test_ahe_trace_analyzer.py`.

- [ ] **Step 3: Implement PR #31's final role and transport contracts**

Rename first-party classes, retain exact aliases, replace suffix inference with role predicates, create a normalized safe tar archive, upload one artifact, and extract it as the runtime user before uv sync. Do not delete uploader-owned remote artifacts from inside the runtime.

- [ ] **Step 4: Run focused tests and static checks**

Run the task tests, Ruff, formatting, and ty.

- [ ] **Step 5: Commit**

```bash
git add src/evolve/integrations/harbor library/meta_agent/runners/harbor.py \
  src/evolve/meta_agent_budget.py tests/test_harbor_agent_roles.py \
  tests/test_miniswe_harbor_wrapper.py tests/test_harbor_file_agent.py \
  tests/test_harbor_meta_agent.py tests/test_m5_operator_runner.py \
  tests/test_ahe_meta_agent.py tests/test_ahe_trace_analyzer.py
git commit -m "refactor: clarify MiniSWE runtime roles"
```

### Task 7: Integrate Recipes, Public Documentation, and the Demo

**Files:**
- Modify: `recipes/aevolve/evolve.yaml`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/gepa/evolve.yaml`
- Modify: `recipes/hill_climb/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/aevolve/README.md`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/gepa/README.md`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `META_AGENTS.md`
- Modify: `library/PROTOCOL.md`
- Modify: `library/README.md`
- Modify: `scaffolds/workspace/README.md`
- Modify: `scaffolds/workspace/AGENTS.md`
- Create: `scaffolds/workspace/operators/preflight.sh`
- Create: `scripts/run_terminal_bench_demo.sh`
- Create: `tests/test_terminal_bench_demo_script.py`
- Modify: `tests/test_contract_recipe_conformance.py`
- Modify: `tests/test_runtime_recipe_conformance.py`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_recipe_composition.py`
- Modify: `tests/test_coherence.py`
- Modify: `tests/test_public_repository.py`
- Modify: `tests/test_release_artifact.py`

**Interfaces:**
- Produces: provider-neutral recipe examples with inline runtime blocks, documented auth/model/proxy ownership, and a short public Terminal-Bench 2.0 demo.
- Consumes: stable APIs from Tasks 1–6.

- [ ] **Step 1: Add failing recipe and public-contract assertions**

Assert every Harbor recipe's runtime block parses and resolves, public files contain no private host/proxy markers, `EVOLVE_HARBOR_MODEL` is provider-qualified, `OPENAI_MODEL` remains bare-model convenience, and the demo defaults to three tasks and one generation.

- [ ] **Step 2: Verify failures**

Run recipe conformance, coherence, public repository, release artifact, and demo script tests.

- [ ] **Step 3: Update recipes and docs narrowly**

Describe the certified evaluation receipt, inline runtime, optional proxy behavior, MiniSWE roles, and model ownership without replacing current-main README identity or unified Skill material. Add the public demo without DevBox paths or credential values.

- [ ] **Step 4: Run focused tests and syntax checks**

Run the task tests, `bash -n scripts/run_terminal_bench_demo.sh`, Ruff, formatting, ty, and architecture checks.

- [ ] **Step 5: Commit**

```bash
git add README.md ARCHITECTURE.md META_AGENTS.md library recipes scaffolds/workspace \
  scripts/run_terminal_bench_demo.sh tests
git commit -m "docs: publish certified evaluation workflow"
```

### Task 8: Local Integration Gate and Remote-Main Reconciliation

**Files:**
- Modify only files required by failures found in the gate.

**Interfaces:**
- Produces: a clean, current integration commit ready for DevBox.
- Consumes: all earlier task outputs and latest `origin/main`.

- [ ] **Step 1: Run the complete local gate**

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q
UV_CACHE_DIR=.uv-cache uv run --frozen ruff check .
UV_CACHE_DIR=.uv-cache uv run --frozen ruff format --check .
UV_CACHE_DIR=.uv-cache uv run --frozen ty check
UV_CACHE_DIR=.uv-cache uv run --frozen pytest -q tests/test_coherence.py tests/test_public_repository.py
git diff --check origin/main...HEAD
```

Run `bash -n` for every changed shell script.

- [ ] **Step 2: Diagnose and fix every failure at its owning boundary**

Do not weaken assertions to make the suite pass. Add a regression test for any newly discovered interaction before fixing it.

- [ ] **Step 3: Refresh remote main and reconcile**

```bash
git fetch origin main
git merge --no-edit origin/main
```

If the merge is non-trivial, resolve semantically using the design precedence, then rerun the complete local gate. If `origin/main` is already an ancestor, do not create an empty merge commit.

- [ ] **Step 4: Commit integration-only fixes**

```bash
git status --short
git add -u
git commit -m "fix: close semantic integration gaps"
```

Skip this commit if no tracked changes remain.

### Task 9: Qualify the Exact Commit on DevBox

**Files:**
- Create outside Git on DevBox: redacted run directory and result manifest.
- Do not modify tracked repository files unless a qualification failure reveals a product defect.

**Interfaces:**
- Produces: exact-SHA DevBox evidence for focused tests, installed MiniSWE, restrictive candidate source, one-task evaluation, and certified AHE 3×3.
- Consumes: DevBox's existing private environment files, caches, proxy setup, model credentials, Docker, Harbor, and the exact local commit bundle/ref.

- [ ] **Step 1: Transfer the exact commit without secrets**

Create a Git bundle or push the branch, verify `git rev-parse HEAD` on DevBox equals the intended SHA, and run `uv sync --dev --frozen` using DevBox's private download proxy environment.

- [ ] **Step 2: Run focused remote contract tests**

Run Harbor/Codex/MiniSWE/runtime/evaluation/task-selection tests and retain the summary.

- [ ] **Step 3: Run installed and candidate MiniSWE smokes**

Verify the installed adapter completes a real Harbor run. Create candidate source with `0700` directories and `0600` files, run the rootless cross-user installation smoke, confirm runtime ownership, and confirm host modes remain unchanged.

- [ ] **Step 4: Run the one-task real candidate evaluation**

Set a one-task effective limit and verify outer status `complete`, one selected task, one expected/completed trial, zero missing trials, no Harbor exception, and acceptance of a valid zero verifier reward.

- [ ] **Step 5: Run certified AHE 3×3**

Use DevBox proxy files only for downloads. Before every LLM-backed command, confirm the model endpoint hostname is present in both `NO_PROXY` and `no_proxy` without printing secret values. Run three tasks across genesis plus three candidate generations and verify every generation tag, certified receipt, task membership, expected trials, archive integrity, and `evolve verify` result.

- [ ] **Step 6: Preserve redacted evidence**

Record commit SHA, commands with secret-bearing arguments removed, exit codes, test counts, artifact directories, receipt IDs, and final statuses. Preserve failed attempts alongside successful retries.

- [ ] **Step 7: Fix and repeat when necessary**

For a product defect, reproduce locally with a failing test, implement the fix, rerun the complete local gate, transfer the new exact SHA, and repeat every affected DevBox smoke.

### Task 10: Publish the Draft and Supersede Source PRs

**Files:**
- No additional source files expected.

**Interfaces:**
- Produces: one draft PR against current `main`, plus closure comments on #23, #26, #29, and #31.
- Consumes: green local gates and exact-SHA DevBox evidence.

- [ ] **Step 1: Perform the final remote-main check**

Fetch `origin/main`. If it advanced after DevBox qualification, integrate it and rerun affected local and DevBox gates before publishing.

- [ ] **Step 2: Push the integration branch**

```bash
git push -u origin codex/semantic-integration-prs-23-26-29-31
```

- [ ] **Step 3: Create the draft PR**

Create a draft PR with sections for summary, semantic precedence, source-PR traceability, compatibility, public proxy/auth guarantees, local validation, DevBox validation, exact qualified SHA, and explicit limitation statement.

- [ ] **Step 4: Verify the draft is visible and targets current main**

Confirm draft state, base/head refs, mergeability metadata, and checks. Do not close source PRs until this succeeds.

- [ ] **Step 5: Close source PRs with supersession links**

Post a concise comment on each of #23, #26, #29, and #31 linking to the new draft and explaining that its behavior was semantically integrated. Then close each PR.

- [ ] **Step 6: Report completion**

Provide the draft PR link, branch, qualified SHA, local gate summary, DevBox result summary/artifact path, and confirmation that all four source PRs are closed.
