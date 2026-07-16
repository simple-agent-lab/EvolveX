# PR 5 and AHE-on-MiniSWE Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one locally verified branch that combines PR 5's strategy/runner split with method-faithful AHE-on-MiniSWE and broad, self-referential HyperAgents execution through Harbor's installed MiniSWE agent.

**Architecture:** Replay PR 5 on `origin/main`, port the AHE branch in behavior-focused layers, and keep strategy, runner, installed agent, and mutable surface independent. A new editable-bundle module packages configured roots under `/app/candidate`, validates the returned Harbor artifact, and applies all roots transactionally; AHE transports only `target`, while HyperAgents transports `target` and `operators`.

**Tech Stack:** Python 3.11+, Typer, PyYAML, Git worktrees, Harbor CLI, Harbor `BaseInstalledAgent`/`mini-swe-agent`, pytest, Ruff, ty.

## Global Constraints

- Work on a fresh local integration branch based on `origin/main`; do not modify `feat/ahe-miniswe` or PR 5's remote branch.
- Preserve PR 5 authorship by replaying commits `fef95bf`, `b1e876c`, and `b9ea2cb` before integration commits.
- Do not push, create/edit/close a PR, or modify remote state during implementation.
- Both production AHE and HyperAgents recipes use `runner: harbor` and `agent: mini-swe-agent`; neither requires a local Codex command.
- AHE transports and mutates `target/**` only.
- HyperAgents transports `target/` and `operators/`, with mutable surface `target/**` and `operators/**`.
- HyperAgents' substantive target-change requirement remains prompt-level policy.
- Preserve natural stage semantics: mutations affect the next invocation of each operator; do not add parent snapshots or delayed activation.
- Keep the evaluator, mechanism, workspace configuration, archive authority, credentials, endpoints, task partitions, and resource limits frozen.
- Keep AHE-specific schemas and decisions out of `src/evolve`.
- Treat a malformed or unsafe returned artifact as a failed proposal and leave the checkout unchanged.

---

## File and Responsibility Map

- `library/meta_agent/runners/editable_bundle.py`: validate editable roots, stage `/app/candidate`, validate returned trees, and transactionally install roots.
- `library/meta_agent/runners/harbor.py`: launch Harbor, collect/redact evidence, and delegate candidate-tree work to `editable_bundle.py`.
- `library/meta_agent/runners/local.py`: retain PR 5's trusted local-command backend.
- `library/meta_agent/runners/__init__.py`: dispatch by `runner` and report runner identity.
- `library/meta_agent/support/evidence.py`: load the normalized feedback bundle for all strategies.
- `library/meta_agent/ahe.py`: AHE evidence-to-hypothesis strategy and optional `ahe-report.json`.
- `library/meta_agent/hyperagents.py`: broad target-required self-referential strategy.
- `library/trace_analyzer/ahe.py`: bounded, current-generation AHE trace evidence.
- `library/rollout/harbor.py`: bounded Harbor rollout collection and redaction.
- `templates/target/harbor/miniswe_source_agent.py`: frozen source-backed MiniSWE evaluator adapter only.
- `src/evolve/workspace.py`: recursively vendor nested runner/support files and frozen MiniSWE assets.
- `src/evolve/{driver,evaluator,feedback,archive}.py`, `src/evolve/frozen/{interfaces,sdk}.py`: retain the AHE branch's generic contract cleanup and evaluator-owned limits.
- `recipes/ahe/{evolve.yaml,README.md}`: compose AHE + Harbor installed MiniSWE + target-only bundle.
- `recipes/hyperagents/{evolve.yaml,README.md}`: compose HyperAgents + Harbor installed MiniSWE + target-and-operators bundle.
- `META_AGENTS.md`, `README.md`, `library/{README.md,PROTOCOL.md}`, `docs/glossary.md`: document strategy, runner, agent, editable-root, and migration semantics.

---

### Task 1: Create the isolated integration branch and replay PR 5

**Files:**
- No source edits.
- Verify: repository status, PR 5 commit sequence, complete baseline test suite.

