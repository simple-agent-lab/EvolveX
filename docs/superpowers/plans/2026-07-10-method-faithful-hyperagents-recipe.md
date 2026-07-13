# Method-Faithful HyperAgents Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder HyperAgents recipe with a framework-native implementation in which a selected meta-agent can atomically improve its task agent and its own next-generation workflow, while upstream `score_child_prop` selection retains valid stepping stones.

**Architecture:** Keep one neutral driver and add only generic validation, atomic admission, staged-evaluation, terminal-record, companion-prompt, genesis-evaluation, and final-anchor lifecycle support. Put HyperAgents prompting, parent weights, compilation policy, and experience records in dedicated `library/` variants; the candidate may mutate only `target/**` and `operators/meta_agent.*`.

**Tech Stack:** Python 3.11+, pytest, Typer, git worktrees/tags, JSON/JSONL artifacts, shell evaluator templates, Harbor, MiniSWE Agent source checkout.

## Global Constraints

- Canonical method: Zhang et al., *Hyperagents*, arXiv:2603.19461, and `facebookresearch/HyperAgents` at its default `score_child_prop` configuration.
- Do not create a HyperAgents-specific driver or copy upstream Docker orchestration.
- The atomic candidate genome is exactly `target/**`, `operators/meta_agent.py`, and `operators/meta_agent.md`.
- `select`, `validate`, `gate`, `record`, evaluator, driver, archive integrity, and `evolve.yaml` remain fixed in V1.
- A rejected workflow admission rejects the whole child; never retain task-agent edits from a rejected combined proposal.
- The default selector is fixed `score_child_prop`; upstream's optional editable selector is outside V1.
- Every valid numeric score is parent-eligible, including zero and scores below the parent.
- A positive staged score proceeds to full evaluation; zero remains selectable and skips full evaluation.
- All in-loop experiment artifacts are readable through `OperatorContext` paths; the mechanism does not create a universal feedback narrative.
- The final anchor runs after the last mutation and cannot feed another proposal.
- Transient provider/evaluator failures do not invalidate the selected parent. Only a deterministic inherited-workflow load failure may do so.
- Preserve unrelated work. Each task stages only its named files and ends with a focused commit.
- The starting worktree has one accepted baseline failure: `tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback`. Task 7 resolves it; no task may introduce another failure.

---

## File Map

### Generic framework changes

- `src/evolve/frozen/interfaces.py`: optional `ValidateOperator`, `ValidateResult`, payload validators, and registry entry.
- `src/evolve/frozen/sdk.py`: invoke validate operators and write `validate/result.json`; stop reading framework feedback files.
- `src/evolve/operators.py`: optionally load an operator script from a trusted checkout while passing the candidate checkout in context.
- `src/evolve/driver.py`: pre-validation surface enforcement, validate lifecycle, atomic self-modification rejection, staged evaluation orchestration, terminal record finalization, real genesis evaluation, and final anchor.
- `src/evolve/evaluator.py`: task-limited/kind-aware evaluator invocation.
- `src/evolve/config.py`: typed accessors for `evaluator.stage` and `evaluator.anchor`.
- `src/evolve/workspace.py`: optional operator scaffolding, Markdown companion installation, and staged/anchor evaluator environment.
- `src/evolve/feedback.py`: delete the framework-authored feedback bundle.
- `templates/evaluator/stub_eval.py`: honor deterministic task limits and evaluation kind.
- `templates/evaluator/engines/harbor.sh`: pass Harbor's supported `--n-tasks` limit and anchor task file.
- `templates/evaluator/parse_score.py`: honor stage-adjusted expected trial counts.
- `ARCHITECTURE.md`, `DESIGN.md`, `README.md`, `library/PROTOCOL.md`, `tests/test_coherence.py`: remove the retired feedback module and document the generic lifecycle.

### HyperAgents method files

- `library/select/score_child_prop.py`: exact upstream score/child-count weights.
- `library/meta_agent/hyperagents.py`: upstream-shaped self-referential editing prompt and complete patch artifacts.
- `library/meta_agent/hyperagents.md`: evolvable strategy prompt.
- `library/validate/hyperagents.py`: fixed compilation/preflight validation.
- `library/validate/_skeleton.py`: reusable validate-operator template.
- `library/record/hyperagents.py`: compact experience manifest and archive annotations.
- `recipes/hyperagents/evolve.yaml`, `recipes/hyperagents/README.md`: real method composition.
- `recipes/hyperagents-smoke/evolve.yaml`, `recipes/hyperagents-smoke/README.md`: deterministic cheap composition.

### Tests

- `tests/test_phase_f_interfaces_sdk.py`: validate protocol and file contract.
- `tests/test_phase_f_init_binding.py`: optional validate binding and Markdown companion installation.
- `tests/test_m3_meta_eval.py`: atomic rejection rather than partial reversion.
- `tests/test_m5_driver_operators.py`: no automatic feedback and validate sequencing.
- `tests/test_m5_record_verb.py`: record finalization preserves primary failures.
- `tests/test_staged_evaluation.py`: zero/positive stage branches, genesis evaluation, and post-loop anchor.
- `tests/test_harbor_evaluator_template.py`: Harbor `--n-tasks` and stage expected-trial behavior.
- `tests/test_hyperagents_select.py`: exact upstream weights.
- `tests/test_hyperagents_meta_agent.py`: prompt, patch, and evidence-path behavior.
- `tests/test_hyperagents_validate_record.py`: compilation and experience record behavior.
- `tests/test_hyperagents_semantics.py`: end-to-end next-generation activation and valid stepping-stone retention.
- `tests/test_m0_init.py`, `tests/test_coherence.py`: initialization and architecture contracts.

---

### Task 1: Add the optional validate protocol and companion-prompt bootstrap

**Files:**
- Modify: `src/evolve/frozen/interfaces.py`
- Modify: `src/evolve/frozen/sdk.py`
- Modify: `src/evolve/workspace.py`
- Create: `library/validate/_skeleton.py`
- Modify: `tests/test_phase_f_interfaces_sdk.py`
- Modify: `tests/test_phase_f_init_binding.py`
- Modify: `tests/test_coherence.py`

**Interfaces:**
- Produces: `ValidateOperator.validate(checkout: Path, ctx: OperatorContext) -> ValidateResult`
- Produces: `ValidateResult(accept: bool, reason: str, artifacts: list[str])`
- Produces: `validate_validate_payload(payload) -> dict[str, Any]`
- Produces file: `runs/gen-N/validate/result.json`
- Preserves: validate is optional and absent from recipes that do not configure `operators.validate`.

