# Method-Faithful AHE Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder AHE recipe with a framework-native, method-faithful AHE loop that evaluates MiniSWE source through Harbor, analyzes task traces with MiniSWE-source debugger agents, attributes prior changes, and explicitly revises or rolls them back.

**Architecture:** Keep the frozen driver neutral and use the existing `select -> rollout -> meta_agent -> evaluate -> gate -> record` lifecycle as a staggered AHE loop. Add only generic YAML, operator-asset, task-vector, and evaluation-artifact plumbing to the framework; put all AHE selection, analysis, attribution, prompting, manifest, rollback, gate, and record policy in explicitly named `library/` variants.

**Tech Stack:** Python 3.11+, PyYAML 6+, pytest, Typer, git worktrees, Harbor, Docker, MiniSWE Agent Python source API, JSON/JSONL artifacts, shell evaluator templates.

## Global Constraints

- The framework recognizes exactly five top-level YAML sections: `experiment`, `target`, `surface`, `operators`, and `evaluator`.
- Nested YAML beneath those sections is unrestricted and must round-trip without loss; unknown top-level sections fail clearly.
- The mechanism interprets only universal operator keys such as `variant`, `script`, and `timeout_s`; every other operator value reaches `OperatorContext.config` unchanged.
- AHE policy must not be added to `src/evolve/driver.py`, `src/evolve/evaluator.py`, or another frozen mechanism path.
- The evolved target, debugger, and evolution agent use MiniSWE's Python source API, never the `mini` CLI.
- `target/harbor_agent.py`, evaluator files, Harbor/Docker config, `.env`, model config, and proxy config are outside the mutable surface.
- Harbor training evaluation uses SWE-bench Pro, 30 fixed training tasks, `k=2`, and `n_concurrent=5`.
- Debugger analysis uses at most five concurrent MiniSWE-source workers and runs after Harbor evaluation.
- Analyze all failures, regressions, agent timeouts, and predicted-risk tasks plus three deterministic rotating successful controls.
- The 30-task sealed test list is never copied into an evolution workspace or exposed to debugger/evolution prompts.
- Download/setup paths may use proxy variables; LLM calls must remove all upper- and lower-case HTTP(S)/ALL proxy variables.
- Preserve all unrelated dirty-worktree changes. Each commit stages only the files named in its task.
- The existing hillclimb process and artifacts on DevBoxS remain untouched.

---

## File Map

### Generic framework changes

- `pyproject.toml`: add the PyYAML runtime dependency.
- `src/evolve/config.py`: load, validate, expose, and render the five-section YAML document with PyYAML.
- `src/evolve/workspace.py`: bootstrap PyYAML; vendor recursive operator assets and recipe evaluator assets safely; export Harbor attempt count.
- `src/evolve/task_vectors.py`: versioned task-vector validation, legacy normalization, and generic pass lookup.
- `src/evolve/evaluator.py`: read task vectors and return a compact artifact-index reference.
- `src/evolve/archive.py`: integrity-stamp the compact evaluation-artifact reference.
- `src/evolve/driver.py`: stamp the generic artifact reference and remove method-level verified-fix attribution.
- `src/evolve/agent.py`: support caller-provided environment overrides without knowing AHE keys.
- `templates/evaluator/engines/harbor.sh`: pass recipe-configured `k` to Harbor `--n-attempts`.
- `templates/evaluator/harbor_artifacts.py`: convert Harbor result directories into the versioned task vector and safe artifact index.
- `templates/evaluator/parse_score.py`: use the artifact collector and write generic evaluator outputs.
- `templates/evaluator/stub_eval.py`: emit the versioned task-vector schema.

### AHE method files

- `library/ahe_support.py`: AHE task states, comparisons, selection, attribution, hashing, and manifest validation.
- `library/select/ahe_latest.py`: newest-valid sequential parent selection.
- `library/rollout/ahe_trace_analysis.py`: debugger task selection, parallel MiniSWE analysis, overview, and attribution.
- `library/rollout/prompts/ahe_debugger.md`: per-task debugger prompt adapted from open AHE materials.
- `library/rollout/prompts/ahe_debugger_overview.md`: cross-task aggregation prompt.
- `library/meta_agent/ahe_evidence_editor.py`: evidence-driven source editing and manifest enforcement.
- `library/meta_agent/prompts/ahe_evolve.md`: AHE evolution prompt adapted from the official repository.
- `library/gate/ahe_artifact_valid.py`: structural/evaluation validity gate without score comparison.
- `library/record/ahe_manifest.py`: compact AHE archive annotation.
- `tools/miniswe_source_agent_command.py`: reusable source-API command for debugger and evolution roles.

### Recipe, protocol, and tests

- `recipes/ahe/evolve.yaml`, `recipes/ahe/README.md`, `recipes/ahe/notes.md`: real AHE composition and documentation.
- `recipes/ahe/evaluator/tasks/train-30.txt`: fixed training task list copied from the validated DevBoxS split.
- `recipes/ahe-smoke/evolve.yaml`, `recipes/ahe-smoke/README.md`: deterministic AHE smoke composition.
- `library/PROTOCOL.md`, `library/README.md`, `recipes/README.md`, `README.md`: document named research variants, generic artifacts, and AHE semantics.
- `tests/test_config_parser.py`, `tests/test_phase_f_init_binding.py`, `tests/test_harbor_evaluator_template.py`, `tests/test_m1_evaluator_invariants.py`: extend existing contracts.
- `tests/test_task_vectors.py`, `tests/test_harbor_artifacts.py`, `tests/test_miniswe_source_agent_command.py`, `tests/test_ahe_support.py`, `tests/test_ahe_rollout.py`, `tests/test_ahe_meta_agent.py`, `tests/test_ahe_gate_record.py`, `tests/test_ahe_integration.py`: focused new coverage.

---

### Task 0: Preserve the current verified Harbor/MiniSWE baseline on a feature branch

**Files:**
- Existing modified baseline files only; no AHE implementation files are created in this task.

**Interfaces:**
- Produces branch: `codex/method-faithful-ahe`
- Produces a clean, tested baseline commit containing the current Harbor evaluator, MiniSWE source wrapper, forced-eval, config-parser, and archive fixes already used by the active hillclimb experiment.

- [ ] **Step 1: Create the feature branch without discarding dirty changes**

```bash
git switch -c codex/method-faithful-ahe
```

Expected: all current modifications remain present on the new branch.

- [ ] **Step 2: Review the exact baseline diff and verify no secret material is present**

```bash
git status --short
git diff --check
rg -n "OPENAI_API_KEY=|sk-[A-Za-z0-9]|sys-proxy-rd-relay" \
  library/meta_agent/agent_command.py \
  src/evolve/archive.py src/evolve/cli.py src/evolve/config.py src/evolve/driver.py \
  src/evolve/frozen/meta_eval.py src/evolve/workspace.py \
  templates/evaluator/engines/harbor.sh templates/target/harbor/miniswe_source_agent.py \
  templates/workspace/operators/meta_agent.md tests/test_config_parser.py
```

Expected: no key literal or proxy endpoint; variable names alone are acceptable.

- [ ] **Step 3: Run the complete baseline test suite**

```bash
uv run pytest -q
```

Expected: the existing suite passes before AHE implementation starts.

- [ ] **Step 4: Stage only the known baseline files**

```bash
git add \
  library/meta_agent/agent_command.py \
  src/evolve/archive.py src/evolve/cli.py src/evolve/config.py src/evolve/driver.py \
  src/evolve/frozen/meta_eval.py src/evolve/workspace.py \
  templates/evaluator/engines/harbor.sh templates/target/harbor/miniswe_source_agent.py \
  templates/workspace/operators/meta_agent.md \
  tests/test_agent_command_meta_agent.py tests/test_config_parser.py \
  tests/test_harbor_evaluator_template.py tests/test_m0_init.py \
  tests/test_m1_evaluator_invariants.py tests/test_m3_meta_eval.py \
  tests/test_m5_record_verb.py tests/test_miniswe_harbor_wrapper.py
git diff --cached --check
```

Expected: the staged set contains only the previously verified Harbor/MiniSWE baseline.

- [ ] **Step 5: Commit the baseline separately**

```bash
git commit -m "Preserve Harbor MiniSWE experiment fixes"
```

This commit is intentionally separate from every method-faithful AHE change.

---

