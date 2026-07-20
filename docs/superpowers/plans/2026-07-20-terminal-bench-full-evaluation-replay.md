# Terminal-Bench Full Evaluation Replay Implementation Plan

> **For the implementing agent:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AHE and HyperAgents recipes run every candidate on the complete Terminal-Bench 2.0 task set while reusing each selected parent's certified evaluation trajectories as meta-agent evidence.

**Architecture:** Add a full-dataset evaluator mode that places every frozen task in one `train` cohort and uses that cohort for canonical evaluation. Add a small rollout operator that resolves the selected parent's certified evaluation artifact and invokes the existing Harbor case collector vendored under the experiment's protected `library/rollout/` tree, feeding the current trace analyzers without launching Harbor again. Keep the driver, evaluator ownership boundary, meta-agent workspace, and candidate evaluation flow unchanged.

**Tech Stack:** Python 3.13, pytest, Typer, YAML recipes, Harbor, Docker, Git worktrees.

## Global Constraints

- AHE and HyperAgents are independent fidelity experiments, not a controlled performance comparison.
- Use the official 89-task `terminal-bench@2.0` dataset from commit `2fd12b88aafdd04a52c298e3940bcb189f9766d6`.
- Reuse all 89 pre-pulled `alexgshaw/<task>:20251031` images on DevBoxS; do not rebuild or repull them.
- Use four Harbor task workers per experiment.
- AHE evaluates all tasks with `k=2`, follows latest valid parent, and mutates only `target/**`.
- HyperAgents evaluates all tasks with `k=1`, uses `score_child_prop`, and mutates `target/**` plus `operators/**`.
- Both long runs contain generation 0 plus ten evolved candidates.
- Do not create train/gate task copies, run a sealed anchor, add strict AHE schema validation, or add a permanent model pin.
- Preserve two meta-agent retries after the initial call.
- Keep the evaluator, dataset, credentials, endpoints, archive, and resource limits protected from model-generated changes.
- Do not expand the main driver or add replay behavior to the already-large Harbor execution path.

---

## File Structure

- Create `library/rollout/evaluation_replay.py`: resolve and verify the selected parent's canonical evaluation artifact, load the vendored Harbor case collector, normalize retained trials, and emit rollout artifacts.
- Modify `library/rollout/harbor.py`: expose the existing case collector as the public `collect_cases` helper used by both live Harbor rollout and replay.
- Modify `src/evolve/workspace.py`: accept `evaluator.task_scope: full`, internally freeze every local dataset task into one cohort, and permit recipes without a user-visible split mapping.
- Modify `src/evolve/evaluator.py`: choose the canonical cohort from `evaluator.evaluation_split` instead of always forcing `gate`.
- Modify `src/evolve/task_sets.py`: include the configured canonical cohort's exact members in the certified task-set identity.
- Modify `recipes/ahe/evolve.yaml` and `recipes/hyperagents/evolve.yaml`: select replay, full TB2 evaluation, method-specific `k`, ten generations, and four workers.
- Modify `recipes/ahe/README.md` and `recipes/hyperagents/README.md`: document each method's full-benchmark lifecycle and the absence of a held-out claim.
- Modify `tests/test_m7_harbor_rollout.py`: cover the public Harbor case collector name.
- Create `tests/test_evaluation_replay_rollout.py`: cover replay resolution, selected-parent behavior, artifact integrity, normalization, and failure modes.
- Modify `tests/test_m8_dataset_splits.py` and `tests/test_m1_evaluator_invariants.py`: cover full-dataset initialization, canonical cohort selection, and exact expected trial counts.
- Modify `tests/test_phase_e_recipes.py`: pin the final AHE and HyperAgents experiment settings.
- Modify `tests/test_m0_init.py` and `tests/test_m9_ahe_recipe.py`: expect the replay operator in initialized AHE/HyperAgents workspaces and verify that the Harbor collector remains vendored.

---

### Task 1: Full-Dataset Canonical Evaluation Mode

