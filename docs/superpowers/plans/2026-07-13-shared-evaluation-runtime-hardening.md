# Shared Evaluation and Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HyperAgents and AHE share one reproducible runtime and one exception-first evaluation certificate so infrastructure failures cannot become evolutionary evidence.

**Architecture:** Keep the kernel to two focused modules. `evaluation.py` owns canonical outcomes and derives the only `selection_eligible` decision; `runtime.py` owns runtime fingerprints, evaluation epochs, append-only attempt paths, preflight state, and process-group cleanup. Harbor remains an adapter that emits task vectors and artifacts, while recipe operators remain responsible for method policy.

**Tech Stack:** Python 3.11+, frozen `uv` environments, dataclasses and `StrEnum`, append-only JSON/JSONL, Harbor, pytest, shell wrappers.

## Global Constraints

- Do not modify the dirty primary checkout or the dirty historical Harbor worktree.
- Work only in `.worktrees/framework-hardening` on `codex/framework-hardening`.
- Preserve HyperAgents and AHE method behavior in library operators; do not add recipe-name branches to the framework driver.
- Add no service, database, workflow engine, plugin system, or cryptographic certificate layer.
- Add only `src/evolve/evaluation.py` and `src/evolve/runtime.py` as new shared kernel modules.
- A reward never overrides an exception or nonzero evaluator return code.
- Only full, current-epoch, framework-certified evaluations are selection-eligible.
- Partial evaluations are diagnostic and never parent-eligible.
- Deterministic evaluator setup/import failure opens the circuit immediately with no blind retry.
- Transient infrastructure failure gets at most two retries of the same candidate and generation.
- Candidate dependency mutation is opt-in and, when enabled, requires consistent `pyproject.toml` and `uv.lock` changes.
- The framework consumes an externally built immutable evaluator capsule by digest; it does not become an image builder.
- HyperAgents old/new meta-replay, synthetic genesis scoring, staged screening, and replay-specific namespaces are omitted.
- AHE-specific manifest recovery is omitted unless a later, separate design identifies a simple behavior present in the original paper and official repository.

---

## Planned File Structure

| File | Responsibility |
|---|---|
| `src/evolve/evaluation.py` | Canonical trial outcomes and immutable evaluation certificate |
| `src/evolve/runtime.py` | Runtime fingerprint, epoch state, append-only attempt paths, preflight marker, owned subprocess cleanup |
| `src/evolve/evaluator.py` | Run one evaluator attempt and translate adapter output into a certificate |
| `src/evolve/task_vectors.py` | Validate portable task/trial evidence used by every recipe |
| `templates/evaluator/harbor_artifacts.py` | Parse Harbor results exception-first and index safe artifacts/cost |
| `templates/evaluator/parse_score.py` | Aggregate Harbor evidence without assigning parent eligibility |
| `templates/evaluator/engines/harbor.sh` | Preserve Harbor return code and pass attempt identity to the parser |
| `src/evolve/archive.py` | Store certificate fields and enforce current-epoch selection invariants |
| `src/evolve/driver.py` | Straight-line retry/pause/gate control flow |
| `src/evolve/cli.py` | Preflight command and nonzero paused exit |
| `templates/target/harbor/miniswe_source_agent.py` | Frozen/offline candidate dependency materialization |
| `src/evolve/frozen/meta_eval.py` | Delete the unsupported HyperAgents replay mechanism |

## Task 1: Create the Integrated Recipe Baseline

**Files:**
- Merge: `codex/method-faithful-hyperagents`
- Merge: `codex/method-faithful-ahe`
- Resolve: shared files listed below
- Test: existing `tests/`

**Interfaces:**
- Consumes: clean recipe heads `7639e5c` and `ab4fc23`
- Produces: one compiling tree containing both sets of recipe operators and AHE artifact abstractions, before semantic hardening

- [ ] **Step 1: Merge HyperAgents history without editing either source branch**

```bash
git merge --no-ff codex/method-faithful-hyperagents -m "Merge method-faithful HyperAgents"
```

Expected: a clean merge because `codex/framework-hardening` is based on the HyperAgents merge base `c790f6d` plus documentation only.

- [ ] **Step 2: Run the HyperAgents branch tests before combining AHE**

```bash
uv run --frozen pytest -q
```

Expected: the HyperAgents branch result, with any pre-existing failure recorded before proceeding. Do not repair unrelated documentation assertions in this step.

- [ ] **Step 3: Start the AHE merge and resolve overlap by responsibility**