**Interfaces:**
- Consumes: `origin/main`, PR 5 head `b9ea2cb292a1599d1df229113d3c4b4eec267804`.
- Produces: isolated branch `feat/pr5-ahe-miniswe-integration` with PR 5's three commits and no uncommitted files.

- [ ] **Step 1: Create an isolated worktree using the required worktree skill**

Invoke `superpowers:using-git-worktrees`, then create the worktree from `origin/main`:

```bash
git fetch origin pull/5/head:refs/remotes/origin/pr/5
git worktree add .worktrees/pr5-ahe-miniswe-integration -b feat/pr5-ahe-miniswe-integration origin/main
```

Expected: the new worktree is on `feat/pr5-ahe-miniswe-integration`, and `git status --short` is empty.

- [ ] **Step 2: Replay PR 5 in its original order**

```bash
git cherry-pick fef95bf9be4536f5330bc98798c62082b8183ef7
git cherry-pick b1e876c475b4b184fc2a87be614cf244c964f8c3
git cherry-pick b9ea2cb292a1599d1df229113d3c4b4eec267804
```

Expected: `git log -3 --format='%h %an %s'` shows Xiaobo Wang's three PR 5 commits in order.

- [ ] **Step 3: Run the PR 5 baseline checks**

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
```

Expected: all four commands exit 0; pytest reports the PR 5 baseline suite passing.

- [ ] **Step 4: Record the integration design on the new branch**

```bash
git cherry-pick 3b32e92
```

Expected: the combined design document is present and the worktree remains clean.

---

### Task 2: Port the generic AHE contract cleanup without restoring `agent_command`

**Files:**
- Modify: `src/evolve/archive.py`
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/feedback.py`
- Modify: `src/evolve/frozen/interfaces.py`
- Modify: `src/evolve/frozen/sdk.py`
- Modify: `library/record/jsonl.py`
- Delete: `library/reflect/credit.py`
- Modify: `templates/workspace/README.md`
- Delete: `templates/workspace/operators/meta_agent.md`
- Delete: `templates/workspace/operators/meta_agent_brief.md`
- Modify: `tests/test_m3_population_self_reference.py`
- Modify: `tests/test_m5_driver_operators.py`
- Modify: `tests/test_m5_record_verb.py`
- Modify: `tests/test_phase_f_interfaces_sdk.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: PR 5's `hyperagents` strategy and runner output contract.
- Produces: generic `MetaAgentResult(changed, notes, usage)` with no `predicted_fixes` or `verified_fixes` framework requirements.

- [ ] **Step 1: Add failing assertions for the removed generic prediction fields**

Add assertions equivalent to:

```python
assert not (run_dir / "meta_agent" / "predicted_fixes.json").exists()
assert "predicted_fixes" not in archive_row
assert "verified_fixes" not in archive_row
assert not (run_dir / "feedback" / "falsification.md").exists()
```

Also assert that historical archive rows containing unknown prediction keys remain readable.

- [ ] **Step 2: Run the focused tests and verify failure**

```bash
uv run pytest -q tests/test_m5_driver_operators.py tests/test_m5_record_verb.py tests/test_phase_f_interfaces_sdk.py tests/test_runtime.py
```

Expected: failures point to prediction-file creation, validation, recording, or feedback generation.

- [ ] **Step 3: Port the method-neutral cleanup from AHE commit `5205443`**

Remove `predicted_fixes` and `verified_fixes` from frozen interfaces, SDK defaults, driver validation, archive annotations, record output, and feedback generation. Preserve PR 5's deletion of `library/meta_agent/agent_command.py`; do not resolve conflicts by recreating it. Delete the unused credit-reflection implementation and prompt companions.

The retained interface must remain:

```python
@dataclass(frozen=True)
class MetaAgentResult:
    changed: list[str]
    notes: list[str]
    usage: dict[str, Any]