- [ ] **Step 1: Write the failing SDK protocol test**

Add imports and this test to `tests/test_phase_f_interfaces_sdk.py`:

```python
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


def test_sdk_main_runs_validate_operator_and_writes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    _set_sdk_env(monkeypatch, tmp_path)

    class TinyValidate(ValidateOperator):
        def validate(self, checkout: Path, ctx) -> ValidateResult:
            return ValidateResult(accept=True, reason="imports pass", artifacts=["validate/imports.log"])

    sdk.main(TinyValidate)

    assert json.loads((run_dir / "validate" / "result.json").read_text()) == {
        "accept": True,
        "artifacts": ["validate/imports.log"],
        "reason": "imports pass",
    }
```

- [ ] **Step 2: Run the protocol test and verify the interface is missing**

Run:

```bash
uv run pytest tests/test_phase_f_interfaces_sdk.py::test_sdk_main_runs_validate_operator_and_writes_result -v
```

Expected: FAIL during import because `ValidateOperator` and `ValidateResult` do not exist.

- [ ] **Step 3: Add the validate ABC, result, validators, and registry entry**

Add to `src/evolve/frozen/interfaces.py`:

```python
class ValidateOperator(ABC):
    @abstractmethod
    def validate(self, checkout: Path, ctx) -> ValidateResult: ...


@dataclass(frozen=True)
class ValidateResult:
    accept: bool
    reason: str
    artifacts: list[str]


def validate_validate_payload(payload: ValidateResult | dict[str, Any]) -> dict[str, Any]:
    data = _payload_dict(payload)
    if not isinstance(data.get("accept"), bool):
        raise PayloadValidationError("accept", "accept must be a boolean")
    if not isinstance(data.get("reason"), str):
        raise PayloadValidationError("reason", "reason must be a string")
    if not isinstance(data.get("artifacts"), list):
        raise PayloadValidationError("artifacts", "artifacts must be a list")
    return {
        "accept": data["accept"],
        "reason": data["reason"],
        "artifacts": [str(path) for path in data["artifacts"]],
    }


def validate_validate_file_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("accept", "validate payload must be a JSON object")
    return validate_validate_payload(cast("dict[str, Any]", payload))
```

Register it immediately after `meta_agent`:

```python
OperatorSpec("validate", ValidateOperator, ValidateResult, "validate", False),
```

Also add `interfaces.ValidateOperator: {"validate"}` to the expected abstract-method
mapping in `test_operator_abcs_have_one_kind_specific_abstract_method`.

- [ ] **Step 4: Dispatch validate from the SDK**

Import the new symbols in `src/evolve/frozen/sdk.py` and add this branch after `MetaAgentOperator`:

```python
elif issubclass(operator_cls, ValidateOperator):
    payload = validate_validate_payload(operator.validate(ctx.checkout, ctx))
    _write_json(ctx.run_dir / "validate" / "result.json", payload)
```

- [ ] **Step 5: Add a reusable validate skeleton**

Create `library/validate/_skeleton.py`:

```python
"""Skeleton fixed candidate-validation operator."""

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class SkeletonValidate(ValidateOperator):
    def validate(self, checkout, ctx) -> ValidateResult:
        return ValidateResult(accept=True, reason="replace with candidate checks", artifacts=[])


if __name__ == "__main__":
    sdk.main(SkeletonValidate)
```

- [ ] **Step 6: Write the failing companion-prompt initialization test**

Add to `tests/test_phase_f_init_binding.py`:

```python
def test_variant_markdown_companion_becomes_active_operator_prompt(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "meta_agent").mkdir(parents=True)
    (library / "meta_agent" / "custom.py").write_text("# custom operator\n")
    (library / "meta_agent" / "custom.md").write_text("CUSTOM STRATEGY\n")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    config = {
        "operators": {
            "select": {"script": str(tmp_path / "select.py")},
            "rollout": {"script": str(tmp_path / "rollout.py")},
            "meta_agent": {"variant": "custom"},
            "gate": {"script": str(tmp_path / "gate.py")},
            "record": {"script": str(tmp_path / "record.py")},
        }
    }
    for name in ("select", "rollout", "gate", "record"):
        (tmp_path / f"{name}.py").write_text(f"# {name}\n")
    binding = next(
        item
        for item in workspace_module._operator_bindings(config, recipe="test", init_cwd=tmp_path)
        if item.kind == "meta_agent"
    )

    assert binding.companion_text == "CUSTOM STRATEGY\n"
```

Expected initial failure: `_OperatorBinding` has no `companion_text` field.

- [ ] **Step 7: Carry a sibling Markdown companion through `_OperatorBinding`**

Extend `_OperatorBinding` with `companion_text: str | None`. Resolve `source.with_suffix(".md")` for both `variant` and `script` bindings, and write it after active operator scripts:

```python
for binding in bindings:
    files[f"operators/{binding.kind}.py"] = _with_provenance(binding.kind, binding.source, binding.text)
    if binding.companion_text is not None:
        files[f"operators/{binding.kind}.md"] = binding.companion_text
```

Iterate over `(*OPERATOR_KINDS, *OPTIONAL_OPERATOR_KINDS)` in `_operator_palette` so configured optional variants are vendored consistently.

- [ ] **Step 8: Run protocol, binding, and registry-coherence tests**

Run:

```bash
uv run pytest tests/test_phase_f_interfaces_sdk.py tests/test_phase_f_init_binding.py tests/test_coherence.py::test_operator_registry_is_the_single_source -v
```

Expected: PASS.

- [ ] **Step 9: Commit the generic validate seam**

```bash
git add src/evolve/frozen/interfaces.py src/evolve/frozen/sdk.py src/evolve/workspace.py \
  library/validate/_skeleton.py tests/test_phase_f_interfaces_sdk.py \
  tests/test_phase_f_init_binding.py tests/test_coherence.py
git commit -m "Add candidate validation operator"
```

---

### Task 2: Enforce the surface, validate, and reject self-modification atomically

**Files:**
- Modify: `src/evolve/driver.py:1-290,838-965`
- Modify: `src/evolve/frozen/sdk.py:170-180`
- Delete: `src/evolve/feedback.py`
- Modify: `tests/test_m3_meta_eval.py`
- Modify: `tests/test_m5_driver_operators.py`
- Modify: `tests/test_m2_feedback_candidate_edits.py`
- Modify: `ARCHITECTURE.md`
- Modify: `DESIGN.md`
- Modify: `README.md`
- Modify: `library/PROTOCOL.md`
- Modify: `tests/test_coherence.py`