```bash
git merge --no-ff --no-commit codex/method-faithful-ahe
```

Resolve conflicts with these exact rules:

- `src/evolve/config.py`: retain AHE's `yaml.safe_load` five-section parser and HyperAgents' ordinary evaluator keys only where still used; do not retain replay configuration.
- `src/evolve/driver.py`: retain HyperAgents' atomic candidate validation/terminal recording and AHE's task evidence delivery; leave evaluation eligibility for Tasks 4–6.
- `src/evolve/evaluator.py`: retain AHE's task-set identity, artifact references, and task-vector validation; leave statuses unchanged until Task 4.
- `src/evolve/archive.py`: retain the union of recipe record fields; leave eligibility unchanged until Task 5.
- `src/evolve/workspace.py`: retain AHE recursive asset discovery and both recipes' operator bindings.
- `templates/evaluator/{harbor_artifacts.py,parse_score.py,engines/harbor.sh}`: retain AHE artifact generation; Task 3 will replace outcome semantics.
- tests and documentation: retain coverage and descriptions for both recipes; remove neither method's library operators.

- [ ] **Step 4: Finish the merge and record the combined baseline**

```bash
git add -A
git commit -m "Merge method-faithful AHE"
uv run --frozen pytest -q
```

Expected: no import or collection errors. Record behavioral failures caused by the known shared defects; do not weaken assertions to make the merge green.

## Task 2: Add the Canonical Outcome and Certificate Model

**Files:**
- Create: `src/evolve/evaluation.py`
- Modify: `src/evolve/task_vectors.py`
- Create: `tests/test_evaluation_certificates.py`
- Modify: `tests/test_task_vectors.py`

**Interfaces:**
- Produces: `Outcome`, `TrialResult`, `EvaluationCertificate`, and `certify_evaluation(...)`
- Consumes later: `src/evolve/evaluator.py`, `src/evolve/archive.py`, and `src/evolve/driver.py`

- [ ] **Step 1: Write failing outcome-precedence tests**

```python
from evolve.evaluation import Outcome, TrialResult, certify_evaluation


def test_exception_reward_is_not_score_eligible():
    trial = TrialResult(
        task_id="task-a", trial=0, outcome=Outcome.INFRASTRUCTURE_FAILED,
        reward=None, owner="evaluator", exception_type="ModuleNotFoundError",
        exception_message="No module named 'fastapi'",
    )
    cert = certify_evaluation(
        experiment_id="exp", epoch=0, generation="7", candidate_id="abc",
        purpose="candidate", attempt=1, evaluator_fingerprint="runtime",
        candidate_fingerprint="candidate", task_set_hash="tasks",
        expected_trials=1, trials=(trial,), cost_usd=1.25, wall_s=3.0,
    )
    assert cert.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert cert.score is None
    assert cert.selection_eligible is False


def test_benchmark_agent_timeout_is_valid_zero_when_contract_allows_it():
    trial = TrialResult(
        task_id="task-a", trial=0, outcome=Outcome.TIMEOUT,
        reward=0.0, owner="benchmark_agent",
    )
    cert = certify_evaluation(
        experiment_id="exp", epoch=0, generation="1", candidate_id="abc",
        purpose="candidate", attempt=1, evaluator_fingerprint="runtime",
        candidate_fingerprint="candidate", task_set_hash="tasks",
        expected_trials=1, trials=(trial,), cost_usd=0.0, wall_s=30.0,
        benchmark_timeout_is_zero=True,
    )
    assert cert.outcome is Outcome.BENCHMARK_COMPLETE
    assert cert.score == 0.0
    assert cert.selection_eligible is True
```

- [ ] **Step 2: Verify the new tests fail for the missing module**

```bash
uv run --frozen pytest tests/test_evaluation_certificates.py -q
```

Expected: FAIL during import because `evolve.evaluation` does not exist.

- [ ] **Step 3: Implement the small immutable model**

