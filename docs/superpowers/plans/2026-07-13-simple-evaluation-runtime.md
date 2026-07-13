# Simple Evaluation Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one package-manager-neutral path from an exact candidate Git snapshot to useful smoke evidence, one canonical evaluation record, and certified-only selection.

**Architecture:** Smoke and commit share one Git-tree builder. The evaluator produces one `EvaluationRecord`, the archive stores it append-only, and `ArchiveView` is the only eligibility reader. Candidate environment repair belongs to the meta-agent; the framework owns evidence and selection validity.

**Tech Stack:** Python 3.11+, Git temporary indexes/worktrees, Typer, pytest, shell evaluator templates, Harbor, and Docker. UV remains MiniSWE-specific.

## Global Constraints

- Work only in `/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/framework-hardening` on `codex/framework-hardening`.
- Never stage `.superpowers/sdd/task-2-report.md` or `.superpowers/sdd/task-8-report.md`.
- Do not modify other worktrees, completed DevBoxS experiments, or push without approval.
- Shared core code must not require `pyproject.toml`, `uv.lock`, or a package manager.
- Do not change HyperAgents selection/workflow mutation or AHE manifest logic;
  this plan changes only their shared runtime/archive adapters.
- Do not reintroduce the unsupported HyperAgents replay admission mechanism.
- Evaluator files and `target/harbor_agent.py` remain immutable.
- Store near-raw smoke stdout/stderr; redact secrets and URL userinfo only.
- Only `benchmark_complete` may be parent-eligible. Partial evidence is scoreless.
- Retry `infrastructure_failed` once against the same generation and commit.
- Every smoke/evaluation attempt is append-only.
- Stop remote validation on an unusual failure; never repair a running trial.

## File Map

- `src/evolve/candidate_snapshot.py`: committable Git tree and detached materialization.
- `src/evolve/candidate_runtime.py`: generic smoke runner and redacted logs.
- `src/evolve/evaluation.py`: canonical record and classifier.
- `src/evolve/evaluator.py`: exact-commit attempt execution.
- `src/evolve/archive.py`, `src/evolve/frozen/interfaces.py`: canonical writes and reads.
- `src/evolve/driver.py`: genesis, retry, evaluation, and gate sequencing.
- `src/evolve/runtime.py`: attempt paths and process ownership.
- `templates/evaluator/smoke.sh`: immutable smoke entry point.
- `templates/evaluator/cleanup_harbor.py`: attempt-owned container cleanup.

The implementation has only three durable data concepts: `CandidateSnapshot`,
`SmokeResult`, and `EvaluationRecord`. Helpers such as `run_owned(...)` are
functions, not new lifecycle objects.

---

### Task 1: Use One Exact Candidate Snapshot

**Files:**
- Create: `src/evolve/candidate_snapshot.py`
- Modify: `src/evolve/git.py`
- Modify: `src/evolve/patching.py`
- Modify: `src/evolve/driver.py:551-631`
- Create: `tests/test_candidate_snapshot.py`
- Modify: `tests/test_manual_commit.py`

**Interfaces:**
- Produces: `CandidateSnapshot`, `build_candidate_snapshot(...)`, `materialize_snapshot(...)`, `commit_candidate_snapshot(...)`.

- [ ] **Step 1: Write RED tests for ignored files and tree identity**

```python
def test_snapshot_excludes_ignored_untracked_file(tmp_path: Path) -> None:
    checkout = git_checkout(tmp_path)
    (checkout / ".gitignore").write_text("ignored.lock\n")
    (checkout / "visible.txt").write_text("visible\n")
    (checkout / "ignored.lock").write_text("ignored\n")
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=["**"], exclude=[])
    with materialize_snapshot(checkout, snapshot) as materialized:
        assert (materialized / "visible.txt").is_file()
        assert not (materialized / "ignored.lock").exists()


def test_commit_tree_equals_snapshot_tree(tmp_path: Path) -> None:
    checkout = git_checkout(tmp_path)
    (checkout / "target" / "agent.py").write_text("VALUE = 2\n")
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=["target/**"], exclude=[])
    commit = commit_candidate_snapshot(checkout, snapshot, "candidate")
    assert git_stdout(checkout, "rev-parse", f"{commit}^{{tree}}") == snapshot.tree
```