**Interfaces:**
- Consumes: optional `operators.validate` from Task 1.
- Produces terminal statuses: `rejected_validation`, `rejected_admission`.
- Produces: `_load_validate_payload(run_dir) -> tuple[dict | None, OperatorOutputError | None]`.
- Removes: automatic `runs/gen-N/feedback/` creation.

- [ ] **Step 1: Replace the partial-reversion test with atomic-rejection assertions**

In `tests/test_m3_meta_eval.py`, make the test meta-agent edit both `target/agent.py` and `operators/meta_agent.py`, force `meta_eval.admit` to return `{"admitted": False}`, then assert:

```python
rows = rows_by_genid(workspace)
assert rows["1"]["status"] == "rejected_admission"
assert rows["1"]["valid_parent"] is False
assert not git(workspace, "tag", "--list", "gen/1")
assert "child-target-change" not in git(workspace, "show", "gen/0:target/agent.py")
assert "child-workflow-change" not in git(workspace, "show", "gen/0:operators/meta_agent.py")
```

- [ ] **Step 2: Add a failing validation-order test**

Add to `tests/test_m5_driver_operators.py` a workspace validate script returning `accept=False`, configure `operators.validate: {}`, and assert:

```python
driver_run(RunOptions(workspace=workspace, max_generations=1))

row = rows_by_genid(workspace)["1"]
assert row["status"] == "rejected_validation"
assert row["reason"] == "candidate validation rejected: broken imports"
assert not git(workspace, "tag", "--list", "gen/1")
assert json.loads((workspace / "runs/gen-1/validate/result.json").read_text())["accept"] is False
```

Run both focused tests. Expected: the old driver partially reverts and commits, so both fail.

- [ ] **Step 3: Add one full terminal-rejection helper**

In `src/evolve/driver.py`, extend terminal/unretryable statuses and add:

```python
def _append_candidate_rejected(
    workspace: Path,
    exp_id: str,
    genid: str,
    parent: str,
    *,
    status: str,
    reason: str,
    mutated: list[str],
    violations: list[str] | None = None,
) -> None:
    append_event(
        workspace,
        exp_id,
        {
            "genid": genid,
            "parent": parent,
            "tag": f"gen/{genid}",
            "score": None,
            "status": status,
            "task_set_hash": None,
            "evaluator_tree": None,
            "valid_parent": False,
            "verdict": "discard",
            "reason": reason,
            "mutated": mutated,
            "surface_violations": list(violations or []),
            "predicted_fixes": [],
            "note": reason,
            "cost": {"usd": 0, "wall_s": 0},
        },
    )
```

- [ ] **Step 4: Enforce the surface before post-proposal operators**

Immediately after `meta_agent` succeeds:

```python
mutated_paths = working_tree_changed_paths(child, f"gen/{parent}")
if not mutated_paths:
    _append_candidate_rejected(
        workspace, exp_id, genid, parent,
        status="no_proposal", reason="no changes to commit", mutated=[],
    )
    return
include, exclude = surface_patterns(workspace)
violations = check_paths(mutated_paths, include, exclude)
if violations:
    _append_candidate_rejected(
        workspace, exp_id, genid, parent,
        status="invalid_proposal", reason="changed paths outside mutable surface",
        mutated=mutated_paths, violations=violations,
    )
    return
```

- [ ] **Step 5: Execute optional validation and reject without committing**

Add `_load_validate_payload` through `validate_validate_file_payload`, extend `_operator_output_error("validate", ...)`, then insert:

```python
if _operator_present(operators_config, "validate"):
    if not _run_operator_or_fail(
        name="validate", checkout=child, workspace=workspace, exp_id=exp_id,
        genid=genid, parent=parent, run_dir=_run_dir(workspace, genid),
        operators_config=operators_config, round_number=round_number,
    ):
        return
    validation, _error = _load_validate_payload(_run_dir(workspace, genid))
    if validation is not None and not validation["accept"]:
        _append_candidate_rejected(
            workspace, exp_id, genid, parent,
            status="rejected_validation",
            reason=f"candidate validation rejected: {validation['reason']}",
            mutated=mutated_paths,
        )
        return
```

- [ ] **Step 6: Replace partial meta-eval reversion with full rejection**

Replace the checkout loop and `operator_reverted` bookkeeping with:

```python
if not os.environ.get("EVOLVE_IN_META_EVAL") and meta_eval.operator_surface_changed(mutated_paths):
    verdict = meta_eval.admit(workspace, f"gen/{parent}", child)
    if not verdict.get("admitted"):
        _write_json(_run_dir(workspace, genid) / "meta_eval.json", verdict)
        _append_candidate_rejected(
            workspace, exp_id, genid, parent,
            status="rejected_admission",
            reason="self-modification admission rejected complete child",
            mutated=mutated_paths,
        )
        return
```

Delete `operator_reverted` fields and their tests.

- [ ] **Step 7: Retire framework feedback generation**

Delete the driver import/call and `src/evolve/feedback.py`. Change `_observation` in the SDK to only expose the rollout summary:

```python
def _observation(run_dir: Path) -> str:
    summary_path = run_dir / "rollout" / "summary.json"
    return summary_path.read_text() if summary_path.exists() else ""
```

Rewrite `tests/test_m2_feedback_candidate_edits.py` as `test_no_framework_feedback_bundle_is_created` and assert:

```python
assert not (workspace / "runs/gen-1/feedback").exists()
assert (workspace / "runs/gen-1/rollout/summary.json").exists()
```

Update `tests/test_m5_driver_operators.py`, `ARCHITECTURE.md`, `DESIGN.md`, `README.md`, and `library/PROTOCOL.md` to remove the feedback-module contract. Remove `feedback.py` from `APPROVED_MODULES` and the architecture table; do not raise the total line budget merely to absorb new driver code.

- [ ] **Step 8: Run atomicity, validation, feedback, and coherence tests**

Run:

```bash
uv run pytest tests/test_m3_meta_eval.py tests/test_m5_driver_operators.py \
  tests/test_m2_feedback_candidate_edits.py tests/test_coherence.py -v
```

Expected: PASS except the already accepted public-documentation assertion if Task 7 has not yet added the literal `hyperagents-smoke` reference.

- [ ] **Step 9: Commit the trusted proposal lifecycle**

```bash
git add src/evolve/driver.py src/evolve/frozen/sdk.py src/evolve/feedback.py \
  tests/test_m3_meta_eval.py tests/test_m5_driver_operators.py \
  tests/test_m2_feedback_candidate_edits.py ARCHITECTURE.md DESIGN.md README.md \
  library/PROTOCOL.md tests/test_coherence.py
git commit -m "Make self-modifying proposals atomic"
```