```

- [ ] **Step 4: Run focused tests and formatting**

```bash
uv run pytest -q tests/test_m3_population_self_reference.py tests/test_m5_driver_operators.py tests/test_m5_record_verb.py tests/test_phase_f_interfaces_sdk.py tests/test_runtime.py
uv run ruff check src/evolve library/record tests/test_m5_driver_operators.py tests/test_runtime.py
```

Expected: all focused tests and Ruff pass.

- [ ] **Step 5: Commit the generic cleanup**

```bash
git add src/evolve library/record templates/workspace tests
git add -u library/reflect
git commit -m "refactor: keep meta-agent contracts method neutral"
```

---

### Task 3: Port the frozen MiniSWE evaluator and resource limits

**Files:**
- Modify: `src/evolve/evaluator.py`
- Modify: `src/evolve/workspace.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `templates/evaluator/stub_eval.py`
- Create: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_harbor_evaluator_config.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_miniswe_harbor_wrapper.py`
- Modify: `tests/test_miniswe_source_agent_command.py`
- Modify: `tests/test_phase_f_init_binding.py`

**Interfaces:**
- Consumes: recipe keys `target.harbor_agent`, `evaluator.agent`, and `evaluator.agent_env`.
- Produces: frozen `target.harbor_agent:MiniSweSourceAgent` that installs candidate source with `uv sync --frozen` and overrides mutable model, step, cost, and environment-timeout values.

- [ ] **Step 1: Write failing evaluator-adapter tests**

Cover these exact behaviors:

```python
assert issubclass(module.MiniSweSourceAgent, HarborMiniSweAgent)
assert "uv sync --project /installed-agent/miniswe-source --frozen" in joined_commands
assert "mini-swe-agent --" not in joined_commands
assert env["MSWEA_MODEL_NAME"] == "openai/test-model"
assert env["MINISWE_STEP_LIMIT"] == "100"
assert env["MINISWE_COST_LIMIT"] == "3.0"
assert env["MINISWE_ENV_TIMEOUT"] == "30"
```

Add failure classification tests for missing lockfile, frozen-sync failure, MiniSWE import failure, and model initialization failure.

- [ ] **Step 2: Run the focused tests and verify failure**

```bash
uv run pytest -q tests/test_miniswe_harbor_wrapper.py tests/test_harbor_evaluator_config.py tests/test_harbor_evaluator_template.py
```

Expected: failures show that the source adapter and frozen `agent.env` ownership are absent.

- [ ] **Step 3: Implement the frozen source-backed evaluator adapter**

Port the AHE branch's `MiniSweSourceAgent` implementation. Keep these fixed paths and responsibilities:

```python
SOURCE_DIR = "/installed-agent/miniswe-source"
VENV_PYTHON = f"{SOURCE_DIR}/.venv/bin/python"
UV_CACHE_DIR = "/installed-agent/uv-cache"
```

The adapter must upload the candidate source, require `pyproject.toml` and `uv.lock`, perform one frozen sync, import the candidate API, force the evaluator-owned model and limits, run `DefaultAgent` through the candidate Python API, and emit runtime evidence. It must not use the installed MiniSWE CLI for canonical evaluation.

- [ ] **Step 4: Wire initialization and evaluator environment ownership**

Teach `workspace.py` to copy the frozen wrapper when `target.harbor_agent: miniswe-source` is configured and to write sorted `evaluator/agent.env` values. Preserve the implicit surface exclusion for `target/harbor_agent.py`.

- [ ] **Step 5: Run focused evaluator tests**

```bash
uv run pytest -q tests/test_miniswe_harbor_wrapper.py tests/test_miniswe_source_agent_command.py tests/test_harbor_evaluator_config.py tests/test_harbor_evaluator_template.py tests/test_phase_f_init_binding.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the evaluator adapter**

```bash
git add src/evolve/evaluator.py src/evolve/workspace.py templates tests
git commit -m "feat: freeze MiniSWE source evaluation"
```

---

### Task 4: Port the bounded AHE rollout and trace analyzer

