# Offline uv Candidate Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare uv-managed candidate dependencies once per candidate and let isolated evaluation environments install the mutable local project offline without whole-batch retries.

**Architecture:** Add a frozen, backend-neutral `candidate_runtime` component that validates and prepares a uv project, emits a receipt, and returns consumer environment variables and mounts. Integrate that contract into the evaluator host and Harbor engine, keep MiniSWE-specific source/import checks in its adapter, and use Harbor's same-trial retry rather than repeating an evaluation batch.

**Tech Stack:** Python 3.12+, dataclasses, uv, Harbor shell templates, pytest, YAML recipes, Docker on DevBoxS.

## Global Constraints

- The first version supports uv-managed Python projects only.
- Candidate `pyproject.toml`, `uv.lock`, source, and build-system files remain mutable.
- Candidate-runtime preparation is benchmark- and agent-independent.
- The preparation host and consumers must share OS, architecture, and Python ABI compatibility; the first deployment is Linux x86-64 on DevBoxS.
- Evaluation backends consume environment variables and mounts without implementing uv resolution.
- Agent-specific source and import validation remains in the agent adapter.
- Package-index/proxy access is allowed only during candidate preparation; isolated uv sync is offline.
- Do not add a daemon, registry mirror, candidate image pipeline, per-lock cache tree, or shared virtual environment.
- Never persist proxy URLs, tokens, credentials, or environment dumps.
- Do not rerun a complete evaluation batch automatically after task-level infrastructure failure.
- AHE and HyperAgents remain independent experiments with four workers each.

---

## File Structure

- Create `src/evolve/uv_runtime.py`: uv configuration validation, preparation, receipt writing, failure ownership, and backend-neutral consumer contract. Keep the existing `candidate_runtime.py` focused on candidate smoke execution.
- Modify `tests/test_candidate_runtime.py`: add focused unit tests for path safety, lock validation, cache preparation, retry, redaction, receipt contents, and disabled mode alongside its existing real-uv rematerialization test.
- Modify `src/evolve/evaluator.py`: invoke candidate preparation before the evaluator engine and pass the consumer contract to the engine.
- Modify `src/evolve/evaluation.py`: retain the candidate-runtime receipt reference in `EvaluationRecord`.
- Modify `tests/test_m1_evaluator_invariants.py`: verify preparation ordering, failure short-circuiting, runtime environment propagation, and receipt archival.
- Modify `templates/evaluator/engines/harbor.sh`: consume generic runtime mounts/environment and support full-dataset install-only smoke.
- Modify `templates/workspace/evolve_harbor_adapter/__init__.py`: use offline uv settings supplied by the runtime contract while keeping MiniSWE checks local.
- Modify `templates/target/harbor/miniswe_source_agent.py`: keep the source-distribution template behavior aligned with the workspace adapter.
- Modify `tests/test_harbor_evaluator_template.py`: verify generic mounts/environment and full-image smoke command construction.
- Modify `tests/test_miniswe_harbor_wrapper.py`: verify offline local sync and separation from model networking.
- Modify `templates/evaluator/harbor_artifacts.py`: make a final repeated verifier timeout scoreable as zero after Harbor's configured task retry.
- Modify `templates/evaluator/parse_score.py`: accept a complete scoreable final vector even when Harbor reports a nonzero process code for its retried timeout.
- Modify `src/evolve/driver.py`: remove automatic complete-batch infrastructure replay.
- Modify `tests/test_evaluation_lifecycle.py`: assert one lifecycle attempt and pause on unresolved infrastructure failure.
- Modify `tests/test_harbor_artifacts.py`: verify same-trial retry results, verifier timeout scoring, and sibling preservation.
- Modify `recipes/ahe/evolve.yaml`, `recipes/hyperagents/evolve.yaml`, and `recipes/hill_climb/evolve.yaml`: opt real uv candidates into the component and configure one Harbor task retry.
- Modify `tests/test_phase_e_recipes.py`: freeze the recipe contract.
- Modify `docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md`: reference the runtime launch prerequisite and corrected smoke tasks.

---

### Task 1: Define the backend-neutral candidate-runtime contract

**Files:**
- Create: `src/evolve/uv_runtime.py`
- Modify: `tests/test_candidate_runtime.py`

**Interfaces:**
- Consumes: evaluator mapping `candidate_runtime: {variant: uv, project: target}` and a detached candidate checkout.
- Produces: `RuntimeMount`, `CandidateRuntimeResult`, and `candidate_runtime_config(checkout, evaluator)`.

- [ ] **Step 1: Write failing configuration and containment tests**