---

### Task 3: Run record as a best-effort terminal finalizer

**Files:**
- Modify: `src/evolve/operators.py`
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/frozen/sdk.py`
- Modify: `tests/test_m5_record_verb.py`
- Modify: `tests/test_phase_f_interfaces_sdk.py`

**Interfaces:**
- Produces: `run_operator(..., operator_checkout: Path | None = None)`.
- Produces: `_run_terminal_record(...) -> None`.
- Preserves: record fields cannot overwrite stamped/identity/evaluation fields.
- Preserves: record failure annotates `record_error` without replacing the primary status.

- [ ] **Step 1: Write a failing test for recording a rejected attempt**

Add to `tests/test_m5_record_verb.py` a meta-agent that produces no patch and a record operator that writes `{"attempt_recorded": true}`. Assert:

```python
driver_run(RunOptions(workspace=workspace, max_generations=1))

row = rows_by_genid(workspace)["1"]
assert row["status"] == "no_proposal"
assert row["attempt_recorded"] is True
assert json.loads((workspace / "runs/gen-1/record/fields.json").read_text()) == {
    "attempt_recorded": True
}
```

- [ ] **Step 2: Write a failing test that record failure preserves validation rejection**

Configure validation to reject and record to exit nonzero, then assert:

```python
row = rows_by_genid(workspace)["1"]
assert row["status"] == "rejected_validation"
assert row["reason"].startswith("candidate validation rejected")
assert "record_error" in row
```

Run both tests. Expected: early-return attempts do not currently invoke record.

- [ ] **Step 3: Separate operator source checkout from candidate context checkout**

Extend `run_operator` in `src/evolve/operators.py`:

```python
def run_operator(
    *,
    name: str,
    checkout: Path,
    workspace: Path,
    genid: str,
    parent: str | None,
    run_dir: Path,
    config_block: dict[str, Any],
    timeout_s: float,
    round_number: int | None = None,
    operator_checkout: Path | None = None,
) -> OperatorResult:
    source_checkout = operator_checkout or checkout
    script = source_checkout / "operators" / f"{name}.py"
    # Keep cwd=checkout and EVOLVE_CHECKOUT=checkout, but pass str(script.resolve())
    # to _OPERATOR_WRAPPER so a fixed parent operator can inspect a rejected child.
```

Thread `operator_checkout` through `_run_operator_guarded` without changing existing callers.

- [ ] **Step 4: Add best-effort record-error annotation**

Add:

```python
def _append_record_error(workspace: Path, exp_id: str, genid: str, note: str) -> None:
    append_event(workspace, exp_id, {"genid": genid, "record_error": note})
```

This event contains no stamped field and therefore cannot replace the primary outcome.

- [ ] **Step 5: Implement terminal record finalization**

Add `_run_terminal_record` that checks out `gen/<parent>` as the trusted operator source for uncommitted/rejected attempts, passes the candidate worktree when it still exists, loads `record/fields.json`, strips protected fields, and calls `record_fields`. For tagged evaluated children, keep `_run_gate_and_record` but route its record half through the same helper.

The core control shape is:

```python
def _run_terminal_record(..., candidate_checkout: Path | None) -> None:
    if not _operator_present(operators_config, "record"):
        return
    with tempfile.TemporaryDirectory(prefix=f"evolve-record-{genid}-") as tempdir:
        operator_checkout = Path(tempdir) / "operator"
        add_worktree(workspace, operator_checkout, f"gen/{parent}")
        try:
            context_checkout = candidate_checkout if candidate_checkout and candidate_checkout.exists() else operator_checkout
            result = _run_operator_guarded(
                name="record", checkout=context_checkout, operator_checkout=operator_checkout,
                workspace=workspace, exp_id=exp_id, genid=genid, parent=parent,
                run_dir=_run_dir(workspace, genid),
                config_block=_operator_config_block(operators_config, "record"),
                timeout_s=operator_timeout(operators_config, "record"),
            )
            if result.returncode != 0:
                _append_record_error(workspace, exp_id, genid, _operator_failure_note(result))
                return
            fields, error = _load_record_fields(_run_dir(workspace, genid))
            if error is not None or fields is None:
                _append_record_error(workspace, exp_id, genid, _operator_output_note(error))
                return
            record_fields(workspace, genid, _strip_record_fields(fields))
        finally:
            remove_worktree(workspace, operator_checkout)
```

Invoke it exactly once after every terminal outcome. Use a `recorded` guard in `_run_child`/resume paths so restarts remain idempotent.

- [ ] **Step 6: Run record and operator isolation tests**

Run:

```bash
uv run pytest tests/test_m5_record_verb.py tests/test_phase_f_interfaces_sdk.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit terminal recording**

```bash
git add src/evolve/operators.py src/evolve/driver.py src/evolve/frozen/sdk.py \
  tests/test_m5_record_verb.py tests/test_phase_f_interfaces_sdk.py
git commit -m "Record every terminal generation attempt"
```

---

### Task 4: Add staged evaluation, real genesis scoring, and a post-loop anchor

**Files:**
- Modify: `src/evolve/config.py`
- Modify: `src/evolve/evaluator.py`
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/workspace.py`
- Modify: `templates/evaluator/stub_eval.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `templates/evaluator/parse_score.py`
- Create: `tests/test_staged_evaluation.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_m0_init.py`

**Interfaces:**
- Produces: `evaluator_stage(workspace) -> dict[str, Any] | None`.
- Produces: `evaluator_anchor(workspace) -> dict[str, Any]`.
- Extends: `evaluate(..., run_name="eval", task_limit=None, eval_kind="research")`.
- Produces archive fields: `stage_score`, `run_full_eval`, and post-loop `kind="anchor"` evaluation.

- [ ] **Step 1: Write zero-stage and positive-stage driver tests**

Create `tests/test_staged_evaluation.py` with a monkeypatched `driver.evaluate` returning controlled `EvaluationResult` objects. The zero test asserts calls `[("eval-stage", 4)]`, final row score `0.0`, `stage_score == 0.0`, `run_full_eval is False`, and `valid_parent is True`. The positive test asserts calls `[("eval-stage", 4), ("eval", None)]`, final score equals the full result, and `run_full_eval is True`.

Use this result helper:

```python
def result(score: float, *, status: str = "complete") -> EvaluationResult:
    return EvaluationResult(
        score=score,
        status=status,
        task_set_hash="tasks",
        evaluator_tree="tree",
        wall_s=0.01,
        task_vector={"task-0": score > 0},
    )
```