**Files:**
- Modify: `library/rollout/harbor.py`
- Create: `library/trace_analyzer/ahe.py`
- Modify: `tests/test_m7_harbor_rollout.py`
- Create: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: current generation `rollout/cases.json`; config keys `max_cases: int` and `field_limit: int`.
- Produces: `TraceAnalyzerResult` plus `feedback.md`, `evidence/selected.md`, `evidence/overview.json`, and `evidence/cases.jsonl`.

- [ ] **Step 1: Write failing bounded-evidence tests**

Assert deterministic failure-first selection and exact artifacts:

```python
assert result.artifacts == [
    "trace_analyzer/feedback.md",
    "trace_analyzer/evidence/selected.md",
    "trace_analyzer/evidence/overview.json",
    "trace_analyzer/evidence/cases.jsonl",
]
assert [row["outcome"] for row in cases] == ["failed", "failed", "passed"]
assert all(len(value) <= field_limit + 64 for value in clipped_fields)
```

Cover missing files, malformed optional fields, secret redaction, Codex-session fallback, and bounded trace collection.

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py tests/test_m7_harbor_rollout.py
```

Expected: the AHE analyzer module or artifacts are missing.

- [ ] **Step 3: Implement the focused analyzer and bounded rollout**

Port AHE commits `5e2728a`, `bf8dfff`, and `37d1b89` semantically. The analyzer reads only the current `rollout/cases.json`, retains failures before successes in rollout order, clips and redacts fields, and never compares generations or interprets causality.

- [ ] **Step 4: Run focused tests**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py tests/test_m7_harbor_rollout.py
uv run ruff check library/rollout/harbor.py library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
```

Expected: all commands pass.

- [ ] **Step 5: Commit rollout evidence support**

```bash
git add library/rollout/harbor.py library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py tests/test_m7_harbor_rollout.py
git commit -m "feat: add bounded AHE trace evidence"
```

---

### Task 5: Add surface-validated editable Harbor bundles

**Files:**
- Create: `library/meta_agent/runners/editable_bundle.py`
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `library/meta_agent/runners/__init__.py`
- Create: `tests/test_editable_bundle.py`
- Modify: `tests/test_harbor_meta_agent.py`

**Interfaces:**
- Consumes: `prepare_editable_bundle(checkout: Path, raw_roots: object, surface: SurfacePolicy) -> EditableBundle`.
- Produces: `install_returned_bundle(checkout: Path, returned_candidate: Path, bundle: EditableBundle, parent_ref: str, surface: SurfacePolicy) -> list[str]`.
- Produces: Harbor artifact source constant `"/app/candidate"`.

- [ ] **Step 1: Write failing root-validation tests**

Create table-driven tests for accepted `['target']` and `['target', 'operators']`, plus rejection of:

```python
pytest.param([], "at least one editable root"),
pytest.param(["/target"], "must be relative"),
pytest.param(["../target"], "must not escape"),
pytest.param(["target", "target/src"], "must not overlap"),
pytest.param(["evaluator"], "not covered by mutable surface"),
```

Assert that staging produces `task_root / 'candidate' / 'target'` and preserves repository-relative paths.

- [ ] **Step 2: Write failing transactional-install tests**

Cover successful two-root replacement, missing roots, unexpected roots, symlinks, special files, out-of-surface mutations, failed `git diff --check`, and a simulated second-root rename failure. For every failure:

```python
assert snapshot_tree(checkout / "target") == before_target
assert snapshot_tree(checkout / "operators") == before_operators
```

- [ ] **Step 3: Run bundle tests and verify failure**

```bash
uv run pytest -q tests/test_editable_bundle.py
```

Expected: import failure for `library.meta_agent.runners.editable_bundle`.

- [ ] **Step 4: Implement the focused bundle module**

Define `EditableBundle` exactly as shown, then implement the three public
signatures listed below it:

```python
@dataclass(frozen=True)
class EditableBundle:
    staging: Path
    task_root: Path
    candidate_root: Path
    roots: tuple[Path, ...]
```