### Task 1: Replace the YAML subset parser with a five-section structured contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/evolve/config.py`
- Modify: `src/evolve/workspace.py:70-90`
- Modify: `tests/test_config_parser.py`
- Modify: `tests/test_m0_init.py`

**Interfaces:**
- Produces: `load_config(config: Resource) -> dict[str, Any]`
- Produces: `render_yaml(value: dict[str, Any]) -> str`
- Preserves: `operator_blocks(workspace)`, `evaluator_values(workspace)`, `surface_lists(workspace)`, and `default_config(recipe, experiment_id)` signatures.

- [ ] **Step 1: Extend the config tests with unrestricted nesting and top-level validation**

Add these tests without deleting the existing nested meta-agent test:

```python
import pytest

from evolve.config import CONFIG_SECTIONS, operator_blocks, render_yaml


def test_operator_blocks_preserve_arbitrary_nested_yaml(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target: {}\n"
        "surface: {include: [target/**], exclude: []}\n"
        "operators:\n"
        "  rollout:\n"
        "    variant: ahe_trace_analysis\n"
        "    controls:\n"
        "      successful: 3\n"
        "      labels: [stable, 'contains: colon']\n"
        "    analyze:\n"
        "      failures: true\n"
        "      thresholds: {partial: 0.5, retry: null}\n"
        "evaluator: {}\n"
    )

    assert operator_blocks(workspace)["rollout"] == {
        "variant": "ahe_trace_analysis",
        "controls": {"successful": 3, "labels": ["stable", "contains: colon"]},
        "analyze": {"failures": True, "thresholds": {"partial": 0.5, "retry": None}},
    }


def test_render_yaml_round_trips_all_five_sections() -> None:
    config = {section: {} for section in CONFIG_SECTIONS}
    config["operators"] = {"rollout": {"custom": {"list": [1, "two"], "flag": True}}}
    rendered = render_yaml(config)
    assert "custom:" in rendered
    assert "- two" in rendered


def test_unknown_top_level_section_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text("experiment: {}\nahe: {}\n")
    with pytest.raises(ValueError, match="unknown top-level config sections: ahe"):
        operator_blocks(workspace)
```

- [ ] **Step 2: Run the focused tests and verify the handwritten parser fails**

Run:

```bash
uv run pytest tests/test_config_parser.py -v
```

Expected: the arbitrary nested test and unknown-section test fail against `_read_section_file`.

- [ ] **Step 3: Add PyYAML and implement one validated document loader**

Add `"PyYAML>=6.0"` to `[project].dependencies`. Replace the handwritten scalar/list/mapping parser in `src/evolve/config.py` with:

```python
import yaml


def load_config(config: Resource) -> dict[str, Any]:
    if not config.is_file():
        return {section: {} for section in CONFIG_SECTIONS}
    loaded = yaml.safe_load(config.read_text())
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError("config document must be a mapping")
    unknown = sorted(str(key) for key in loaded if key not in CONFIG_SECTIONS)
    if unknown:
        raise ValueError("unknown top-level config sections: %s" % ", ".join(unknown))
    result: dict[str, Any] = {}
    for section in CONFIG_SECTIONS:
        value = loaded.get(section, {})
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValueError(f"{section} section must be a mapping")
        result[section] = value
    return result


def _read_config_file(config: Resource) -> dict[str, Any]:
    return load_config(config)


def _read_section_file(config: Resource, name: str) -> dict[str, Any]:
    return dict(load_config(config)[name])


def render_yaml(value: dict[str, Any]) -> str:
    validated = {section: value.get(section, {}) for section in CONFIG_SECTIONS}
    return yaml.safe_dump(validated, sort_keys=False, allow_unicode=False)
```

Delete `_parse_value`, `_parse_inline_mapping`, `_parse_inline_list`, `_coerce_scalar`, `_render_mapping`, `_is_inline_mapping`, `_format_inline_mapping`, and `_format_scalar` after callers are migrated.

- [ ] **Step 4: Update the self-contained workspace console dependency bootstrap**

Change `_CONSOLE` to install both runtime dependencies:

```bash
exec uv run --quiet --with "typer>=0.12" --with "PyYAML>=6.0" --python ">=3.11" python -m evolve "$@"
```

Update the fallback error to require `typer` and `PyYAML` when using a system Python.

- [ ] **Step 5: Run config and initialization tests**

Run:

```bash
uv run pytest tests/test_config_parser.py tests/test_m0_init.py tests/test_phase_e_recipes.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit only the YAML contract changes**

```bash
git add pyproject.toml uv.lock src/evolve/config.py src/evolve/workspace.py tests/test_config_parser.py tests/test_m0_init.py
git commit -m "Add extensible five-section YAML config"
```

---

### Task 2: Vendor operator prompts and recipe evaluator assets generically

**Files:**
- Modify: `src/evolve/workspace.py:37-42,163-219`
- Modify: `tests/test_phase_f_init_binding.py`
- Modify: `tests/test_phase_e_recipes.py`

**Interfaces:**
- Produces: `_operator_assets(recipe: str) -> dict[str, str]`
- Produces: `_recipe_evaluator_assets(recipe: str) -> dict[str, str]`
- Requires: selected operator prompts resolve beneath `workspace/library/{kind}/`.

- [ ] **Step 1: Write failing tests for recursive prompt and recipe-task vendoring**

Add:

```python
def test_operator_assets_vendor_nested_prompt_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    library = tmp_path / "library"
    (library / "meta_agent" / "prompts").mkdir(parents=True)
    (library / "meta_agent" / "prompts" / "ahe.md").write_text("AHE prompt\n")
    monkeypatch.setattr(workspace_module, "library_root", lambda: library)

    assets = workspace_module._operator_assets("ahe")

    assert assets == {"library/meta_agent/prompts/ahe.md": "AHE prompt\n"}