```python
from pathlib import Path

import pytest

from evolve.uv_runtime import candidate_runtime_config


def test_uv_runtime_config_resolves_project_inside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "target").mkdir(parents=True)

    config = candidate_runtime_config(
        checkout,
        {"candidate_runtime": {"variant": "uv", "project": "target"}},
    )

    assert config is not None
    assert config.variant == "uv"
    assert config.project == (checkout / "target").resolve()
    assert config.project_relative == "target"


@pytest.mark.parametrize(
    "value, message",
    [
        ("target", "candidate_runtime must be a mapping"),
        ({"variant": "pip", "project": "target"}, "unsupported candidate runtime variant"),
        ({"variant": "uv", "project": "../outside"}, "candidate runtime project escapes checkout"),
        ({"variant": "uv", "project": "/tmp/outside"}, "candidate runtime project must be relative"),
    ],
)
def test_uv_runtime_config_rejects_invalid_or_escaping_paths(
    tmp_path: Path, value: object, message: str
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    with pytest.raises(ValueError, match=message):
        candidate_runtime_config(checkout, {"candidate_runtime": value})


def test_missing_runtime_config_disables_preparation(tmp_path: Path) -> None:
    assert candidate_runtime_config(tmp_path, {}) is None
```

- [ ] **Step 2: Run the tests and confirm the module is missing**

Run: `uv run pytest -q tests/test_candidate_runtime.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'evolve.uv_runtime'`.

- [ ] **Step 3: Implement the contract and strict configuration parser**

```python
# src/evolve/uv_runtime.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation import Outcome


@dataclass(frozen=True)
class UvRuntimeConfig:
    variant: str
    project: Path
    project_relative: str


@dataclass(frozen=True)
class RuntimeMount:
    source: Path
    target: str
    read_only: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "bind",
            "source": str(self.source),
            "target": self.target,
            "read_only": self.read_only,
        }


@dataclass(frozen=True)
class CandidateRuntimeResult:
    variant: str | None
    project: str | None
    environment: tuple[tuple[str, str], ...] = ()
    mounts: tuple[RuntimeMount, ...] = ()
    outcome: Outcome | None = None
    reason: str | None = None
    receipt_path: Path | None = None

    @property
    def ready(self) -> bool:
        return self.outcome is None

    def environment_json(self) -> str:
        return json.dumps(dict(self.environment), sort_keys=True, separators=(",", ":"))

    def mounts_json(self) -> str:
        return json.dumps([mount.to_dict() for mount in self.mounts], sort_keys=True, separators=(",", ":"))


def candidate_runtime_config(checkout: Path, evaluator: dict[str, Any]) -> UvRuntimeConfig | None:
    value = evaluator.get("candidate_runtime")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("evaluator.candidate_runtime must be a mapping")
    if value.get("variant") != "uv":
        raise ValueError(f"unsupported candidate runtime variant: {value.get('variant')!r}")
    raw_project = value.get("project")
    if not isinstance(raw_project, str) or not raw_project.strip():
        raise ValueError("evaluator.candidate_runtime.project must be a relative path")
    relative = Path(raw_project)
    if relative.is_absolute():
        raise ValueError("candidate runtime project must be relative")
    root = checkout.resolve()
    project = (root / relative).resolve()
    try:
        project.relative_to(root)
    except ValueError:
        raise ValueError("candidate runtime project escapes checkout") from None
    return UvRuntimeConfig("uv", project, project.relative_to(root).as_posix())
```

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest -q tests/test_candidate_runtime.py`

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add src/evolve/uv_runtime.py tests/test_candidate_runtime.py
git commit -m "feat: define candidate runtime contract"
```

---

### Task 2: Prepare uv dependencies once and emit a redacted receipt

**Files:**
- Modify: `src/evolve/uv_runtime.py`
- Modify: `tests/test_candidate_runtime.py`

**Interfaces:**
- Consumes: `prepare_candidate_runtime(checkout, run_dir, runtime_root, candidate_commit, evaluator, env=None)` and `run_owned` command execution.
- Produces: a successful `CandidateRuntimeResult` with offline environment/mounts, or a candidate/infrastructure-owned result with `candidate-runtime.json`.

- [ ] **Step 1: Add failing success, cache-hit, retry, invalid-lock, and redaction tests**

Use a fake executable uv script that appends each argument vector to `UV_CALLS`, returns the requested exit codes, and creates no real environment. Assert:

```python
result = prepare_candidate_runtime(
    checkout,
    run_dir,
    runtime_root,
    candidate_commit="abc123",
    evaluator=evaluator,
    env=env,
)
assert result.ready
assert dict(result.environment) == {
    "UV_CACHE_DIR": "/opt/evolve/uv/cache",
    "UV_LINK_MODE": "copy",
    "UV_OFFLINE": "1",
    "UV_PYTHON_INSTALL_DIR": "/opt/evolve/uv/python",
}
assert [mount.target for mount in result.mounts] == [
    "/opt/evolve/uv/cache",
    "/opt/evolve/uv/python",
]
receipt = json.loads((run_dir / "candidate-runtime.json").read_text())
assert receipt["variant"] == "uv"
assert receipt["project"] == "target"
assert receipt["outcome"] == "ready"
assert receipt["attempts"] == 1
assert "proxy.example" not in json.dumps(receipt)
```

Add separate tests asserting:

- missing `pyproject.toml` or `uv.lock` returns `Outcome.CANDIDATE_INVALID` without running uv;
- failed `uv lock --check` returns candidate invalid and is not retried;
- a warm offline probe avoids the network-capable sync;
- an offline cache miss triggers at most two online sync attempts;
- two failed online attempts return `Outcome.INFRASTRUCTURE_FAILED`;
- `user:password@proxy.example` is redacted from the receipt reason; and
- the disposable `UV_PROJECT_ENVIRONMENT` directory is absent after every outcome.

- [ ] **Step 2: Run the focused tests and verify missing behavior**

Run: `uv run pytest -q tests/test_candidate_runtime.py`

Expected: FAIL because `prepare_candidate_runtime` is not defined.

- [ ] **Step 3: Implement uv preparation with one cheap offline probe and at most two online attempts**

Add constants and helpers:

```python
CONTAINER_UV_CACHE = "/opt/evolve/uv/cache"
CONTAINER_UV_PYTHON = "/opt/evolve/uv/python"
RECEIPT_NAME = "candidate-runtime.json"


def _digest_project(project: Path) -> str:
    digest = hashlib.sha256()
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        path = project / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _redact(message: str) -> str:
    return re.sub(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@", r"\1***:***@", message)[:2000]
```

Implement `prepare_candidate_runtime` with this control flow:

```python
def prepare_candidate_runtime(
    checkout: Path,
    run_dir: Path,
    runtime_root: Path,
    candidate_commit: str,
    evaluator: dict[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> CandidateRuntimeResult:
    config = candidate_runtime_config(checkout, evaluator)
    if config is None:
        return CandidateRuntimeResult(None, None)
    run_dir.mkdir(parents=True, exist_ok=True)
    project = config.project
    missing = [name for name in ("pyproject.toml", "uv.lock") if not (project / name).is_file()]
    if missing:
        return _finish_runtime(
            run_dir, config, Outcome.CANDIDATE_INVALID,
            f"candidate uv project missing {', '.join(missing)}", attempts=0,
            cache_warm=False, uv_version=None,
        )

    values = clean_python_env(env)
    uv = uv_executable(values)
    cache = Path(values.get("EVOLVE_UV_CACHE_DIR") or runtime_root / "uv-cache").resolve()
    python_dir = Path(
        values.get("EVOLVE_UV_PYTHON_INSTALL_DIR") or runtime_root / "uv-python"
    ).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    python_dir.mkdir(parents=True, exist_ok=True)
    temporary_environment = run_dir / ".candidate-runtime-venv"
    command_env = {
        **values,
        "UV_CACHE_DIR": str(cache),
        "UV_PYTHON_INSTALL_DIR": str(python_dir),
        "UV_PROJECT_ENVIRONMENT": str(temporary_environment),
    }
    try:
        checked = run_owned([uv, "lock", "--check", "--project", str(project)], cwd=checkout, env=command_env)
        if checked.returncode:
            return _finish_runtime(
                run_dir, config, Outcome.CANDIDATE_INVALID,
                _redact(checked.stderr or checked.stdout or "uv lock --check failed"),
                attempts=0, cache_warm=False, uv_version=_uv_version(uv, checkout, command_env),
            )
        sync = [uv, "sync", "--project", str(project), "--frozen", "--no-install-local"]
        offline = run_owned([*sync, "--offline"], cwd=checkout, env=command_env)
        cache_warm = offline.returncode == 0
        attempts = 1
        if not cache_warm:
            for attempts in (1, 2):
                shutil.rmtree(temporary_environment, ignore_errors=True)
                online = run_owned(sync, cwd=checkout, env=command_env)
                if online.returncode == 0:
                    break
            else:
                return _finish_runtime(
                    run_dir, config, Outcome.INFRASTRUCTURE_FAILED,
                    _redact(online.stderr or online.stdout or "uv dependency preparation failed"),
                    attempts=2, cache_warm=False, uv_version=_uv_version(uv, checkout, command_env),
                )
        return _finish_ready_runtime(
            run_dir, config, cache, python_dir,
            attempts=attempts, cache_warm=cache_warm,
            uv_version=_uv_version(uv, checkout, command_env),
        )
    finally:
        shutil.rmtree(temporary_environment, ignore_errors=True)
```

Implement `_finish_runtime` and `_finish_ready_runtime` to atomically write a sorted JSON receipt via a temporary sibling and `Path.replace`. Include only schema version, variant, project, candidate commit, candidate dependency digest, uv version, cache-warm boolean, attempt count, outcome, duration, and redacted reason. Do not serialize host environment variables or source cache listings.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest -q tests/test_candidate_runtime.py`

Expected: PASS.

- [ ] **Step 5: Run static checks for the new module**

Run: `uv run ruff check src/evolve/uv_runtime.py tests/test_candidate_runtime.py && uv run ty check`

Expected: PASS.

- [ ] **Step 6: Commit preparation**

```bash
git add src/evolve/uv_runtime.py tests/test_candidate_runtime.py
git commit -m "feat: prepare uv candidate runtimes"
```

---

### Task 3: Integrate candidate preparation into evaluation lifecycle

**Files:**
- Modify: `src/evolve/evaluation.py`
- Modify: `src/evolve/evaluator.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Consumes: `prepare_candidate_runtime(...) -> CandidateRuntimeResult`.
- Produces: evaluator environment variables `EVOLVE_CANDIDATE_RUNTIME_ENV_JSON` and `EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON`, plus `EvaluationRecord.candidate_runtime`.