**Files:**
- Modify: `src/evolve/workspace.py:136-161`
- Modify: `src/evolve/evaluator.py:35-75,181-197`
- Modify: `src/evolve/task_sets.py:17-62`
- Modify: `tests/test_m8_dataset_splits.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: `evaluator.task_scope`, `evaluator.evaluation_split`, the local dataset path, and `evaluator.k`.
- Produces: `evaluation_split_name(evaluator: dict[str, Any], purpose: str) -> str`, a resolved `evaluator/splits.json` whose `train` list contains all tasks in full mode, and certified task-set identities containing every selected task.

- [ ] **Step 1: Add failing initialization tests for full task scope**

Add to `tests/test_m8_dataset_splits.py`:

```python
def test_init_full_task_scope_freezes_every_task_without_partition(tmp_path: Path, monkeypatch) -> None:
    from evolve.workspace import InitOptions, init_workspace

    dataset = _dataset(tmp_path / "tasks", count=4)
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("EVOLVE_RUNTIME_DIGEST", "sha256:test-runtime")
    monkeypatch.setattr(
        "evolve.workspace.default_config",
        lambda _recipe, name: {
            "experiment": {"id": name, "max_generations": 1, "children_per_gen": 1},
            "target": {"seed": "builtin-dummy", "harbor_agent": "miniswe-source"},
            "surface": {"include": ["target/**"], "exclude": []},
            "operators": {
                "select": {"variant": "ahe_latest"},
                "rollout": {"variant": "harbor"},
                "meta_agent": {"variant": "ahe"},
                "gate": {"variant": "ahe_artifact_valid"},
                "record": {"variant": "jsonl"},
            },
            "evaluator": {
                "engine": "harbor",
                "dataset": str(dataset),
                "agent": "evolve_harbor_adapter:MiniSweSourceAgent",
                "task_scope": "full",
                "evaluation_split": "train",
                "sampling": "static",
                "tasks_per_round": 4,
                "k": 2,
                "n_concurrent": 4,
            },
        },
    )

    init_workspace(InitOptions(workspace=workspace, recipe="ahe", dataset=str(dataset)))

    manifest = json.loads((workspace / "evaluator" / "splits.json").read_text())
    assert manifest["ratios"] == {"train": 1.0, "gate": 0.0, "sealed": 0.0}
    assert manifest["tasks"]["train"] == [f"task-{index}" for index in range(4)]
    assert manifest["tasks"]["gate"] == []
    assert manifest["tasks"]["sealed"] == []
    config = (workspace / "evolve.yaml").read_text()
    assert "task_scope: full" in config
    assert "evaluation_split: train" in config