def test_recipe_evaluator_assets_copy_training_but_not_sealed_files(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    recipes = tmp_path / "recipes"
    (recipes / "ahe" / "evaluator" / "tasks").mkdir(parents=True)
    (recipes / "ahe" / "evaluator" / "tasks" / "train-30.txt").write_text("task-a\n")
    (recipes / "ahe" / "sealed").mkdir()
    (recipes / "ahe" / "sealed" / "test-30.txt").write_text("secret-task\n")
    monkeypatch.setattr(workspace_module, "recipe_root", lambda: recipes)

    assert workspace_module._recipe_evaluator_assets("ahe") == {
        "evaluator/tasks/train-30.txt": "task-a\n"
    }
```

- [ ] **Step 2: Run the tests and verify the helpers do not exist**

Run:

```bash
uv run pytest tests/test_phase_f_init_binding.py -v
```

Expected: FAIL with missing `_operator_assets` and `_recipe_evaluator_assets`.

- [ ] **Step 3: Implement recursive, text-only, non-hidden asset collection**

Add a Traversable-safe walker and collectors:

```python
def _walk_files(root, prefix: Path = Path("")):
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        relative = prefix / item.name
        if any(part.startswith(".") for part in relative.parts):
            continue
        if isinstance(item, Path) and item.is_symlink():
            raise ValueError(f"operator asset may not be a symlink: {item}")
        if item.is_dir():
            yield from _walk_files(item, relative)
        elif item.is_file():
            yield relative, item


def _operator_assets(recipe: str) -> dict[str, str]:
    assets: dict[str, str] = {}
    for kind in OPERATOR_KINDS:
        for directory in (recipe_root() / recipe / "operators" / kind, library_root() / kind):
            if not directory.is_dir():
                continue
            for relative, source in _walk_files(directory):
                if relative.suffix == ".py":
                    continue
                assets.setdefault(f"library/{kind}/{relative.as_posix()}", source.read_text())
    for relative, source in _walk_files(library_root()):
        if len(relative.parts) == 1 and relative.suffix == ".py" and not relative.name.startswith("_"):
            assets.setdefault(f"library/{relative.as_posix()}", source.read_text())
    return assets


def _recipe_evaluator_assets(recipe: str) -> dict[str, str]:
    root = recipe_root() / recipe / "evaluator"
    if not root.is_dir():
        return {}
    return {f"evaluator/{rel.as_posix()}": source.read_text() for rel, source in _walk_files(root)}
```

Merge both dictionaries into `files` after operator bindings. Do not recurse into `recipes/{recipe}/sealed/`.

- [ ] **Step 4: Run binding and recipe tests**

Run:

```bash
uv run pytest tests/test_phase_f_init_binding.py tests/test_phase_e_recipes.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit asset vendoring**

```bash
git add src/evolve/workspace.py tests/test_phase_f_init_binding.py tests/test_phase_e_recipes.py
git commit -m "Vendor operator and recipe assets"
```

---

### Task 3: Introduce the versioned task-vector contract and move falsification out of the driver

**Files:**
- Create: `src/evolve/task_vectors.py`
- Modify: `templates/evaluator/stub_eval.py`
- Modify: `src/evolve/driver.py:265-268,327-339`
- Modify: `library/record/jsonl.py`
- Create: `tests/test_task_vectors.py`
- Modify: `tests/test_m5_driver_operators.py`

**Interfaces:**
- Produces: `normalize_task_vector(payload: object) -> dict[str, Any]`
- Produces: `validate_task_vector(payload: object) -> dict[str, Any]`
- Produces: `task_passed(payload: object, task_id: str) -> bool | None`
- Preserves: legacy `{"task": true}` archive reads.

- [ ] **Step 1: Write failing versioned and legacy task-vector tests**

Create `tests/test_task_vectors.py`:

```python
import pytest

from evolve.task_vectors import TaskVectorError, normalize_task_vector, task_passed


def test_normalize_legacy_boolean_vector() -> None:
    assert normalize_task_vector({"task-a": True, "task-b": False}) == {
        "schema_version": 1,
        "tasks": {
            "task-a": {"trials": [{"trial": 0, "status": "complete", "reward": 1.0}]},
            "task-b": {"trials": [{"trial": 0, "status": "complete", "reward": 0.0}]},
        },
    }


def test_versioned_vector_preserves_partial_and_infra_trials() -> None:
    vector = {
        "schema_version": 1,
        "tasks": {
            "task-a": {"trials": [
                {"trial": 0, "status": "complete", "reward": 1.0},
                {"trial": 1, "status": "infra_failed", "reward": None, "exception_type": "VerifierTimeoutError"},
            ]}
        },
    }
    assert normalize_task_vector(vector) == vector
    assert task_passed(vector, "task-a") is None


def test_invalid_task_vector_rejects_duplicate_trial_numbers() -> None:
    with pytest.raises(TaskVectorError, match="duplicate trial 0"):
        normalize_task_vector({
            "schema_version": 1,
            "tasks": {"task-a": {"trials": [
                {"trial": 0, "status": "complete", "reward": 1.0},
                {"trial": 0, "status": "complete", "reward": 0.0},
            ]}},
        })
```

- [ ] **Step 2: Run the test and verify the module is missing**

```bash
uv run pytest tests/test_task_vectors.py -v
```

Expected: collection fails because `evolve.task_vectors` does not exist.

- [ ] **Step 3: Implement strict normalization and validation**

Create `src/evolve/task_vectors.py` with:

```python
from __future__ import annotations

from typing import Any

TRIAL_STATUSES = {"complete", "agent_timeout", "infra_failed", "cancelled"}


class TaskVectorError(ValueError):
    pass


def normalize_task_vector(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TaskVectorError("task vector must be an object")
    if "schema_version" not in payload:
        if not all(isinstance(key, str) and isinstance(value, bool) for key, value in payload.items()):
            raise TaskVectorError("legacy task vector must map strings to booleans")
        return {
            "schema_version": 1,
            "tasks": {
                key: {"trials": [{"trial": 0, "status": "complete", "reward": 1.0 if value else 0.0}]}
                for key, value in sorted(payload.items())
            },
        }
    if payload.get("schema_version") != 1 or not isinstance(payload.get("tasks"), dict):
        raise TaskVectorError("unsupported task vector schema")
    tasks: dict[str, Any] = {}
    for task_id, task in sorted(payload["tasks"].items()):
        if not isinstance(task_id, str) or not isinstance(task, dict) or not isinstance(task.get("trials"), list):
            raise TaskVectorError(f"invalid task entry: {task_id}")
        seen: set[int] = set()
        trials = []
        for raw in task["trials"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("trial"), int):
                raise TaskVectorError(f"invalid trial for {task_id}")
            trial = int(raw["trial"])
            if trial in seen:
                raise TaskVectorError(f"duplicate trial {trial} for {task_id}")
            seen.add(trial)
            status = raw.get("status")
            reward = raw.get("reward")
            if status not in TRIAL_STATUSES:
                raise TaskVectorError(f"invalid status {status!r} for {task_id}")
            if reward is not None and (isinstance(reward, bool) or not isinstance(reward, (int, float))):
                raise TaskVectorError(f"invalid reward for {task_id} trial {trial}")
            trials.append(dict(raw))
        tasks[task_id] = {**task, "trials": sorted(trials, key=lambda item: item["trial"])}
    return {"schema_version": 1, "tasks": tasks}


def validate_task_vector(payload: object) -> dict[str, Any]:
    return normalize_task_vector(payload)


def task_passed(payload: object, task_id: str) -> bool | None:
    task = normalize_task_vector(payload)["tasks"].get(task_id)
    if not task:
        return None
    trials = task["trials"]
    if not trials or any(item["status"] != "complete" or item.get("reward") is None for item in trials):
        return None
    return all(float(item["reward"]) > 0 for item in trials)
```

- [ ] **Step 4: Update the stub evaluator to emit schema version 1**

Replace the boolean writer with `k` completed trials per task while retaining the same aggregate score. Parse `EVOLVE_HARBOR_ATTEMPTS` from `evaluator/eval.env`, defaulting to 1:

```python
def _attempts() -> int:
    for line in Path("evaluator/eval.env").read_text().splitlines():
        if line.startswith("EVOLVE_HARBOR_ATTEMPTS="):
            return max(1, int(line.split("=", 1)[1]))
    return 1


task_results = {f"task-{i}": (f"task-{i}" not in failed) for i in range(K)}
task_vector = {
    "schema_version": 1,
    "tasks": {
        task_id: {
            "trials": [
                {"trial": trial, "status": "complete", "reward": 1.0 if passed else 0.0}
                for trial in range(_attempts())
            ]
        }
        for task_id, passed in task_results.items()
    },
}
passed = sum(task_results.values())
```

- [ ] **Step 5: Move `verified_fixes` computation from the driver to `jsonl` record policy**

Delete `_verified_fixes` and its call from `src/evolve/driver.py`. In `library/record/jsonl.py`, import `ArchiveView` and `task_passed`, then add:

```python
def _verified_fixes(child: Row, ctx: OperatorContext) -> list[str] | None:
    parent = ArchiveView(ctx.workspace).row(str(child.get("parent"))) if child.get("parent") is not None else None
    predicted = child.get("predicted_fixes") or json.loads(
        (ctx.run_dir / "meta_agent" / "predicted_fixes.json").read_text()
    )
    if parent is None or not predicted or child.get("task_vector") is None or parent.get("task_vector") is None:
        return None
    return [
        task_id for task_id in predicted
        if task_passed(parent["task_vector"], task_id) is False
        and task_passed(child["task_vector"], task_id) is True
    ]
```

Include `verified_fixes` in record fields only when the helper returns a list. This preserves existing behavior while removing method policy from the mechanism.

- [ ] **Step 6: Run task-vector and driver tests**

```bash
uv run pytest tests/test_task_vectors.py tests/test_m5_driver_operators.py tests/test_m7_verify.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit the task-vector contract**

```bash
git add src/evolve/task_vectors.py src/evolve/driver.py library/record/jsonl.py templates/evaluator/stub_eval.py tests/test_task_vectors.py tests/test_m5_driver_operators.py
git commit -m "Add versioned task vector contract"
```

---

### Task 4: Make Harbor `k` real and emit generic task/artifact evidence

**Files:**
- Create: `templates/evaluator/harbor_artifacts.py`
- Modify: `templates/evaluator/parse_score.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `src/evolve/workspace.py:115-155,433-456`
- Modify: `src/evolve/evaluator.py`
- Modify: `src/evolve/archive.py:10-27`
- Modify: `src/evolve/driver.py:639-676,705-740`
- Create: `tests/test_harbor_artifacts.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Produces evaluator file: `task_vector.json`
- Produces evaluator file: `evaluation_artifacts.json`
- Produces archive field: `evaluation_artifacts: {path: str, sha256: str}`
- Produces env: `EVOLVE_HARBOR_ATTEMPTS` set to the configured evaluator `k`.

- [ ] **Step 1: Write a fake Harbor job test with two attempts and a verifier timeout**

Create `tests/test_harbor_artifacts.py` using helper-written trial `result.json` files. Assert:

```python
def write_trial(
    path: Path,
    *,
    task: str,
    trial: str,
    reward: float | None,
    exception_type: str | None = None,
) -> None:
    path.mkdir(parents=True)
    payload = {
        "task_name": task,
        "trial_name": trial,
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": (
            {"exception_type": exception_type, "exception_message": "fixture failure"}
            if exception_type else None
        ),
    }
    (path / "result.json").write_text(json.dumps(payload))