- [ ] **Step 1: Write failing lifecycle tests**

Add tests that monkeypatch `evolve.evaluator.prepare_candidate_runtime` and assert:

```python
assert order == ["prepare", "eval"]
assert json.loads(captured_env["EVOLVE_CANDIDATE_RUNTIME_ENV_JSON"])["UV_OFFLINE"] == "1"
assert json.loads(captured_env["EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON"])[0]["target"] == "/opt/evolve/uv/cache"
```

Add a candidate-invalid preparation result and assert the evaluator script is not called, the resulting record is `Outcome.CANDIDATE_INVALID`, and its score is `None`. Repeat for infrastructure failure. Add an assertion that `record.to_dict()["candidate_runtime"]` contains the receipt path and SHA-256.

- [ ] **Step 2: Run the focused tests**

Run: `uv run pytest -q tests/test_m1_evaluator_invariants.py`

Expected: FAIL because evaluation does not prepare or archive candidate runtimes.

- [ ] **Step 3: Add the receipt field to `EvaluationRecord`**

```python
@dataclass(frozen=True)
class EvaluationRecord:
    # existing fields unchanged
    retry_of: int | None = None
    artifacts: dict[str, str] | None = None
    candidate_runtime: dict[str, str] | None = None
```

No custom serialization branch is required because `to_dict` already begins with `asdict(self)`.

- [ ] **Step 4: Prepare before `_run_eval_script` and short-circuit owned failures**

In `evaluate`, after `run_dir.mkdir(parents=True)` and before `_run_eval_script`, call:

```python
runtime = prepare_candidate_runtime(
    checkout,
    run_dir,
    workspace / "runs" / "runtime",
    candidate_commit,
    evaluator,
)
base["candidate_runtime"] = _runtime_receipt_reference(workspace, runtime.receipt_path)
if not runtime.ready:
    return classify_evaluation(
        **base,
        trials=(),
        setup_outcome=runtime.outcome,
        setup_reason=runtime.reason,
        benchmark_timeout_is_zero=timeout_zero,
        cost_usd=0.0,
        wall_s=time.monotonic() - start,
        artifacts=None,
    )
```

Extend `_run_eval_script` with a required `runtime: CandidateRuntimeResult` argument and set:

```python
env["EVOLVE_CANDIDATE_RUNTIME_ENV_JSON"] = runtime.environment_json()
env["EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON"] = runtime.mounts_json()
```

Implement `_runtime_receipt_reference` using the same relative-path containment and SHA-256 pattern as `_evaluation_artifact_reference`.

- [ ] **Step 5: Run focused tests and existing evaluator tests**

Run: `uv run pytest -q tests/test_candidate_runtime.py tests/test_m1_evaluator_invariants.py tests/test_evaluation_records.py`

Expected: PASS.

- [ ] **Step 6: Commit lifecycle integration**

```bash
git add src/evolve/evaluation.py src/evolve/evaluator.py tests/test_m1_evaluator_invariants.py
git commit -m "feat: prepare candidate runtime before evaluation"
```

---

### Task 4: Make Harbor consume the runtime contract and MiniSWE sync offline

**Files:**
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `templates/workspace/evolve_harbor_adapter/__init__.py`
- Modify: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: the two backend-neutral JSON environment variables from Task 3.
- Produces: Harbor `--mounts` and `--ae KEY=VALUE` arguments; MiniSWE task-local offline sync.

- [ ] **Step 1: Write failing Harbor contract tests**

Run the generated Harbor evaluator with:

```python
env["EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON"] = json.dumps([
    {"type": "bind", "source": str(cache), "target": "/opt/evolve/uv/cache", "read_only": False},
    {"type": "bind", "source": str(python_dir), "target": "/opt/evolve/uv/python", "read_only": False},
])
env["EVOLVE_CANDIDATE_RUNTIME_ENV_JSON"] = json.dumps({
    "UV_CACHE_DIR": "/opt/evolve/uv/cache",
    "UV_LINK_MODE": "copy",
    "UV_OFFLINE": "1",
    "UV_PYTHON_INSTALL_DIR": "/opt/evolve/uv/python",
})
```

Assert the captured Harbor arguments contain exactly that mount array and four agent environment entries. Assert no proxy value is used to change those uv settings.

Add separate smoke assertions:

- `EVOLVE_CANDIDATE_SMOKE_MODE=single` forces one task, one attempt, one worker;
- `EVOLVE_CANDIDATE_SMOKE_MODE=full` adds `--install-only`, forces one attempt, retains configured task count, and retains four workers.

- [ ] **Step 2: Write failing MiniSWE offline-sync tests**

Update the existing install test to require:

```python
sync_env = environment.envs[sync_index]
assert sync_env["UV_OFFLINE"] == "1"
assert sync_env["UV_LINK_MODE"] == "copy"
assert sync_env["UV_CACHE_DIR"] == "/opt/evolve/uv/cache"
assert sync_env["UV_PYTHON_INSTALL_DIR"] == "/opt/evolve/uv/python"
assert "http_proxy" not in sync_env
assert "https_proxy" not in sync_env
```

Assert the adapter runs exactly two offline uv sync phases in order:

```python
sync_commands = [command for command in environment.commands if "uv sync" in command]
assert len(sync_commands) == 2
assert "--no-install-local" in sync_commands[0]
assert "--no-install-local" not in sync_commands[1]
```

Make the fake environment fail each phase separately. The external-only phase must raise `EvolveRuntimeInfrastructureError` without `EVOLVE_CANDIDATE_INVALID`; the full local-project phase must raise `EvolveCandidateInvalidError` with `EVOLVE_CANDIDATE_INVALID: local_project_sync_failed`.

Keep the model execution assertions for `OPENAI_API_KEY` and `OPENAI_BASE_URL`; offline package installation must not disable model endpoint networking.

- [ ] **Step 3: Run focused tests and observe failures**

Run: `uv run pytest -q tests/test_harbor_evaluator_template.py tests/test_miniswe_harbor_wrapper.py`

Expected: FAIL because Harbor still builds one cache mount and the adapter still applies install proxies.

- [ ] **Step 4: Consume generic JSON in Harbor shell**

Replace the hard-coded `uv_mount` construction with:

```sh
runtime_mounts=${EVOLVE_CANDIDATE_RUNTIME_MOUNTS_JSON:-}
runtime_env=${EVOLVE_CANDIDATE_RUNTIME_ENV_JSON:-}
[ -n "$runtime_mounts" ] || runtime_mounts='[]'
[ -n "$runtime_env" ] || runtime_env='{}'
set -- "$@" --mounts "$runtime_mounts"
python3 - "$runtime_env" <<'PY' > "$EVOLVE_RUN_DIR/candidate-runtime.env"
import json, sys
values = json.loads(sys.argv[1])
if not isinstance(values, dict):
    raise SystemExit("candidate runtime environment must be an object")
for key, value in sorted(values.items()):
    if not isinstance(key, str) or not isinstance(value, str) or "\n" in key + value or "=" in key:
        raise SystemExit("invalid candidate runtime environment entry")
    print(f"{key}={value}")
PY
while IFS= read -r runtime_entry || [ -n "$runtime_entry" ]; do
  [ -n "$runtime_entry" ] && set -- "$@" --ae "$runtime_entry"
done < "$EVOLVE_RUN_DIR/candidate-runtime.env"
```

Keep the old single uv-cache mount only when the runtime JSON variables are absent, so existing workspaces remain runnable.

Implement `single` and `full` install-only behavior as specified in Step 1.

- [ ] **Step 5: Make MiniSWE installation consume offline runtime settings**

Add `UV_PYTHON_INSTALL_DIR = "/opt/evolve/uv/python"`, change the cache constant to `/opt/evolve/uv/cache`, and make `_install_env` return only model-independent runtime keys:

```python
def _install_env(self) -> dict[str, str]:
    return {
        "UV_CACHE_DIR": self._get_env("UV_CACHE_DIR") or UV_CACHE_DIR,
        "UV_LINK_MODE": self._get_env("UV_LINK_MODE") or "copy",
        "UV_OFFLINE": self._get_env("UV_OFFLINE") or "1",
        "UV_PYTHON_INSTALL_DIR": self._get_env("UV_PYTHON_INSTALL_DIR") or UV_PYTHON_INSTALL_DIR,
    }
```

The uv-binary fallback download remains only for legacy workspaces without the prepared contract; when `UV_OFFLINE=1`, a missing uploaded uv binary is an immediate setup error rather than a curl attempt.

Replace the single sync with two offline phases:

```python
await self._runtime_phase(
    environment,
    f"uv sync --project {SOURCE_DIR} --frozen --no-install-local",
    "offline_dependencies_missing",
    env=install_env,
)
await self._candidate_phase(
    environment,
    f"uv sync --project {SOURCE_DIR} --frozen",
    "local_project_sync_failed",
    env=install_env,
)
```

Define two `RuntimeError` subclasses in the adapter:

```python
class EvolveCandidateInvalidError(RuntimeError):
    pass


class EvolveRuntimeInfrastructureError(RuntimeError):
    pass
```

All candidate-marker branches, including missing project/lock/source and
`_candidate_phase`, raise `EvolveCandidateInvalidError`. `_runtime_phase`
catches the environment exception and raises
`EvolveRuntimeInfrastructureError("EVOLVE_RUNTIME_INFRASTRUCTURE: <code>")`.
The structural split classifies cache readiness separately from mutable local
build behavior without parsing uv stderr and gives Harbor distinct retryable
exception types.