- `prepare_editable_bundle(checkout: Path, raw_roots: object, surface: SurfacePolicy) -> EditableBundle`
- `install_returned_bundle(checkout: Path, returned_candidate: Path, bundle: EditableBundle, parent_ref: str, surface: SurfacePolicy) -> list[str]`
- `cleanup_editable_bundle(bundle: EditableBundle) -> None`

Use `tempfile.mkdtemp`, `shutil.copytree`, `Path.resolve`, `lstat`, `working_tree_changed_paths`, `check_paths`, and `git diff --check`. Stage every returned root before renaming any live root; keep backups until validation completes; restore all backups on every exception.

- [ ] **Step 5: Run bundle tests and verify passing behavior**

```bash
uv run pytest -q tests/test_editable_bundle.py
```

Expected: all bundle tests pass.

- [ ] **Step 6: Adapt the Harbor runner to `/app/candidate`**

Replace target-specific `_TargetSwap`, `_artifact_target`, and `_stage_target` logic with the bundle interfaces. `_build_command` must use `bundle.task_root` for `--path`, request `--artifact /app/candidate`, and append this contract to the prompt:

```text
The editable candidate is at `/app/candidate`. Edit only paths allowed by the supplied surface rules. The complete `/app/candidate` directory is returned as the candidate artifact.
```

Default `editable_roots` to `['target']` for backward compatibility. Pass `parent_ref` and `load_surface_policy(checkout)` into transactional installation.

- [ ] **Step 7: Update Harbor runner tests**

Make fake Harbor return `artifacts/app/candidate/{target,operators}` and assert the generated command includes:

```python
assert option("--artifact") == "/app/candidate"
assert option("--agent") == "mini-swe-agent"
assert "--path" in args
```

Cover target-only and two-root round trips and verify `runner_name(ctx) == 'harbor'` in provenance.

- [ ] **Step 8: Run runner tests and commit**

```bash
uv run pytest -q tests/test_editable_bundle.py tests/test_harbor_meta_agent.py
uv run ruff check library/meta_agent/runners tests/test_editable_bundle.py tests/test_harbor_meta_agent.py
git add library/meta_agent/runners tests/test_editable_bundle.py tests/test_harbor_meta_agent.py
git commit -m "feat: return editable Harbor candidate bundles"
```

---

### Task 6: Adapt the AHE strategy to shared evidence and runner dispatch

**Files:**
- Create: `library/meta_agent/ahe.py`
- Modify: `library/meta_agent/support/evidence.py`
- Create: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Consumes: `load_feedback(run_dir: Path, fallback: str = '') -> str` and `run_agent(checkout: Path, prompt: str, ctx: OperatorContext) -> AgentRunResult`.
- Produces: `AheMetaAgent.run(checkout: Path, observation: str, ctx: OperatorContext) -> MetaAgentResult` and optional `meta_agent/ahe-report.json` preservation.

- [ ] **Step 1: Write failing AHE strategy tests**

Assert that the prompt contains current evidence, source-inspection instructions, one coherent harness change, frozen-boundary rules, experiment history, surface rules, and the report schema. Mock `run_agent` and assert:

```python
assert result.changed == ["target/src/minisweagent/agents/default.py"]
assert "variant: ahe" in result.notes
assert "runner: harbor" in result.notes
assert "ahe-report: preserved" in result.notes
assert (run_dir / "meta_agent" / "patch.diff").is_file()
```

Cover missing and malformed reports and `AgentCommandError` artifact retention.

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py
```

Expected: AHE strategy module missing.

- [ ] **Step 3: Implement AHE using shared dispatch**

Port the AHE prompt and report behavior from `feat/ahe-miniswe`, but replace direct `run_meta_agent` and duplicate feedback loading with:

```python
from library.meta_agent.runners import run_agent, runner_name
from library.meta_agent.support.evidence import load_feedback

