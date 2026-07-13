# MiniSWE Candidate Runtime and Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every MiniSWE candidate use its committed dependency lock, materialize that environment once per Harbor container with a shared uv cache, run the resulting virtualenv directly, and offer the meta-agent an optional protected smoke command that reports sanitized environment feedback.

**Architecture:** Keep dependency admission and smoke orchestration in one small host-side module, `evolve.candidate_runtime`. Keep container-specific setup in the existing MiniSWE Harbor wrapper and cache mounting in the existing Harbor evaluator shell. The optional smoke command invokes that same Harbor setup path in install-only mode; it does not introduce another installer or become a mandatory generation gate.

**Tech Stack:** Python 3.11+, Typer, uv, pytest, POSIX shell, Harbor custom agents, Docker bind mounts.

## Global Constraints

- Work only in `/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening` on `codex/framework-hardening`.
- Preserve unrelated changes, especially `.superpowers/sdd/task-2-report.md`.
- Write each regression test before the implementation that makes it pass.
- Never print `.env`, API keys, tokens, proxy URLs, or raw inherited environment mappings.
- Never regenerate `target/uv.lock` during candidate admission, smoke, or evaluation.
- Never install an ad hoc package inside a running benchmark trial.
- Never run plain `uv run --project /installed-agent/miniswe-source` in a trial.
- Keep `target/harbor_agent.py`, evaluator files, and `.evolve/` outside the mutable surface for every recipe.
- The smoke command is advisory. A candidate may be admitted without running it, but normal Harbor setup must still use frozen materialization and direct virtualenv execution.
- `candidate-smoke --full` initializes the configured LiteLLM path but makes no model API request.
- Optimize for the one-machine workflow: use one shared host uv cache; do not add cross-machine cache transfer or distributed cache coordination.
- Do not push. Commit only coherent local changes.

---

## File Ownership

| Concern | Owning file |
|---|---|
| Project/lock validation, runtime fingerprints, smoke attempt orchestration | `src/evolve/candidate_runtime.py` |
| Seed lock preservation and init rejection | `src/evolve/workspace.py` |
| Candidate admission before commit/tag | `src/evolve/driver.py` |
| Protected candidate wrapper | `src/evolve/surface.py` |
| Frozen sync, preflight, direct Python, proxy split | `templates/target/harbor/miniswe_source_agent.py` |
| Shared cache mount and install-only Harbor mode | `templates/evaluator/engines/harbor.sh` |
| Stable install-only result classification | `templates/evaluator/parse_smoke.py` |
| Safe in-container runtime facts and materialization records | `templates/evaluator/harbor_artifacts.py`, `src/evolve/candidate_runtime.py` |
| Shared cache path propagation | `src/evolve/evaluator.py` |
| Protected CLI entry point | `src/evolve/cli.py` |
| Optional meta-agent guidance | `templates/workspace/operators/meta_agent.md`, `templates/workspace/operators/meta_agent_brief.md`, `library/meta_agent/agent_command.py`, `library/meta_agent/hyperagents.py`, `library/meta_agent/prompts/ahe_evolve.md` |

---

## Task 1: Enforce the MiniSWE project/lock contract

**Files:**