```python
# src/evolve/evaluation.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    BENCHMARK_COMPLETE = "benchmark_complete"
    CANDIDATE_INVALID = "candidate_invalid"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    trial: int
    outcome: Outcome
    reward: float | None
    owner: str
    exception_type: str | None = None
    exception_message: str | None = None

    def score_eligible(self, *, benchmark_timeout_is_zero: bool) -> bool:
        return self.outcome is Outcome.BENCHMARK_COMPLETE or (
            self.outcome is Outcome.TIMEOUT
            and self.owner == "benchmark_agent"
            and benchmark_timeout_is_zero
        )


@dataclass(frozen=True)
class EvaluationCertificate:
    experiment_id: str
    epoch: int
    generation: str
    candidate_id: str
    purpose: str
    attempt: int
    evaluator_fingerprint: str
    candidate_fingerprint: str
    task_set_hash: str
    expected_trials: int
    outcome: Outcome
    reason: str
    trials: tuple[TrialResult, ...]
    score: float | None
    selection_eligible: bool
    retryable: bool
    cost_usd: float
    wall_s: float
    retry_of: int | None = None
    evaluation_artifacts: dict[str, str] | None = None
    provenance: dict[str, str] | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["trials"] = [
            {**asdict(trial), "outcome": trial.outcome.value} for trial in self.trials
        ]
        return payload


def certify_evaluation(*, benchmark_timeout_is_zero: bool = False, **values: Any) -> EvaluationCertificate:
    trials = tuple(values.pop("trials"))
    expected_trials = int(values["expected_trials"])
    if len(trials) != expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "missing required trial evidence"
    elif any(t.outcome is Outcome.INFRASTRUCTURE_FAILED for t in trials):
        failed = next(t for t in trials if t.outcome is Outcome.INFRASTRUCTURE_FAILED)
        outcome = Outcome.INFRASTRUCTURE_FAILED
        reason = f"{failed.owner}:{failed.exception_type or 'trial_failed'}"
    elif any(t.outcome is Outcome.CANDIDATE_INVALID for t in trials):
        outcome, reason = Outcome.CANDIDATE_INVALID, "candidate trial invalid"
    elif any(t.outcome is Outcome.CANCELLED for t in trials):
        outcome, reason = Outcome.CANCELLED, "evaluation cancelled"
    elif all(t.score_eligible(benchmark_timeout_is_zero=benchmark_timeout_is_zero) for t in trials):
        outcome, reason = Outcome.BENCHMARK_COMPLETE, "all required trials are score-eligible"
    else:
        outcome, reason = Outcome.TIMEOUT, "non-score-eligible timeout"
    score = None
    if outcome is Outcome.BENCHMARK_COMPLETE:
        score = sum(float(t.reward or 0.0) for t in trials) / len(trials)
    return EvaluationCertificate(
        **values, trials=trials, outcome=outcome, reason=reason, score=score,
        selection_eligible=outcome is Outcome.BENCHMARK_COMPLETE,
        retryable=outcome is Outcome.INFRASTRUCTURE_FAILED,
    )
```

- [ ] **Step 4: Update task-vector validation to use the five outcome strings**

Replace AHE's `TRIAL_STATUSES` with values from `Outcome`, require reward only
for `benchmark_complete` and score-eligible benchmark-agent timeouts, and retain
exception fields for every non-complete outcome. Legacy boolean vectors still
normalize to `benchmark_complete` trials.

- [ ] **Step 5: Run focused tests and commit**

```bash
uv run --frozen pytest tests/test_evaluation_certificates.py tests/test_task_vectors.py -q
git add src/evolve/evaluation.py src/evolve/task_vectors.py tests/test_evaluation_certificates.py tests/test_task_vectors.py
git commit -m "Add canonical evaluation certificates"
```

Expected: all focused tests pass.

## Task 3: Make Harbor Evidence Exception-First

**Files:**
- Modify: `templates/evaluator/harbor_artifacts.py`
- Modify: `templates/evaluator/parse_score.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `tests/test_harbor_artifacts.py`
- Modify: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: canonical outcome strings from Task 2
- Produces: `task_vector.json`, `evaluation_artifacts.json`, and `cost.json`; never parent eligibility

- [ ] **Step 1: Add the historical `fastapi` regression fixture**

Create a Harbor `result.json` with both verifier reward `0.0` and:

```json
{
  "exception_info": {
    "exception_type": "NonZeroAgentExitCodeError",
    "exception_message": "ModuleNotFoundError: No module named 'fastapi'"
  },
  "verifier_result": {"rewards": {"reward": 0.0}},
  "agent_result": {"cost_usd": 0.25}
}
```

Assert that its trial outcome is `infrastructure_failed`, reward is `null`, and
cost remains `0.25`. Add a separate import fixture whose exception message starts
with `EVOLVE_CANDIDATE_INVALID:` and expect `candidate_invalid`. Add an
`AgentExecutionTimeoutError` fixture that expects `timeout`, owner
`benchmark_agent`, reward `0.0`.

- [ ] **Step 2: Verify the exception-plus-reward test fails**

```bash
uv run --frozen pytest tests/test_harbor_artifacts.py -q
```

Expected: FAIL because `_trial_status` currently checks reward before exception.

- [ ] **Step 3: Replace `_trial_status` with exception-first ownership mapping**

```python
def _trial_result(result: dict[str, Any]) -> tuple[str, float | None, str]:
    exception = result.get("exception_info") or {}
    exception_type = str(exception.get("exception_type") or "")
    message = str(exception.get("exception_message") or "")
    if exception_type in {"AgentTimeoutError", "AgentExecutionTimeoutError"}:
        return "timeout", 0.0, "benchmark_agent"
    if exception_type:
        if "EVOLVE_CANDIDATE_INVALID:" in message:
            return "candidate_invalid", None, "candidate"
        return "infrastructure_failed", None, "ambiguous"
    reward = _reward(result)
    if reward is not None:
        return "benchmark_complete", reward, "benchmark"
    return "infrastructure_failed", None, "evaluator"