Apply the same constants and environment behavior to `templates/target/harbor/miniswe_source_agent.py`.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest -q tests/test_harbor_evaluator_template.py tests/test_miniswe_harbor_wrapper.py`

Expected: PASS.

- [ ] **Step 7: Commit Harbor consumption**

```bash
git add templates/evaluator/engines/harbor.sh templates/workspace/evolve_harbor_adapter/__init__.py templates/target/harbor/miniswe_source_agent.py tests/test_harbor_evaluator_template.py tests/test_miniswe_harbor_wrapper.py
git commit -m "feat: consume prepared uv runtime in Harbor"
```

---

### Task 5: Narrow retries to Harbor trials and score repeated verifier timeout as zero

**Files:**
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/evaluation.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `templates/evaluator/harbor_artifacts.py`
- Modify: `templates/evaluator/parse_score.py`
- Modify: `tests/test_evaluation_lifecycle.py`
- Modify: `tests/test_harbor_artifacts.py`
- Modify: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: Harbor `--max-retries 1`, same-trial result replacement, and final `result.json` exception data.
- Produces: exactly one lifecycle evaluation attempt, one final result per planned Harbor trial, and scoreable `benchmark_verifier` timeout evidence.

- [ ] **Step 1: Replace the lifecycle retry expectation with a failing no-batch-replay test**

Replace `test_later_candidate_infrastructure_retries_same_commit_once` with:

```python
def test_candidate_infrastructure_failure_is_recorded_once_without_batch_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _lifecycle_workspace(
        tmp_path,
        {"genesis": ["benchmark_complete"], "candidate": ["infrastructure_failed", "benchmark_complete"]},
    )
    monkeypatch.setenv("EVOLVE_AGENT_COMMAND", smoke_agent_command())

    with pytest.raises(EvaluationPaused, match="infrastructure failed"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))

    attempts = _evaluation_events(workspace, "1")
    assert [event["attempt"] for event in attempts] == [1]
    assert attempts[0]["retry_of"] is None
```

- [ ] **Step 2: Add failing verifier-timeout and sibling-preservation parser tests**

Create a fake Harbor job with `config.json` containing `retry.max_retries: 1` and an exclude list that does not include `VerifierTimeoutError`. Add:

- one final verifier-timeout result with a completed `agent_result`;
- one successful sibling result; and
- exactly the expected two trial directories.

Assert the vector contains timeout reward `0.0`, owner `benchmark_verifier`, and the successful sibling unchanged. Add negative tests showing a verifier timeout remains infrastructure-owned when retries are disabled or no agent result exists. Run the parser with a nonzero Harbor return code and assert it still returns zero only when the complete final vector is scoreable; an incomplete vector must still return 3.

- [ ] **Step 3: Run focused tests and verify failures**

Run: `uv run pytest -q tests/test_evaluation_lifecycle.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py`

Expected: FAIL because the driver repeats the batch and the parser treats all verifier timeouts as infrastructure failures.

- [ ] **Step 4: Replace whole-evaluation retry with one lifecycle attempt**

Rename `_evaluate_with_one_infra_retry` to `_evaluate_once`, remove `retry_of`/resume logic, and keep append-before-reraise behavior:

```python
def _evaluate_once(... ) -> EvaluationRecord:
    try:
        record = evaluate(workspace, tag, genid, purpose=purpose)
    except EvaluationInterrupted as interrupted:
        record, cause = interrupted.args
        _append_lifecycle_evaluation(workspace, record, metadata, pending_gate_on_complete)
        raise cause
    _append_lifecycle_evaluation(workspace, record, metadata, pending_gate_on_complete)
    if record.outcome is Outcome.INFRASTRUCTURE_FAILED:
        raise EvaluationPaused(f"gen/{genid} infrastructure failed")
    return record
```

Update genesis and candidate call sites. Keep explicit `eval --force` behavior available to the user, but never invoke it automatically.

- [ ] **Step 5: Configure one Harbor retry without excluding verifier timeouts**

When `EVOLVE_HARBOR_MAX_RETRIES` is positive, add:

```sh
set -- "$@" --max-retries "$EVOLVE_HARBOR_MAX_RETRIES"
set -- "$@" --retry-exclude AgentTimeoutError
set -- "$@" --retry-exclude EvolveCandidateInvalidError
set -- "$@" --retry-exclude ApiUsageLimitError
```

Supplying this explicit exclude set replaces Harbor's default set, allowing `VerifierTimeoutError`, `EvolveRuntimeInfrastructureError`, and setup/environment exceptions to retry while excluding candidate-invalid proposals.

- [ ] **Step 6: Classify only a final post-retry verifier timeout as zero**

Load the Harbor job config once in `_load_task_trials` and pass a boolean into `_trial_result`:

```python
def _verifier_timeout_is_final_zero(jobs_dir: Path) -> bool:
    configs = [path for path in jobs_dir.glob("*/config.json") if path.parent.parent == jobs_dir]
    if len(configs) != 1:
        return False
    payload = json.loads(configs[0].read_text())
    retry = payload.get("retry") if isinstance(payload, dict) else None
    excluded = set((retry or {}).get("exclude_exceptions") or [])
    return int((retry or {}).get("max_retries") or 0) >= 1 and "VerifierTimeoutError" not in excluded