feedback = load_feedback(ctx.run_dir, observation)
agent_run = run_agent(checkout, prompt, ctx)
notes = [
    "variant: ahe",
    f"runner: {runner_name(ctx)}",
    _report_note(report_path),
    "written-by: operators/meta_agent.py",
    *patch.notes,
]
```

Use `create_candidate_patch(checkout=checkout, parent_ref=parent_ref, surface=load_surface_policy(checkout), repair=False)` so any surface violation remains an explicit failed proposal.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py tests/test_harbor_meta_agent.py
uv run ruff check library/meta_agent/ahe.py library/meta_agent/support/evidence.py tests/test_ahe_meta_agent.py
git add library/meta_agent/ahe.py library/meta_agent/support/evidence.py tests/test_ahe_meta_agent.py
git commit -m "feat: run AHE through shared meta-agent backends"
```

---

### Task 7: Make HyperAgents broad, target-required, and Harbor-backed

**Files:**
- Modify: `library/meta_agent/hyperagents.py`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hyperagents-smoke/evolve.yaml`
- Modify: `recipes/hyperagents/README.md`
- Modify: `tests/test_hyperagents_meta_agent.py`
- Modify: `tests/test_m5_driver_operators.py`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_phase_f_init_binding.py`
- Modify: `docs/superpowers/specs/2026-07-16-broad-target-required-hyperagents-design.md`

**Interfaces:**
- Consumes: shared `load_feedback`, `run_agent`, and Harbor bundle roots.
- Produces: HyperAgents candidate surface `target/**` plus `operators/**`, with natural stage activation.

- [ ] **Step 1: Write failing recipe and prompt tests**

Assert production configuration contains:

```python
assert "    - target/**" in config
assert "    - operators/**" in config
assert "variant: hyperagents" in config
assert "runner: harbor" in config
assert "agent: mini-swe-agent" in config
assert "editable_roots: [target, operators]" in config
```

Assert the prompt requires a substantive `target/**` change, permits any `operators/**` change alongside it, and describes natural stage behavior without claiming universal descendant-only activation.

- [ ] **Step 2: Run focused tests and verify failure**

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
```

Expected: recipe and prompt assertions fail against PR 5's narrower or local-runner configuration.

- [ ] **Step 3: Update the HyperAgents strategy**

Retain PR 5's shared evidence loading and runner dispatch. Replace the prompt policy with the approved broad target-required text. Keep `create_candidate_patch(checkout=checkout, parent_ref=parent_ref, surface=load_surface_policy(checkout), repair=False)` and notes:

```python
notes = [
    "variant: hyperagents",
    f"runner: {runner_name(ctx)}",
    "written-by: operators/meta_agent.py",
    *patch.notes,
]
```

- [ ] **Step 4: Configure real and smoke recipes deliberately**

Set the real HyperAgents recipe to Harbor's installed MiniSWE agent and two roots. Keep the smoke recipe deterministic: use the fake/test command path expected by its tests, but retain the same broad surface and prompt semantics. Do not require Docker or credentials for the default unit suite.

- [ ] **Step 5: Document and test natural stage semantics**

Update the broad HyperAgents design to state:

```text
An operator mutation becomes active the next time that operator is invoked. Changes to already-run rollout, trace, and meta-agent stages affect later generations; changes to not-yet-run validate, novelty, gate, or record stages may affect the current generation. Canonical evaluation remains frozen.
```

Add a focused driver test where the meta-agent changes `operators/record.py` and the changed record behavior is observed in the same generation, while a changed `operators/meta_agent.py` is observed only when producing a later child.

- [ ] **Step 6: Run tests and commit**

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py tests/test_m5_driver_operators.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
uv run ruff check library/meta_agent/hyperagents.py tests/test_hyperagents_meta_agent.py tests/test_m5_driver_operators.py
git add library/meta_agent/hyperagents.py recipes/hyperagents recipes/hyperagents-smoke tests docs/superpowers/specs/2026-07-16-broad-target-required-hyperagents-design.md
git commit -m "feat: broaden target-required HyperAgents evolution"
```

---