```

Do not infer ownership from exception type or path substrings. Candidate
materialization emits the explicit `EVOLVE_CANDIDATE_INVALID:` marker added in
Task 7. Preserve the first-line exception message so every other ambiguous
failure can trigger the unchanged-control path in Task 6.

- [ ] **Step 4: Propagate Harbor return code and cost**

Change the wrapper tail to:

```sh
harbor "$@" > "$EVOLVE_RUN_DIR/harbor.log" 2>&1 || harbor_rc=$?
python3 evaluator/parse_score.py "$jobs_dir" "$EVOLVE_RUN_DIR" "$harbor_rc"
parser_rc=$?
[ "$harbor_rc" -eq 0 ] || exit 3
exit "$parser_rc"
```

`parse_score.py` must reject a nonzero Harbor return code as
`infrastructure_failed`, even if result files contain rewards. It must sum
`agent_result.cost_usd` across every discovered trial and write
`{"usd": <sum>}` to `cost.json` for complete and failed attempts.

- [ ] **Step 5: Run focused tests and commit**

```bash
uv run --frozen pytest tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py -q
git add templates/evaluator tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py
git commit -m "Classify Harbor outcomes exception first"
```

## Task 4: Add Runtime Fingerprints, Epochs, and Append-Only Attempt Paths

**Files:**
- Create: `src/evolve/runtime.py`
- Modify: `src/evolve/evaluator.py`
- Create: `tests/test_runtime.py`
- Modify: `tests/test_m1_evaluator_invariants.py`

**Interfaces:**
- Produces: `RuntimeFingerprint`, `current_epoch(...)`, `attempt_dir(...)`, `mark_preflight(...)`, and `run_owned(...)`
- Consumes later: driver and CLI in Task 6

- [ ] **Step 1: Write failing identity and append-only tests**

```python
def test_attempt_paths_never_replace_prior_evidence(tmp_path):
    first = attempt_dir(tmp_path, epoch=0, purpose="candidate", generation="7", candidate_id="abc", attempt=1)
    second = attempt_dir(tmp_path, epoch=0, purpose="candidate", generation="7", candidate_id="abc", attempt=2)
    first.mkdir(parents=True)
    (first / "marker").write_text("first")
    second.mkdir(parents=True)
    assert first != second
    assert (first / "marker").read_text() == "first"


def test_changed_capsule_digest_requires_new_epoch(tmp_path):
    mark_preflight(tmp_path, RuntimeFingerprint("sha256:old", "eval", "tasks"), epoch=0)
    with pytest.raises(EvaluationPaused, match="new evaluation epoch"):
        current_epoch(tmp_path, RuntimeFingerprint("sha256:new", "eval", "tasks"))