Also test that an already-staged path raises `CandidateSnapshotError("candidate index is not clean")`.

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_candidate_snapshot.py tests/test_manual_commit.py
```

Expected: `ModuleNotFoundError: evolve.candidate_snapshot`.

- [ ] **Step 3: Add temporary-index support to Git helpers**

```python
def git(
    workspace: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git is required")
    result = subprocess.run(
        [executable, "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
        env=None if env is None else {**os.environ, **env},
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result


def git_stdout(workspace: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return git(workspace, *args, env=env).stdout.strip()
```

- [ ] **Step 4: Implement the snapshot module**

```python
class CandidateSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSnapshot:
    parent_ref: str
    commit: str
    tree: str
    changed_paths: tuple[str, ...]


def build_candidate_snapshot(checkout: Path, parent_ref: str, *, include: list[str], exclude: list[str]) -> CandidateSnapshot:
    if git(checkout, "diff", "--cached", "--quiet", check=False).returncode:
        raise CandidateSnapshotError("candidate index is not clean")
    changed = tuple(working_tree_changed_paths(checkout, parent_ref))
    violations = check_paths(list(changed), include, exclude)
    if violations:
        raise CandidateSnapshotError("changed paths outside mutable surface: " + ", ".join(violations))
    with tempfile.TemporaryDirectory(prefix="evolve-index-") as temporary:
        env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(checkout, "read-tree", parent_ref, env=env)
        if changed:
            git(checkout, "add", "-A", "--", *changed, env=env)
        tree = git_stdout(checkout, "write-tree", env=env)
        commit = git_stdout(checkout, "commit-tree", tree, "-p", parent_ref, "-m", "evolve snapshot")
    return CandidateSnapshot(parent_ref, commit, tree, changed)


@contextmanager
def materialize_snapshot(repo: Path, snapshot: CandidateSnapshot) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="evolve-snapshot-") as temporary:
        checkout = Path(temporary) / "checkout"
        add_worktree(repo, checkout, snapshot.commit)
        try:
            yield checkout
        finally:
            remove_worktree(repo, checkout)


def commit_candidate_snapshot(checkout: Path, snapshot: CandidateSnapshot, message: str) -> str:
    commit = commit_paths(checkout, list(snapshot.changed_paths), message)
    if git_stdout(checkout, "rev-parse", f"{commit}^{{tree}}") != snapshot.tree:
        raise CandidateSnapshotError("candidate commit differs from reviewed snapshot")
    return commit
```

- [ ] **Step 5: Route patching and commit through the snapshot**

In `commit_child(...)`, build one snapshot after surface configuration, preserve the existing no-proposal/rejection events, commit with `commit_candidate_snapshot(...)`, and only then create `gen/<id>`. Remove `validate_miniswe_candidate(...)` from admission. Make `create_candidate_patch(...)` derive its changed paths and diff from the same snapshot commit.

- [ ] **Step 6: Verify GREEN and commit**

```bash
uv run pytest -q tests/test_candidate_snapshot.py tests/test_manual_commit.py tests/test_patching.py tests/test_m5_driver_operators.py
git add src/evolve/candidate_snapshot.py src/evolve/git.py src/evolve/patching.py src/evolve/driver.py tests/test_candidate_snapshot.py tests/test_manual_commit.py tests/test_patching.py tests/test_m5_driver_operators.py
git commit -m "Use exact candidate snapshots"
```

Expected: all tests pass; only listed files are committed.

---

### Task 2: Make Smoke Generic and Diagnostic

**Files:**
- Rewrite: `src/evolve/candidate_runtime.py`
- Modify: `src/evolve/cli.py:137-159`
- Modify: `src/evolve/workspace.py`
- Create: `templates/evaluator/smoke.sh`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `templates/workspace/operators/meta_agent.md`
- Modify: `templates/workspace/operators/meta_agent_brief.md`
- Modify: `library/meta_agent/agent_command.py`
- Modify: `library/meta_agent/hyperagents.py`
- Modify: `library/meta_agent/ahe_evidence_editor.py`
- Rewrite: `tests/test_candidate_smoke.py`

**Interfaces:**
- Consumes: Task 1 snapshot helpers.
- Produces: `SmokeResult` and `run_candidate_smoke(...)` with redacted stdout/stderr paths.

- [ ] **Step 1: Write three vertical smoke tests**

```python
def test_smoke_exposes_missing_module_from_snapshot(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, stderr="ModuleNotFoundError: No module named 'fastapi'\n", rc=2)
    result = run_candidate_smoke(checkout, workspace=checkout)
    assert result.status == "failed"
    assert "No module named 'fastapi'" in result.stderr_path.read_text()


def test_smoke_redacts_proxy_credential_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@example.invalid:8080")
    checkout = smoke_checkout(tmp_path, stderr="http://user:secret@example.invalid:8080 fastapi\n", rc=2)
    text = run_candidate_smoke(checkout, workspace=checkout).stderr_path.read_text()
    assert "secret" not in text
    assert "fastapi" in text


def test_smoke_without_evaluator_script_is_unsupported(tmp_path: Path) -> None:
    checkout = smoke_checkout(tmp_path, create_script=False)
    assert run_candidate_smoke(checkout, workspace=checkout).status == "unsupported"
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_candidate_smoke.py
```

Expected: current MiniSWE/UV-specific smoke behavior fails these tests.

- [ ] **Step 3: Implement one package-neutral smoke runner**

```python
@dataclass(frozen=True)
class SmokeResult:
    status: Literal["passed", "failed", "unsupported"]
    attempt_dir: Path
    snapshot_tree: str
    returncode: int | None
    stdout_path: Path
    stderr_path: Path


def run_candidate_smoke(checkout: Path, *, workspace: Path) -> SmokeResult:
    include, exclude = surface_patterns(workspace)
    snapshot = build_candidate_snapshot(checkout, "HEAD", include=include, exclude=exclude)
    attempt = _next_attempt(workspace / "runs" / "smoke")
    with materialize_snapshot(checkout, snapshot) as materialized:
        script = materialized / "evaluator" / "smoke.sh"
        if not script.is_file():
            return _write_result(attempt, "unsupported", snapshot.tree, None, "", "")
        completed = subprocess.run(
            [str(script)], cwd=materialized,
            env={**os.environ, "EVOLVE_RUN_DIR": str(attempt), "EVOLVE_ATTEMPT_ID": attempt.name},
            text=True, capture_output=True, check=False,
        )
    return _write_result(
        attempt, "passed" if completed.returncode == 0 else "failed", snapshot.tree,
        completed.returncode, _redact(completed.stdout, os.environ), _redact(completed.stderr, os.environ),
    )
```

`_redact(...)` replaces values of at least four characters from environment
keys matching `KEY|TOKEN|SECRET|PASSWORD|PROXY`, plus URL userinfo matching
`r"(?i)(https?://)[^/@\s]+@"`; it leaves all other traceback text unchanged.

- [ ] **Step 4: Add the immutable smoke script and simple CLI**

```sh
#!/bin/sh
set -eu
: "${EVOLVE_RUN_DIR:?EVOLVE_RUN_DIR is required}"
export EVOLVE_CANDIDATE_SMOKE_MODE=full
export EVOLVE_CANDIDATE_SMOKE_JOBS_DIR="$EVOLVE_RUN_DIR/jobs"
exec ./evaluator/eval.sh
```

Generate it only for Harbor evaluators. Keep only `candidate-smoke --full`; print the last 200 redacted stderr lines and full artifact paths. Exit 2 for `failed`, 3 for `unsupported`.

- [ ] **Step 5: Let the meta-agent repair candidate environments**

Use this guidance in all three meta-agent paths:

```text
When runtime uncertainty is relevant, run `./evolve candidate-smoke --full`.
Read its stdout/stderr artifacts, repair the candidate environment with the
candidate's own tools, and rerun smoke. Do not edit evaluator-owned files.
```

Delete shared initialization/admission calls requiring MiniSWE project/lock files. Keep frozen MiniSWE synchronization in its evaluator wrapper.

- [ ] **Step 6: Verify GREEN and commit**

```bash
uv run pytest -q tests/test_candidate_smoke.py tests/test_agent_command_meta_agent.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py tests/test_harbor_evaluator_template.py
git add src/evolve/candidate_runtime.py src/evolve/cli.py src/evolve/workspace.py templates/evaluator/smoke.sh templates/evaluator/engines/harbor.sh templates/workspace/operators/meta_agent.md templates/workspace/operators/meta_agent_brief.md library/meta_agent/agent_command.py library/meta_agent/hyperagents.py library/meta_agent/ahe_evidence_editor.py tests/test_candidate_smoke.py tests/test_agent_command_meta_agent.py tests/test_hyperagents_meta_agent.py tests/test_ahe_meta_agent.py tests/test_harbor_evaluator_template.py
git commit -m "Expose generic candidate smoke diagnostics"
```

Expected: all tests pass and `rg "validate_miniswe_candidate" src/evolve` has no runtime caller.

---

### Task 3: Replace Parallel Results with One Evaluation Record

**Files:**
- Rewrite: `src/evolve/evaluation.py`
- Modify: `src/evolve/task_vectors.py`
- Rewrite: `src/evolve/evaluator.py`
- Simplify: `src/evolve/runtime.py`
- Modify: `src/evolve/workspace.py`
- Modify: `templates/evaluator/parse_score.py`
- Rename: `tests/test_evaluation_certificates.py` to `tests/test_evaluation_records.py`
- Modify: `tests/test_task_vectors.py`
- Modify: `tests/test_m1_evaluator_invariants.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Produces: `EvaluationRecord`, `classify_evaluation(...)`, `trial_results(...)`, and `evaluate(...) -> EvaluationRecord`.

- [ ] **Step 1: Write the four canonical classification tests**

```python
def test_exception_beats_numeric_reward() -> None:
    trial = TrialResult("task", 0, Outcome.INFRASTRUCTURE_FAILED, 0.0, "infrastructure", "ModuleNotFoundError")
    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=1)
    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED
    assert record.score is None


def test_candidate_failure_beats_missing_trial_count() -> None:
    trial = TrialResult("task", 0, Outcome.CANDIDATE_INVALID, None, "candidate", "RuntimeError")
    record = classify_evaluation(**record_values(), trials=(trial,), expected_trials=60)
    assert record.outcome is Outcome.CANDIDATE_INVALID


def test_candidate_wide_setup_failure_needs_no_trial_rows() -> None:
    record = classify_evaluation(
        **record_values(),
        trials=(),
        expected_trials=60,
        setup_outcome=Outcome.CANDIDATE_INVALID,
        setup_reason="candidate dependency setup failed",
    )
    assert record.outcome is Outcome.CANDIDATE_INVALID
    assert record.score is None


def test_missing_evidence_is_infrastructure() -> None:
    record = classify_evaluation(**record_values(), trials=(), expected_trials=1)
    assert record.outcome is Outcome.INFRASTRUCTURE_FAILED


def test_complete_trials_are_the_only_scored_aggregate() -> None:
    trials = (
        TrialResult("a", 0, Outcome.BENCHMARK_COMPLETE, 1.0, "benchmark"),
        TrialResult("b", 0, Outcome.BENCHMARK_COMPLETE, 0.0, "benchmark"),
    )
    record = classify_evaluation(**record_values(), trials=trials, expected_trials=2)
    assert record.outcome is Outcome.BENCHMARK_COMPLETE
    assert record.score == 0.5
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_evaluation_records.py tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py
```

Expected: imports or assertions fail against `EvaluationCertificate` and legacy status aggregation.

- [ ] **Step 3: Implement the single record and classifier**

```python
@dataclass(frozen=True)
class EvaluationRecord:
    experiment_id: str
    generation: str
    candidate_commit: str
    purpose: str
    attempt: int
    evaluator_fingerprint: str
    task_set_hash: str
    runtime_fingerprint: str
    expected_trials: int
    outcome: Outcome
    reason: str
    trials: tuple[TrialResult, ...]
    score: float | None
    cost_usd: float
    wall_s: float
    retry_of: int | None = None
    artifacts: dict[str, str] | None = None

    @property
    def status(self) -> str:
        return "complete" if self.outcome is Outcome.BENCHMARK_COMPLETE else self.outcome.value

    @property
    def selection_eligible(self) -> bool:
        return self.outcome is Outcome.BENCHMARK_COMPLETE and self.purpose in {"candidate", "genesis"}

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["trials"] = [{**asdict(trial), "outcome": trial.outcome.value} for trial in self.trials]
        return payload


def classify_evaluation(
    *,
    trials: tuple[TrialResult, ...],
    expected_trials: int,
    benchmark_timeout_is_zero: bool = False,
    setup_outcome: Outcome | None = None,
    setup_reason: str | None = None,
    **values: Any,
) -> EvaluationRecord:
    outcomes = tuple(_effective_outcome(trial) for trial in trials)
    if setup_outcome is not None:
        outcomes = (setup_outcome, *outcomes)
    if Outcome.INFRASTRUCTURE_FAILED in outcomes:
        outcome = Outcome.INFRASTRUCTURE_FAILED
        reason = (
            setup_reason
            if setup_outcome is Outcome.INFRASTRUCTURE_FAILED and setup_reason
            else "infrastructure-owned trial failure"
        )
    elif Outcome.CANDIDATE_INVALID in outcomes:
        outcome = Outcome.CANDIDATE_INVALID
        reason = (
            setup_reason
            if setup_outcome is Outcome.CANDIDATE_INVALID and setup_reason
            else "candidate-owned trial failure"
        )
    elif len(trials) != expected_trials:
        outcome, reason = Outcome.INFRASTRUCTURE_FAILED, "missing required trial evidence"
    elif Outcome.CANCELLED in outcomes:
        outcome, reason = Outcome.CANCELLED, "evaluation cancelled"
    elif all(
        trial.score_eligible(benchmark_timeout_is_zero=benchmark_timeout_is_zero)
        for trial in trials
    ):
        outcome, reason = Outcome.BENCHMARK_COMPLETE, "all required trials are scoreable"
    else:
        outcome, reason = Outcome.TIMEOUT, "non-scoreable timeout"
    score = None
    if outcome is Outcome.BENCHMARK_COMPLETE:
        score = sum(float(t.reward) for t in trials if t.reward is not None) / len(trials)
    return EvaluationRecord(**values, expected_trials=expected_trials, trials=trials, outcome=outcome, reason=reason, score=score)
```

Retain one explicit evaluator boolean for scoreable benchmark-agent timeouts; never infer it from exception strings.

- [ ] **Step 4: Convert task vectors directly to trials**

```python
def trial_results(payload: object) -> tuple[TrialResult, ...]:
    vector = normalize_task_vector(payload)
    return tuple(
        TrialResult(
            task_id=task_id,
            trial=int(raw["trial"]),
            outcome=Outcome(str(raw["status"])),
            reward=float(raw["reward"]) if raw.get("reward") is not None else None,
            owner=str(raw.get("owner") or "benchmark"),
            exception_type=str(raw["exception_type"]) if raw.get("exception_type") else None,
            exception_message=str(raw["exception_message"]) if raw.get("exception_message") else None,
        )
        for task_id, task in vector["tasks"].items()
        for raw in task["trials"]
    )
```

- [ ] **Step 5: Make `evaluate(...)` append-only and return the record**

Use:

```python
def evaluate(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    purpose: str = "candidate",
    attempt: int = 1,
    retry_of: int | None = None,
    round_number: int | None = None,
    task_limit: int | None = None,
) -> EvaluationRecord:
```

Store attempts below `runs/evaluations/<purpose>/gen-<g>/candidate-<commit>/attempt-<n>/`; refuse an existing directory and never call `shutil.rmtree`. Run a detached exact tag, read `task_vector.json` and `cost.json`, derive score through `classify_evaluation(...)`, and retain the evaluator return code only as infrastructure evidence when no candidate-owned structured failure exists. Populate `setup_outcome` only from structured evaluator evidence; never classify it by matching raw stderr text.

At workspace initialization, read `EVOLVE_RUNTIME_DIGEST` and write its value
to immutable `evaluator/runtime.pin`. Harbor workspaces require a non-empty
value and a clear error explains that it must identify the evaluator capsule
(normally an immutable image digest). Stub-only tests may use a fixed
`sha256:test-runtime` fixture. Do not inspect or encode candidate dependency
files here.

Record the three identities separately:

```python
evaluator_fingerprint = tag_evaluator_tree
task_set_hash = task_set.digest
runtime_fingerprint = sha256((checkout / "evaluator" / "runtime.pin").read_bytes()).hexdigest()
```

The candidate commit is already its own identity. Do not introduce a combined
fingerprint or evaluation epoch.

- [ ] **Step 6: Keep parser outputs as evidence, not authority**

`parse_score.py` continues writing task vectors, artifact indexes, cost, and compatibility status/score files. `evaluator.py` ignores the compatibility score when constructing `EvaluationRecord`. This leaves one aggregate classifier.

- [ ] **Step 7: Verify GREEN and commit**

```bash
uv run pytest -q tests/test_evaluation_records.py tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py tests/test_runtime.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py
git add src/evolve/evaluation.py src/evolve/task_vectors.py src/evolve/evaluator.py src/evolve/runtime.py src/evolve/workspace.py templates/evaluator/parse_score.py tests/test_evaluation_records.py tests/test_task_vectors.py tests/test_m1_evaluator_invariants.py tests/test_runtime.py tests/test_harbor_artifacts.py tests/test_harbor_evaluator_template.py
git rm tests/test_evaluation_certificates.py
git commit -m "Use one canonical evaluation record"
```

Expected: all tests pass and `rg "class EvaluationCertificate" src/evolve` returns no matches.

---

### Task 4: Connect Genesis, Retry, and Archive Writes

**Files:**
- Modify: `src/evolve/archive.py`
- Modify: `src/evolve/workspace.py:420-446`
- Modify: `src/evolve/driver.py:640-880`
- Modify: `tests/test_m0_init.py`
- Modify: `tests/test_selection_certification.py`
- Create: `tests/test_evaluation_lifecycle.py`
- Modify: `tests/test_ahe_integration.py`

**Interfaces:**
- Consumes: `EvaluationRecord` and `evaluate(...)` from Task 3.
- Produces: `append_evaluation_record(...)` and the only one-retry lifecycle.

- [ ] **Step 1: Write genesis and retry tests**

```python
def test_failed_real_genesis_is_not_selectable(tmp_path: Path) -> None:
    workspace = lifecycle_workspace(tmp_path, ["candidate_invalid"])
    with pytest.raises(RuntimeError, match="genesis candidate_invalid"):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))
    row = ArchiveView(workspace).row("0")
    assert row is not None and row["score"] is None
    assert ArchiveView(workspace).valid_parents() == []


def test_infrastructure_retries_same_commit_once(tmp_path: Path) -> None:
    workspace = lifecycle_workspace(tmp_path, ["infrastructure_failed", "benchmark_complete"])
    run(RunOptions(workspace, max_generations=0, children_per_gen=1))
    attempts = evaluation_events(workspace, "0")
    assert [event["attempt"] for event in attempts] == [1, 2]
    assert attempts[0]["candidate_commit"] == attempts[1]["candidate_commit"]
    assert attempts[1]["retry_of"] == 1


def test_two_infrastructure_failures_pause(tmp_path: Path) -> None:
    workspace = lifecycle_workspace(tmp_path, ["infrastructure_failed", "infrastructure_failed"])
    with pytest.raises(EvaluationPaused):
        run(RunOptions(workspace, max_generations=1, children_per_gen=1))
    assert not tag_exists(workspace, "gen/1")
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_evaluation_lifecycle.py tests/test_m0_init.py tests/test_selection_certification.py
```

Expected: failures from the synthetic genesis score and legacy direct stamping.

- [ ] **Step 3: Initialize genesis as pending**

```python
{
    "genid": "0", "parent": None, "tag": "gen/0",
    "score": None, "outcome": None, "status": "pending",
    "valid_parent": False, "verdict": "pending",
    "reason": "generation zero requires real evaluation",
    "mutated": [], "cost": {"usd": 0, "wall_s": 0},
}
```

Delete the synthetic task vector and score.

- [ ] **Step 4: Append records without translating validity twice**

```python
def append_evaluation_record(workspace: Path, record: EvaluationRecord) -> dict[str, Any]:
    event = {
        **record.to_dict(),
        "event_type": "evaluation",
        "genid": record.generation,
        "tag": f"gen/{record.generation}",
        "status": record.status,
        "selection_eligible": record.selection_eligible,
        "valid_parent": record.selection_eligible,
        "verdict": "keep" if record.selection_eligible else "discard",
        "cost": {"usd": record.cost_usd, "wall_s": record.wall_s},
        MECHANISM_EVAL_FIELD: True,
    }
    append_event(workspace, record.experiment_id, event)
    return event
```

- [ ] **Step 5: Add the only retry helper and remove direct stamps**

```python
def _evaluate_with_one_infra_retry(
    workspace: Path,
    tag: str,
    genid: str,
    *,
    purpose: str,
    round_number: int | None = None,
) -> EvaluationRecord:
    first = evaluate(
        workspace, tag, genid, purpose=purpose, attempt=1,
        round_number=round_number,
    )
    append_evaluation_record(workspace, first)
    if first.outcome is not Outcome.INFRASTRUCTURE_FAILED:
        return first
    second = evaluate(
        workspace, tag, genid, purpose=purpose, attempt=2, retry_of=1,
        round_number=round_number,
    )
    append_evaluation_record(workspace, second)
    if second.outcome is Outcome.INFRASTRUCTURE_FAILED:
        raise EvaluationPaused(f"gen/{genid} infrastructure failed twice")
    return second
```

Route genesis, candidate, forced, and per-round evaluations through it. Genesis accepts only `benchmark_complete`; candidate-invalid later children skip recipe gate/record operators and leave the prior valid parent available. Delete every `valid_parent = result.status in {"complete", "partial"}` path.

- [ ] **Step 6: Verify GREEN and commit**

```bash
uv run pytest -q tests/test_evaluation_lifecycle.py tests/test_m0_init.py tests/test_selection_certification.py tests/test_ahe_integration.py tests/test_m5_driver_operators.py tests/test_m5_record_verb.py
git add src/evolve/archive.py src/evolve/workspace.py src/evolve/driver.py tests/test_m0_init.py tests/test_selection_certification.py tests/test_evaluation_lifecycle.py tests/test_ahe_integration.py tests/test_m5_driver_operators.py tests/test_m5_record_verb.py
git commit -m "Connect canonical evaluation lifecycle"
```

Expected: all tests pass and genesis has no synthetic score.

---

### Task 5: Make `ArchiveView` the Only Eligibility Reader

**Files:**
- Modify: `src/evolve/archive.py`
- Rewrite: `src/evolve/population.py`
- Modify: `src/evolve/frozen/interfaces.py:34-64`
- Modify: `src/evolve/frozen/sdk.py`
- Modify: `src/evolve/report.py`
- Modify: `library/gate/parent_eligible.py`
- Modify: `library/gate/ahe_artifact_valid.py`
- Modify: `library/select/score_child_prop.py`
- Modify: `library/rollout/ahe_trace_analysis.py`
- Modify: `tests/test_selection_certification.py`
- Modify: `tests/test_hyperagents_select.py`
- Modify: `tests/test_hyperagents_semantics.py`
- Modify: `tests/test_ahe_gate_record.py`
- Modify: `tests/test_ahe_rollout.py`

**Interfaces:**
- Produces: `is_parent_record(...)` and `ArchiveView.valid_parents()` as the only eligibility boundary.

- [ ] **Step 1: Write no-promotion and no-partial-parent tests**

```python
@pytest.mark.parametrize("outcome", ["candidate_invalid", "infrastructure_failed", "timeout", "cancelled"])
def test_gate_cannot_promote_invalid_evaluation(tmp_path: Path, outcome: str) -> None:
    workspace = archive_workspace(tmp_path)
    append_evaluation(workspace, generation="1", outcome=outcome, valid_parent=False)
    append_event(workspace, workspace.name, {"genid": "1", "valid_parent": True, "verdict": "keep", "reason": "recipe"})
    assert ArchiveView(workspace).valid_parents() == []


def test_legacy_partial_is_visible_but_not_selectable(tmp_path: Path) -> None:
    workspace = archive_workspace(tmp_path)
    append_event(workspace, workspace.name, {"genid": "1", "status": "partial", "score": 0.5, "valid_parent": True})
    assert ArchiveView(workspace).row("1") is not None
    assert ArchiveView(workspace).valid_parents() == []


@pytest.mark.parametrize(
    "field", ["evaluator_fingerprint", "task_set_hash", "runtime_fingerprint"]
)
def test_mismatched_fixed_identity_is_not_selectable(tmp_path: Path, field: str) -> None:
    workspace = archive_workspace(tmp_path)
    append_complete_evaluation(workspace, generation="1", **{field: "wrong"})
    assert ArchiveView(workspace).valid_parents() == []
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_selection_certification.py tests/test_hyperagents_select.py tests/test_ahe_gate_record.py
```

Expected: legacy status-based readers admit an invalid or partial fixture.

- [ ] **Step 3: Define and use one eligibility predicate**

```python
def is_parent_record(row: dict[str, Any], expected: dict[str, str]) -> bool:
    return (
        row.get("outcome") == Outcome.BENCHMARK_COMPLETE.value
        and row.get("purpose") in {"candidate", "genesis"}
        and row.get("selection_eligible") is True
        and row.get("valid_parent") is True
        and row.get("evaluator_fingerprint") == expected["evaluator_fingerprint"]
        and row.get("task_set_hash") == expected["task_set_hash"]
        and row.get("runtime_fingerprint") == expected["runtime_fingerprint"]
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
    )
```

Derive `expected` from immutable `gen/0:evaluator`, the bound task set, and
`gen/0:evaluator/runtime.pin`. Make `ArchiveView.valid_parents()` return an
empty list when those Git objects are unavailable; otherwise filter
`self.rows()` with this function. Make population, SDK, best-row reporting,
and recipe selectors delegate to `ArchiveView` or this predicate; none may
inspect `status` for eligibility.

- [ ] **Step 4: Make gate events rejection-only**

Archive merge may change a canonical record's `valid_parent` from true to false. Ignore false-to-true promotion unless the underlying evaluation event already has `selection_eligible=true`.

Use this shared gate precondition in both generic and AHE gates:

```python
keep = child.get("outcome") == "benchmark_complete" and child.get("selection_eligible") is True
```

AHE artifact validation remains an additional rejection rule. Keep `status` only for display compatibility. Historical rows without canonical `outcome` are readable but require reevaluation before selection.

- [ ] **Step 5: Verify GREEN and commit**

```bash
uv run pytest -q tests/test_selection_certification.py tests/test_hyperagents_select.py tests/test_hyperagents_semantics.py tests/test_ahe_gate_record.py tests/test_ahe_rollout.py tests/test_ahe_select.py tests/test_ahe_meta_agent.py
git add src/evolve/archive.py src/evolve/population.py src/evolve/frozen/interfaces.py src/evolve/frozen/sdk.py src/evolve/report.py library/gate/parent_eligible.py library/gate/ahe_artifact_valid.py library/select/score_child_prop.py library/rollout/ahe_trace_analysis.py tests/test_selection_certification.py tests/test_hyperagents_select.py tests/test_hyperagents_semantics.py tests/test_ahe_gate_record.py tests/test_ahe_rollout.py tests/test_ahe_select.py tests/test_ahe_meta_agent.py
git commit -m "Select only canonical evaluation records"
```

Expected: all tests pass and `rg 'status.*partial|partial.*valid_parent' src/evolve library/gate library/select` finds no eligibility rule.

---

### Task 6: Own Runtime Cleanup and Validate One Real Candidate

**Files:**
- Modify: `src/evolve/runtime.py`
- Modify: `src/evolve/evaluator.py`
- Modify: `src/evolve/candidate_runtime.py`
- Modify: `src/evolve/workspace.py:76-107`
- Create: `templates/evaluator/cleanup_harbor.py`
- Modify: `templates/evaluator/engines/harbor.sh`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_candidate_smoke.py`
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_harbor_evaluator_template.py`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `library/PROTOCOL.md`

**Interfaces:**
- Produces: `run_owned(...)`, pinned workspace console, attempt-scoped Harbor cleanup, fresh locked MiniSWE seeds, and one real DevBoxS canary report.

- [ ] **Step 1: Write runtime ownership tests**

```python
def test_owned_process_kills_child_group_on_timeout(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    result = run_owned(
        [sys.executable, str(spawning_script(tmp_path)), str(pid_file)],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=0.2,
    )
    assert result.timed_out is True
    assert not child_pid_is_alive(int(pid_file.read_text()))


def test_cleanup_removes_only_exact_trial_compose_project(tmp_path: Path, monkeypatch) -> None:
    jobs = harbor_jobs_with_trial(tmp_path, "task__ABC")
    assert run_cleanup_with_fake_docker(jobs, monkeypatch) == [["docker", "rm", "-f", "owned-container"]]


def test_console_has_no_accidental_python_fallback(tmp_path: Path) -> None:
    workspace = initialized_workspace(tmp_path)
    text = (workspace / "evolve").read_text()
    assert "EVOLVE_FRAMEWORK_PYTHON" in text
    assert "python3.13 python3.12 python3.11 python3" not in text
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest -q tests/test_runtime.py tests/test_candidate_smoke.py tests/test_agent_runner.py tests/test_harbor_evaluator_template.py
```

Expected: failures for evaluator process ownership, cleanup, and console fallback.

- [ ] **Step 3: Implement one owned-process helper**

```python
@dataclass(frozen=True)
class OwnedResult:
    returncode: int
    stdout: str
    stderr: str
    wall_s: float
    timed_out: bool


def run_owned(command: list[str], *, cwd: Path, env: dict[str, str], timeout_s: float | None = None) -> OwnedResult:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
        return OwnedResult(process.returncode, stdout, stderr, time.monotonic() - started, False)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return OwnedResult(process.returncode, stdout, stderr, time.monotonic() - started, True)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
```

Use it in evaluator and smoke; remove their direct `subprocess.run(...)` calls.

- [ ] **Step 4: Add exact Harbor Compose cleanup**

`cleanup_harbor.py` reads only trial `config.json` files below the current jobs directory, extracts `trial_name`, forms Harbor's project name from `f"{trial_name}__env"` by lowercasing and replacing characters outside `[a-z0-9_-]` with `-`, queries:

```bash
docker ps -aq --filter label=com.docker.compose.project=<exact-project>
```

and runs `docker rm -f` only for returned IDs. In `harbor.sh`, set `--job-name "$EVOLVE_ATTEMPT_ID"` and trap `EXIT`, `TERM`, and `INT` to run:

```sh
"$EVOLVE_FRAMEWORK_PYTHON" evaluator/cleanup_harbor.py "$jobs_dir"
```

Preserve the Harbor return code after cleanup.

- [ ] **Step 5: Pin the generated framework console**

```sh
PYTHON="${EVOLVE_FRAMEWORK_PYTHON:-@FRAMEWORK_PYTHON@}"
if [ ! -x "$PYTHON" ]; then
  echo "evolve: pinned framework Python is unavailable; set EVOLVE_FRAMEWORK_PYTHON" >&2
  exit 1
fi
exec "$PYTHON" -m evolve "$@"
```

Render `sys.executable` at initialization. Do not dynamically install Typer/PyYAML or fall back to arbitrary system Python.

- [ ] **Step 6: Run focused, static, and full local verification**

```bash
uv run ruff check src/evolve tests library
uv run pytest -q tests/test_runtime.py tests/test_candidate_smoke.py tests/test_agent_runner.py tests/test_harbor_evaluator_template.py
uv run pytest -q
git diff --check
```

Expected: Ruff and all tests pass; diff check prints nothing.

- [ ] **Step 7: Commit local implementation and documentation**

```bash
git add src/evolve/runtime.py src/evolve/evaluator.py src/evolve/candidate_runtime.py src/evolve/workspace.py templates/evaluator/cleanup_harbor.py templates/evaluator/engines/harbor.sh tests/test_runtime.py tests/test_candidate_smoke.py tests/test_agent_runner.py tests/test_harbor_evaluator_template.py README.md ARCHITECTURE.md library/PROTOCOL.md
git commit -m "Own evaluation runtime lifecycle"
```

- [ ] **Step 8: Create fresh AHE and HyperAgents MiniSWE seeds on DevBoxS**

Under a new timestamped canary root, extract each historical `gen/0:target` without changing historical workspaces. For each seed:

- AHE source: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-ahe-30x30-20260711-204345/workspace`
- HyperAgents source: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/swebenchpro-miniswe-hyperagents-30x30-20260711-020208/workspace`

1. run `uv add --project <seed> fastapi`, which updates both the project and lock;
2. run `uv lock --project <seed>` with the configured installation proxy without printing proxy values;
3. add `!uv.lock` to the seed `.gitignore` when `git check-ignore uv.lock` succeeds;
4. initialize and commit the complete seed; and
5. require `git ls-files --error-unmatch pyproject.toml uv.lock` to succeed.

Require the AHE and HyperAgents source tree hashes to remain different.

- [ ] **Step 9: Initialize one fresh canary and verify its committed object**

Before Harbor, require:

```bash
git -C "$WORKSPACE" cat-file -e gen/0:target/pyproject.toml
git -C "$WORKSPACE" cat-file -e gen/0:target/uv.lock
git -C "$WORKSPACE" diff --quiet
git -C "$WORKSPACE" diff --cached --quiet
```

Record framework commit, candidate commit/tree, evaluator fingerprint, runtime digest, and task-file SHA-256. Never record environment values.
Set `EVOLVE_RUNTIME_DIGEST` to the immutable DevBoxS evaluator capsule digest
before initialization; do not invent a digest from the candidate lock.

- [ ] **Step 10: Run one full smoke and one one-task evaluation**

```bash
./evolve candidate-smoke --full
./evolve eval . 0
```

Use exactly one training task and one trial. Verify from artifacts that frozen sync, MiniSWE import, LiteLLM model initialization, direct virtualenv Python, redacted diagnostics, canonical outcome, root-workspace cleanliness, and attempt-owned container cleanup all behave as designed.

If anything unusual occurs, stop and report. Do not start a comparative or held-out experiment.

- [ ] **Step 11: Store a self-contained remote report**

Write it only under the new canary root. Include local/full test results, commit and task identities, smoke/evaluation outcomes, artifact paths and hashes, cleanup result, and credential/proxy safe-scan booleans. Do not push.

---

## Final Simplicity Review

- `rg "CandidateDependencyIdentity|EvaluationCertificate|class EvaluationResult|certified_parent_rows" src/evolve` returns no matches.
- `rg "mark_preflight|current_epoch|epoch-" src/evolve tests` returns no matches.
- `rg 'Literal\["quick"|"container"' src/evolve tests` returns no smoke mode variants.
- `rg 'status.*partial|partial.*valid_parent' src/evolve library/gate library/select` returns no eligibility rule.
- One aggregate classifier and one candidate tree builder exist.
- Smoke has one public mode and one immutable evaluator entry point.
- Shared core code contains no UV or Python dependency filenames.
- Failed genesis and reward-bearing exceptions are scoreless and unselectable.
- The two unrelated SDD reports remain unstaged.
- Nothing has been pushed.