- [ ] **Step 2: Write genesis and anchor lifecycle tests**

In the same file, assert that `run(max_generations=0)` replaces the scaffold generation-zero score through a real `evaluate(..., eval_kind="genesis")` call, and that `anchor.final: true` produces one `kind="anchor"` event only after all child meta-agent calls. Run the command twice and assert anchor idempotence.

- [ ] **Step 3: Run the focused tests and verify no staged lifecycle exists**

```bash
uv run pytest tests/test_staged_evaluation.py -v
```

Expected: FAIL because the config helpers and evaluator arguments are absent.

- [ ] **Step 4: Add typed stage and anchor config accessors**

In `src/evolve/config.py`:

```python
def evaluator_stage(workspace: Path) -> dict[str, Any] | None:
    value = evaluator_values(workspace).get("stage")
    if not isinstance(value, dict):
        return None
    tasks = value.get("tasks")
    if not isinstance(tasks, int) or isinstance(tasks, bool) or tasks < 1:
        raise ValueError("evaluator.stage.tasks must be a positive integer")
    proceed_if = str(value.get("proceed_if", "positive"))
    if proceed_if != "positive":
        raise ValueError("evaluator.stage.proceed_if must be positive")
    return {"tasks": tasks, "proceed_if": proceed_if}


def evaluator_anchor(workspace: Path) -> dict[str, Any]:
    value = evaluator_values(workspace).get("anchor")
    return dict(value) if isinstance(value, dict) else {}
```

- [ ] **Step 5: Pass task limit and evaluation kind to evaluator scripts**

Extend `evaluate`/`_run_eval_script` with `task_limit` and `eval_kind`. Add only when set:

```python
env["EVOLVE_EVAL_KIND"] = eval_kind
if task_limit is not None:
    env["EVOLVE_TASK_LIMIT"] = str(task_limit)
```

Update `templates/evaluator/engines/harbor.sh` after dataset arguments:

```sh
if [ -n "${EVOLVE_TASK_LIMIT:-}" ]; then
  set -- "$@" --n-tasks "$EVOLVE_TASK_LIMIT"
  export EVOLVE_HARBOR_EXPECTED_TRIALS=$((EVOLVE_TASK_LIMIT * EVOLVE_HARBOR_N))
fi
if [ "${EVOLVE_EVAL_KIND:-research}" = "anchor" ] && [ -n "${EVOLVE_HARBOR_ANCHOR_TASK_FILE:-}" ]; then
  EVOLVE_HARBOR_TASK_FILE=$EVOLVE_HARBOR_ANCHOR_TASK_FILE
fi
```

Harbor `--n-tasks` is supported by `harbor-framework/harbor` as `-l/--n-tasks` and is applied after filters. Make `parse_score.py` prefer `os.environ["EVOLVE_HARBOR_EXPECTED_TRIALS"]` over the value loaded from `eval.env`.

Make `stub_eval.py` use:

```python
K = int(os.environ.get("EVOLVE_TASK_LIMIT", "8"))
prefix = "sealed-task" if os.environ.get("EVOLVE_EVAL_KIND") == "anchor" else "task"
task_vector = {f"{prefix}-{i}": (f"{prefix}-{i}" not in failed) for i in range(K)}
```

- [ ] **Step 6: Orchestrate stage then full in `eval_child`**

Extract `_evaluate_candidate`:

```python
def _evaluate_candidate(workspace: Path, tag: str, genid: str, round_number: int | None):
    stage = evaluator_stage(workspace)
    if stage is None:
        return evaluate(workspace, tag, genid, round_number=round_number), None, True
    staged = evaluate(
        workspace, tag, genid, round_number=round_number,
        run_name="eval-stage", task_limit=stage["tasks"], eval_kind="stage",
    )
    if staged.status not in {"complete", "partial"} or staged.score is None or staged.score <= 0:
        return staged, staged.score, False
    full = evaluate(workspace, tag, genid, round_number=round_number, eval_kind="research")
    return full, staged.score, True
```

Stamp `stage_score` and `run_full_eval` into the evaluation event. The gate continues to accept `complete`/`partial`, including score zero.

- [ ] **Step 7: Evaluate genesis before selection and anchor after the loop**

At the start of `run`, call `_ensure_genesis_evaluated` when generation zero still has `note == "initial scaffold"`. Append a mechanism evaluation event with `kind="genesis_eval"`, real score/status/hash/tree/vector, and no pending gate.

After the generation loop, call `_maybe_run_final_anchor`. It should read `evaluator.anchor.final`, select `best_row`, skip when that generation already has an anchor evaluation, and append a protected `kind="anchor"` evaluation using `run_name="eval-anchor"`, `eval_kind="anchor"`. It must not invoke gate, record, reflect, select, rollout, or meta-agent afterward.

- [ ] **Step 8: Verify Harbor arguments, stage behavior, genesis, and anchor**

Run:

```bash
uv run pytest tests/test_staged_evaluation.py tests/test_harbor_evaluator_template.py tests/test_m0_init.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit staged and terminal evaluation lifecycle**

```bash
git add src/evolve/config.py src/evolve/evaluator.py src/evolve/driver.py src/evolve/workspace.py \
  templates/evaluator/stub_eval.py templates/evaluator/engines/harbor.sh \
  templates/evaluator/parse_score.py tests/test_staged_evaluation.py \
  tests/test_harbor_evaluator_template.py tests/test_m0_init.py
git commit -m "Add staged and final evaluation lifecycle"
```

---

### Task 5: Implement upstream `score_child_prop` exactly

**Files:**
- Create: `library/select/score_child_prop.py`
- Create: `tests/test_hyperagents_select.py`

**Interfaces:**
- Produces: `selection_weights(rows: list[Row]) -> list[tuple[str, float]]`.
- Produces: `ScoreChildProportionalSelect.pick(archive, ctx) -> SelectResult`.
- Requires: child counts include every recorded direct child attempt of a valid candidate.

- [ ] **Step 1: Write exact-weight tests**

Create `tests/test_hyperagents_select.py` and import the variant through `importlib.util`. Use rows with scores `0.2`, `0.5`, `0.8`, and nine children of the `0.8` node. Assert:

```python
weighted = dict(module.selection_weights(rows))
midpoint = (0.8 + 0.5 + 0.2) / 3
assert weighted["1"] == pytest.approx(1 / (1 + math.exp(-10 * (0.2 - midpoint))))
assert weighted["2"] == pytest.approx(1 / (1 + math.exp(-10 * (0.5 - midpoint))))
assert weighted["3"] == pytest.approx(
    (1 / (1 + math.exp(-10 * (0.8 - midpoint)))) * math.exp(-((9 / 8) ** 3))
)
```

Add invalid, missing-score, and Boolean-score rows and assert they are absent. Add a deterministic `ctx.rng = random.Random(0)` test asserting every selected parent belongs to the weighted candidate IDs.

- [ ] **Step 2: Run the selector tests and verify the variant is missing**

```bash
uv run pytest tests/test_hyperagents_select.py -v
```

Expected: FAIL because `library/select/score_child_prop.py` does not exist.

- [ ] **Step 3: Implement the upstream formula**

Create `library/select/score_child_prop.py`:

```python
"""HyperAgents score-proportional, child-penalized parent selection."""