- Create: `src/evolve/candidate_runtime.py`
- Modify: `src/evolve/workspace.py`
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/surface.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_manual_commit.py`
- Modify: `tests/test_m5_driver_operators.py`
- Modify: `tests/test_patching.py`
- Create: `tests/test_candidate_runtime.py`

### Step 1: Add locked MiniSWE test fixtures

- [ ] Add a helper in `tests/conftest.py` that writes the smallest valid MiniSWE-style project and generates its lock once with uv:

```python
def write_locked_miniswe_seed(path: Path, *, dependencies: list[str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    deps = dependencies or []
    (path / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"mini-swe-agent\"\n"
        "version = \"0.0.0\"\n"
        "requires-python = \">=3.11\"\n"
        f"dependencies = {json.dumps(deps)}\n"
    )
    package = path / "src" / "minisweagent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("\n")
    subprocess.run(
        ["uv", "lock", "--offline", "--project", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return path
```

- [ ] Replace hand-written MiniSWE seed fixtures that omit `uv.lock` with this helper. Do not weaken non-MiniSWE fixtures.

### Step 2: Write failing init and validation tests

- [ ] In `tests/test_m0_init.py`, add:

```python
def test_init_preserves_miniswe_uv_lock_byte_for_byte(tmp_path: Path) -> None:
    seed = write_locked_miniswe_seed(tmp_path / "seed")
    expected = (seed / "uv.lock").read_bytes()
    workspace = tmp_path / "workspace"

    init_workspace(InitOptions(workspace=workspace, recipe="hill_climb", seed=str(seed)))

    assert (workspace / "target" / "uv.lock").read_bytes() == expected


def test_init_rejects_miniswe_seed_without_uv_lock(tmp_path: Path) -> None:
    seed = write_locked_miniswe_seed(tmp_path / "seed")
    (seed / "uv.lock").unlink()

    with pytest.raises(CandidateDependencyError, match="uv.lock is required"):
        init_workspace(InitOptions(workspace=tmp_path / "workspace", recipe="hill_climb", seed=str(seed)))
```

- [ ] In `tests/test_candidate_runtime.py`, add direct contract tests:

```python
def test_validate_rejects_project_change_without_lock_change(tmp_path: Path) -> None:
    checkout = initialized_miniswe_workspace(tmp_path)
    project = checkout / "target" / "pyproject.toml"
    project.write_text(project.read_text().replace("dependencies = []", 'dependencies = ["idna"]'))

    with pytest.raises(CandidateDependencyError) as exc:
        validate_miniswe_candidate(checkout, changed_paths=["target/pyproject.toml"])

    assert exc.value.code == "project_changed_without_lock"


def test_validate_rejects_incompatible_lock_without_mutating_it(tmp_path: Path) -> None:
    checkout = initialized_miniswe_workspace(tmp_path)
    project = checkout / "target" / "pyproject.toml"
    project.write_text(project.read_text().replace("dependencies = []", 'dependencies = ["idna"]'))
    before = (checkout / "target" / "uv.lock").read_bytes()

    with pytest.raises(CandidateDependencyError) as exc:
        validate_miniswe_candidate(
            checkout,
            changed_paths=["target/pyproject.toml", "target/uv.lock"],
        )

    assert exc.value.code == "lock_incompatible"
    assert (checkout / "target" / "uv.lock").read_bytes() == before
```

- [ ] Add a positive test showing a compatible lock-only update is accepted. This avoids treating file timestamps or lock rewrites as proof of incompatibility.

### Step 3: Confirm the tests fail for the intended reasons

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_m0_init.py \
  tests/test_candidate_runtime.py \
  -q
```

Expected: imports or assertions fail because `CandidateDependencyError` and `validate_miniswe_candidate` do not exist, and init does not require a lock.

### Step 4: Implement the small host-side contract module

- [ ] Create `src/evolve/candidate_runtime.py` with only pure validation/fingerprint helpers at this stage:

```python
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class CandidateDependencyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CandidateDependencyIdentity:
    project_sha256: str
    lock_sha256: str

    @property
    def digest(self) -> str:
        payload = f"{self.project_sha256}\n{self.lock_sha256}\n".encode()
        return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_miniswe_candidate(
    checkout: Path,
    *,
    changed_paths: Iterable[str] = (),
) -> CandidateDependencyIdentity:
    target = checkout / "target"
    project = target / "pyproject.toml"
    lock = target / "uv.lock"
    changed = set(changed_paths)
    if not project.is_file():
        raise CandidateDependencyError("project_missing", "target/pyproject.toml is required")
    if not lock.is_file():
        raise CandidateDependencyError("lock_missing", "target/uv.lock is required")
    if "target/pyproject.toml" in changed and "target/uv.lock" not in changed:
        raise CandidateDependencyError(
            "project_changed_without_lock",
            "target/pyproject.toml changed without target/uv.lock",
        )
    completed = subprocess.run(
        ["uv", "lock", "--check", "--offline", "--project", str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise CandidateDependencyError(
            "lock_incompatible",
            "target/uv.lock does not match target/pyproject.toml",
        )
    return CandidateDependencyIdentity(_sha256(project), _sha256(lock))
```

The exception must contain a stable code and a short safe message. Do not attach uv stdout/stderr because index URLs may contain credentials.

### Step 5: Enforce validation at init and both admission paths

- [ ] In `src/evolve/workspace.py`, call `validate_miniswe_candidate(workspace)` immediately after vendoring a MiniSWE source target and before writing `target/harbor_agent.py`. `shutil.copytree` already preserves `uv.lock`; the new test makes that behavior contractual.

- [ ] In `src/evolve/driver.py`, call validation after surface validation and before commit/tag in both paths:

```python
changed = working_tree_changed_paths(child_worktree, parent_ref)
check_candidate_surface(child_worktree, changed)
validate_miniswe_candidate(child_worktree, changed_paths=changed)
```

Use the existing target-kind/config check so non-MiniSWE targets are unchanged. Do not infer MiniSWE solely from a random `pyproject.toml`.

- [ ] Add one automatic-driver test and one manual-commit test proving an incompatible pair is rejected before a generation tag or archive row can be created.

### Step 6: Protect evaluator-owned wrapper machinery globally

- [ ] In `src/evolve/surface.py`, extend the implicit exclusions:

```python
IMPLICIT_EXCLUDES = (
    "evaluator/**",
    "target/harbor_agent.py",
    "archive.jsonl",
    ".evolve/**",
    "evolve",
)
```

- [ ] Add a generic surface test in `tests/test_patching.py` showing that `target/harbor_agent.py` is rejected even when a recipe says `include: ["target/**"]` and has no explicit exclusion.

### Step 7: Run focused tests and commit

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_candidate_runtime.py \
  tests/test_m0_init.py \
  tests/test_manual_commit.py \
  tests/test_m5_driver_operators.py \
  tests/test_patching.py \
  -q
```

Expected: all pass; missing, stale, and unprotected dependency states fail with stable candidate errors.

- [ ] Commit:

```bash
git add src/evolve/candidate_runtime.py src/evolve/workspace.py src/evolve/driver.py src/evolve/surface.py tests
git commit -m "Enforce MiniSWE dependency locks"
```

---

## Task 2: Materialize once and execute the virtualenv directly

**Files:**

- Modify: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `tests/test_miniswe_harbor_wrapper.py`

### Step 1: Replace old command expectations with failing runtime-contract tests

- [ ] Update `tests/test_miniswe_harbor_wrapper.py` so the generated wrapper must contain:

```python
assert "uv sync --project /installed-agent/miniswe-source --frozen" in text
assert "/installed-agent/miniswe-source/.venv/bin/python" in text
assert "uv run --project /installed-agent/miniswe-source" not in text
assert "uv.lock" in text
```

- [ ] Add behavioral tests using the existing fake `exec_as_agent` recorder:

```python
async def test_install_syncs_frozen_once_before_preflight(agent) -> None:
    await agent.install()
    commands = agent.recorded_commands
    assert sum("uv sync" in command for command in commands) == 1
    assert next(i for i, command in enumerate(commands) if "uv sync" in command) < next(
        i for i, command in enumerate(commands) if "EVOLVE_PREFLIGHT" in command
    )


async def test_run_uses_materialized_python_without_uv(agent) -> None:
    await agent.run(task="test")
    assert agent.recorded_commands[-1].startswith(
        "/installed-agent/miniswe-source/.venv/bin/python "
    )
    assert "uv run" not in agent.recorded_commands[-1]
```

- [ ] Add explicit failure tests:

  - missing `uv.lock` raises `EVOLVE_CANDIDATE_INVALID: lock_missing`;
  - frozen sync failure raises `EVOLVE_CANDIDATE_INVALID: frozen_sync_failed`;
  - a simulated LiteLLM build failure is classified as `frozen_sync_failed`;
  - MiniSWE import failure raises `EVOLVE_CANDIDATE_INVALID: miniswe_import_failed`;
  - configured LiteLLM initialization failing with `ModuleNotFoundError("fastapi")` raises `EVOLVE_CANDIDATE_INVALID: model_path_import_failed`.

- [ ] Add an offline warm-cache test where the fake uv command rejects all network access but frozen sync succeeds against a populated cache. Assert the wrapper does not add `--offline` to normal cold setup; offline mode is a test of cache completeness, not the production default.

### Step 2: Confirm failures

- [ ] Run:

```bash
uv run --frozen pytest tests/test_miniswe_harbor_wrapper.py -q
```

Expected: the old wrapper still contains per-trial `uv run`, does not require a lock, and has no stable phase errors.

### Step 3: Make phases explicit in the wrapper

- [ ] In `templates/target/harbor/miniswe_source_agent.py`, define these constants:

```python
SOURCE = "/installed-agent/miniswe-source"
UV_CACHE = "/installed-agent/uv-cache"
VENV_PYTHON = f"{SOURCE}/.venv/bin/python"
RUNNER = "/installed-agent/run_miniswe.py"
```

- [ ] Extend source validation to require both dependency files:

```python
for name in ("pyproject.toml", "uv.lock"):
    if not (source / name).is_file():
        raise RuntimeError(f"EVOLVE_CANDIDATE_INVALID: {name.removesuffix('.toml').replace('.', '_')}_missing")
```

Use an explicit mapping so `uv.lock` produces `lock_missing`, not a string-derived spelling.

- [ ] Add a helper that converts only known candidate phases to stable exceptions:

```python
async def _candidate_phase(self, command: str, code: str, *, env: dict[str, str] | None = None) -> None:
    try:
        await self._environment.exec_as_agent(command, env=env)
    except Exception:
        raise RuntimeError(f"EVOLVE_CANDIDATE_INVALID: {code}") from None
```

Do not wrap uv bootstrap, Docker upload, or system package installation with this helper; failures there remain infrastructure/setup failures.

### Step 4: Split installation and runtime environments

- [ ] Keep a small installation environment containing only uv cache and explicitly configured installation proxies:

```python
def _install_env(self) -> dict[str, str]:
    env = {"UV_CACHE_DIR": UV_CACHE}
    for name in PROXY_NAMES:
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env
```

- [ ] Keep model/runtime propagation allow-listed. It may include model name, explicit endpoint variables, and API credential names, but it must actively unset generic proxies:

```python
def _runtime_env(self) -> dict[str, str]:
    env = {name: value for name in MODEL_ENV_NAMES if (value := os.environ.get(name))}
    env.update({name: "" for name in PROXY_NAMES})
    return env
```

`PROXY_NAMES` must contain uppercase and lowercase `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`. Do not log either environment mapping.

- [ ] Add a test that installation sees proxy variables while preflight and `run()` see empty proxy values, and that `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and the configured model name still reach runtime.

### Step 5: Frozen sync, import, and model-path preflight

- [ ] During `install()`, after source upload and uv bootstrap, run exactly once:

```python
await self._candidate_phase(
    f"uv sync --project {SOURCE} --frozen",
    "frozen_sync_failed",
    env=self._install_env(),
)
```

- [ ] Run the preflight with `VENV_PYTHON`, never with uv. Put the preflight body in a checked-in string constant so tests can inspect it. Its behavior must be:

```python
import importlib
import os

importlib.import_module("minisweagent")
print("EVOLVE_PREFLIGHT: miniswe_import_ok")

if os.environ.get("EVOLVE_CANDIDATE_SMOKE_MODE") != "container":
    from minisweagent.config import get_config_from_spec
    from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

    config = get_config_from_spec(os.environ.get("MINISWE_CONFIG", "mini"))
    model_kwargs = {
        key: value
        for key, value in dict(config.get("model") or {}).items()
        if key in LitellmModelConfig.model_fields
    }
    model_kwargs["model_name"] = os.environ["MSWEA_MODEL_NAME"]
    model_kwargs["cost_tracking"] = "ignore_errors"
    LitellmModel(**model_kwargs)
    print("EVOLVE_PREFLIGHT: model_path_init_ok")
```

This is the same config and `LitellmModel` construction path already used by `RUNNER`, stopped before `DefaultAgent.run()`. Keep those two snippets structurally aligned with a regression test. It must not call LiteLLM completion or make a network request.

- [ ] Separate MiniSWE import and model-path initialization into two commands or two caught blocks so `miniswe_import_failed` and `model_path_import_failed` are unambiguous without traceback parsing.

- [ ] After sync, write `/logs/agent/evolve-runtime.json` using `VENV_PYTHON`. The file is safe framework evidence and contains only:

```json
{
  "schema_version": 1,
  "candidate_tree_sha256": "...",
  "project_sha256": "...",
  "lock_sha256": "...",
  "python_version": "3.x.y",
  "python_abi": "cpython-3xx-...",
  "platform": "...",
  "uv_version": "0.x.y",
  "task_image_identity": "sha256:...",
  "dependency_cache_hit": false,
  "install_proxy_present": true,
  "runtime_proxy_present": false
}
```

Compute `candidate_tree_sha256` from sorted candidate source paths and bytes, excluding `.venv`. Compute `task_image_identity` inside the actual task container from the normalized `/etc/os-release` bytes plus Python's platform/ABI values; this is deliberately local-machine identity, not a portable registry attestation. Compute `dependency_cache_hit` from a marker under `/installed-agent/uv-cache/evolve-graphs/<project-lock-digest>` that is checked before sync and created only after successful sync. Store only proxy-presence booleans, never values.

- [ ] Add wrapper tests proving the evidence file is created only after frozen sync, contains no supplied sentinel secrets, and reports a cache hit on a second materialization with the same project/lock digest.

### Step 6: Execute direct Python for task writing and runtime

- [ ] Replace every source-side Python launch with `VENV_PYTHON`:

```python
await self._environment.exec_as_agent(
    f"{VENV_PYTHON} {RUNNER}",
    env=self._runtime_env(),
)
```

If task serialization currently uses Python, use the same interpreter. No code path after `install()` may invoke uv.

### Step 7: Run focused tests and commit

- [ ] Run:

```bash
uv run --frozen pytest tests/test_miniswe_harbor_wrapper.py -q
rg -n "uv run --project /installed-agent/miniswe-source" \
  templates/target/harbor/miniswe_source_agent.py tests
```

Expected: pytest passes and `rg` finds only negative test assertions, not a runtime command.

- [ ] Commit:

```bash
git add templates/target/harbor/miniswe_source_agent.py tests/test_miniswe_harbor_wrapper.py
git commit -m "Materialize MiniSWE candidates with frozen uv"
```

---

## Task 3: Reuse one uv cache and add the optional protected smoke command

**Files:**

- Modify: `src/evolve/candidate_runtime.py`
- Modify: `src/evolve/evaluator.py`
- Modify: `src/evolve/cli.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Create: `templates/evaluator/parse_smoke.py`
- Modify: `templates/evaluator/harbor_artifacts.py`
- Modify: `tests/test_candidate_runtime.py`
- Create: `tests/test_candidate_smoke.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `tests/test_harbor_artifacts.py`

### Step 1: Write failing cache-mount tests

- [ ] In `tests/test_harbor_evaluator_template.py`, extend the fake Harbor executable to record all arguments and mounted directories. Add:

```python
def test_harbor_mounts_one_shared_uv_cache_for_every_generation(workspace: Path) -> None:
    first = run_fake_harbor(workspace, genid="1")
    second = run_fake_harbor(workspace, genid="2")

    expected = workspace / "runs" / "runtime" / "uv-cache"
    assert first.mount_source("/installed-agent/uv-cache") == expected
    assert second.mount_source("/installed-agent/uv-cache") == expected
    assert expected.is_dir()
```

- [ ] Add a second assertion that the cache directory is not deleted between evaluator runs. The existing per-generation jobs directory may still be recreated.

- [ ] Add a materialization-record test: two successful trials with the same candidate/runtime facts must append attempts below the same `runs/runtime/candidates/<digest>/` directory; a changed lock or task image identity must use a different directory.

### Step 2: Write failing smoke parser and CLI tests

- [ ] In `tests/test_candidate_smoke.py`, cover the three modes:

```python
def test_quick_smoke_validates_pair_without_invoking_harbor(...): ...
def test_container_smoke_runs_one_install_only_harbor_task(...): ...
def test_full_smoke_requests_model_path_preflight_without_model_call(...): ...
```

- [ ] Add append-only artifact assertions:

```python
first = run_candidate_smoke(checkout, mode="quick", run_dir=run_dir)
second = run_candidate_smoke(checkout, mode="quick", run_dir=run_dir)
assert first.attempt_dir.name == "attempt-1"
assert second.attempt_dir.name == "attempt-2"
assert (first.attempt_dir / "result.json").exists()
```

- [ ] Add a redaction test with sentinel values in every proxy and credential variable. Assert no file under either attempt contains a sentinel.

- [ ] Add stable status tests for `templates/evaluator/parse_smoke.py`:

  - Harbor result with no exception and return code 0 -> `passed`, exit 0;
  - exception message beginning `EVOLVE_CANDIDATE_INVALID: frozen_sync_failed` -> `candidate_invalid`, exit 2;
  - missing result, timeout, or unrelated setup exception -> `infrastructure_failed`, exit 3;
  - `ModuleNotFoundError: fastapi` is only candidate-invalid when the wrapper supplied the stable `model_path_import_failed` marker; the parser never guesses from arbitrary traceback text.

### Step 3: Confirm failures

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_candidate_runtime.py \
  tests/test_candidate_smoke.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_artifacts.py \
  -q
```

Expected: no cache mount, smoke command, or smoke parser exists yet.

### Step 4: Propagate and mount a shared cache

- [ ] In `src/evolve/evaluator.py`, set one deterministic host path before invoking `evaluator/eval.sh`:

```python
env["EVOLVE_UV_CACHE_DIR"] = str(workspace / "runs" / "runtime" / "uv-cache")
```

Create it with mode `0o755`; do not clear it between generations.

- [ ] In `templates/evaluator/engines/harbor.sh`, add a bind mount to the existing Harbor argument list:

```sh
mkdir -p "$EVOLVE_UV_CACHE_DIR"
uv_mount=$(python3 -c 'import json,sys; print(json.dumps([{"type":"bind","source":sys.argv[1],"target":"/installed-agent/uv-cache"}]))' "$EVOLVE_UV_CACHE_DIR")
set -- "$@" --mounts "$uv_mount"
```

Keep JSON construction in Python to avoid shell escaping bugs. Mount the same path for normal evaluation and smoke. Do not mount the candidate virtualenv; each task container materializes its own `.venv` from the shared package cache.

### Step 5: Add a narrow install-only Harbor path

- [ ] In `templates/evaluator/engines/harbor.sh`, branch only at argument finalization and result parsing:

```sh
if [ -n "${EVOLVE_CANDIDATE_SMOKE_MODE:-}" ]; then
  jobs_dir=$EVOLVE_CANDIDATE_SMOKE_JOBS_DIR
  set -- "$@" --install-only --ae "EVOLVE_CANDIDATE_SMOKE_MODE=$EVOLVE_CANDIDATE_SMOKE_MODE"
fi
```

The host smoke runner must also set task limit, attempts, and concurrency to one. Reject a missing smoke jobs directory rather than falling back to the normal evaluator jobs directory.

- [ ] After Harbor exits, keep the normal `parse_score.py` path unchanged. For smoke only, call:

```sh
python3 evaluator/parse_smoke.py "$jobs_dir" "$EVOLVE_RUN_DIR/harbor-result.json" "$harbor_rc"
exit $?
```

### Step 6: Implement explicit smoke result parsing

- [ ] In `templates/evaluator/harbor_artifacts.py`, expose the existing explicit exception-marker classification as a public helper, for example:

```python
def classify_exception_info(exception_info: object) -> tuple[str, str] | None:
    """Return (owner, stable_category), or None when no exception is present."""
```

Keep existing benchmark classification behavior unchanged.

- [ ] Create `templates/evaluator/parse_smoke.py`. It must recursively read Harbor `result.json` files, use `classify_exception_info`, and write only this safe schema:

```json
{
  "schema_version": 1,
  "status": "passed | candidate_invalid | infrastructure_failed",
  "owner": "candidate | infrastructure | none",
  "category": "frozen_sync_failed | model_path_import_failed | ... | none",
  "harbor_returncode": 0,
  "trial_results_seen": 1
}
```

Do not copy exception messages, commands, environment dictionaries, or Harbor logs into this JSON. Copy the allow-listed fields from `/logs/agent/evolve-runtime.json` when present. Exit 0, 2, or 3 according to the status.

### Step 7: Extend the host module with append-only smoke orchestration

- [ ] In `src/evolve/candidate_runtime.py`, add:

```python
SmokeMode = Literal["quick", "container", "full"]


@dataclass(frozen=True)
class CandidateSmokeResult:
    status: str
    mode: SmokeMode
    attempt_dir: Path
    dependency_digest: str


def run_candidate_smoke(
    checkout: Path,
    *,
    workspace: Path,
    run_dir: Path,
    mode: SmokeMode = "full",
) -> CandidateSmokeResult:
    identity = validate_miniswe_candidate(
        checkout,
        changed_paths=working_tree_changed_paths(checkout, head_tag(checkout) or "gen/0"),
    )
    attempt = _next_attempt(run_dir / "meta_agent" / "smoke")
    if mode == "quick":
        harbor = {"status": "passed", "owner": "none", "category": "none"}
    else:
        harbor = _run_harbor_install_only(checkout, workspace, attempt, mode)
    _write_sanitized_result(attempt / "result.json", identity, mode, harbor)
    return CandidateSmokeResult(harbor["status"], mode, attempt, identity.digest)
```

Implementation details:

- `_next_attempt` creates the first absent `attempt-N` with `mkdir(exist_ok=False)`.
- `_run_harbor_install_only` invokes `evaluator/eval.sh` from the candidate checkout with a minimal copied environment plus the existing model endpoint/credential allow-list. It sets `EVOLVE_TASK_LIMIT=1`, `EVOLVE_HARBOR_N=1`, `EVOLVE_HARBOR_ATTEMPTS=1`, and `EVOLVE_HARBOR_N_CONCURRENT=1`.
- It sets `EVOLVE_UV_CACHE_DIR` to `workspace/runs/runtime/uv-cache` and `EVOLVE_CANDIDATE_SMOKE_JOBS_DIR` beneath the attempt directory.
- It never reads or writes `.env`; the evaluator shell remains responsible for its normal configuration sourcing.
- It reads `harbor-result.json`, adds only dependency hashes, mode, timestamps, and phase booleans, then writes `result.json` atomically.
- For successful container/full smoke, it combines candidate tree, project, lock, Python/ABI, platform, uv, and task-image identities into a deterministic materialization digest. It writes an append-only reference under `workspace/runs/runtime/candidates/<digest>/attempts/`; the record contains metadata and outcomes, never a virtualenv or secret.
- For `container`, the wrapper skips only LiteLLM initialization. For `full`, it performs all preflight imports and initialization without a request.
- Return status is advisory. The function does not tag, archive, or invalidate a generation by itself.

- [ ] Extend normal Harbor artifact collection to copy the same allow-listed runtime facts to `EVOLVE_RUN_DIR/candidate_runtime.json`, then call the same `record_materialization(...)` helper from `src/evolve/evaluator.py`. This makes training/evaluation records and optional-smoke records use one schema and one digest function. Keep the existing `RuntimeFingerprint` for evaluator-capsule epochs unchanged; the candidate materialization digest is nested evidence, not a replacement epoch.

### Step 8: Add the protected CLI command

- [ ] In `src/evolve/cli.py`, add:

```python
@app.command("candidate-smoke")
@_guard
def candidate_smoke(
    quick: bool = typer.Option(False, "--quick"),
    container: bool = typer.Option(False, "--container"),
    full: bool = typer.Option(False, "--full"),
    checkout: Path = typer.Option(Path("."), "--checkout"),
) -> None:
    mode = select_smoke_mode(quick=quick, container=container, full=full)
    result = run_candidate_smoke(
        checkout.resolve(),
        workspace=Path(os.environ.get("EVOLVE_WORKSPACE", checkout)).resolve(),
        run_dir=Path(os.environ.get("EVOLVE_RUN_DIR", checkout / "runs" / "runtime")).resolve(),
        mode=mode,
    )
    print(f"candidate-smoke: {result.status} mode={result.mode} result={result.attempt_dir / 'result.json'}")
    if result.status == "candidate_invalid":
        raise typer.Exit(2)
    if result.status == "infrastructure_failed":
        raise typer.Exit(3)
```

`select_smoke_mode` rejects combinations such as `--quick --full`; no flag means `full`. Keep the output to one safe summary line.

### Step 9: Run focused tests and commit

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_candidate_runtime.py \
  tests/test_candidate_smoke.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_artifacts.py \
  -q
```

Expected: all pass, including two evaluations sharing the same cache and two smoke attempts producing separate artifacts.

- [ ] Commit:

```bash
git add \
  src/evolve/candidate_runtime.py \
  src/evolve/evaluator.py \
  src/evolve/cli.py \
  templates/evaluator/engines/harbor.sh \
  templates/evaluator/parse_smoke.py \
  templates/evaluator/harbor_artifacts.py \
  tests
git commit -m "Add protected MiniSWE candidate smoke"
```

---

## Task 4: Tell meta-agents when and how to use smoke

**Files:**

- Modify: `templates/workspace/operators/meta_agent.md`
- Modify: `templates/workspace/operators/meta_agent_brief.md`
- Modify: `library/meta_agent/agent_command.py`
- Modify: `library/meta_agent/hyperagents.py`
- Modify: `library/meta_agent/prompts/ahe_evolve.md`
- Modify: `library/PROTOCOL.md`
- Modify: `tests/test_agent_command_meta_agent.py`
- Modify: `tests/test_hyperagents_meta_agent.py`
- Modify: `tests/test_ahe_meta_agent.py`

### Step 1: Write failing prompt tests

- [ ] For agent-command, HyperAgents, and AHE, assert their built prompt contains all four ideas:

```python
assert "candidate-smoke" in prompt
assert "optional" in prompt.lower()
assert "do not edit" in prompt.lower()
assert "no model request" in prompt.lower()
```

- [ ] Assert the guidance does not say smoke is required for admission and does not invite direct uv/pip installation.

### Step 2: Confirm failures

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_agent_command_meta_agent.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_ahe_meta_agent.py \
  -q
```

Expected: prompt assertions fail because the command is not mentioned.

### Step 3: Add one concise guidance paragraph to each prompt path

- [ ] Use this wording, adjusted only for surrounding grammar:

```text
Environment feedback is optional. When dependency or runtime uncertainty is relevant, you may run the protected command `./evolve candidate-smoke --full`. Read its sanitized result artifact; do not edit the command, evaluator, Harbor wrapper, lock, or environment machinery, and do not install packages manually. Full smoke initializes the configured model path but makes no model request. A smoke failure is evidence to diagnose, not permission to modify evaluator-owned files.
```

- [ ] Put the generic copy in `templates/workspace/operators/meta_agent.md` and `meta_agent_brief.md`.
- [ ] Ensure the agent-command and HyperAgents builders include it for already-initialized workspaces, where the template text may predate this change.
- [ ] Add the same rule to AHE's custom prompt because it does not rely solely on the generic builder.

Avoid a new prompt utility module for one paragraph. A short duplicated constant in the two Python builders is easier to read than another abstraction; tests keep the copies aligned.

### Step 4: Document the operator contract

- [ ] In `library/PROTOCOL.md`, add a short `candidate-smoke` section:

- `--quick`: project/lock validation only;
- `--container`: frozen sync plus MiniSWE import in one representative Harbor task image;
- `--full` (default): container checks plus configured LiteLLM path initialization, no API request;
- artifacts are append-only and sanitized;
- the command is optional and never modifies candidate source or the lock;
- exit 0 is pass, 2 is candidate dependency/runtime invalid, 3 is infrastructure failure.

### Step 5: Run focused tests and commit

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_agent_command_meta_agent.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_ahe_meta_agent.py \
  -q
```

- [ ] Commit:

```bash
git add \
  templates/workspace/operators/meta_agent.md \
  templates/workspace/operators/meta_agent_brief.md \
  library/meta_agent/agent_command.py \
  library/meta_agent/hyperagents.py \
  library/meta_agent/prompts/ahe_evolve.md \
  library/PROTOCOL.md \
  tests/test_agent_command_meta_agent.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_ahe_meta_agent.py
git commit -m "Guide meta-agents to optional runtime smoke"
```

---

## Task 5: Verify with focused tests, the full suite, and a real Harbor canary

**Files:**

- Modify only if verification exposes a defect in the preceding implementation.
- Create canary artifacts outside the repository or under the generated experiment workspace, never in source control.

### Step 1: Static forbidden-command and credential checks

- [ ] Run:

```bash
rg -n "uv run --project /installed-agent/miniswe-source" src templates library tests
rg -n "print\(.*(API_KEY|TOKEN|PASSWORD|PROXY)|pprint\(.*env|json\.dumps\(.*environ" src templates library
```

Expected: the first command finds only negative regression assertions or documentation saying the command is forbidden. The second finds no new secret-printing path.

### Step 2: Run all focused tests together

- [ ] Run:

```bash
uv run --frozen pytest \
  tests/test_candidate_runtime.py \
  tests/test_candidate_smoke.py \
  tests/test_miniswe_harbor_wrapper.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_harbor_artifacts.py \
  tests/test_m0_init.py \
  tests/test_manual_commit.py \
  tests/test_m5_driver_operators.py \
  tests/test_patching.py \
  tests/test_agent_command_meta_agent.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_ahe_meta_agent.py \
  -q
```

Expected: all pass.

### Step 3: Run lint and the full suite

- [ ] Run:

```bash
uv run --frozen ruff check src tests library templates
uv run --frozen pytest -q
```

Expected: zero lint errors and the full suite passes. Record exact counts and elapsed time in the handoff; do not summarize as merely “green.”

### Step 4: Build a no-push bundle for the real canary

- [ ] Commit any verification fixes locally, then create a temporary bundle without pushing:

```bash
git bundle create /tmp/framework-hardening-candidate-runtime.bundle codex/framework-hardening
scp /tmp/framework-hardening-candidate-runtime.bundle DevBoxS:/tmp/framework-hardening-candidate-runtime.bundle
```

- [ ] Open a shell with `ssh DevBoxS`. In that remote shell, clone the bundle into a new temporary directory and use the configured environment script without printing it:

```bash
set -eu
rm -rf /data00/home/zimuwang/canaries/framework-hardening-candidate-runtime
git clone /tmp/framework-hardening-candidate-runtime.bundle /data00/home/zimuwang/canaries/framework-hardening-candidate-runtime
cd /data00/home/zimuwang/canaries/framework-hardening-candidate-runtime
git switch codex/framework-hardening
. /data00/home/zimuwang/env/project-env.sh
uv sync --frozen
```

The remote path is disposable canary state, not a release or push. If a suitable locked MiniSWE seed path differs on the machine, locate it by filename and inspect only `pyproject.toml`/`uv.lock`; never print its `.env`.

### Step 5: Run one real full smoke twice

- [ ] Initialize a fresh workspace from the matching locked MiniSWE seed, then run full smoke twice against one representative configured Harbor task:

```bash
set -eu
cd /data00/home/zimuwang/canaries/framework-hardening-candidate-runtime
. /data00/home/zimuwang/env/project-env.sh
workspace=/data00/home/zimuwang/canaries/framework-hardening-runtime-workspace
test -f "$MINISWE_LOCKED_SEED/pyproject.toml"
test -f "$MINISWE_LOCKED_SEED/uv.lock"
rm -rf "$workspace"
./evolve init "$workspace" --recipe hill_climb --seed "$MINISWE_LOCKED_SEED"
EVOLVE_WORKSPACE="$workspace" EVOLVE_RUN_DIR="$workspace/runs/gen-0/manual" \
  "$workspace/evolve" candidate-smoke --checkout "$workspace" --full
EVOLVE_WORKSPACE="$workspace" EVOLVE_RUN_DIR="$workspace/runs/gen-0/manual" \
  "$workspace/evolve" candidate-smoke --checkout "$workspace" --full
```

Before running, replace `MINISWE_LOCKED_SEED` with the configured path in the shell environment; do not echo it if it embeds credentials (it should be a local filesystem path).

- [ ] Verify from sanitized artifacts, not terminal intuition:

```bash
workspace=/data00/home/zimuwang/canaries/framework-hardening-runtime-workspace
python3 -c "import json,pathlib; files=sorted(pathlib.Path(\"$workspace/runs/gen-0/manual/meta_agent/smoke\").glob(\"attempt-*/result.json\")); assert len(files)==2; rows=[json.loads(p.read_text()) for p in files]; assert all(r[\"status\"]==\"passed\" for r in rows); assert rows[0][\"dependency_digest\"]==rows[1][\"dependency_digest\"]; print(\"smoke attempts: 2 passed; dependency digest stable\")"
test -d "$workspace/runs/runtime/uv-cache"
```

The second run must reuse the same cache directory. Compare Harbor timing/download evidence only if it is already sanitized; do not expose proxy URLs.

### Step 6: Run one normal Harbor trial through the direct interpreter path

- [ ] Invoke the normal evaluator with a one-task limit, using the same workspace and cache:

```bash
set -eu
workspace=/data00/home/zimuwang/canaries/framework-hardening-runtime-workspace
cd "$workspace"
. /data00/home/zimuwang/env/project-env.sh
run_dir="$workspace/runs/gen-0/canary-eval"
mkdir -p "$run_dir" "$workspace/runs/runtime/uv-cache"
EVOLVE_GENID=0 EVOLVE_RUN_DIR="$run_dir" EVOLVE_TASK_LIMIT=1 \
  EVOLVE_UV_CACHE_DIR="$workspace/runs/runtime/uv-cache" \
  evaluator/eval.sh
```

- [ ] Confirm all of the following from the result and Harbor artifacts:

  - frozen sync completed;
  - MiniSWE import completed;
  - configured LiteLLM path initialized with no missing FastAPI;
  - the trial launched `/installed-agent/miniswe-source/.venv/bin/python`;
  - no plain `uv run --project` occurred after setup;
  - generic proxy variables were absent from model execution;
  - the one task reached a normal benchmark outcome rather than setup timeout.

If the real canary fails, preserve its sanitized attempt artifacts and return to the smallest failing test. Do not classify success from mocks alone.

### Step 7: Final local review

- [ ] Run:

```bash
git status --short
git log --oneline -6
git diff HEAD~4..HEAD --stat
```

Expected: only intentional commits plus the pre-existing `.superpowers/sdd/task-2-report.md` working-tree change. Do not stage or rewrite that file.

- [ ] Report exact focused/full test results, canary task/result, cache reuse evidence, and remaining limitations. Do not push.