def test_collect_harbor_artifacts_groups_trials_and_classifies_infra(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    write_trial(jobs / "task-a__one", task="task-a", trial="one", reward=1.0)
    write_trial(jobs / "task-a__two", task="task-a", trial="two", reward=0.0)
    write_trial(
        jobs / "task-b__one",
        task="task-b",
        trial="one",
        reward=None,
        exception_type="VerifierTimeoutError",
    )

    vector, artifacts, scoring_rewards = collect_harbor_artifacts(jobs)

    assert [trial["reward"] for trial in vector["tasks"]["task-a"]["trials"]] == [1.0, 0.0]
    assert vector["tasks"]["task-b"]["trials"][0]["status"] == "infra_failed"
    assert scoring_rewards == [1.0, 0.0]
    assert artifacts["jobs_dir"] == str(jobs.resolve())
    assert "config" not in json.dumps(artifacts).lower()
```

Also test `AgentTimeoutError` becomes `status: agent_timeout`, `reward: 0.0`, and is included in scoring rewards.

- [ ] **Step 2: Extend the evaluator shell test to require `--n-attempts 2`**

Call `_eval_env("experiment", "swebenchpro@1.0", n_concurrent=5, tasks_per_round=2, trials=2, partial_floor=0.8, agent="mini-swe-agent", dataset_mode="registry")` and assert:

```python
assert args[args.index("--n-attempts") + 1] == "2"
```

- [ ] **Step 3: Run the focused tests and verify failure**

```bash
uv run pytest tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py -v
```

Expected: collector import fails and Harbor still reports `--n-attempts 1`.

- [ ] **Step 4: Implement the standalone Harbor artifact collector**

Create `templates/evaluator/harbor_artifacts.py` with these public signatures and complete bodies that perform the traversal and serialization described immediately below:

```python
def collect_harbor_artifacts(
    jobs_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[float]]:
    trials = _load_task_trials(jobs_dir)
    return _build_task_vector(trials), _build_artifact_index(jobs_dir, trials), _scoring_rewards(trials)


def write_harbor_artifacts(jobs_dir: Path, run_dir: Path) -> list[float]:
    task_vector, artifact_index, rewards = collect_harbor_artifacts(jobs_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task_vector.json").write_text(json.dumps(task_vector, indent=2, sort_keys=True) + "\n")
    (run_dir / "evaluation_artifacts.json").write_text(
        json.dumps(artifact_index, indent=2, sort_keys=True) + "\n"
    )
    return rewards
```

Define the private helpers in the same module with these exact signatures:

- `_load_task_trials(jobs_dir: Path) -> list[dict[str, Any]]`
- `_build_task_vector(trials: list[dict[str, Any]]) -> dict[str, Any]`
- `_build_artifact_index(jobs_dir: Path, trials: list[dict[str, Any]]) -> dict[str, Any]`
- `_scoring_rewards(trials: list[dict[str, Any]]) -> list[float]`

`_load_task_trials` returns normalized dictionaries containing `task_name`, `trial_name`, `status`, `reward`, `exception_type`, `exception_message`, `trial_dir`, and safe artifact metadata. The other three helpers are pure projections of that normalized list.

Implementation requirements:

```python
SAFE_ARTIFACTS = (
    "agent/mini-swe-agent.trajectory.json",
    "agent/mini-swe-agent.txt",
    "agent/trajectory.json",
    "trial.log",
    "verifier/reward.txt",
    "verifier/test-stdout.txt",
    "result.json",
    "exception.txt",
)

def _trial_status(result: dict[str, Any], reward: float | None) -> tuple[str, float | None]:
    if reward is not None:
        return "complete", reward
    exception_type = str((result.get("exception_info") or {}).get("exception_type") or "")
    if exception_type in {"AgentTimeoutError", "AgentExecutionTimeoutError"}:
        return "agent_timeout", 0.0
    return "infra_failed", None
```

Walk only directories whose `result.json` contains string `task_name` and `trial_name`; ignore the job-level result. Group by full `task_name`, sort by `trial_name`, assign zero-based trial indices, and include `exception_type`/`exception_message` without traceback text. The artifact index contains only relative safe-file paths, byte sizes, SHA-256 hashes, trial names, task names, and the absolute `jobs_dir`; never serialize Harbor `config` or environment data.

- [ ] **Step 5: Make score parsing write both generic artifacts**

In `parse_score.py`, import `write_harbor_artifacts`, replace recursive reward discovery with:

```python
rewards = write_harbor_artifacts(jobs_dir, run_dir)
completed_trials = len(rewards)
```

Preserve the existing partial-floor and exit-code behavior.

- [ ] **Step 6: Propagate configured attempts to Harbor**

In `_eval_env`, add:

```python
f"EVOLVE_HARBOR_ATTEMPTS={max(trials, 1)}\n"
```

In `harbor.sh`, replace the hard-coded attempt count with:

```bash
set -- "$@" --jobs-dir "$jobs_dir" --n-attempts "${EVOLVE_HARBOR_ATTEMPTS:-1}" -n "${EVOLVE_HARBOR_N_CONCURRENT:-$EVOLVE_HARBOR_N}" -y -q
```

Copy `templates/evaluator/harbor_artifacts.py` into generated workspaces beside `parse_score.py`.

- [ ] **Step 7: Stamp the compact artifact reference**

Extend `EvaluationResult` with:

```python
evaluation_artifacts: dict[str, str] | None = None
```

After evaluator execution, validate `task_vector.json` with `validate_task_vector`. If `evaluation_artifacts.json` exists, compute:

```python
evaluation_artifacts = {
    "path": (run_dir / "evaluation_artifacts.json").relative_to(workspace).as_posix(),
    "sha256": _sha256_file(run_dir / "evaluation_artifacts.json"),
}
```

Add `evaluation_artifacts` to `STAMPED_FIELDS`, `_stamp_evaluation`, and per-round re-evaluation events. Add integrity tests showing a hand-edited artifact hash cannot replace a mechanism stamp.

- [ ] **Step 8: Run focused and invariant tests**

```bash
uv run pytest tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py tests/test_m1_evaluator_invariants.py tests/test_m7_verify.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit Harbor evidence support**

```bash
git add templates/evaluator/harbor_artifacts.py templates/evaluator/parse_score.py templates/evaluator/engines/harbor.sh src/evolve/workspace.py src/evolve/evaluator.py src/evolve/archive.py src/evolve/driver.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py tests/test_m1_evaluator_invariants.py
git commit -m "Preserve Harbor task and trace evidence"
```

---

### Task 5: Add a reusable source-only MiniSWE command and proxy-safe command environment

**Files:**
- Create: `tools/miniswe_source_agent_command.py`
- Modify: `src/evolve/agent.py`
- Modify: `tests/test_agent_runner.py`
- Create: `tests/test_miniswe_source_agent_command.py`

**Interfaces:**
- Changes: `run_meta_agent(workspace: Path | str, prompt: str, config: dict[str, Any] | None = None, *, env_overrides: dict[str, str | None] | None = None) -> AgentRunResult`
- Produces command contract: reads `EVOLVE_PROMPT_FILE`; writes trajectory to `EVOLVE_SOURCE_AGENT_OUTPUT_PATH` when set.

- [ ] **Step 1: Write an agent-runner test for caller-owned environment removal**

Add a child script that prints whether proxy variables exist, then call:

```python
result = run_meta_agent(
    workspace=tmp_path,
    prompt="inspect env",
    config={"command": f"{sys.executable} {script}"},
    env_overrides={"http_proxy": None, "HTTPS_PROXY": None, "ROLE": "debugger"},
)
assert "http_proxy=False" in result.stdout
assert "HTTPS_PROXY=False" in result.stdout
assert "ROLE=debugger" in result.stdout
```

- [ ] **Step 2: Run the test and verify the signature fails**

```bash
uv run pytest tests/test_agent_runner.py -v
```

Expected: FAIL because `env_overrides` is not accepted.

- [ ] **Step 3: Implement generic environment overrides**

Add the keyword-only parameter `env_overrides: dict[str, str | None] | None = None` after `config` in the existing signature. Immediately after the existing prompt-file creation, replace the environment assignment with:

```python
env = {**os.environ, "EVOLVE_PROMPT_FILE": prompt_file}
for key, value in (env_overrides or {}).items():
    if value is None:
        env.pop(key, None)
        else:
            env[key] = value
```

The helper remains generic; AHE operators decide which keys to remove.

- [ ] **Step 4: Add the proven MiniSWE source wrapper as a repository tool**

Port `/data00/home/zimuwang/simple-evolve-agent-project/tools/miniswe_source_meta_agent.py` into `tools/miniswe_source_agent_command.py`. Retain source imports:

```python
from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.config import get_config_from_spec
from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig
```

Add role/output support:

```python
role = os.environ.get("EVOLVE_SOURCE_AGENT_ROLE", "evolution")
output_path = Path(os.environ.get(
    "EVOLVE_SOURCE_AGENT_OUTPUT_PATH",
    str(Path.cwd() / "runs" / f"miniswe-source-{role}.trajectory.json"),
))
output_path.parent.mkdir(parents=True, exist_ok=True)
```

Remove all proxy variants before importing or calling MiniSWE:

```python
PROXY_ENV = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")
for name in PROXY_ENV:
    os.environ.pop(name, None)
```

Do not print API keys, base URLs containing credentials, or environment dumps. Keep `--check` source-import validation.

- [ ] **Step 5: Test the wrapper with fake MiniSWE modules**

Mirror the fake-module pattern in `tests/test_miniswe_harbor_wrapper.py`. Assert `DefaultAgent.run()` receives the prompt, `LocalEnvironmentConfig.cwd` is `Path.cwd()`, the role-specific trajectory path is used, and proxy variables are absent before the fake model is constructed.

- [ ] **Step 6: Run focused tests**

```bash
uv run pytest tests/test_agent_runner.py tests/test_miniswe_source_agent_command.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit source-only command support**

```bash
git add src/evolve/agent.py tools/miniswe_source_agent_command.py tests/test_agent_runner.py tests/test_miniswe_source_agent_command.py
git commit -m "Add proxy-safe MiniSWE source command"
```

---

### Task 6: Implement AHE task states, attribution, manifest validation, and sequential selection

**Files:**
- Create: `library/ahe_support.py`
- Create: `library/select/ahe_latest.py`
- Create: `tests/test_ahe_support.py`
- Modify: `tests/test_phase_f_init_binding.py`

**Interfaces:**
- Produces: `task_states(vector: object, required_trials: int = 2) -> dict[str, str]`
- Produces: `compare_states(previous: dict[str, str], current: dict[str, str]) -> dict[str, list[str]]`
- Produces: `evaluate_manifest(manifest: dict[str, Any], previous: object, current: object) -> dict[str, Any]`
- Produces: `select_debugger_tasks(current_states: dict[str, str], comparison: dict[str, list[str]], predicted_risks: list[str], *, successful_controls: int, seed: int, generation: int) -> dict[str, list[str]]`
- Produces: `validate_change_manifest(manifest: object, *, generation: str, parent: str, changed_paths: list[str], run_dir: Path, surface_report: dict[str, Any]) -> dict[str, Any]`
- Produces: `verify_relative_hash(workspace: Path, reference: object) -> Path`

- [ ] **Step 1: Write table-driven AHE support tests**

Cover:

```python
def test_task_states_require_two_complete_trials() -> None:
    vector = make_vector({"pass": [1, 1], "partial": [1, 0], "fail": [0, 0], "unknown": [1, None]})
    assert task_states(vector) == {
        "fail": "fail", "partial": "partial", "pass": "pass", "unknown": "unknown"
    }


def test_compare_states_orders_improvements_and_regressions() -> None:
    assert compare_states(
        {"a": "fail", "b": "pass", "c": "unknown"},
        {"a": "pass", "b": "partial", "c": "fail"},
    ) == {
        "improved": ["a"],
        "regressed": ["b"],
        "unchanged": [],
        "unknown": ["c"],
    }


def test_manifest_attribution_marks_harmful_change() -> None:
    result = evaluate_manifest(
        {"changes": [{"id": "chg-1", "predicted_fixes": ["a"], "risk_tasks": ["b"]}]},
        make_vector({"a": [0, 0], "b": [1, 1]}),
        make_vector({"a": [0, 0], "b": [0, 0]}),
    )
    assert result["changes"][0]["verdict"] == "HARMFUL"
```

Define the test helper in the same file:

```python
def make_vector(outcomes: dict[str, list[int | None]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "tasks": {
            task_id: {
                "trials": [
                    {
                        "trial": index,
                        "status": "complete" if reward is not None else "infra_failed",
                        "reward": float(reward) if reward is not None else None,
                    }
                    for index, reward in enumerate(rewards)
                ]
            }
            for task_id, rewards in outcomes.items()
        },
    }
```

Validate deterministic controls using `random.Random(seed + generation)` and a sorted success pool. Validate manifests reject missing `risk_tasks`, missing evidence paths, path traversal, changed-file coverage gaps, and duplicate coverage.

- [ ] **Step 2: Run tests and verify imports fail**

```bash
uv run pytest tests/test_ahe_support.py -v
```

Expected: FAIL because `library/ahe_support.py` is absent.

- [ ] **Step 3: Implement pure AHE policy helpers**

Keep this module independent of driver internals. Import only stdlib plus `evolve.task_vectors.normalize_task_vector`. Use ordered states:

```python
STATE_RANK = {"fail": 0, "partial": 1, "pass": 2}

def _state(trials: list[dict[str, Any]], required_trials: int) -> str:
    if len(trials) != required_trials or any(item["status"] != "complete" for item in trials):
        return "unknown"
    passed = sum(float(item["reward"]) > 0 for item in trials)
    return "pass" if passed == required_trials else "fail" if passed == 0 else "partial"
```

Manifest verdict rules:

```python
if realized_risks and not verified_fixes:
    verdict = "HARMFUL"
elif realized_risks:
    verdict = "MIXED"
elif verified_fixes and len(verified_fixes) == len(predicted_fixes):
    verdict = "EFFECTIVE"
elif verified_fixes:
    verdict = "PARTIALLY_EFFECTIVE"
else:
    verdict = "INEFFECTIVE"
```

- [ ] **Step 4: Implement the explicit AHE selector**

Create `library/select/ahe_latest.py` with its own class, even though the initial ordering resembles `newest.py`:

```python
class AheLatestSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid AHE parent")
        chosen = max(parents, key=lambda row: (_generation_key(row), str(row.get("genid", ""))))
        return SelectResult(parents=[str(chosen["genid"])])
```

Add the standard subprocess isolation imports and `sdk.main(AheLatestSelect)`.

- [ ] **Step 5: Run support and binding tests**

```bash
uv run pytest tests/test_ahe_support.py tests/test_phase_f_init_binding.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit AHE policy foundations**

```bash
git add library/ahe_support.py library/select/ahe_latest.py tests/test_ahe_support.py tests/test_phase_f_init_binding.py
git commit -m "Add AHE attribution and sequential selection"
```

---

### Task 7: Implement parallel MiniSWE trace analysis and attribution rollout

**Files:**
- Create: `library/rollout/ahe_trace_analysis.py`
- Create: `library/rollout/prompts/ahe_debugger.md`
- Create: `library/rollout/prompts/ahe_debugger_overview.md`
- Create: `tests/test_ahe_rollout.py`

**Interfaces:**
- Consumes: parent archive fields `task_vector`, `evaluation_artifacts`, `ahe_manifest_path`, `ahe_manifest_sha256`.
- Produces: `rollout/analysis/selection.json`, `rollout/analysis/detail/*.md`, `rollout/analysis/overview.md`, `rollout/attribution.json`.
- Returns: `RolloutResult(summary: dict[str, Any], artifacts: list[str])`.

- [ ] **Step 1: Write a deterministic rollout test with a fake source-agent runner**

Construct a workspace archive with parent `1`, grandparent `0`, versioned vectors, artifact indexes, and a prior manifest. Monkeypatch the module's `run_meta_agent` to return task-specific text. Assert:

```python
assert json.loads((run_dir / "rollout/analysis/selection.json").read_text()) == {
    "generation": "2",
    "tasks": {
        "failed-task": ["failure"],
        "regressed-task": ["regression"],
        "risk-task": ["predicted_risk"],
        "stable-pass": ["successful_control"],
    },
}
assert (run_dir / "rollout/analysis/detail/failed-task.md").exists()
assert (run_dir / "rollout/analysis/overview.md").exists()
assert json.loads((run_dir / "rollout/attribution.json").read_text())["summary"]
assert max_active_debuggers == 5
```

Also assert each fake call receives proxy removals and runs in a task-specific scratch directory, not the candidate checkout.

- [ ] **Step 2: Run the test and verify the operator is missing**

```bash
uv run pytest tests/test_ahe_rollout.py -v
```

Expected: import fails.

- [ ] **Step 3: Implement artifact loading and debugger selection**

The operator must:

1. Resolve the selected parent via `ArchiveView(ctx.workspace).row(ctx.parent)`.
2. Verify each referenced artifact-index hash before reading it.
3. Load the grandparent via the parent's `parent` field.
4. Call `evaluate_manifest` when both vectors and a parent manifest exist; otherwise write a baseline attribution.
5. Call `select_debugger_tasks` with required categories and configured control count/seed.
6. Write `selection.json` before launching LLM work.

- [ ] **Step 4: Implement bounded parallel debugger calls**

Use `ThreadPoolExecutor(max_workers=workers)` where `workers` defaults to 5 and is capped at 5. Each call uses:

```python
PROXY_REMOVALS = {
    "http_proxy": None,
    "https_proxy": None,
    "HTTP_PROXY": None,
    "HTTPS_PROXY": None,
    "all_proxy": None,
    "ALL_PROXY": None,
}

run_meta_agent(
    workspace=scratch_dir,
    prompt=prompt,
    config={"command": command, "timeout_s": timeout_s},
    env_overrides={
        **PROXY_REMOVALS,
        "EVOLVE_SOURCE_AGENT_ROLE": "debugger",
        "EVOLVE_SOURCE_AGENT_OUTPUT_PATH": str(trajectory_path),
        "EVOLVE_RUN_DIR": str(task_run_dir),
    },
)
```

Resolve `command` from `ctx.config["debugger"]["command"]`, then `EVOLVE_AHE_DEBUGGER_COMMAND`, then `EVOLVE_AGENT_COMMAND`. Retry each task according to `debugger.attempts`, recording final failures in `analysis/failures.json`. Require a report or explicit failure record for every regression and predicted-risk task.

- [ ] **Step 5: Add official-AHE-inspired prompts**

The per-task prompt must require: exact trace evidence with file path, failure phase, root cause, passing contrast where available, candidate harness component, and no edits. The overview prompt reads only detail reports and attribution and groups cross-task patterns; it must not read sealed-test data or propose task-specific patches.

- [ ] **Step 6: Implement overview aggregation and rollout result**

Run one final source-agent call after the worker pool. Write stdout to `overview.md`. Return a summary containing analyzed/failed/control counts and attribution verdict counts, plus relative paths for all produced artifacts.

- [ ] **Step 7: Run rollout tests**

```bash
uv run pytest tests/test_ahe_rollout.py tests/test_agent_runner.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit the AHE analysis stage**

```bash
git add library/rollout/ahe_trace_analysis.py library/rollout/prompts/ahe_debugger.md library/rollout/prompts/ahe_debugger_overview.md tests/test_ahe_rollout.py
git commit -m "Add AHE trace analysis rollout"
```

---

### Task 8: Implement the evidence editor and pre-evaluation manifest gate

**Files:**
- Create: `library/meta_agent/ahe_evidence_editor.py`
- Create: `library/meta_agent/prompts/ahe_evolve.md`
- Create: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Consumes: rollout analysis, attribution, feedback bundle, current config, git generation tags, surface policy.
- Produces: `meta_agent/change_manifest.json`, `changed.json`, `surface-check.json`, `patch.diff`, `rationale.md`, `predicted_fixes.json`, `risk_tasks.json`, `usage.json`.

- [ ] **Step 1: Write a failing editor test with a deterministic manifest-writing command**

The fake command edits `target/agent.py` and writes JSON to `EVOLVE_AHE_MANIFEST_PATH`. Assert the operator returns exactly the changed source paths and writes flattened predictions/risks. Add negative tests for missing manifest, missing evidence, uncovered changed file, `../` evidence path, and `target/harbor_agent.py` edits.

- [ ] **Step 2: Run the test and verify the variant is missing**

```bash
uv run pytest tests/test_ahe_meta_agent.py -v
```

Expected: import fails.

- [ ] **Step 3: Build the evolution prompt from explicit artifacts**

Implement `build_ahe_prompt(checkout, ctx)` to concatenate:

```python
prompt_chunks = [
    prompt_template,
    "# Experiment Config\n\n```yaml\n%s\n```" % (checkout / "evolve.yaml").read_text().rstrip(),
    "# Analysis Overview\n\n%s" % overview.read_text().rstrip(),
    "# Previous Change Attribution\n\n```json\n%s\n```" % attribution.read_text().rstrip(),
    "# Evolution History\n\n%s" % attempts.read_text().rstrip(),
    "# Surface Rules\n\n%s" % surface_rules,
    "# Required Manifest Path\n\n%s" % manifest_path,
]
```

Adapt the official AHE evolve prompt's loop convention, evidence-first reading order, component-level pivot rule, `KEEP`/`REVISE`/`ROLLBACK + PIVOT` decision, one-commit-per-logical-change guidance, and mandatory manifest. Replace NexAU-specific component names with MiniSWE source component levels.

- [ ] **Step 4: Run the source-only evolution command with proxy removal**

Call `run_meta_agent` in the child checkout with `EVOLVE_SOURCE_AGENT_ROLE=evolution`, a role-specific trajectory path, `EVOLVE_AHE_MANIFEST_PATH`, and all proxy variables removed. Resolve command from `ctx.config.command`, then `EVOLVE_AGENT_COMMAND`.

- [ ] **Step 5: Validate patch, surface, and manifest before returning success**

Use existing `create_candidate_patch`, `load_surface_policy`, and `patch_parent_ref`. Then call `validate_change_manifest` with:

```python
validate_change_manifest(
    manifest=manifest,
    generation=ctx.genid,
    parent=str(ctx.parent),
    changed_paths=patch.changed_paths,
    run_dir=ctx.run_dir,
    surface_report=patch.surface_report,
)
```

Write `predicted_fixes.json` and `risk_tasks.json` as sorted unions across manifest entries. Any validation failure writes failure artifacts and exits nonzero so the driver records `operator_failed` before Harbor evaluation.

- [ ] **Step 6: Run editor tests**

```bash
uv run pytest tests/test_ahe_meta_agent.py tests/test_agent_command_meta_agent.py -v
```

Expected: PASS, including unchanged behavior for `agent_command`.

- [ ] **Step 7: Commit the evidence editor**

```bash
git add library/meta_agent/ahe_evidence_editor.py library/meta_agent/prompts/ahe_evolve.md tests/test_ahe_meta_agent.py
git commit -m "Add AHE evidence-driven source editor"
```

---

### Task 9: Implement AHE artifact validity gate and compact archive record

**Files:**
- Create: `library/gate/ahe_artifact_valid.py`
- Create: `library/record/ahe_manifest.py`
- Create: `tests/test_ahe_gate_record.py`

**Interfaces:**
- Gate consumes: child stamped row, `meta_agent/change_manifest.json`, `task_vector`, and `evaluation_artifacts` reference.
- Record produces: `valid_parent`, `verdict`, `reason`, `ahe_manifest_path`, `ahe_manifest_sha256`, `ahe_decision`, `predicted_fixes`, `risk_tasks`, `ahe_attribution`, and analysis paths.

- [ ] **Step 1: Write failing gate tests proving score independence**

Create a complete child with score `0.1`, parent score `0.9`, valid task vector/artifact hash/manifest, and assert `accept`. Then corrupt the artifact hash and assert `reject`. Add a missing-manifest rejection.

- [ ] **Step 2: Write failing record tests for compact fields**

Assert large report text and raw manifest bodies do not appear in record fields, while relative paths and SHA-256 hashes do.

- [ ] **Step 3: Run tests and verify variants are missing**

```bash
uv run pytest tests/test_ahe_gate_record.py -v
```

Expected: import fails.

- [ ] **Step 4: Implement structural gate behavior**

`AheArtifactValidGate.decide` accepts only when:

```python
usable_status = child.get("status") in {"complete", "partial"}
has_score = isinstance(child.get("score"), (int, float)) and not isinstance(child.get("score"), bool)
vector_ok = validate_task_vector(child.get("task_vector"))
artifact_ok = verify_relative_hash(ctx.workspace, child["evaluation_artifacts"])
manifest_ok = validate_change_manifest(
    json.loads((ctx.run_dir / "meta_agent" / "change_manifest.json").read_text()),
    generation=ctx.genid,
    parent=str(ctx.parent),
    changed_paths=list(child.get("mutated") or []),
    run_dir=ctx.run_dir,
    surface_report={"ok": True, "mutated": list(child.get("mutated") or []), "violations": []},
)
```

Never read or compare the parent score. Return a reason naming the first invalid artifact.

- [ ] **Step 5: Implement compact AHE record fields**

Hash the manifest and reference it relative to workspace. Flatten sorted predicted/risk task unions and summarize attribution verdict counts. Read the already-written `gate.json` for canonical verdict fields. Keep full reports and manifests on disk.

- [ ] **Step 6: Run gate and record tests**

```bash
uv run pytest tests/test_ahe_gate_record.py tests/test_m5_record_verb.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit AHE gate and record**

```bash
git add library/gate/ahe_artifact_valid.py library/record/ahe_manifest.py tests/test_ahe_gate_record.py
git commit -m "Add AHE artifact gate and manifest record"
```

---

### Task 10: Wire the real and smoke AHE recipes and update protocol documentation

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/ahe/notes.md`
- Create: `recipes/ahe/evaluator/tasks/train-30.txt`
- Modify: `recipes/ahe-smoke/evolve.yaml`
- Modify: `recipes/ahe-smoke/README.md`
- Modify: `library/PROTOCOL.md`
- Modify: `library/README.md`
- Modify: `recipes/README.md`
- Modify: `README.md`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_phase_f_init_binding.py`

**Interfaces:**
- Real recipe selects all five named AHE variants.
- Real recipe uses `dataset: swebenchpro@1.0`, registry mode, 30-task file, `k: 2`, `n_concurrent: 5`.
- Smoke recipe selects the same AHE variants with builtin target and deterministic evaluator setup.

- [ ] **Step 1: Copy the validated 30-task training list from DevBoxS**

```bash
mkdir -p recipes/ahe/evaluator/tasks
scp DevBoxS:/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hc-ahe-30x30-20260709/tasks/train-30.txt recipes/ahe/evaluator/tasks/train-30.txt
test "$(grep -cvE '^[[:space:]]*(#|$)' recipes/ahe/evaluator/tasks/train-30.txt)" -eq 30
```

Do not copy `test-30.txt` into the repository recipe or generated workspace.

- [ ] **Step 2: Write recipe tests before changing YAML**

Assert AHE alone contains:

```python
assert "variant: ahe_latest" in ahe
assert "variant: ahe_trace_analysis" in ahe
assert "variant: ahe_evidence_editor" in ahe
assert "variant: ahe_artifact_valid" in ahe
assert "variant: ahe_manifest" in ahe
assert "dataset: swebenchpro@1.0" in ahe
assert "k: 2" in ahe
assert "n_concurrent: 5" in ahe
assert "target/harbor_agent.py" in ahe
```

Assert hillclimb does not contain AHE variants or prompts. Update the recipe-artifact test to allow a recipe-owned `evaluator/` directory while still rejecting arbitrary files.

- [ ] **Step 3: Run recipe tests and verify failure**

```bash
uv run pytest tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py -v
```

Expected: AHE assertions fail.

- [ ] **Step 4: Replace the placeholder AHE YAML composition**

Use the approved config from the design spec, with these concrete paths:

```yaml
surface:
  include: [target/**]
  exclude: [target/harbor_agent.py]
operators:
  select: {variant: ahe_latest}
  rollout:
    variant: ahe_trace_analysis
    debugger: {workers: 5, command: null, attempts: 3}
    controls: {successful: 3, rotation_seed: 0}
    analyze: {failures: true, regressions: true, timeouts: true, predicted_risks: true}
  meta_agent:
    variant: ahe_evidence_editor
    command: null
    prompt: library/meta_agent/prompts/ahe_evolve.md
    rollback: {allow_partial: true, pivot_after_revert: true}
  gate: {variant: ahe_artifact_valid}
  record: {variant: ahe_manifest}
  timeout_s: 3600
evaluator:
  engine: harbor
  dataset: swebenchpro@1.0
  dataset_mode: registry
  task_file: evaluator/tasks/train-30.txt
  tasks_per_round: 30
  k: 2
  n_concurrent: 5
  partial_floor: 0.8
```

The smoke recipe uses the same variants but `seed: builtin-dummy`, `dataset: pass@k`, and no real task file.

- [ ] **Step 5: Update protocol and recipe prose**

Document that library variants may carry explicit research-method names when the name denotes real behavior, not a label-only preset. Add the generic `task_vector.json` and `evaluation_artifacts.json` evaluator contracts, prompt asset paths, and AHE artifact names. Remove the note claiming AHE is only a rollback-shaped scaffold.

- [ ] **Step 6: Run recipe and initialization tests**

```bash
uv run pytest tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py tests/test_m0_init.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit recipe wiring and docs**

```bash
git add recipes/ahe recipes/ahe-smoke library/PROTOCOL.md library/README.md recipes/README.md README.md tests/test_phase_e_recipes.py tests/test_phase_f_init_binding.py
git commit -m "Wire method-faithful AHE recipe"
```

---

### Task 11: Add a deterministic two-iteration AHE integration test

**Files:**
- Create: `tests/test_ahe_integration.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Demonstrates: manifest-backed generation, harmful attribution, explicit rollback-pivot, sequential selection, and score-independent gate.

- [ ] **Step 1: Add deterministic debugger and editor command fixtures**

In `tests/conftest.py`, add command builders. The editor command reads `EVOLVE_GENID`; generation 1 writes a failing change and predicts `task-0`, generation 2 restores the parent behavior and writes `decision: rollback_pivot`. Both write complete manifests to `EVOLVE_AHE_MANIFEST_PATH`. The debugger command prints a fixed evidence report.

- [ ] **Step 2: Write the end-to-end test**

The test initializes `ahe-smoke`, replaces the stub vectors so generation 1 regresses despite a high synthetic aggregate score, runs two generations, and asserts:

```python
rows = rows_by_genid(workspace)
assert rows["1"]["valid_parent"] is True
assert rows["1"]["ahe_decision"] == "keep"
assert rows["2"]["parent"] == "1"
assert rows["2"]["ahe_decision"] == "rollback_pivot"
assert rows["2"]["ahe_attribution"]["HARMFUL"] == 1
assert "target/agent.py" in rows["2"]["mutated"]
assert (workspace / "runs/gen-2/rollout/attribution.json").exists()
```

Also assert no generated prompt contains the sealed test filename or proxy value.

- [ ] **Step 3: Run the integration test and repair only contract-level failures**

```bash
uv run pytest tests/test_ahe_integration.py -v
```

Expected: PASS. Any failure must be fixed in the owning operator or generic contract, not with an AHE branch in the driver.

- [ ] **Step 4: Run all focused AHE tests together**

```bash
uv run pytest tests/test_task_vectors.py tests/test_harbor_artifacts.py tests/test_miniswe_source_agent_command.py tests/test_ahe_support.py tests/test_ahe_rollout.py tests/test_ahe_meta_agent.py tests/test_ahe_gate_record.py tests/test_ahe_integration.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit integration coverage**

```bash
git add tests/conftest.py tests/test_ahe_integration.py
git commit -m "Test AHE attribution and rollback loop"
```

---

### Task 12: Run full local verification and review the implementation

**Files:**
- Modify only files required by test, lint, or type failures caused by Tasks 1-11.

**Interfaces:**
- Produces: locally verified implementation ready for remote smoke testing.

- [ ] **Step 1: Run the complete test suite**

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint and static type checks**

```bash
uv run ruff check .
uv run ty check
```

Expected: both commands exit 0. Do not reformat unrelated files.

- [ ] **Step 3: Verify the AHE/hillclimb composition diff**

```bash
uv run python - <<'PY'
from evolve.config import default_config
for name in ("hill_climb", "ahe"):
    cfg = default_config(name, name)
    print(name, {kind: block.get("variant") for kind, block in cfg["operators"].items() if isinstance(block, dict)})
PY
```

Expected: no active operator variant is shared between AHE and hillclimb except where explicitly justified; prompts differ.

- [ ] **Step 4: Run secret/proxy and CLI-path scans**

```bash
rg -n "OPENAI_API_KEY=|sk-[A-Za-z0-9]|mini-swe-agent --|http_proxy=.*8118|https_proxy=.*8118" src library recipes templates tools tests
```

Expected: no secret literals, no MiniSWE CLI invocation, and no proxy endpoint embedded in code or recipe files. Test fixtures may mention variable names but not real values.

- [ ] **Step 5: Request a code review**

Use `superpowers:requesting-code-review` against the implementation commits. Address correctness findings before remote execution.

- [ ] **Step 6: Turn each review finding into an exact follow-up task before editing**

For every actionable finding, append a checkbox to this plan naming the exact file, failing test, implementation delta, verification command, and commit command. Skip this step when review finds no required changes. Never use `git add -A`, `git commit -a`, or an unspecified path in the dirty worktree.

---

### Task 13: Sync a clean snapshot to DevBoxS and run the real two-task smoke

**Files:**
- Remote snapshot: `/data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-${COMMIT}-20260710`
- Remote smoke root: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-smoke-20260710`
- Reuse source: `/data00/home/zimuwang/simple-evolve-agent-project/sources/mini-swe-agent`
- Reuse env: `/data00/home/zimuwang/simple-evolve-agent-project/.env`

**Interfaces:**
- Produces: real Harbor/MiniSWE smoke artifacts for two tasks, `k=2`, and two AHE iterations.

- [ ] **Step 1: Record the exact verified commit and create a remote snapshot**

```bash
COMMIT=$(git rev-parse --short=12 HEAD)
git archive --format=tar HEAD | ssh DevBoxS "mkdir -p /data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-$COMMIT-20260710 && tar -xf - -C /data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-$COMMIT-20260710"
```

Do not copy the local `.env`.

- [ ] **Step 2: Install and verify the remote snapshot without printing secrets**

```bash
ssh DevBoxS "cd /data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-$COMMIT-20260710 && uv sync --all-groups && uv run pytest -q"
```

Expected: complete remote test suite passes.

- [ ] **Step 3: Create a two-task file from the validated training split**

```bash
ssh DevBoxS "mkdir -p /data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-smoke-20260710/tasks && head -n 2 /data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hc-ahe-30x30-20260709/tasks/train-30.txt > /data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-smoke-20260710/tasks/train-2.txt"
```

Verify exactly two nonblank task IDs.

- [ ] **Step 4: Initialize the real AHE workspace from the local MiniSWE source**

Use the snapshot's `evolve init` with `--recipe ahe` and `--seed /data00/home/zimuwang/simple-evolve-agent-project/sources/mini-swe-agent`. Patch only workspace-owned YAML values: experiment ID/max generations, `evaluator.task_file`, `tasks_per_round: 2`, `k: 2`, `n_concurrent: 5`, Harbor jobs root, debugger command, and meta-agent command. Keep all five top-level sections and do not embed `.env` values.

- [ ] **Step 5: Force the real generation-zero Harbor baseline before evolution**

With `SMOKE_WS=/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-smoke-20260710/workspace`, run:

```bash
evolve eval "$SMOKE_WS" 0 --force
```

Expected: `runs/gen-0/eval/task_vector.json` has two trials for both tasks and `runs/gen-0/eval/evaluation_artifacts.json` exists. Do not start generation 1 until this baseline evidence is present.

- [ ] **Step 6: Preflight source-only commands and proxy isolation**

Source the stable `.env` in a shell without printing it, then run:

```bash
uv run --project /data00/home/zimuwang/simple-evolve-agent-project/sources/mini-swe-agent \
  python /data00/home/zimuwang/simple-evolve-agent-project/framework/ahe-$COMMIT-20260710/tools/miniswe_source_agent_command.py --check
```

Expected: source imports succeed and the command reports only MiniSWE version/model name, never credentials. Run the wrapper's environment self-test to confirm all proxy variables are absent inside the LLM process.

- [ ] **Step 7: Run two real AHE iterations in the foreground**

Run with five Harbor workers and capture logs under the smoke root. Do not detach this first smoke. Expected artifacts for each completed generation:

```text
rollout/analysis/selection.json
rollout/analysis/detail/*.md
rollout/analysis/overview.md
rollout/attribution.json
meta_agent/change_manifest.json
eval/task_vector.json
eval/evaluation_artifacts.json
gate.json
record/fields.json
```

- [ ] **Step 8: Exercise rollback deterministically if the real run has no falsified prediction**

Run the deterministic integration command on DevBoxS against retained Harbor-shaped fixture artifacts. Require a `HARMFUL` or `MIXED` attribution followed by a `rollback_pivot` manifest. Do not alter the real smoke archive to manufacture a result.

- [ ] **Step 9: Audit the smoke result**

Verify:

```bash
SMOKE_WS=/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-smoke-20260710/workspace
evolve status "$SMOKE_WS"
evolve verify "$SMOKE_WS"
git -C "$SMOKE_WS" tag --list 'gen/*'
```

Check task-vector trial counts are exactly two per completed task; artifact hashes resolve; no test-30 task appears anywhere under the workspace; no proxy URL appears in prompts/source; and no `target/harbor_agent.py` mutation exists.

- [ ] **Step 10: Write a readiness report**

Create `smoke-readiness.json` under the remote smoke root with commit, task IDs, iteration count, trial counts, exception classes, artifact checks, source-only checks, proxy isolation, and `ready_for_30x30: true|false`. Never include `.env` values.

---

### Task 14: Launch the fresh 30/30 AHE experiment only after the readiness gate passes

**Files:**
- Remote experiment root: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-${RUN_TS}` where `RUN_TS=$(date +%Y%m%d-%H%M%S)`.
- Reuse validated train/test files from the existing experiment root; keep test outside the workspace.

**Interfaces:**
- Produces: one detached 30-training-task AHE run and separately retained baseline/final sealed-test evaluations.

- [ ] **Step 1: Require an affirmative smoke gate**

Read `smoke-readiness.json`. Stop if `ready_for_30x30` is not exactly `true`; report the failing check rather than launching.

- [ ] **Step 2: Create a fresh experiment root and workspace**

Define the paths first:

```bash
RUN_TS=$(date +%Y%m%d-%H%M%S)
FULL_EXP=/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-${RUN_TS}
FULL_WS=$FULL_EXP/workspace
```

Initialize `FULL_WS` from the same verified framework snapshot and local MiniSWE source. Copy only `train-30.txt` into the workspace evaluator path. Keep `test-30.txt` under the experiment root with permissions and paths not exposed to the workspace or prompts.

- [ ] **Step 3: Configure the full run**

Use 30 training tasks, `k=2`, Harbor `n_concurrent=5`, debugger workers 5, one evolution agent, and `max_generations: 50`. Set the initial operational checkpoint at generation 30; generations 31-50 continue only if the run is healthy and still producing proposals.

- [ ] **Step 4: Launch detached with explicit PID and log files**

Before launching, force-evaluate the real training baseline and require 30 tasks with two trials each:

```bash
evolve eval "$FULL_WS" 0 --force
```

Expected: generation 0 has 60 completed/scored trials or an explicitly classified partial result that blocks launch until resolved.

Then launch detached with explicit PID and log files.

Use the `FULL_EXP` and `FULL_WS` values established in Step 2. Use a unique session/process group, write PID files under `$FULL_EXP/pids/`, and write one top-level log plus framework and Harbor job paths. Do not create a Codex scheduled automation.

- [ ] **Step 5: Verify immediate liveness and first-generation artifacts**

Confirm the top PID, process group, first Harbor job, task count, attempt count, worker count, and source-only command before considering the launch successful.

- [ ] **Step 6: Evaluate the sealed test only at allowed checkpoints**

Run Harbor on the sealed 30-task test list for generation 0 and, after evolution, the final generation and best observed training-score generation. Store those jobs outside the evolution workspace and never feed their vectors or traces back into AHE.

- [ ] **Step 7: Report launch locations and readiness honestly**

Tell the user the exact experiment root, workspace, Harbor jobs directory, top-level log, PID, current generation, and any remaining risk. Call the experiment ready only after smoke and first-generation checks pass.