import math
import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import SelectOperator, SelectResult


def selection_weights(rows):
    candidates = {
        str(row["genid"]): row
        for row in rows
        if row.get("valid_parent") is True
        and row.get("status") in {"complete", "partial"}
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
    }
    if not candidates:
        return []
    child_counts = {genid: 0 for genid in candidates}
    for row in rows:
        parent = str(row.get("parent"))
        if parent in child_counts:
            child_counts[parent] += 1
    scores = [float(row["score"]) for row in candidates.values()]
    top = sorted(scores, reverse=True)[:3]
    midpoint = sum(top) / len(top)
    weighted = []
    for genid, row in candidates.items():
        score = float(row["score"])
        score_weight = 1 / (1 + math.exp(-10 * (score - midpoint)))
        child_penalty = math.exp(-((child_counts[genid] / 8) ** 3))
        weighted.append((genid, score_weight * child_penalty))
    return weighted


class ScoreChildProportionalSelect(SelectOperator):
    def pick(self, archive, ctx) -> SelectResult:
        weighted = selection_weights(archive.rows())
        if not weighted:
            raise RuntimeError("score_child_prop found no valid scored parents")
        genids = [genid for genid, _weight in weighted]
        weights = [weight for _genid, weight in weighted]
        if sum(weights) <= 0:
            weights = [1.0] * len(weights)
        return SelectResult(parents=ctx.rng.choices(genids, weights=weights, k=max(1, ctx.fan_out)))


if __name__ == "__main__":
    sdk.main(ScoreChildProportionalSelect)
```

- [ ] **Step 4: Run selector tests**

```bash
uv run pytest tests/test_hyperagents_select.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit upstream parent selection**

```bash
git add library/select/score_child_prop.py tests/test_hyperagents_select.py
git commit -m "Add HyperAgents parent selection"
```

---

### Task 6: Implement dedicated HyperAgents meta-agent, validator, and record variants

**Files:**
- Create: `library/meta_agent/hyperagents.py`
- Create: `library/meta_agent/hyperagents.md`
- Create: `library/validate/hyperagents.py`
- Create: `library/record/hyperagents.py`
- Create: `tests/test_hyperagents_meta_agent.py`
- Create: `tests/test_hyperagents_validate_record.py`

**Interfaces:**
- Produces artifacts: `meta_agent/model_patch.diff`, `meta_agent/output.txt`, `meta_agent/prompt.md`, `meta_agent/usage.json`, and standard patch/surface files.
- Consumes directly: `ctx.workspace/archive.jsonl`, `ctx.workspace/runs/`, `ctx.checkout`, and `ctx.run_dir`.
- Produces: validate result plus `validate/compile.log`.
- Produces: `record/experience.json` and archive field `experience_record`.

- [ ] **Step 1: Write prompt and patch-artifact tests**

In `tests/test_hyperagents_meta_agent.py`, create a checkout, archive, prior run artifact, and fake `run_meta_agent`. Assert the constructed prompt contains the checkout path, archive path, runs path, remaining iterations, and the sentence `Modify any part of the allowed codebase`. Assert it does not contain `You are editing the MiniSWE source checkout under target/`.

After the fake agent edits both `target/agent.py` and `operators/meta_agent.md`, assert `model_patch.diff` contains both paths and the returned `changed` list contains both.

- [ ] **Step 2: Write validator and record tests**

In `tests/test_hyperagents_validate_record.py`, assert valid Python under `operators/meta_agent.py` and `target/**/*.py` returns accept. Introduce `target/broken.py` with `def broken(:` and assert rejection reason names that file and `validate/compile.log` exists.

Create a child row with stage/full fields plus run artifacts and assert `record/hyperagents.py` writes:

```json
{
  "genid": "1",
  "parent": "0",
  "score": 0.5,
  "stage_score": 0.25,
  "run_full_eval": true,
  "status": "complete"
}
```

and returns `experience_record: runs/gen-1/record/experience.json`.

- [ ] **Step 3: Run the focused tests and verify variants are absent**

```bash
uv run pytest tests/test_hyperagents_meta_agent.py tests/test_hyperagents_validate_record.py -v
```

Expected: FAIL because the files do not exist.

- [ ] **Step 4: Create the evolvable HyperAgents prompt**

Create `library/meta_agent/hyperagents.md`:

```markdown
# HyperAgents Self-Improvement

Modify any part of the allowed codebase to improve downstream task performance.
You may improve the task agent, this meta-agent workflow and prompt, or their
interaction. Inspect prior generations and evaluation artifacts before editing.
Make one coherent repository change; descendants inherit the complete patch.
Do not modify fixed evaluator, selection, validation, gate, record, configuration,
or mechanism files.
```

- [ ] **Step 5: Implement the self-referential meta-agent variant**

Create `library/meta_agent/hyperagents.py` around the existing public agent and patching APIs:

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.agent import AgentCommandError, run_meta_agent
from evolve.frozen import sdk
from evolve.frozen.interfaces import MetaAgentOperator, MetaAgentResult
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref


def _remaining_iterations(ctx) -> str:
    text = (ctx.workspace / "evolve.yaml").read_text()
    maximum = next((int(line.split(":", 1)[1]) for line in text.splitlines() if line.strip().startswith("max_generations:")), 0)
    current = int(str(ctx.genid).split("-", 1)[0])
    return str(max(maximum - current, 0))


def build_prompt(checkout: Path, ctx) -> str:
    strategy = (checkout / "operators" / "meta_agent.md").read_text().rstrip()
    return (
        f"{strategy}\n\n"
        f"Repository: {checkout}\n"
        f"Archive: {ctx.workspace / 'archive.jsonl'}\n"
        f"Prior generation artifacts: {ctx.workspace / 'runs'}\n"
        f"Current generation artifacts: {ctx.run_dir}\n"
        f"Iterations remaining after this proposal: {_remaining_iterations(ctx)}\n\n"
        "Edit the checkout directly. Do not print a patch instead of editing files.\n"
    )