```

- [ ] **Step 2: Verify the tests fail for missing interfaces**

```bash
uv run --frozen pytest tests/test_runtime.py -q
```

- [ ] **Step 3: Implement the filesystem-only runtime state**

`RuntimeFingerprint` contains only epoch-defining fields: `capsule_digest`,
evaluator lock/tree hash, and task-set hash. Its `digest` property hashes
canonical JSON. Candidate commit/lock/Python/platform produce a separate
`candidate_fingerprint` recorded on each certificate; candidate evolution must
not create an evaluator epoch. `current_epoch` reads
`runs/runtime/preflight.json`; it returns the epoch
only on an exact digest match. `mark_preflight` writes via a temporary file plus
`Path.replace`. `attempt_dir` returns:

```text
runs/evaluations/epoch-<e>/<purpose>/gen-<g>/candidate-<id>/attempt-<a>/
```

It raises if the directory already exists; evaluator code must never call
`shutil.rmtree` on an attempt directory.

For Harbor, `evaluator.runtime.capsule_digest` is required and must be a
`sha256:` image digest supplied by the experiment launcher. Stub evaluators use
the committed evaluator-tree hash. `evaluator.runtime.canary_task` is optional;
when absent, preflight uses the first bound task from the task-set identity.

- [ ] **Step 4: Move `evaluate(...)` to the append-only interface**

Use this signature:

```python
def evaluate(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    epoch: int,
    purpose: str = "candidate",
    attempt: int = 1,
    round_number: int | None = None,
) -> EvaluationCertificate:
```

The function computes the candidate commit ID, obtains the certified runtime
fingerprint, creates the unique attempt directory, runs `eval.sh`, validates the
task vector, calls `certify_evaluation`, and writes `certificate.json` before
returning. Adapter exceptions become a certificate; only programmer errors such
as an invalid tag may escape.

- [ ] **Step 5: Run tests and commit**

```bash
uv run --frozen pytest tests/test_runtime.py tests/test_m1_evaluator_invariants.py -q
git add src/evolve/runtime.py src/evolve/evaluator.py tests/test_runtime.py tests/test_m1_evaluator_invariants.py
git commit -m "Add append-only evaluation attempts"
```

## Task 5: Enforce Archive Certification and Current-Epoch Selection

**Files:**
- Modify: `src/evolve/archive.py`
- Modify: `src/evolve/population.py`
- Modify: `src/evolve/driver.py`
- Create: `tests/test_selection_certification.py`
- Modify: `tests/test_m5_record_verb.py`

**Interfaces:**
- Consumes: `EvaluationCertificate.to_dict()`
- Produces: `append_certificate(...)` and `certified_parent_rows(...)`

- [ ] **Step 1: Write failing invariant tests**

Test all three cases:

```python
assert append_certificate(workspace, infra_certificate).get("valid_parent") is False
assert append_certificate(workspace, cancelled_certificate).get("valid_parent") is False
assert certified_parent_rows(workspace, epoch=1) == []  # archive contains only epoch 0
```

Also run a malicious gate operator that emits `valid_parent: true` after an
infrastructure certificate and assert the archive still reports false.

- [ ] **Step 2: Verify tests fail under coarse status eligibility**

```bash
uv run --frozen pytest tests/test_selection_certification.py tests/test_m5_record_verb.py -q
```

- [ ] **Step 3: Make certificate stamping the only eligibility writer**

Add certificate fields to `STAMPED_FIELDS`: `epoch`, `attempt`, `purpose`,
`evaluator_fingerprint`, `candidate_fingerprint`, `outcome`,
`selection_eligible`, and `evaluation_artifacts`. `append_certificate` derives:

```python
valid_parent = certificate.selection_eligible and certificate.epoch == current_epoch
event = {
    **certificate.to_dict(),
    "status": "complete" if valid_parent else certificate.outcome.value,
    "valid_parent": valid_parent,
    "verdict": "keep" if valid_parent else "discard",
}
```

Gate and record payloads may only turn a certified candidate from keep to
discard. They cannot change stamped fields or turn false into true.

- [ ] **Step 4: Replace all parent queries with current-epoch certification**

`population.valid_parent_rows`, `best_row`, HyperAgents selection, and AHE latest
selection must consume rows whose `selection_eligible is True` and whose `epoch`
matches `current_epoch`. Remove every `status in {"complete", "partial"}` parent
predicate.

- [ ] **Step 5: Run tests and commit**

```bash
uv run --frozen pytest tests/test_selection_certification.py tests/test_m5_record_verb.py tests/test_hyperagents_select.py tests/test_ahe_select.py -q
git add src/evolve/archive.py src/evolve/population.py src/evolve/driver.py library/select tests
git commit -m "Require certified evaluations for selection"
```

## Task 6: Add Preflight, Retry, Circuit Breaker, and Evaluation Epochs

**Files:**
- Modify: `src/evolve/runtime.py`
- Modify: `src/evolve/driver.py`
- Modify: `src/evolve/cli.py`
- Modify: `src/evolve/config.py`
- Create: `tests/test_evaluation_supervision.py`
- Modify: `tests/test_m0_run_resume.py`

**Interfaces:**
- Produces: `preflight(...)`, `EvaluationPaused`, and driver exit code 4
- Consumes: `EvaluationCertificate.retryable` and deterministic failure reason

- [ ] **Step 1: Write failing supervision tests**

Cover these exact sequences:

- deterministic `ModuleNotFoundError` in evaluator startup: one attempt, no new
  generation, outstanding fake worker cancelled, CLI exits 4;
- transient worker loss: attempts 1, 2, and 3 use the same candidate/generation,
  then pause;
- repaired capsule: `preflight --new-epoch` increments the epoch and requires
  active-parent re-certification before selection;
- older candidate nomination: lazily re-certifies in the new epoch before it can
  be returned by a selector;
- three consecutive `operator_failed` rows: pause before generation four.

- [ ] **Step 2: Verify the tests fail**

```bash
uv run --frozen pytest tests/test_evaluation_supervision.py tests/test_m0_run_resume.py -q
```

- [ ] **Step 3: Implement preflight as one normal-purpose evaluation**

`preflight(workspace, *, new_epoch=False)` verifies the configured evaluator
capsule digest, frozen/offline candidate materialization, evaluator imports, and
entry-point startup, then runs one configured canary through `evaluate` with
purpose `preflight`. On success it atomically records the fingerprint and epoch.
On failure it raises `EvaluationPaused` and never starts generation 1.

Add one CLI command:

```python
@app.command()
def preflight(workspace: Path, new_epoch: bool = typer.Option(False, "--new-epoch")) -> None:
    epoch = runtime_preflight(workspace.resolve(), new_epoch=new_epoch)
    print(f"preflight certified evaluation epoch {epoch}")