```

- [ ] **Step 2: Add failing task-identity and evaluator-environment tests**

Add to `tests/test_m1_evaluator_invariants.py`:

```python
def test_full_scope_candidate_identity_contains_all_train_tasks(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    evaluator_dir = checkout / "evaluator"
    evaluator_dir.mkdir(parents=True)
    (evaluator_dir / "splits.json").write_text(json.dumps({
        "version": 1,
        "tasks": {"train": ["a", "b", "c"], "gate": [], "sealed": []},
    }))
    evaluator = {
        "dataset": "terminal-bench@2.0",
        "evaluation_split": "train",
        "k": 2,
    }

    identity = effective_task_set_identity(checkout, evaluator)

    assert identity.members == ("a", "b", "c")
```

Also add to `tests/test_m1_evaluator_invariants.py`, using its existing
`make_eval_script` helper:

```python
def test_eval_script_receives_configured_candidate_cohort(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    (checkout / "evaluator").mkdir(parents=True)
    make_eval_script(
        checkout / "evaluator" / "eval.sh",
        "#!/bin/sh\n"
        "set -eu\n"
        'printf "%s\\n" "$EVOLVE_EVAL_SPLIT" > selected-split\n',
    )
    run_dir = workspace / "runs" / "evaluations" / "candidate" / "gen-1" / "attempt-1"
    run_dir.mkdir(parents=True)

    result = _run_eval_script(checkout, run_dir, "1", None, "candidate", "train")

    assert result.returncode == 0
    assert (checkout / "selected-split").read_text() == "train\n"
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_m8_dataset_splits.py tests/test_m1_evaluator_invariants.py -q
```

Expected: FAIL because full mode still requires `evaluator.split`, candidate identity omits train members, and `_run_eval_script` has no evaluation-split argument.

- [ ] **Step 4: Add one canonical cohort resolver**

Add to `src/evolve/task_sets.py`:

```python
def evaluation_split_name(evaluator: dict[str, Any], purpose: str = "candidate") -> str:
    if purpose == "anchor":
        return "sealed"
    value = evaluator.get("evaluation_split", "gate")
    if value not in {"train", "gate", "sealed"}:
        raise ValueError(f"unknown evaluator.evaluation_split: {value}")
    return str(value)
```

Update `effective_task_set_identity` so that, when neither `task_names` nor
`task_file` is configured, it loads `evaluator/splits.json` and uses
`manifest["tasks"][evaluation_split_name(evaluator, purpose)]`. Keep the existing
anchor behavior through the same resolver.

- [ ] **Step 5: Permit full task scope during workspace initialization**

In `src/evolve/workspace.py`, replace the unconditional split requirement with:

```python
    task_scope = str(evaluator.get("task_scope", "partitioned"))
    split = evaluator.get("split")
    if task_scope == "full":
        if split is not None:
            raise ValueError("evaluator.task_scope full must not define evaluator.split")
        if evaluator.get("evaluation_split") != "train":
            raise ValueError("evaluator.task_scope full requires evaluator.evaluation_split train")
        split = {"train": 1.0, "gate": 0.0, "sealed": 0.0, "seed": 0}
    elif not isinstance(split, dict):
        raise ValueError("evaluator.split must be a mapping")
```

Pass the resulting internal mapping to the existing `build_manifest`; do not
add a second manifest format.

- [ ] **Step 6: Propagate the configured canonical cohort to evaluation**

In `src/evolve/evaluator.py`, import `evaluation_split_name`, compute it from the
candidate checkout's evaluator config, pass it into `_run_eval_script`, and use
it for `EVOLVE_EVAL_SPLIT`:

```python
def _run_eval_script(
    checkout: Path,
    run_dir: Path,
    genid: str,
    task_limit: int | None,
    purpose: str,
    evaluation_split: str,
) -> OwnedResult:
    ...
    env["EVOLVE_EVAL_SPLIT"] = evaluation_split
```

Call it with:

```python
split_name = evaluation_split_name(evaluator, purpose)
result = _run_eval_script(checkout, run_dir, genid, task_limit, purpose, split_name)
```

- [ ] **Step 7: Run focused and compatibility tests**

Run:

```bash
uv run pytest tests/test_m8_dataset_splits.py tests/test_m1_evaluator_invariants.py tests/test_evaluation_lifecycle.py tests/test_selection_certification.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the full-dataset mode**

```bash
git add src/evolve/workspace.py src/evolve/evaluator.py src/evolve/task_sets.py tests/test_m8_dataset_splits.py tests/test_m1_evaluator_invariants.py
git commit -m "feat: support full benchmark evaluation"
```

---

### Task 2: Replay Certified Parent Evaluations as Rollout Evidence

**Files:**
- Create: `library/rollout/evaluation_replay.py`
- Create: `tests/test_evaluation_replay_rollout.py`
- Modify: `library/rollout/harbor.py:334,579`
- Modify: `tests/test_m7_harbor_rollout.py`

**Interfaces:**
- Consumes: `OperatorContext.parent`, `ArchiveView.row(parent)`, the row's `artifacts.path` and `artifacts.sha256`, the sibling retained Harbor `jobs/` directory, and `checkout/library/rollout/harbor.py`.
- Produces: `EvaluationReplayRollout.rollout(checkout: Path, ctx: OperatorContext) -> RolloutResult` plus the public `collect_cases(jobs_dir: Path, field_limit: int = 2000, pass_threshold: float = 1.0) -> list[dict[str, Any]]` helper.

- [ ] **Step 1: Rename the Harbor case collector through failing tests**

In `tests/test_m7_harbor_rollout.py`, replace every `_collect_cases` reference
with `collect_cases`, including monkeypatch targets.

- [ ] **Step 2: Run the collector tests and verify they fail**

Run:

```bash
uv run pytest tests/test_m7_harbor_rollout.py -q
```

Expected: FAIL with `AttributeError` because `collect_cases` is not exported.

- [ ] **Step 3: Make the existing collector public without changing behavior**

In `library/rollout/harbor.py`, rename `_collect_cases` to `collect_cases` and
update the live rollout call site:

```python
def collect_cases(
    jobs_dir: Path,
    field_limit: int = 2000,
    pass_threshold: float = 1.0,
) -> list[dict[str, Any]]:
    ...

cases = collect_cases(jobs_dir, field_limit=field_limit, pass_threshold=pass_threshold)
```

- [ ] **Step 4: Add replay success and selected-parent tests**

Create `tests/test_evaluation_replay_rollout.py` with helpers that write a
minimal trial and a certified artifact manifest. The primary test must use a
non-latest parent ID:

```python
def test_replay_uses_selected_parent_certified_evaluation(tmp_path: Path, monkeypatch) -> None:
    module = _replay_module()
    workspace = tmp_path / "workspace"
    jobs = workspace / "runs" / "evaluations" / "candidate" / "gen-3" / "attempt-1" / "jobs"
    _write_trial(jobs, name="task-a__trial-0", task_name="task-a", reward=1.0)
    artifact_path = jobs.parent / "evaluation_artifacts.json"
    artifact_path.write_text(json.dumps({"jobs_dir": str(jobs), "trials": []}))
    reference = {
        "path": artifact_path.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    }
    rows = {
        "3": {"genid": "3", "artifacts": reference, "score": 1.0},
        "4": {"genid": "4", "artifacts": {"path": "wrong", "sha256": "wrong"}, "score": 0.0},
    }
    monkeypatch.setattr(module, "ArchiveView", lambda _workspace: _Archive(rows))
    monkeypatch.setattr(
        module,
        "_load_collect_cases",
        lambda _checkout: lambda _jobs, **_kwargs: [
            {"task_name": "task-a", "trial_name": "task-a__trial-0", "reward": 1.0, "outcome": "passed"}
        ],
    )
    ctx = _context(workspace, parent="3")

    result = module.EvaluationReplayRollout().rollout(workspace, ctx)

    cases = json.loads((ctx.run_dir / "rollout" / "cases.json").read_text())
    assert [case["task_name"] for case in cases] == ["task-a"]
    assert result.summary["source_parent"] == "3"
    assert result.summary["tasks_observed"] == 1
    assert result.summary["trials_observed"] == 1
    assert result.summary["mean_observed_reward"] == 1.0
```

- [ ] **Step 5: Add replay integrity and missing-evidence tests**

Add parameterized tests asserting clear failures for:

```python
@pytest.mark.parametrize(
    ("parent", "reference", "message"),
    [
        (None, None, "evaluation replay requires a selected parent"),
        ("3", None, "selected parent 3 has no certified evaluation artifacts"),
        ("3", {"path": "missing.json", "sha256": "0" * 64}, "artifact path is missing"),
    ],
)
def test_replay_rejects_missing_parent_evidence(...):
    ...

def test_replay_rejects_artifact_digest_mismatch(...):
    with pytest.raises(SystemExit, match="artifact digest mismatch"):
        module.EvaluationReplayRollout().rollout(workspace, ctx)

def test_replay_rejects_jobs_path_without_trial_results(...):
    with pytest.raises(SystemExit, match="produced no trial results"):
        module.EvaluationReplayRollout().rollout(workspace, ctx)
```

- [ ] **Step 6: Run replay tests and verify they fail**

Run:

```bash
uv run pytest tests/test_evaluation_replay_rollout.py tests/test_m7_harbor_rollout.py -q
```

Expected: replay tests fail because `evaluation_replay.py` does not exist; Harbor collector tests pass after Step 3.

- [ ] **Step 7: Implement the minimal replay operator**

Create `library/rollout/evaluation_replay.py` with this structure:

```python
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from evolve.frozen import sdk
from evolve.frozen.interfaces import ArchiveView, OperatorContext, RolloutOperator, RolloutResult


def _load_collect_cases(checkout: Path):
    path = checkout / "library" / "rollout" / "harbor.py"
    if not path.is_file():
        raise SystemExit(f"vendored Harbor rollout is missing: {path}")
    spec = importlib.util.spec_from_file_location("evolve_evaluation_replay_harbor", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load vendored Harbor rollout: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collector = getattr(module, "collect_cases", None)
    if not callable(collector):
        raise SystemExit("vendored Harbor rollout has no collect_cases helper")
    return collector


def _certified_artifact(workspace: Path, parent: str, row: dict[str, Any]) -> Path:
    reference = row.get("artifacts")
    if not isinstance(reference, dict):
        raise SystemExit(f"selected parent {parent} has no certified evaluation artifacts")
    relative = reference.get("path")
    expected = reference.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise SystemExit(f"selected parent {parent} has malformed evaluation artifacts")
    path = (workspace / relative).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as error:
        raise SystemExit("evaluation artifact path escapes workspace") from error
    if not path.is_file():
        raise SystemExit(f"evaluation artifact path is missing: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit("evaluation artifact digest mismatch")
    return path


class EvaluationReplayRollout(RolloutOperator):
    def rollout(self, checkout: Path, ctx: OperatorContext) -> RolloutResult:
        if ctx.parent is None:
            raise SystemExit("evaluation replay requires a selected parent")
        row = ArchiveView(ctx.workspace).row(ctx.parent)
        if row is None:
            raise SystemExit(f"selected parent {ctx.parent} is missing from archive")
        artifact = _certified_artifact(ctx.workspace, ctx.parent, row)
        jobs_dir = artifact.parent / "jobs"
        cases = _load_collect_cases(checkout)(
            jobs_dir,
            field_limit=int(ctx.config.get("field_limit", 2000)),
            pass_threshold=float(ctx.config.get("pass_threshold", 1.0)),
        )
        if not cases:
            raise SystemExit("evaluation replay produced no trial results")
        rollout_dir = ctx.run_dir / "rollout"
        rollout_dir.mkdir(parents=True, exist_ok=True)
        (rollout_dir / "cases.json").write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n")
        rewards = [float(case["reward"]) for case in cases if isinstance(case.get("reward"), (int, float))]
        tasks = {str(case["task_name"]) for case in cases}
        counts = {name: sum(case.get("outcome") == name for case in cases) for name in ("passed", "failed", "agent_error", "infra_error", "incomplete")}
        return RolloutResult(
            summary={
                "variant": "evaluation_replay",
                "source_parent": ctx.parent,
                "tasks_requested": len(tasks),
                "tasks_observed": len(tasks),
                "trials_observed": len(cases),
                "passed": counts["passed"],
                "failed": counts["failed"],
                "agent_errors": counts["agent_error"],
                "infra_errors": counts["infra_error"] + counts["incomplete"],
                "mean_observed_reward": round(sum(rewards) / len(rewards), 6) if rewards else None,
                "jobs_dir": str(jobs_dir),
            },
            artifacts=["rollout/cases.json", f"evaluation-artifacts:{artifact.relative_to(ctx.workspace)}"],
        )


if __name__ == "__main__":
    sdk.main(EvaluationReplayRollout)
```

- [ ] **Step 8: Run rollout and analyzer compatibility tests**

Run:

```bash
uv run pytest tests/test_evaluation_replay_rollout.py tests/test_m7_harbor_rollout.py tests/test_ahe_trace_analyzer.py tests/test_hyperagents_semantics.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit evaluation replay**

```bash
git add library/rollout/evaluation_replay.py library/rollout/harbor.py tests/test_evaluation_replay_rollout.py tests/test_m7_harbor_rollout.py
git commit -m "feat: replay parent evaluations as rollout evidence"
```

---

### Task 3: Bind the Real AHE and HyperAgents Recipes

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/hyperagents/README.md`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_recipe_inventory.py`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_m9_ahe_recipe.py`

**Interfaces:**
- Consumes: `task_scope: full`, `evaluation_split: train`, and rollout variant `evaluation_replay` from Tasks 1 and 2.
- Produces: production recipes whose initialized workspaces evaluate exactly 89 tasks with method-specific `k`, four workers, and ten evolved candidates.

- [ ] **Step 1: Replace old recipe assertions with the approved experiment contract**

In `tests/test_phase_e_recipes.py`, assert the following exact properties:

```python
if name == "ahe":
    assert "max_generations: 10" in config
    assert "dataset: terminal-bench@2.0" in config
    assert "rollout: {variant: evaluation_replay" in config
    assert "task_scope: full" in config
    assert "evaluation_split: train" in config
    assert "tasks_per_round: 89" in config
    assert "k: 2" in config
    assert "n_concurrent: 4" in config
    assert "split:" not in config
    assert "anchor:" not in config
elif name == "hyperagents":
    assert "max_generations: 10" in config
    assert "dataset: terminal-bench@2.0" in config
    assert "rollout: {variant: evaluation_replay" in config
    assert "task_scope: full" in config
    assert "evaluation_split: train" in config
    assert "tasks_per_round: 89" in config
    assert "k: 1" in config
    assert "n_concurrent: 4" in config
    assert "split:" not in config
    assert "anchor:" not in config
```

Keep the existing assertions for AHE latest-parent selection, AHE target-only
edits, HyperAgents `score_child_prop`, HyperAgents target-plus-operator edits,
the Harbor meta-agent runner, and `max_retries: 2`.

In `tests/test_m0_init.py` and `tests/test_m9_ahe_recipe.py`, replace active
`HarborRollout`/`source=library/rollout/harbor.py` expectations for AHE and
HyperAgents with `EvaluationReplayRollout` and
`source=library/rollout/evaluation_replay.py`. Also assert that initialized
workspaces contain `library/rollout/harbor.py`, because replay loads its public
collector from that protected vendored copy.

- [ ] **Step 2: Run recipe tests and verify they fail**

Run:

```bash
uv run pytest tests/test_phase_e_recipes.py tests/test_recipe_inventory.py tests/test_m0_init.py tests/test_m9_ahe_recipe.py -q
```

Expected: FAIL because the recipes still use SWE-bench Lite, partitioned tasks,
live Harbor rollouts, eight generations, and HyperAgents concurrency 16.

- [ ] **Step 3: Update the AHE recipe**

Set the relevant AHE fields to:

```yaml
experiment:
  id: ahe
  max_generations: 10
operators:
  rollout: {variant: evaluation_replay, field_limit: 2000, timeout_s: 600}
  trace_analyzer: {variant: ahe, max_tasks: 90, max_concurrent: 16, timeout_per_task: 600, retry_attempts: 3, field_limit: 2000, timeout_s: 3600}
  meta_agent: {variant: ahe, runner: harbor, agent: mini-swe-agent, model: openai/gpt-5.4, environment: docker, image: evolve-meta-agent-app:ubuntu-latest, editable_roots: [target], max_retries: 2, timeout_s: 3600}
evaluator:
  engine: harbor
  dataset: terminal-bench@2.0
  agent: evolve_harbor_adapter:MiniSweSourceAgent
  task_scope: full
  evaluation_split: train
  sampling: static
  tasks_per_round: 89
  k: 2
  n_concurrent: 4
```

Retain the approved MiniSWE limits, setup timeout multiplier, evaluator retry,
partial floor, AHE gate, and AHE record configuration. Remove `split` and
`anchor`.

- [ ] **Step 4: Update the HyperAgents recipe**

Set the relevant HyperAgents fields to:

```yaml
experiment:
  id: hyperagents
  max_generations: 10
operators:
  rollout: {variant: evaluation_replay, field_limit: 2000, timeout_s: 600}
  trace_analyzer: {variant: trace_browser, max_chars: 30000, timeout_s: 600}
  meta_agent: {variant: hyperagents, runner: harbor, agent: mini-swe-agent, model: openai/gpt-5.4, environment: docker, image: evolve-meta-agent-app:ubuntu-latest, editable_roots: [target, operators], max_retries: 2, timeout_s: 21600}
evaluator:
  engine: harbor
  dataset: terminal-bench@2.0
  agent: evolve_harbor_adapter:MiniSweSourceAgent
  task_scope: full
  evaluation_split: train
  sampling: static
  tasks_per_round: 89
  k: 1
  n_concurrent: 4
```

Retain `score_child_prop`, validation, parent-eligible gate, record operator,
surface rules, and partial floor. Remove `budget_usd`, `split`, and `anchor`.

- [ ] **Step 5: Update method READMEs**

In `recipes/ahe/README.md`, state that each certified full-benchmark evaluation
is replayed as the next AHE debugger input and is not rerun as a separate
rollout. In `recipes/hyperagents/README.md`, state that the selected parent's
certified evaluation is exposed to the trace browser before a child is produced
and immediately evaluated. Both READMEs must say that the 89-task learning curve
is an optimization result, not a held-out generalization result.

- [ ] **Step 6: Run recipe and initialization tests**

Run:

```bash
uv run pytest tests/test_phase_e_recipes.py tests/test_recipe_inventory.py tests/test_phase_f_init_binding.py tests/test_m0_init.py tests/test_m9_ahe_recipe.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit recipe binding**

```bash
git add recipes/ahe/evolve.yaml recipes/hyperagents/evolve.yaml recipes/ahe/README.md recipes/hyperagents/README.md tests/test_phase_e_recipes.py tests/test_recipe_inventory.py tests/test_m0_init.py tests/test_m9_ahe_recipe.py
git commit -m "feat: bind AHE and HyperAgents to full TB2 evaluation"
```

---

### Task 4: Local Verification and Official-Task Smoke on DevBoxS

**Files:**
- Verify: all files changed in Tasks 1-3
- Runtime artifacts: `/data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8`
- Runtime artifacts: `/data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-smoke4-2fd12b8`
- Runtime artifacts: `/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-official-smoke-20260720-v1`

**Interfaces:**
- Consumes: committed source from Tasks 1-3, the official local TB2 clone at `/private/tmp/terminal-bench-2`, the existing server-side credential file, the pre-pulled task images, and the validated MiniSWE seed from the previous readiness run.
- Produces: two complete generation-0-plus-two-child smoke workspaces with exact certified trial counts and no residual experiment processes or Docker resources.

- [ ] **Step 1: Run formatting, type, focused, and full tests locally**

Run:

```bash
uv run ruff check .
uv run ty check
uv run pytest -q
git diff --check
```

Expected: every command exits 0 and the full suite reports all tests passed.

- [ ] **Step 2: Commit any test-only corrections separately**

If Step 1 required test corrections, stage only those explicit paths and commit:

```bash
git add tests
git commit -m "test: cover full TB2 evaluation lifecycle"
```

Expected: no production behavior is bundled into this commit.

- [ ] **Step 3: Package the committed source and official dataset without Git metadata**

Run locally:

```bash
git archive --format=tar.gz -o /private/tmp/simple-evolve-agent-tb2-full.tar.gz HEAD
git -C /private/tmp/terminal-bench-2 archive --format=tar.gz -o /private/tmp/terminal-bench-2-2fd12b8.tar.gz HEAD
```

Expected: both archives exist and `git status --short` contains only the known,
intentional local changes, if any.

- [ ] **Step 4: Transfer and extract into new explicit server directories**

Run:

```bash
scp /private/tmp/simple-evolve-agent-tb2-full.tar.gz DevBoxS:/data00/home/zimuwang/simple-evolve-agent-4054173/
scp /private/tmp/terminal-bench-2-2fd12b8.tar.gz DevBoxS:/data00/home/zimuwang/simple-evolve-agent-4054173/datasets/
ssh DevBoxS 'set -e; test ! -e /data00/home/zimuwang/simple-evolve-agent-4054173/source-tb2-full; test ! -e /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8; mkdir -p /data00/home/zimuwang/simple-evolve-agent-4054173/source-tb2-full /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8; tar -xzf /data00/home/zimuwang/simple-evolve-agent-4054173/simple-evolve-agent-tb2-full.tar.gz -C /data00/home/zimuwang/simple-evolve-agent-4054173/source-tb2-full; tar -xzf /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8.tar.gz -C /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8'
```

Expected: source and dataset directories are new and extraction exits 0. Stop
instead of overwriting if either directory already contains files.

- [ ] **Step 5: Create the four-task smoke dataset without renaming tasks**

Run:

```bash
ssh DevBoxS 'set -e; test ! -e /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-smoke4-2fd12b8; mkdir -p /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-smoke4-2fd12b8; cp -a /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8/cancel-async-tasks /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8/largest-eigenval /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8/prove-plus-comm /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8/regex-log /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-smoke4-2fd12b8/'
```

Expected: exactly four immediate child directories contain `task.toml`, with
the original task names and no `-train` or `-gate` suffixes.

- [ ] **Step 6: Run the server preflight**

Verify without printing credentials:

```bash
ssh DevBoxS 'test "$(find /data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-2fd12b8 -mindepth 2 -maxdepth 2 -name task.toml | wc -l)" -eq 89 && test "$(docker image ls --format "{{.Repository}}:{{.Tag}}" | grep "^alexgshaw/.*:20251031$" | sort -u | wc -l)" -eq 89 && docker info >/dev/null && df -h /data00 && docker network ls --format "{{.Name}}" | wc -l'
```

Expected: task and image checks exit 0; Docker responds; disk and network counts
are recorded for the smoke report.

- [ ] **Step 7: Initialize fresh AHE and HyperAgents smoke workspaces**

On DevBoxS, source credentials with export enabled, set the immutable runtime
digest used by the validated readiness run, and initialize both workspaces from
the same prior MiniSWE target snapshot:

```bash
ssh DevBoxS 'bash -lc "set -a; . /data00/home/zimuwang/simple-evolve-agent-project/.env; set +a; export EVOLVE_RUNTIME_DIGEST=tb2-official-smoke-runtime-20260720; export EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv; source=/data00/home/zimuwang/simple-evolve-agent-4054173/source-tb2-full; root=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-official-smoke-20260720-v1; dataset=/data00/home/zimuwang/simple-evolve-agent-4054173/datasets/terminal-bench-2-smoke4-2fd12b8; seed=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-readiness-20260718-222022/ahe/target; test ! -e \"$root\"; mkdir -p \"$root\"; cd \"$source\"; uv run evolve init \"$root/ahe\" --recipe ahe --dataset \"$dataset\" --seed \"$seed\"; uv run evolve init \"$root/hyperagents\" --recipe hyperagents --dataset \"$dataset\" --seed \"$seed\""'
```

Expected: both workspaces contain generation-0 tags, unique experiment IDs,
four-task train cohorts, and no gate or sealed members.

- [ ] **Step 8: Confirm smoke-specific generation and task counts are committed**

Set `max_generations: 2` and `tasks_per_round: 4` in each smoke workspace,
preserving AHE `k=2`, HyperAgents `k=1`, and both `n_concurrent: 4`. Commit each
workspace configuration and recreate its `gen/0` tag at the new commit so cache
identity includes the smoke settings:

```bash
ssh DevBoxS 'for method in ahe hyperagents; do w=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-official-smoke-20260720-v1/$method; sed -i "s/max_generations: 10/max_generations: 2/; s/tasks_per_round: 89/tasks_per_round: 4/" "$w/evolve.yaml"; git -C "$w" add evolve.yaml; git -C "$w" commit -m "configure official TB2 smoke"; git -C "$w" tag -f gen/0; done'
```

Expected: both `gen/0` tags point at committed smoke configuration. This is a
mechanical runtime configuration edit, not a source-code implementation step.

- [ ] **Step 9: Launch both smokes concurrently with shared cache and persistent logs**

Run under separate process groups and record only PIDs, not secret-bearing
command lines:

```bash
ssh DevBoxS 'bash -lc "set -a; . /data00/home/zimuwang/simple-evolve-agent-project/.env; set +a; export EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv; export EVOLVE_UV_CACHE_DIR=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-smoke-fixes-20260718-170754/shared-uv-cache; root=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-official-smoke-20260720-v1; setsid \"$root/ahe/evolve\" run \"$root/ahe\" --max-generations 2 --verbose >\"$root/ahe/smoke.log\" 2>&1 & echo $! >\"$root/ahe/driver.pid\"; setsid \"$root/hyperagents/evolve\" run \"$root/hyperagents\" --max-generations 2 --verbose >\"$root/hyperagents/smoke.log\" 2>&1 & echo $! >\"$root/hyperagents/driver.pid\""'
```

Expected: two driver PIDs are recorded and no credentials are printed.

- [ ] **Step 10: Monitor conditionally until both drivers finish**

Poll at intervals shorter than 60 seconds using PID/status-only output. For each
method, inspect archive completion counts, `rollout/summary.json`, analyzer
summary, meta-agent artifacts, and candidate evaluations. Do not use `ps` output
that includes command arguments.

Expected final certified counts:

- AHE: three evaluated snapshots, eight trials per snapshot, 24 total trials.
- HyperAgents: three evaluated snapshots, four trials per snapshot, 12 total trials.
- Every generation-1 and generation-2 replay names the actual selected parent.

- [ ] **Step 11: Verify reports, lifecycle invariants, and cleanup**

Run:

```bash
ssh DevBoxS 'set -e; root=/data00/home/zimuwang/simple-evolve-agent-4054173/experiments/tb2-official-smoke-20260720-v1; for method in ahe hyperagents; do w="$root/$method"; EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv "$w/evolve" report "$w"; complete=$(EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv "$w/evolve" status "$w" | awk "\$1 == \"status.complete:\" {print \$2}"); test "$complete" -eq 3; done; test -z "$(docker ps --format "{{.Names}}" | grep -E "tb2-official-smoke-20260720-v1" || true)"'
```

Also confirm:

- AHE replayed each canonical evaluation into its debugger without a second task run.
- HyperAgents replayed the selected archive parent and immediately evaluated each child.
- In-progress generations never appeared as score 0.
- No smoke-owned processes, containers, or networks remain.

Expected: both reports list generation 2 as the latest completed generation;
all invariant checks pass regardless of whether scores improved.

- [ ] **Step 12: Record smoke evidence and commit final documentation corrections**

Add only durable findings—artifact root, exact task/image counts, trial counts,
and any corrected operational command—to the experiment design or recipe
READMEs. Then run:

```bash
git add docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md recipes/ahe/README.md recipes/hyperagents/README.md
git commit -m "docs: record official TB2 smoke evidence"
```

Expected: the commit contains documentation only. Do not commit generated
experiment artifacts or credentials.

---

## Final Verification Checklist

- [ ] `uv run ruff check .` passes.
- [ ] `uv run ty check` passes.
- [ ] `uv run pytest -q` passes.
- [ ] `git diff --check` passes.
- [ ] Full-mode task identity contains all selected task names and method-specific `k`.
- [ ] Replay verifies the selected parent's artifact digest and never selects merely the latest row.
- [ ] AHE performs one Harbor evaluation per snapshot and analyzes those same trajectories.
- [ ] HyperAgents performs one immediate Harbor evaluation per produced child.
- [ ] The four-task official smoke completes generation 0 plus generations 1 and 2 for both methods.
- [ ] DevBoxS reuses all pre-pulled task images and leaves no smoke-owned processes, containers, or networks.