class HyperAgentsMetaAgent(MetaAgentOperator):
    def run(self, checkout: Path, observation: str, ctx) -> MetaAgentResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        prompt = build_prompt(checkout, ctx)
        out = ctx.run_dir / "meta_agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "prompt.md").write_text(prompt)
        try:
            agent_run = run_meta_agent(workspace=checkout, prompt=prompt, config=ctx.config)
        except AgentCommandError as exc:
            (out / "output.txt").write_text(exc.output)
            (out / "usage.json").write_text(json.dumps(exc.usage, sort_keys=True) + "\n")
            raise SystemExit(exc.returncode)
        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
        )
        (out / "model_patch.diff").write_text(patch.diff)
        (out / "patch.diff").write_text(patch.diff)
        (out / "output.txt").write_text(agent_run.output)
        (out / "surface-check.json").write_text(json.dumps(patch.surface_report, indent=2, sort_keys=True) + "\n")
        (out / "usage.json").write_text(json.dumps(agent_run.usage, indent=2, sort_keys=True) + "\n")
        (out / "predicted_fixes.json").write_text("[]\n")
        return MetaAgentResult(
            changed=patch.changed_paths,
            notes=["written-by: operators/meta_agent.py", "variant: hyperagents"],
            usage=agent_run.usage,
        )


if __name__ == "__main__":
    sdk.main(HyperAgentsMetaAgent)
```

- [ ] **Step 6: Implement fixed compilation validation**

Create `library/validate/hyperagents.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import ValidateOperator, ValidateResult


class HyperAgentsValidate(ValidateOperator):
    def validate(self, checkout: Path, ctx) -> ValidateResult:
        files = [checkout / "operators" / "meta_agent.py", *sorted((checkout / "target").rglob("*.py"))]
        log = ctx.run_dir / "validate" / "compile.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        checked = []
        try:
            for path in files:
                compile(path.read_bytes(), str(path), "exec")
                checked.append(path.relative_to(checkout).as_posix())
        except (OSError, SyntaxError) as exc:
            log.write_text(f"FAIL {path.relative_to(checkout).as_posix()}: {exc}\n")
            return ValidateResult(False, f"compile failed for {path.relative_to(checkout).as_posix()}", ["validate/compile.log"])
        log.write_text("\n".join(f"PASS {path}" for path in checked) + "\n")
        return ValidateResult(True, "meta-agent and task-agent Python compile", ["validate/compile.log"])


if __name__ == "__main__":
    sdk.main(HyperAgentsValidate)
```

- [ ] **Step 7: Implement the compact experience record**

Create `library/record/hyperagents.py`:

```python
from __future__ import annotations

import json
import os
import sys

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import RecordOperator, RecordResult


class HyperAgentsRecord(RecordOperator):
    def annotate(self, child, ctx) -> RecordResult:
        experience = {
            key: child.get(key)
            for key in ("genid", "parent", "status", "score", "stage_score", "run_full_eval")
        }
        path = ctx.run_dir / "record" / "experience.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(experience, indent=2, sort_keys=True) + "\n")
        relative = path.relative_to(ctx.workspace).as_posix()
        return RecordResult(fields={"experience_record": relative})


if __name__ == "__main__":
    sdk.main(HyperAgentsRecord)
```

- [ ] **Step 8: Run method-operator tests**

```bash
uv run pytest tests/test_hyperagents_meta_agent.py tests/test_hyperagents_validate_record.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit dedicated method operators**

```bash
git add library/meta_agent/hyperagents.py library/meta_agent/hyperagents.md \
  library/validate/hyperagents.py library/record/hyperagents.py \
  tests/test_hyperagents_meta_agent.py tests/test_hyperagents_validate_record.py
git commit -m "Add HyperAgents method operators"
```

---

### Task 7: Compose the recipes and prove method-faithful behavior

**Files:**
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hyperagents/README.md`
- Modify: `recipes/hyperagents-smoke/evolve.yaml`
- Modify: `recipes/hyperagents-smoke/README.md`
- Modify: `recipes/README.md`
- Modify: `README.md`
- Modify: `library/README.md`
- Modify: `tests/test_hyperagents_semantics.py`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_coherence.py`

**Interfaces:**
- Consumes every generic and method interface from Tasks 1-6.
- Produces default real recipe: fixed selector/validator/gate/record and atomic task/meta-agent genome.
- Produces deterministic smoke recipe with the same control flow.
- Resolves the accepted baseline `hyperagents-smoke` documentation failure.

- [ ] **Step 1: Extend the initialization contract for the real recipe**

Add a test that initializes `hyperagents` with a local MiniSWE-shaped seed and asserts:

```python
assert "score_child_prop" in (workspace / "operators/select.py").read_text()
assert "variant: hyperagents" in (workspace / "operators/meta_agent.py").read_text()
assert "HyperAgents Self-Improvement" in (workspace / "operators/meta_agent.md").read_text()
assert "HyperAgentsValidate" in (workspace / "operators/validate.py").read_text()
assert "HyperAgentsRecord" in (workspace / "operators/record.py").read_text()
assert surface_lists(workspace) == (
    ["target/**", "operators/meta_agent.py", "operators/meta_agent.md"],
    [],
)
```

- [ ] **Step 2: Strengthen the two-generation semantics test**

Keep the current proof that generation 1 uses the old workflow and generation 2 uses the edited workflow. Add assertions that a lower-scoring but valid generation remains in `valid_parent_rows`, forbidden edits to `operators/gate.py` reject the entire child, and `operators/validate.py`/`operators/record.py` remain byte-identical across valid tags.

- [ ] **Step 3: Run the tests and verify placeholder recipes fail them**

```bash
uv run pytest tests/test_hyperagents_semantics.py tests/test_m0_init.py -v
```

Expected: FAIL because current recipes still select random/generic variants and expose `operators/**`.

- [ ] **Step 4: Replace the real recipe composition**

Set `recipes/hyperagents/evolve.yaml` to:

```yaml
experiment:
  id: hyperagents
  max_generations: 8
  target_score: null
  budget_usd: 150
  children_per_gen: 1
  mode: driver
  seed: 0
target:
  seed: https://github.com/SWE-agent/mini-swe-agent.git
  harbor_agent: miniswe-source
surface:
  include:
    - target/**
    - operators/meta_agent.py
    - operators/meta_agent.md
  exclude: []
operators:
  select: {variant: score_child_prop, seed: 0}
  rollout: {variant: noop}
  meta_agent: {variant: hyperagents, timeout_s: 21600}
  validate: {variant: hyperagents, timeout_s: 300}
  gate: {variant: parent_eligible}
  record: {variant: hyperagents}
  timeout_s: 600
evaluator:
  engine: harbor
  dataset: swe-bench-lite
  agent: target.harbor_agent:MiniSweSourceAgent
  split: {train: 0.5, gate: 0.4, sealed: 0.1, seed: 0}
  sampling: static
  tasks_per_round: 16
  stage: {tasks: 4, proceed_if: positive}
  anchor: {final: true, every_rounds: 0}
  k: 1
  n_concurrent: 16
  partial_floor: 0.8
```

Use the same variants and surface in `hyperagents-smoke`, but retain its builtin target, stub-friendly budget, and small task counts.

- [ ] **Step 5: Rewrite recipe documentation around the actual method**

Document the original paper/repository, fixed default selection, atomic genome, next-generation activation, external validation extension, staged evaluation, and the distinction between method faithfulness and benchmark validation. Remove claims that random selection or broad `operators/**` exposure defines HyperAgents.

Add a literal `hyperagents-smoke` reference to `recipes/README.md`, resolving the accepted coherence failure. Update top-level/library docs only where their operator/lifecycle tables changed.

- [ ] **Step 6: Run all deterministic and static verification**

```bash
uv run pytest -q
uv run ruff check src library tests
uv run ty check
git diff --check
```

Expected: all tests pass, including the previously accepted coherence failure; Ruff and ty report no new errors.

- [ ] **Step 7: Run a deterministic two-generation smoke**

```bash
test ! -e /tmp/hyperagents-smoke
EVAL_STUB=1 EVOLVE_HOME=/tmp/hyperagents-smoke-home \
  uv run evolve init /tmp/hyperagents-smoke --recipe hyperagents-smoke
EVAL_STUB=1 EVOLVE_HOME=/tmp/hyperagents-smoke-home \
  EVOLVE_AGENT_COMMAND="$(uv run python -c 'from tests.conftest import smoke_agent_command; print(smoke_agent_command())')" \
  uv run evolve run /tmp/hyperagents-smoke --max-generations 2
EVAL_STUB=1 EVOLVE_HOME=/tmp/hyperagents-smoke-home \
  uv run evolve verify /tmp/hyperagents-smoke
```

Expected: generations 1 and 2 have numeric scores and valid-parent status; validate and experience artifacts exist for both; verify reports archive integrity OK.

- [ ] **Step 8: Commit the recipe and deterministic proof**

```bash
git add recipes/hyperagents recipes/hyperagents-smoke recipes/README.md README.md library/README.md \
  tests/test_hyperagents_semantics.py tests/test_m0_init.py tests/test_coherence.py
git commit -m "Make HyperAgents method faithful"
```

---

### Task 8: Run the live Harbor candidate-liveness smoke and record status

**Files:**
- Modify only after a successful run: `recipes/hyperagents/README.md`

**Interfaces:**
- Consumes: Harbor, Docker, MiniSWE source agent, configured LLM credentials, and the complete method implementation.
- Produces: a documented run ID, benchmark/task count, score, candidate patch paths, validation result, wall time, and cost.
- Does not produce: a benchmark-validation claim.

- [ ] **Step 1: Confirm runtime prerequisites without printing secrets**

```bash
command -v harbor
docker info >/dev/null
test -n "${OPENAI_API_KEY:-${ANTHROPIC_API_KEY:-${GEMINI_API_KEY:-}}}"
uv run evolve --help >/dev/null
```

Expected: all commands return zero. Do not echo credential values.

- [ ] **Step 2: Initialize a one-generation live workspace**

```bash
test ! -e /tmp/hyperagents-live-smoke
EVOLVE_HOME=/tmp/hyperagents-live-home \
  uv run evolve init /tmp/hyperagents-live-smoke --recipe hyperagents
```

Before running, use the `apply_patch` tool on
`/tmp/hyperagents-live-smoke/evolve.yaml` with this exact patch, then commit the
workspace configuration and retag generation zero:

```diff
*** Begin Patch
*** Update File: /tmp/hyperagents-live-smoke/evolve.yaml
@@
-  max_generations: 8
+  max_generations: 1
@@
-  tasks_per_round: 16
-  stage: {tasks: 4, proceed_if: positive}
+  tasks_per_round: 2
+  stage: {tasks: 1, proceed_if: positive}
@@
-  n_concurrent: 16
+  n_concurrent: 2
*** End Patch
```

```bash
git -C /tmp/hyperagents-live-smoke add evolve.yaml
git -C /tmp/hyperagents-live-smoke commit -m "Configure HyperAgents live smoke"
git -C /tmp/hyperagents-live-smoke tag -f gen/0
```

- [ ] **Step 3: Run one live candidate**

```bash
EVOLVE_HOME=/tmp/hyperagents-live-home \
  uv run evolve run /tmp/hyperagents-live-smoke --max-generations 1
```

Expected: the meta-agent creates a nonempty `meta_agent/model_patch.diff`; validation accepts; staged evaluation writes a numeric score; the terminal row is recorded. A zero score validly skips full evaluation.

- [ ] **Step 4: Verify artifacts and integrity**

```bash
EVOLVE_HOME=/tmp/hyperagents-live-home uv run evolve verify /tmp/hyperagents-live-smoke
test -s /tmp/hyperagents-live-smoke/runs/gen-1/meta_agent/model_patch.diff
test -s /tmp/hyperagents-live-smoke/runs/gen-1/validate/result.json
test -s /tmp/hyperagents-live-smoke/runs/gen-1/record/experience.json
```

Expected: verification succeeds and every artifact is nonempty.

- [ ] **Step 5: Document the smoke result without overstating it**

Add a dated `Smoke verification` paragraph to `recipes/hyperagents/README.md` containing the exact run settings, terminal status, stage/full score, validator result, and artifact locations. State explicitly: `This verifies candidate liveness and method wiring; it is not benchmark validation.`

- [ ] **Step 6: Re-run final verification and commit the evidence note**

```bash
uv run pytest -q
uv run ruff check src library tests
uv run ty check
git diff --check
git add recipes/hyperagents/README.md
git commit -m "Document HyperAgents live smoke"
```

Expected: all checks pass and the final commit changes only the recipe README.