```

- [ ] **Step 4: Keep retry control flow explicit in the driver**

```python
for attempt in range(1, 4):
    certificate = evaluate(..., epoch=epoch, attempt=attempt)
    append_certificate(..., certificate)
    if certificate.selection_eligible:
        break
    if certificate.outcome is not Outcome.INFRASTRUCTURE_FAILED:
        return
    if is_deterministic_infrastructure_failure(certificate):
        raise EvaluationPaused(certificate.reason)
else:
    raise EvaluationPaused("transient infrastructure failure exhausted two retries")
```

Do not introduce a retry class hierarchy or scheduler. `is_deterministic...`
matches a short explicit set of evaluator-owned setup/import reason codes emitted
by the adapter.

- [ ] **Step 5: Add ambiguous-ownership control without general replay**

When the Harbor adapter marks ownership `ambiguous`, run the unchanged active
parent once with purpose `control` under the identical runtime/task fingerprint.
Equivalent failure opens the infrastructure circuit. A successful control makes
the child `candidate_invalid`. No scores are compared and no descendants are
generated.

- [ ] **Step 6: Make paused experiments observable at the process boundary**

Catch `EvaluationPaused` in the CLI, print `evolve: paused: <reason>`, and exit
4. A normal completed loop exits 0. Do not convert pause to a successful return.

- [ ] **Step 7: Run tests and commit**

```bash
uv run --frozen pytest tests/test_evaluation_supervision.py tests/test_m0_run_resume.py -q
git add src/evolve/runtime.py src/evolve/driver.py src/evolve/cli.py src/evolve/config.py tests
git commit -m "Pause poisoned evaluation runs"
```

## Task 7: Freeze Candidate Dependencies and Own Nested Work

**Files:**
- Modify: `src/evolve/runtime.py`
- Modify: `templates/target/harbor/miniswe_source_agent.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Create: `tests/test_candidate_runtime.py`
- Create: `tests/test_process_ownership.py`
- Modify: `tests/test_miniswe_source_agent_command.py`

**Interfaces:**
- Produces: content-addressed candidate cache and `run_owned(...)`
- Consumes: recipe surface permission for `target/pyproject.toml` and `target/uv.lock`

- [ ] **Step 1: Write failing frozen-materialization tests**

Assert that:

- candidate dependency changes are rejected when only one of `pyproject.toml`
  and `uv.lock` changes;
- unchanged lock hashes reuse the same cache directory;
- changing one dependency creates a new cache key while retaining the shared
  global `uv` package cache;
- trial commands contain `uv sync --frozen --offline` and never plain `uv run
  --project` against an unresolved environment.

- [ ] **Step 2: Implement candidate cache preparation**

Use `runs/runtime/candidates/<sha256>/` as a small materialization record. The
hash includes candidate commit, `pyproject.toml`, `uv.lock`, Python ABI, and
platform. Preparation runs once with a shared `UV_CACHE_DIR`; trials receive the
frozen source and cache and execute:

```sh
UV_CACHE_DIR=/installed-agent/uv-cache uv sync \
  --project /installed-agent/miniswe-source --frozen --offline
```

This reuses package artifacts and does not download the whole environment for a
one-package change.

If frozen synchronization fails, `MiniSweSourceAgent.install` raises
`RuntimeError("EVOLVE_CANDIDATE_INVALID: frozen dependency materialization failed")`;
the Harbor adapter can therefore assign ownership without parsing arbitrary
traceback text.

- [ ] **Step 3: Write failing recursive-cancellation tests**

Launch a fake evaluator that forks a grandchild, cancel the attempt, and assert
both PIDs disappear. Mock `docker ps` with containers labeled by experiment and
attempt, then assert cleanup targets only those IDs and records cleanup errors.

- [ ] **Step 4: Implement one process-group helper in `runtime.py`**

`run_owned(command, *, cwd, env, timeout_s, experiment_id, attempt_id)` uses
`subprocess.Popen(..., start_new_session=True)`. On timeout/cancellation it sends
`SIGTERM` to the process group, waits five seconds, sends `SIGKILL` if needed,
and invokes the configured container cleanup command with both identity labels.
The Harbor wrapper exports those labels for every trial container. Do not add a
background supervisor daemon.

- [ ] **Step 5: Run tests and commit**

```bash
uv run --frozen pytest tests/test_candidate_runtime.py tests/test_process_ownership.py tests/test_miniswe_source_agent_command.py -q
git add src/evolve/runtime.py templates/target/harbor/miniswe_source_agent.py templates/evaluator/engines/harbor.sh tests
git commit -m "Freeze and own evaluation runtimes"
```

## Task 8: Simplify HyperAgents to the Upstream Method Boundary

**Files:**
- Delete: `src/evolve/frozen/meta_eval.py`
- Delete: replay-specific tests from `tests/test_m3_meta_eval.py`
- Modify: `src/evolve/driver.py`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `recipes/hyperagents-smoke/evolve.yaml`
- Modify: `tests/test_hyperagents_semantics.py`
- Modify: `tests/test_hyperagents_validate_record.py`

**Interfaces:**
- Consumes: shared certificate and atomic candidate validation
- Produces: upstream-faithful select → modify → validate → evaluate → archive flow

- [ ] **Step 1: Write the failing no-replay test**

Run a HyperAgents child that changes its permitted meta-agent workflow and target
surface. Assert exactly one candidate evaluation purpose exists, no `old`/`new`
replay directories exist, and the full child is either committed or rejected
atomically.

- [ ] **Step 2: Remove replay and unsupported screening paths**

Delete the `meta_eval` import and admission block from `_run_child`, delete
`src/evolve/frozen/meta_eval.py`, remove `EVOLVE_IN_META_EVAL`, and remove
synthetic genesis/replay tests. Remove `evaluator.stage` and replay/anchor-only
configuration; neither is part of the verified upstream online method used for
this implementation. Keep HyperAgents score-child-proportional selection,
meta-agent modification, candidate validation, and archive behavior.

- [ ] **Step 3: Assert valid lower-scoring children remain archived**

Add a test where a full certified child scores below its parent. Assert it remains
selection-eligible and in the archive; the HyperAgents selector, not a framework
admission gate, controls its future probability.

- [ ] **Step 4: Run tests and commit**

```bash
uv run --frozen pytest tests/test_hyperagents_semantics.py tests/test_hyperagents_meta_agent.py tests/test_hyperagents_select.py tests/test_hyperagents_validate_record.py -q
git add -A
git commit -m "Use certified evaluation for HyperAgents"
```

## Task 9: Reconnect AHE to the Shared Evidence Contract

**Files:**
- Modify: `library/ahe_support.py`
- Modify: `library/rollout/ahe_trace_analysis.py`
- Modify: `library/gate/ahe_artifact_valid.py`
- Modify: `library/record/ahe_manifest.py`
- Modify: `tests/test_ahe_integration.py`
- Modify: `tests/test_ahe_gate_record.py`
- Modify: `tests/test_ahe_rollout.py`

**Interfaces:**
- Consumes: canonical task vectors, artifact hashes, certificate artifact path, current epoch
- Produces: unchanged AHE analysis/attribution/rollback behavior over trustworthy evidence

- [ ] **Step 1: Write the corrupted-evaluation integration test**