def _trial_result(result: dict[str, Any], *, verifier_timeout_is_final_zero: bool) -> tuple[str, float | None, str]:
    exception = result.get("exception_info") or {}
    exception_type = str(exception.get("exception_type") or "")
    if exception_type in {"AgentTimeoutError", "AgentExecutionTimeoutError"}:
        return "timeout", 0.0, "benchmark_agent"
    if (
        exception_type == "VerifierTimeoutError"
        and verifier_timeout_is_final_zero
        and result.get("agent_result") is not None
    ):
        return "timeout", 0.0, "benchmark_verifier"
    # existing candidate/infra/reward branches follow
```

Update `TrialResult.score_eligible` to accept timeout owners in `{"benchmark_agent", "benchmark_verifier"}` when `benchmark_timeout_is_zero` is enabled. Set `benchmark_timeout_is_zero: true` in the three real uv recipes in Task 6.

Update `_effective_outcome` so a canonical benchmark timeout is not overwritten merely because its retained diagnostic includes the original exception type:

```python
def _effective_outcome(trial: TrialResult) -> Outcome:
    if trial.outcome is Outcome.TIMEOUT and trial.owner in {"benchmark_agent", "benchmark_verifier"}:
        return Outcome.TIMEOUT
    if trial.exception_type or trial.exception_message:
        return Outcome.CANDIDATE_INVALID if trial.owner == "candidate" else Outcome.INFRASTRUCTURE_FAILED
    if trial.outcome is Outcome.CANDIDATE_INVALID and trial.owner != "candidate":
        return Outcome.INFRASTRUCTURE_FAILED
    return trial.outcome
```

In `parse_score.py`, remove the unconditional `harbor_rc != 0` failure branch. Always write artifacts first, then return complete only when the number of scoreable rewards equals `expected_trials`; include `harbor_rc` in metrics for diagnosis. In `harbor.sh`, remove `[ "$harbor_rc" -eq 0 ] || exit 3` and exit with `parser_rc`, so a complete canonical vector controls the evaluator outcome while incomplete or non-scoreable Harbor failures remain infrastructure failures.

- [ ] **Step 7: Run focused tests**

Run: `uv run pytest -q tests/test_evaluation_lifecycle.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py tests/test_evaluation_records.py`

Expected: PASS.

- [ ] **Step 8: Commit retry semantics**

```bash
git add src/evolve/driver.py src/evolve/evaluation.py templates/evaluator/engines/harbor.sh templates/evaluator/harbor_artifacts.py templates/evaluator/parse_score.py tests/test_evaluation_lifecycle.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py
git commit -m "fix: scope evaluation retries to Harbor trials"
```

---

### Task 6: Opt uv recipes in and freeze the generated-workspace contract

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hill_climb/evolve.yaml`
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `tests/test_config_parser.py`
- Modify: `docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md`

**Interfaces:**
- Consumes: evaluator `candidate_runtime` and existing `max_retries` rendering.
- Produces: generated workspaces that opt into uv preparation and one task retry.

- [ ] **Step 1: Write failing recipe assertions**

For each real uv recipe assert parsed YAML contains:

```python
assert evaluator["candidate_runtime"] == {"variant": "uv", "project": "target"}
assert evaluator["max_retries"] == 1
assert evaluator["benchmark_timeout_is_zero"] is True
```

Assert smoke recipes with `builtin-dummy` do not opt in.

- [ ] **Step 2: Run recipe tests and verify failure**

Run: `uv run pytest -q tests/test_phase_e_recipes.py tests/test_config_parser.py`

Expected: FAIL because the candidate runtime blocks are absent and HyperAgents has no task retry.

- [ ] **Step 3: Add the runtime block to real uv recipes**

```yaml
evaluator:
  engine: harbor
  candidate_runtime: {variant: uv, project: target}
  max_retries: 1
  benchmark_timeout_is_zero: true
```

Retain AHE `k: 2`, HyperAgents `k: 1`, both `n_concurrent: 4`, and every previously approved full-benchmark field.

Verify workspace initialization preserves the nested runtime mapping in `evolve.yaml`; no `workspace.py` change is expected because `_runtime_config` already deep-copies evaluator fields. Do not flatten proxy or runtime paths into committed configuration.

- [ ] **Step 4: Update the experiment design**

Add a launch-prerequisite paragraph linking the offline uv runtime design, state that dependency preparation runs once per candidate, and replace the earlier problematic smoke set with the four official easy tasks:

```text
cobol-modernization
fix-git
overfull-hbox
prove-plus-comm
```

Clarify that the two smoke experiments are one-time pre-launch gates, not per-generation work.

- [ ] **Step 5: Run recipe and workspace-generation tests**

Run: `uv run pytest -q tests/test_phase_e_recipes.py tests/test_config_parser.py tests/test_m0_init.py`