### Task 8: Compose the production AHE recipe and workspace assets

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/ahe/notes.md`
- Modify: `src/evolve/workspace.py`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_m9_ahe_recipe.py`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_phase_f_init_binding.py`

**Interfaces:**
- Consumes: AHE strategy, AHE trace analyzer, Harbor runner, `editable_roots`, and frozen MiniSWE evaluator adapter.
- Produces: initialized AHE workspace with runnable nested runner/support modules and target-only meta-agent transport.

- [ ] **Step 1: Write failing recipe composition tests**

Assert the AHE recipe contains:

```python
assert "trace_analyzer: {variant: ahe" in config
assert "meta_agent: {variant: ahe" in config
assert "runner: harbor" in config
assert "agent: mini-swe-agent" in config
assert "model: openai/gpt-5.4" in config
assert "editable_roots: [target]" in config
assert "gate: {variant: hillclimb, strict: true" in config
assert "agent: target.harbor_agent:MiniSweSourceAgent" in config
```

After initialization, assert `operators/meta_agent.py`, `library/meta_agent/runners/*.py`, and `library/meta_agent/support/evidence.py` are present and importable.

- [ ] **Step 2: Run tests and verify failure**

```bash
uv run pytest -q tests/test_m0_init.py tests/test_m9_ahe_recipe.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
```

Expected: AHE recipe and nested asset assertions fail.

- [ ] **Step 3: Update recursive asset vendoring**

Ensure `workspace._walk_files` skips dot paths and `__pycache__`, and `_operator_assets` includes nested Python support files as well as non-Python assets:

```python
if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
    continue

if relative.suffix != ".py" or len(relative.parts) > 1:
    assets.setdefault(f"library/{kind}/{relative.as_posix()}", text)
```

Preserve PR 5's package import layout.

- [ ] **Step 4: Compose AHE declaratively**

Use MiniSWE source seed, target-only mutable surface, Harbor rollout, AHE trace analyzer, AHE meta-agent, Harbor installed MiniSWE editing agent, strict hill-climb gate, frozen evaluator adapter, and evaluator-owned limits. Remove the local Codex `command` key entirely.

- [ ] **Step 5: Run recipe tests and commit**

```bash
uv run pytest -q tests/test_m0_init.py tests/test_m9_ahe_recipe.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
uv run ruff check src/evolve/workspace.py tests/test_m0_init.py tests/test_m9_ahe_recipe.py
git add recipes/ahe src/evolve/workspace.py tests/test_m0_init.py tests/test_m9_ahe_recipe.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
git commit -m "feat: compose AHE on Harbor-installed MiniSWE"
```

---

### Task 9: Align documentation and migration guidance

**Files:**
- Modify: `META_AGENTS.md`
- Modify: `README.md`
- Modify: `docs/glossary.md`
- Modify: `library/README.md`
- Modify: `library/PROTOCOL.md`
- Modify: `skills/evolve-agent/SKILL.md`
- Modify: `recipes/hill_climb/README.md`
- Modify: `recipes/hill_climb/evolve.yaml`
- Modify: `recipes/hill_climb-smoke/evolve.yaml`

**Interfaces:**
- Consumes: final configuration and runtime semantics from Tasks 5–8.
- Produces: one consistent public description of strategy, runner, agent, editable roots, AHE independence, HyperAgents self-reference, and legacy migrations.

- [ ] **Step 1: Add documentation consistency assertions**

Extend coherence tests to reject active examples containing:

```python
for obsolete in ("variant: feedback_guided", "variant: agent_command", "runner: agent_command"):
    assert obsolete not in active_docs_and_recipes
```

Allow historical design documents to retain old terms when explicitly marked historical.

- [ ] **Step 2: Run coherence and recipe tests and verify failure**

```bash
uv run pytest -q tests/test_coherence.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
```

Expected: stale runner names or missing editable-root guidance cause failures.

- [ ] **Step 3: Update the documentation**

Document these exact distinctions:

```text
variant = improvement strategy
runner = execution and isolation backend
agent = concrete Harbor or local editing agent
editable_roots = repository trees transported through Harbor
surface.include = paths whose returned mutations may be retained
```

Show AHE and HyperAgents YAML examples, explain installed CLI versus source-backed evaluator adapter, document natural operator stage semantics, and migrate `feedback_guided` to `hyperagents` and `agent_command` to `runner: local` only where backward migration examples require it.

- [ ] **Step 4: Run documentation tests and commit**

```bash
uv run pytest -q tests/test_coherence.py tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
git add META_AGENTS.md README.md docs/glossary.md library/README.md library/PROTOCOL.md skills/evolve-agent/SKILL.md recipes/hill_climb recipes/hill_climb-smoke tests/test_coherence.py
git commit -m "docs: explain meta-agent strategies and editable runners"
```

---

### Task 10: Add combined fake-Harbor end-to-end coverage

**Files:**
- Modify: `tests/test_m9_ahe_recipe.py`
- Create: `tests/test_hyperagents_harbor_recipe.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: initialized AHE and HyperAgents workspaces and fake Harbor artifact protocol.
- Produces: credential-free end-to-end proof of target-only and target-plus-operators mutation flows.

- [ ] **Step 1: Extend the fake Harbor helper**

Make the helper inspect `--artifact`, copy the staged `/app/candidate` equivalent, mutate paths selected by the test, and emit one valid trial, artifact manifest, trajectory, usage payload, and result file. Parameterize mutations as:

```python
{"target/src/minisweagent/__init__.py": "AHE_GENERATION_1 = True\n"}

{
    "target/src/minisweagent/__init__.py": "HYPER_GENERATION_1 = True\n",
    "operators/record.py": "# changed by hyperagent\n",
}
```

- [ ] **Step 2: Write the failing AHE end-to-end assertion**

Initialize AHE, run one generation with fake Harbor, and assert target mutation, AHE evidence artifacts, AHE report handling, strict gate behavior, frozen wrapper identity, and absence of operator mutations.

- [ ] **Step 3: Write the failing HyperAgents end-to-end assertion**

Initialize HyperAgents, run one generation, and assert both target and operator changes are committed, evaluator-owned paths remain unchanged, the canonical score is recorded, and Harbor receives `editable_roots == ['target', 'operators']` through the staged tree.

- [ ] **Step 4: Run both end-to-end tests**

```bash
uv run pytest -q tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py
```

Expected: both pass without Docker, network, model credentials, Codex, or a real Harbor installation.

- [ ] **Step 5: Commit end-to-end coverage**

```bash
git add tests/conftest.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py
git commit -m "test: cover Harbor-backed AHE and HyperAgents flows"
```

---

### Task 11: Run full verification and review the combined diff

**Files:**
- Modify only files required to fix failures found by verification.
- Verify: complete branch against `origin/main` and design requirements.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: clean, locally verified integration branch ready for later human review and optional publication.

- [ ] **Step 1: Run the focused integration suite**

```bash
uv run pytest -q \
  tests/test_editable_bundle.py \
  tests/test_harbor_meta_agent.py \
  tests/test_ahe_meta_agent.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_hyperagents_harbor_recipe.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_phase_e_recipes.py \
  tests/test_phase_f_init_binding.py
```

Expected: all focused tests pass.

- [ ] **Step 2: Run static verification**

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
git diff --check origin/main...HEAD
```

Expected: all commands exit 0 with no diagnostics.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest -q
```

Expected: the complete suite passes with no skipped test introduced to hide an integration failure.

- [ ] **Step 4: Audit the final diff and history**

```bash
git status --short
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
git log --reverse --format='%h %an <%ae> %s' origin/main..HEAD
```

Expected: status is clean; PR 5 commits retain original authorship; no `agent_command.py`, secrets, runtime artifacts, `.superpowers/`, or worktree files are present; all changed files belong to the approved design.

- [ ] **Step 5: Run the completion verification skill**

Invoke `superpowers:verification-before-completion` and re-run any command it requires before claiming the branch is ready.

- [ ] **Step 6: Commit any verification-only fixes**

If verification required source changes, stage only those files and commit:

```bash
git commit -m "fix: close combined integration regressions"
```

If no fixes were required, do not create an empty commit.

The final handoff reports the local branch, commit range, exact verification results, and deferred publication work. It does not push or modify either GitHub PR.