Feed AHE a generation whose 60 trials contain `NonZeroAgentExitCodeError` plus
reward `0.0`. Assert the generation is not a valid parent, AHE analysis labels
the task outcomes unknown/infrastructure rather than regressions, and the
manifest points to the exact append-only attempt evidence.

- [ ] **Step 2: Replace AHE-local outcome assumptions with shared helpers**

Use `normalize_task_vector` and certificate `selection_eligible`; remove checks
that equate trial `complete`/reward presence with valid evidence. Preserve
task-set binding, artifact hashes, evidence-path validation, sequential latest
selection, predicted-fix validation, and rollback/pivot policy.

- [ ] **Step 3: Add only the generic operator-failure breaker**

Verify three consecutive AHE manifest/schema `operator_failed` generations pause
the run with their artifacts intact. Do not add schema auto-repair, prompt retry
heuristics, or an AHE branch in `driver.py`.

- [ ] **Step 4: Run tests and commit**

```bash
uv run --frozen pytest tests/test_ahe_integration.py tests/test_ahe_gate_record.py tests/test_ahe_rollout.py tests/test_ahe_meta_agent.py -q
git add library tests
git commit -m "Use certified evaluation evidence in AHE"
```

## Task 10: Complete Documentation, Full Verification, and DevBoxS Canaries

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `DESIGN.md`
- Modify: `README.md`
- Modify: `docs/glossary.md`
- Modify: `library/PROTOCOL.md`
- Modify: `recipes/hyperagents/README.md`
- Modify: `recipes/ahe/README.md`
- Create: `docs/evaluation-runtime.md`

**Interfaces:**
- Produces: one readable operator-facing contract and verified small remote runs

- [ ] **Step 1: Document one straight-line lifecycle**

Document: preflight → candidate → attempt → certificate → recipe gate → archive.
Include the five outcomes, immediate deterministic circuit, two transient
retries, epoch repair, lazy re-certification, dependency opt-in, and exit code 4.
Remove old replay and partial-parent descriptions.

- [ ] **Step 2: Run static and full local verification**

```bash
uv run --frozen ruff check .
uv run --frozen ty check
uv run --frozen pytest -q
```

Expected: all checks pass. If the original `hyperagents-smoke` coherence failure
survives the branch merges, repair only its stale documentation expectation and
record that as a separate commit.

- [ ] **Step 3: Inspect the built runtime manifest before remote execution**

```bash
uv run --frozen evolve init /tmp/evolve-hyperagents-runtime-smoke --recipe hyperagents-smoke
uv run --frozen evolve init /tmp/evolve-ahe-runtime-smoke --recipe ahe-smoke
uv run --frozen evolve preflight /tmp/evolve-hyperagents-runtime-smoke
uv run --frozen evolve preflight /tmp/evolve-ahe-runtime-smoke
```

Expected: both print `preflight certified evaluation epoch 0`; their evaluator
capsule and task-set fingerprints match where configuration is shared.

- [ ] **Step 4: Run one small DevBoxS canary per recipe**

Use two tasks, one trial per task, one generation, and the same immutable
evaluator capsule. Confirm:

- no online dependency resolution occurs inside a Harbor trial;
- every attempt has a unique append-only directory and `certificate.json`;
- cost in the archive equals the sum of Harbor trial cost;
- a forced evaluator import failure exits 4 without generation advancement and
  leaves no owned process/container;
- restoring a repaired capsule requires `--new-epoch` and active-parent
  re-certification;
- HyperAgents and AHE each preserve their recipe-specific operator sequence.

- [ ] **Step 5: Commit documentation and verification evidence**

```bash
git add ARCHITECTURE.md DESIGN.md README.md docs library/PROTOCOL.md recipes
git commit -m "Document certified evaluation runtime"
git status --short
```

Expected: clean worktree. Do not start a 30×30 experiment until both canaries
pass and their fingerprints/certificates have been reviewed.

## Final Simplicity Review

Before declaring implementation complete, verify these negative requirements:

- exactly two new shared core modules exist;
- there is one certificate dataclass and one eligibility predicate;
- retry control is a visible three-iteration loop, not a scheduler;
- epoch state is one JSON file, not a database;
- preflight is an ordinary purpose-tagged evaluation path;
- ambiguous ownership uses at most one unchanged control;
- HyperAgents has no replay process or synthetic score;
- AHE has no framework-specific recovery branch;
- evaluator capsule repair is external and explicit;
- candidate packages are reused through content-addressed cache rather than
  re-downloaded wholesale.