Expected: PASS.

- [ ] **Step 6: Commit recipe adoption**

```bash
git add recipes/ahe/evolve.yaml recipes/hyperagents/evolve.yaml recipes/hill_climb/evolve.yaml tests/test_phase_e_recipes.py tests/test_config_parser.py docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md
git commit -m "feat: enable uv candidate runtime in real recipes"
```

---

### Task 7: Verify locally and run both DevBoxS pre-launch smoke experiments

**Files:**
- Modify only if evidence changes documentation: `docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md`
- Runtime artifacts only on DevBoxS under a new unique experiment root.

**Interfaces:**
- Consumes: committed Tasks 1–6, the official 89-task dataset at commit `2fd12b88aafdd04a52c298e3940bcb189f9766d6`, pre-pulled `alexgshaw/<task>:20251031` images, and server-side credentials.
- Produces: passing local suite, 89-image install-only evidence, and completed AHE/HyperAgents generation-0 plus two-child smoke evidence.

- [ ] **Step 1: Run the complete local verification suite**

Run:

```bash
uv run ruff check .
uv run ty check
uv run pytest -q
```

Expected: all commands exit 0; the pytest count is at least the current 247 tests plus the new tests.

- [ ] **Step 2: Confirm the worktree is clean and deploy an immutable source snapshot**

Run: `git status --short && git rev-parse HEAD`

Expected: empty status and a recorded commit SHA.

Archive the committed tree, copy it to a new DevBoxS source directory, and verify its digest. Do not modify or reuse the current v5 experiment workspaces.

- [ ] **Step 3: Stop only the obsolete v5 drivers and clean their owned Harbor resources**

Read each v5 `driver.pid`, verify its command line belongs to the exact v5 AHE or HyperAgents workspace, send `TERM` to its process group, wait for exit, and run that workspace's `evaluator/cleanup_harbor.py` against its own job directories. Do not remove unrelated containers or Docker networks.

- [ ] **Step 4: Build the official-easy smoke dataset**

Create a new dataset directory by copying exactly these official task directories from the immutable 89-task dataset:

```text
cobol-modernization
fix-git
overfull-hbox
prove-plus-comm
```

Assert it contains exactly four `task.toml` files and that all four corresponding pre-pulled images exist.

- [ ] **Step 5: Run Smoke 1 once across all 89 images without LLM calls**

Initialize one real uv workspace from the committed source and seed. Source the server credential file without printing it, set `EVOLVE_CANDIDATE_SMOKE_MODE=full`, retain four Harbor workers, and run the evaluator against the full immutable dataset.

Success assertions:

```text
89 expected installs
89 completed import preflights
0 model calls
0 image pulls
0 setup timeouts
0 missing offline artifacts
candidate-runtime.json outcome == ready
exactly one candidate preparation receipt
```

Inspect setup-duration distribution and require no task-local sync to reach the configured setup timeout. If any image fails compatibility, stop before Smoke 2 and diagnose that exact image/runtime boundary.

- [ ] **Step 6: Run Smoke 2 concurrently for AHE and HyperAgents**

Initialize new uniquely named AHE and HyperAgents workspaces against the four-task easy dataset. Launch both persistent drivers concurrently with four workers each and `--max-generations 2`.

Success assertions for each method:

```text
generation 0 plus generations 1 and 2 recorded
complete expected task vector for every candidate
AHE uses k=2; HyperAgents uses k=1
no infrastructure_failed evaluation event
no retry_of lifecycle event
one candidate-runtime.json per evaluated candidate
valid meta-agent artifact for each child generation
no experiment-owned process, container, or network remains afterward
```

Scores may be zero and are not a smoke failure.

- [ ] **Step 7: Re-run local verification after any smoke-driven correction**

If Smoke 1 or Smoke 2 exposed a code defect, return to the relevant task, add a failing regression test, implement one correction, then rerun:

```bash
uv run ruff check .
uv run ty check
uv run pytest -q
```

Expected: PASS before redeploying a new immutable source snapshot. Never patch the deployed server source in place.

- [ ] **Step 8: Commit evidence-only documentation changes if needed**

```bash
git add docs/superpowers/specs/2026-07-20-ahe-hyperagents-terminal-bench-2-experiment-design.md
git commit -m "docs: record offline runtime smoke evidence"
```

Skip this commit when the existing design already captures all observed evidence.

---

## Completion Criteria

- A uv candidate is prepared once before each evaluation, regardless of task count or `k`.
- Isolated candidate sync is offline and installs the current local source.
- Changed valid lockfiles are honored; stale lockfiles are candidate invalid.
- Registry/proxy/cache failures are infrastructure-owned and never scored.
- Candidate-runtime receipts are archived without secrets.
- Harbor retries only the failed planned trial and preserves completed siblings.
- The driver never automatically repeats a complete evaluation batch.
- A repeated verifier timeout after agent completion contributes reward zero.
- All local tests and static checks pass.
- The 89-image install-only smoke and concurrent two-method evolution smoke pass before the full experiments launch.
