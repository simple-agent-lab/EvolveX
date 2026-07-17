# Official-Style AHE Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current AHE recipe into a thin, official-style sequential loop with required per-task LLM debugger reports, cross-generation attribution, and manifest-backed edits.

**Architecture:** Keep the generic driver and operator protocol unchanged. Add one method-neutral read-only Harbor prompt runner, make `trace_analyzer/ahe.py` own official-style task grouping/debugger orchestration/attribution, make `meta_agent/ahe.py` own the evolve prompt and required manifest, and compose AHE-specific selection and gating through ordinary recipe variants.

**Tech Stack:** Python 3.11+, Harbor CLI, MiniSWE Harbor agent, PyYAML, pytest/pytest-xdist, Ruff, ty, Git.

## Global Constraints

- Current `main` is the only implementation baseline; do not merge or copy the earlier `codex/method-faithful-ahe` branch.
- Do not add AHE-specific branches, fields, or schemas to `src/evolve/driver.py` or `src/evolve/frozen/interfaces.py`.
- Keep `target/**` as the only mutable AHE surface.
- Reuse the AHE meta-agent's allowlisted Harbor/model configuration; do not add a second model block.
- Use official debugger defaults: `max_tasks: 90`, `max_concurrent: 16`, `timeout_per_task: 600`, `retry_attempts: 3`.
- Run one required LLM debugger call per selected task, containing all rollouts for that task.
- Do not silently fall back when debugger analysis fails; exhausted failures stop the trace-analyzer operator.
- Keep the overview deterministic; the official implementation uses per-task LLM calls and aggregates their one-line diagnoses without a separate overview LLM call.
- Require one validated `change_manifest.json` that covers every changed target path exactly once.
- Allow a lower-scoring, structurally valid AHE generation to remain the next sequential parent.
- Remove `budget_usd` and `max_cases` from the AHE recipe.
- Do not modify HyperAgents in this plan.

## File Structure

- Modify `library/meta_agent/runners/harbor.py`: expose a method-neutral read-only Harbor prompt execution path that shares command construction, logging, process cleanup, result parsing, redaction, and usage extraction with the editing path.
- Modify `library/meta_agent/runners/__init__.py`: export the read-only runner.
- Modify `library/trace_analyzer/ahe.py`: group task rollouts, build official prompts, run debugger calls, write reports, and compute cross-generation attribution.
- Create `library/meta_agent/support/ahe_manifest.py`: extract and validate the AHE manifest independently of the meta-agent process wrapper.
- Modify `library/meta_agent/ahe.py`: build the official-style evolve prompt, extract/validate the returned manifest, and persist it.
- Create `library/select/ahe_latest.py`: select the newest valid AHE parent.
- Create `library/gate/ahe_artifact_valid.py`: admit canonically evaluated children only when the AHE manifest artifact exists and matches the child identity.
- Modify `recipes/ahe/evolve.yaml` and `recipes/ahe/README.md`: bind the new variants and official debugger defaults.
- Modify `tests/test_harbor_meta_agent.py`, `tests/test_ahe_trace_analyzer.py`, `tests/test_ahe_meta_agent.py`, and `tests/test_m9_ahe_recipe.py`; create focused selector, gate, and lifecycle tests.

---

### Task 1: Add a method-neutral read-only Harbor prompt runner

**Files:**
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `library/meta_agent/runners/__init__.py`
- Modify: `tests/test_harbor_meta_agent.py`

**Interfaces:**
- Consumes: existing Harbor configuration keys and `OperatorContext`.
- Produces: `run_readonly_agent(checkout: Path, prompt: str, ctx: OperatorContext, *, output_dir: Path, job_name: str, timeout_s: float) -> AgentRunResult`.
- Invariant: read-only execution never prepares, returns, or installs an editable candidate artifact.

- [ ] **Step 1: Write a failing read-only runner test**

Add a fake-Harbor mode that accepts no `--artifact`, writes one trial result plus one final trajectory message, and records its arguments. Add this test:

```python
def test_harbor_readonly_agent_returns_response_without_candidate_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    _install_fake_harbor(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARBOR_MODE", "readonly")
    runner = _harbor_runner_module()
    ctx = _ctx(checkout, run_dir)

    result = runner.run_readonly_agent(
        checkout,
        "Analyze this trace",
        ctx,
        output_dir=run_dir / "trace_analyzer/debugger/task-a/attempt-1",
        job_name="ahe-debug-task-a-attempt-1",
        timeout_s=30,
    )

    assert result.output == "ROOT CAUSE: tool retry loop"
    assert result.usage["usd"] == 0.25
    command = json.loads(
        (run_dir / "trace_analyzer/debugger/task-a/attempt-1/command.json").read_text()
    )
    assert "--artifact" not in command
    assert not (checkout / "target" / "added.txt").exists()
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py::test_harbor_readonly_agent_returns_response_without_candidate_artifact
```

Expected: fail with `AttributeError` because `run_readonly_agent` does not exist.

- [ ] **Step 3: Refactor shared Harbor command construction**

Replace the artifact-specific `_build_command` internals with a shared base builder and keep the current editing wrapper:

```python
def _base_command(
    harbor: str,
    task_root: Path,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
) -> list[str]:
    command = [
        harbor,
        "exec",
        "--path",
        str(task_root.resolve()),
        "--no-scan",
        "--instruction-path",
        str(prompt_path.resolve()),
        "--workdir",
        "/app",
        "--tasks-dir",
        str(tasks_dir.resolve()),
        "--agent",
        str(config.get("agent") or "codex"),
        "--jobs-dir",
        str(jobs_root.resolve()),
        "--job-name",
        job_name,
        "--n-concurrent",
        "1",
        "--n-attempts",
        "1",
        "--max-retries",
        str(_nonnegative_int(config.get("max_retries"), 0)),
    ]
    environment = config.get("environment")
    if environment:
        command.extend(["--env", str(environment)])
    image = config.get("image")
    if image:
        command.extend(["--image", str(image)])
    model = config.get("model")
    if model:
        command.extend(["--model", str(model)])
    kwargs = config.get("agent_kwargs")
    if isinstance(kwargs, dict):
        for key, value in kwargs.items():
            command.extend(["--ak", f"{key}={value}"])
    _append_agent_env(command, config)
    if os.environ.get("EVOLVE_LIVE_OUTPUT") != "1":
        command.append("--quiet")
    return command


def _build_command(
    harbor: str,
    bundle: _EditableBundle,
    prompt_path: Path,
    jobs_root: Path,
    tasks_dir: Path,
    job_name: str,
    config: dict[str, Any],
) -> list[str]:
    command = _base_command(
        harbor, bundle.task_root, prompt_path, jobs_root, tasks_dir, job_name, config
    )
    artifact_index = command.index("--tasks-dir")
    command[artifact_index:artifact_index] = ["--artifact", _ARTIFACT_SOURCE]
    return command
```

Keep `_build_command`'s existing explicit signature; only its body changes.

- [ ] **Step 4: Add explicit per-call timeout support**

Change `_run_harbor` to accept an optional timeout while retaining the operator-derived default:

```python
def _run_harbor(
    command: list[str],
    checkout: Path,
    log_path: Path,
    config: dict[str, Any],
    *,
    timeout_s: float | None = None,
) -> tuple[int, float]:
    effective_timeout = timeout_s if timeout_s is not None else _run_timeout()
```

In the existing function body, change only `process.wait(timeout=_run_timeout())` to
`process.wait(timeout=effective_timeout)`. Preserve the existing `Popen`, reader
thread, SIGTERM/SIGKILL cleanup, redacted log write, and elapsed-time return; do
not replace them with `subprocess.run`.

- [ ] **Step 5: Implement the read-only runner**

Add this public function after `_usage`:

```python
def run_readonly_agent(
    checkout: Path,
    prompt: str,
    ctx: OperatorContext,
    *,
    output_dir: Path,
    job_name: str,
    timeout_s: float,
) -> AgentRunResult:
    harbor = shutil.which("harbor")
    if harbor is None:
        raise AgentCommandError("Harbor read-only runner requires the harbor CLI on PATH", returncode=1)
    task_root = output_dir / "task"
    prompt_path = output_dir / "prompt.md"
    jobs_root = output_dir / "jobs"
    tasks_dir = output_dir / "tasks"
    task_root.mkdir(parents=True, exist_ok=False)
    prompt_path.write_text(prompt.rstrip() + "\n")
    command = _base_command(harbor, task_root, prompt_path, jobs_root, tasks_dir, job_name, ctx.config)
    _write_json(output_dir / "command.json", [_redact(arg) for arg in command])
    returncode, wall_s = _run_harbor(
        command,
        checkout,
        output_dir / "harbor.log",
        ctx.config,
        timeout_s=timeout_s,
    )
    trial_dir, trial = _trial_result(jobs_root / job_name)
    usage = _usage(trial, wall_s)
    _write_json(output_dir / "trial.json", trial)
    output = _agent_output(trial_dir).strip()
    if returncode != 0:
        raise AgentCommandError(f"harbor exec exited {returncode}", output=output, usage=usage, returncode=returncode)
    if trial.get("exception_info") not in (None, {}):
        raise AgentCommandError(
            f"Harbor read-only trial failed: {_redact(str(trial.get('exception_info')))}",
            output=output,
            usage=usage,
            returncode=1,
        )
    if not output:
        raise AgentCommandError("Harbor read-only trial returned no agent response", usage=usage, returncode=1)
    return AgentRunResult(
        stdout=output,
        stderr="",
        output=output,
        returncode=0,
        wall_s=wall_s,
        usage=usage,
    )
```

Export it from `library/meta_agent/runners/__init__.py`:

```python
from library.meta_agent.runners.harbor import run_readonly_agent

__all__ = ["run_agent", "run_readonly_agent", "runner_name"]
```

- [ ] **Step 6: Run focused Harbor tests**

Run:

```bash
uv run pytest -q tests/test_harbor_meta_agent.py
uv run ruff check library/meta_agent/runners tests/test_harbor_meta_agent.py
```

Expected: all tests pass and existing editable bundle behavior is unchanged.

- [ ] **Step 7: Commit the runner**

```bash
git add library/meta_agent/runners/harbor.py library/meta_agent/runners/__init__.py tests/test_harbor_meta_agent.py
git commit -m "feat: add read-only Harbor agent execution"
```

---

### Task 2: Build official-style AHE debugger jobs and prompts

**Files:**
- Modify: `library/trace_analyzer/ahe.py`
- Modify: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: normalized rollout cases already produced by `_normalize`.
- Produces: `TaskAnalysisJob`, `_build_jobs(cases, max_tasks)`, and `_debugger_prompt(job)`.

- [ ] **Step 1: Add failing grouping and ordering tests**

Add:

```python
def test_ahe_groups_all_rollouts_per_task_and_prioritizes_failures() -> None:
    module = _module()
    cases = [
        _case("pass-a-1", "passed", 1.0) | {"task_name": "task-a"},
        _case("pass-a-2", "passed", 1.0) | {"task_name": "task-a"},
        _case("fail-b-1", "failed", 0.0) | {"task_name": "task-b"},
        _case("pass-b-2", "passed", 1.0) | {"task_name": "task-b"},
    ]

    jobs = module._build_jobs(cases, max_tasks=90)

    assert [job.task_name for job in jobs] == ["task-b", "task-a"]
    assert [case["trial_name"] for case in jobs[0].cases] == ["fail-b-1", "pass-b-2"]
    assert jobs[0].mode == "debug"
    assert jobs[1].mode == "summary"


def test_ahe_max_tasks_matches_official_priority_order() -> None:
    module = _module()
    cases = [
        _case("pass", "passed", 1.0) | {"task_name": "pass-task"},
        _case("fail", "failed", 0.0) | {"task_name": "fail-task"},
    ]
    assert [job.task_name for job in module._build_jobs(cases, max_tasks=1)] == ["fail-task"]
```

- [ ] **Step 2: Run the grouping tests and verify RED**

```bash
uv run pytest -q \
  tests/test_ahe_trace_analyzer.py::test_ahe_groups_all_rollouts_per_task_and_prioritizes_failures \
  tests/test_ahe_trace_analyzer.py::test_ahe_max_tasks_matches_official_priority_order
```

Expected: fail because `_build_jobs` is undefined.

- [ ] **Step 3: Add the job dataclass and builder**

Add:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskAnalysisJob:
    task_name: str
    cases: tuple[Case, ...]
    n_pass: int
    n_fail: int
    n_timeout: int
    mode: str


def _build_jobs(cases: list[Case], max_tasks: int) -> list[TaskAnalysisJob]:
    grouped: dict[str, list[Case]] = {}
    for case in cases:
        task_name = str(case.get("task_name") or case.get("trial_name") or "unknown")
        grouped.setdefault(task_name, []).append(case)
    jobs: list[TaskAnalysisJob] = []
    for task_name, task_cases in grouped.items():
        n_pass = sum(case.get("outcome") == "passed" for case in task_cases)
        n_timeout = sum(case.get("outcome") in {"timeout", "incomplete"} for case in task_cases)
        n_fail = len(task_cases) - n_pass - n_timeout
        jobs.append(
            TaskAnalysisJob(
                task_name=task_name,
                cases=tuple(task_cases),
                n_pass=n_pass,
                n_fail=n_fail,
                n_timeout=n_timeout,
                mode="debug" if n_fail or n_timeout else "summary",
            )
        )
    jobs.sort(key=lambda job: (job.mode == "summary", -(job.n_fail + job.n_timeout), job.task_name))
    return jobs[:max_tasks]
```

- [ ] **Step 4: Add exact official-style prompt tests**

Assert failure prompts contain `FAILURE POINT`, `ROOT CAUSE`, `WHAT SHOULD HAVE BEEN DONE`, and `GENERAL LESSON`; success prompts contain `KEY STRATEGY`, `SUCCESS FACTORS`, and `REUSABLE PATTERN`. For multi-rollout jobs assert the prompt labels each trace and requests `PASS vs FAIL` comparison.

```python
def test_ahe_debugger_prompts_match_official_k1_modes() -> None:
    module = _module()
    failed = module._build_jobs([_case("f", "failed", 0.0)], 90)[0]
    passed = module._build_jobs([_case("p", "passed", 1.0)], 90)[0]
    assert all(
        heading in module._debugger_prompt(failed)
        for heading in (
            "FAILURE POINT",
            "ROOT CAUSE",
            "WHAT SHOULD HAVE BEEN DONE",
            "GENERAL LESSON",
        )
    )
    assert all(name in module._debugger_prompt(passed) for name in ("KEY STRATEGY", "SUCCESS FACTORS", "REUSABLE PATTERN"))
```

- [ ] **Step 5: Implement the prompt renderer**

Port the four official prompt constants (`debug k=1`, `debug k>1`, `summary k=1`, `summary k>1`) into `ahe.py`. Implement:

```python
def _debugger_prompt(job: TaskAnalysisJob) -> str:
    trace_labels = ", ".join(
        f"trace{index:02d}={'PASS' if case.get('outcome') == 'passed' else 'TIMEOUT' if case.get('outcome') in {'timeout', 'incomplete'} else 'FAIL'}"
        for index, case in enumerate(job.cases, start=1)
    )
    evidence = "\n\n".join(
        f"## trace{index:02d}\n```json\n{json.dumps(case, indent=2, sort_keys=True)}\n```"
        for index, case in enumerate(job.cases, start=1)
    )
    template = _prompt_template(job.mode, len(job.cases))
    return template.format(
        task_name=job.task_name,
        n_total=len(job.cases),
        n_pass=job.n_pass,
        n_fail=job.n_fail,
        n_timeout=job.n_timeout,
        trace_labels=trace_labels,
    ) + "\n\n# Bounded trace evidence\n\n" + evidence
```

Use the official word caps: under 300 words for failures and under 150 words for all-pass summaries.

- [ ] **Step 6: Run focused tests and commit**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py
uv run ruff check library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "feat: build official-style AHE debugger jobs"
```

---

### Task 3: Execute required debugger calls with official concurrency and failure behavior

**Files:**
- Modify: `library/trace_analyzer/ahe.py`
- Modify: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: `run_readonly_agent`, `TaskAnalysisJob`, and the frozen meta-agent config.
- Produces: `_run_debugger_jobs(checkout, ctx, jobs) -> list[DebuggerResult]`.

- [ ] **Step 1: Write failing configuration-reuse and failure tests**

Create a checkout `evolve.yaml` whose AHE meta-agent block contains `agent`, `model`, `environment`, `image`, `agent_kwargs`, `agent_env`, `agent_pythonpath`, and `editable_roots`. Assert `_debugger_runner_config` returns every allowlisted key and excludes `editable_roots`, `variant`, `runner`, and `timeout_s`.

Monkeypatch `run_readonly_agent` to fail twice and succeed on the third call; assert exactly three attempts. Add another test that always raises `AgentCommandError` and assert `AheTraceAnalyzer.analyze` propagates a failure instead of emitting fallback prose.

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py -k 'runner_config or retries or debugger_failure'
```

Expected: fail because debugger execution functions do not exist.

- [ ] **Step 3: Implement allowlisted configuration reuse**

```python
from dataclasses import replace
from evolve.config import operator_blocks
from evolve.agent import AgentCommandError
from library.meta_agent.runners import run_readonly_agent

_DEBUGGER_RUNNER_KEYS = (
    "agent", "model", "environment", "image", "agent_kwargs", "agent_env", "agent_pythonpath"
)


def _debugger_runner_config(checkout: Path) -> dict[str, Any]:
    meta = operator_blocks(checkout).get("meta_agent")
    if not isinstance(meta, dict):
        raise RuntimeError("AHE debugger requires operators.meta_agent configuration")
    config = {key: meta[key] for key in _DEBUGGER_RUNNER_KEYS if key in meta}
    config["max_retries"] = 0
    if not config.get("agent") or not config.get("model"):
        raise RuntimeError("AHE debugger requires meta-agent agent and model")
    return config
```

- [ ] **Step 4: Add result type, safe names, retries, and concurrency**

```python
import concurrent.futures
import hashlib


@dataclass(frozen=True)
class DebuggerResult:
    job: TaskAnalysisJob
    response: str
    usage: dict[str, Any]


def _safe_task_name(task_name: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", task_name):
        return task_name
    return "task-" + hashlib.sha256(task_name.encode()).hexdigest()


def _run_debugger_job(checkout: Path, ctx: OperatorContext, job: TaskAnalysisJob) -> DebuggerResult:
    attempts = _positive_int(ctx.config.get("retry_attempts"), 3)
    timeout_s = float(ctx.config.get("timeout_per_task") or 600)
    runner_ctx = replace(ctx, config=_debugger_runner_config(checkout))
    slug = _safe_task_name(job.task_name)
    last_error: AgentCommandError | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = run_readonly_agent(
                checkout,
                _debugger_prompt(job),
                runner_ctx,
                output_dir=ctx.run_dir / "trace_analyzer/debugger" / slug / f"attempt-{attempt}",
                job_name=f"ahe-debug-{slug}-attempt-{attempt}",
                timeout_s=timeout_s,
            )
            return DebuggerResult(job=job, response=result.output.strip(), usage=dict(result.usage))
        except AgentCommandError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _run_debugger_jobs(
    checkout: Path, ctx: OperatorContext, jobs: list[TaskAnalysisJob]
) -> list[DebuggerResult]:
    if not jobs:
        raise RuntimeError("AHE debugger found no rollout tasks")
    results = [_run_debugger_job(checkout, ctx, jobs[0])]
    workers = _positive_int(ctx.config.get("max_concurrent"), 16)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_debugger_job, checkout, ctx, job): job for job in jobs[1:]}
        completed = [future.result() for future in concurrent.futures.as_completed(futures)]
    by_name = {result.job.task_name: result for result in [*results, *completed]}
    return [by_name[job.task_name] for job in jobs]
```

Do not catch errors around `future.result()`; any exhausted debugger failure must fail the operator.

- [ ] **Step 5: Wire debugger execution into `analyze`**

Remove the existing `_select(cases, max_cases)` call and its `max_cases`
configuration read. Replace them with:

```python
jobs = _build_jobs(cases, _positive_int(ctx.config.get("max_tasks"), 90))
debugger_results = _run_debugger_jobs(checkout, ctx, jobs)
```

Keep raw case normalization, redaction, and bounded JSONL output. Do not emit successful `TraceAnalyzerResult` until all debugger jobs finish.

- [ ] **Step 6: Run focused tests and commit**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py tests/test_harbor_meta_agent.py
uv run ruff check library/trace_analyzer/ahe.py library/meta_agent/runners tests/test_ahe_trace_analyzer.py
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "feat: run required AHE debugger analyses"
```

---

### Task 4: Write official-style reports and cross-generation attribution

**Files:**
- Modify: `library/trace_analyzer/ahe.py`
- Modify: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: ordered `DebuggerResult` values, current cases, prior run cases, and prior manifest.
- Produces: `analysis/overview.md`, `analysis/detail/*.md`, `analysis/change_evaluation.json`, `feedback.md`, and `evidence/selected.md`.

- [ ] **Step 1: Add failing report and attribution tests**

Build a generation-2 fixture:

```text
runs/gen-1/rollout/cases.json: task-a failed, task-b passed
runs/gen-1/meta_agent/change_manifest.json: predicts task-a, risks task-b
runs/gen-2/rollout/cases.json: task-a passed, task-b failed
```

Assert:

```python
change = json.loads((ctx.run_dir / "trace_analyzer/analysis/change_evaluation.json").read_text())
assert change["transitions"]["task-a"] == "fail_to_pass"
assert change["transitions"]["task-b"] == "pass_to_fail"
assert change["prediction_results"]["task-a"] == "confirmed"
assert change["risk_results"]["task-b"] == "realized"
assert "ROOT CAUSE" in (ctx.run_dir / "trace_analyzer/analysis/detail/task-a.md").read_text()
assert "task-a" in (ctx.run_dir / "trace_analyzer/analysis/overview.md").read_text()
```

Add a generation-1 baseline test. Add a generation-2 missing-prior-artifact test that expects a raised error.

- [ ] **Step 2: Run the new tests and verify RED**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py -k 'change_evaluation or official_reports or missing_prior'
```

Expected: fail because analysis artifacts are not written.

- [ ] **Step 3: Implement task outcome and transition classification**

```python
def _task_outcomes(cases: list[Case]) -> dict[str, str]:
    grouped = {job.task_name: job for job in _build_jobs(cases, max_tasks=max(1, len(cases)))}
    outcomes: dict[str, str] = {}
    for task_name, job in grouped.items():
        if job.n_fail or job.n_timeout:
            outcomes[task_name] = "fail"
        elif job.n_pass:
            outcomes[task_name] = "pass"
        else:
            outcomes[task_name] = "unknown"
    return outcomes


def _transition(before: str | None, after: str | None) -> str:
    if before == "fail" and after == "pass":
        return "fail_to_pass"
    if before == "pass" and after == "fail":
        return "pass_to_fail"
    if before == after == "pass":
        return "unchanged_pass"
    if before == after == "fail":
        return "unchanged_fail"
    return "unknown"
```

- [ ] **Step 4: Implement baseline and prior-manifest attribution**

For `ctx.parent in (None, "0")`, write:

```json
{"status":"baseline","manifest":null,"transitions":{},"prediction_results":{},"risk_results":{}}
```

For later generations, require both:

```python
prior_run = ctx.workspace / "runs" / f"gen-{ctx.parent}"
prior_cases_path = prior_run / "rollout" / "cases.json"
manifest_path = prior_run / "meta_agent" / "change_manifest.json"
```

Load `predicted_effects` and `risk_tasks` from every manifest change. Classify a prediction as `confirmed` only for `fail_to_pass`, `not_confirmed` otherwise; classify a risk as `realized` only for `pass_to_fail`, `not_realized` otherwise.

- [ ] **Step 5: Write official-style task details and deterministic overview**

Each detail file must contain task identity, pass/fail counts, trace labels, the LLM response, verifier evidence for failing rollouts, and bounded source case JSON. The overview must group timeout/debug/summary tasks and use one line per task extracted from the first nonempty `ROOT CAUSE`, `FAILURE POINT`, or prose line.

Construct `feedback.md` and `evidence/selected.md` as:

```python
combined = overview_text + "\n\n" + "\n\n".join(
    f"# Detail: {result.job.task_name}\n\n{detail_text[result.job.task_name]}"
    for result in debugger_results
)
```

This makes all reports available to the containerized meta-agent without host-path access.

- [ ] **Step 6: Update the artifact contract**

Set:

```python
ARTIFACTS = [
    "trace_analyzer/feedback.md",
    "trace_analyzer/analysis/overview.md",
    "trace_analyzer/analysis/change_evaluation.json",
    "trace_analyzer/evidence/selected.md",
    "trace_analyzer/evidence/overview.json",
    "trace_analyzer/evidence/cases.jsonl",
]
```

Append each generated `analysis/detail/<safe-name>.md` path in deterministic task order.

- [ ] **Step 7: Run tests and commit**

```bash
uv run pytest -q tests/test_ahe_trace_analyzer.py
uv run ruff check library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "feat: attribute AHE changes from debugger reports"
```

---

### Task 5: Require and validate the AHE change manifest

**Files:**
- Create: `library/meta_agent/support/ahe_manifest.py`
- Modify: `library/meta_agent/ahe.py`
- Modify: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Produces: `extract_manifest(output: str) -> dict[str, Any]` and `validate_manifest(payload, *, genid, parent, changed_paths, evidence_tasks) -> dict[str, Any]`.
- Consumes: the meta-agent's final Harbor response and `create_candidate_patch` output.

- [ ] **Step 1: Write failing extraction and validation tests**

Test exact delimiter extraction:

```python
MANIFEST_START = "<AHE_CHANGE_MANIFEST>"
MANIFEST_END = "</AHE_CHANGE_MANIFEST>"

output = f"summary\n{MANIFEST_START}\n{json.dumps(valid)}\n{MANIFEST_END}\n"
assert extract_manifest(output) == valid
```

Parameterize rejections for no block, two blocks, malformed JSON, wrong generation, wrong parent, missing causal fields, evidence task not analyzed, unsafe file path, duplicate file coverage, and changed-path mismatch. Add a `rollback_pivot` test requiring one rollback and one distinct non-rollback change.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py -k 'manifest'
```

Expected: fail because the support module and required behavior do not exist.

- [ ] **Step 3: Implement extraction**

```python
MANIFEST_START = "<AHE_CHANGE_MANIFEST>"
MANIFEST_END = "</AHE_CHANGE_MANIFEST>"


def extract_manifest(output: str) -> dict[str, Any]:
    starts = [match.start() for match in re.finditer(re.escape(MANIFEST_START), output)]
    ends = [match.start() for match in re.finditer(re.escape(MANIFEST_END), output)]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("meta-agent output must contain exactly one AHE manifest block")
    raw = output[starts[0] + len(MANIFEST_START) : ends[0]].strip()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AHE manifest must be a JSON object")
    return payload
```

- [ ] **Step 4: Implement schema and semantic validation**

Validate these exact top-level keys and types:

```python
required = {"schema_version", "generation", "parent", "decision", "changes", "validation"}
if set(payload) != required:
    raise ValueError("AHE manifest keys must match the version-1 schema")
if payload["schema_version"] != 1:
    raise ValueError("AHE manifest schema_version must be 1")
if str(payload["generation"]) != genid or str(payload["parent"]) != str(parent):
    raise ValueError("AHE manifest identity does not match operator context")
if payload["decision"] not in {"keep", "revise", "rollback_pivot"}:
    raise ValueError("invalid AHE decision")
```

For each change, require exact keys `id`, `type`, `files`, `evidence_tasks`, `root_cause`, `targeted_fix`, `predicted_effects`, `risk_tasks`, and `component`. Require nonempty `id`, `files`, `evidence_tasks`, `root_cause`, `targeted_fix`, and `predicted_effects`; permit an empty `risk_tasks`. Require every file to start with `target/`, forbid absolute and `..` paths, cover `changed_paths` exactly once, and require every evidence/prediction/risk task to be present in `evidence_tasks` supplied by the analyzer.

Require `validation == {"commands": list[str], "result": "passed"}` with at least one nonempty command.

- [ ] **Step 5: Replace the optional report in `AheMetaAgent.run`**

After `create_candidate_patch`, load task names from `trace_analyzer/evidence/overview.json`, extract and validate the returned manifest, then write it:

```python
manifest = validate_manifest(
    extract_manifest(agent_run.output),
    genid=ctx.genid,
    parent=ctx.parent,
    changed_paths=patch.changed_paths,
    evidence_tasks=_evidence_tasks(ctx.run_dir),
)
_write_json(out / "change_manifest.json", manifest)
```

Remove `REPORT_TEMPLATE`, `_report_note`, and all `ahe-report.json` language. On extraction/validation failure, preserve `output.txt`, `patch.diff`, `changed.json`, `surface-check.json`, and `usage.json`, then exit nonzero so the driver records `operator_failed`.

- [ ] **Step 6: Run tests and commit**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py
uv run ruff check library/meta_agent/ahe.py library/meta_agent/support/ahe_manifest.py tests/test_ahe_meta_agent.py
git add library/meta_agent/ahe.py library/meta_agent/support/ahe_manifest.py tests/test_ahe_meta_agent.py
git commit -m "feat: require manifest-backed AHE edits"
```

---

### Task 6: Adapt the AHE evolve prompt to debugger reports and attribution

**Files:**
- Modify: `library/meta_agent/ahe.py`
- Modify: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Consumes: feedback bundle, `analysis/change_evaluation.json`, prior manifest, archive history, and surface rules.
- Produces: an official-style prompt with the required final manifest contract.

- [ ] **Step 1: Write a failing prompt-contract test**

Create current debugger feedback, a generation-2 attribution file, and a prior manifest. Assert `build_prompt` contains:

```python
for required in (
    "KEEP",
    "REVISE",
    "ROLLBACK + PIVOT",
    "fail_to_pass",
    "pass_to_fail",
    "Current debugger reports evaluate the selected parent",
    "<AHE_CHANGE_MANIFEST>",
    "pass@1",
):
    assert required in prompt
```

Assert the prompt does not instruct the container to write a host `run_dir` path.

- [ ] **Step 2: Run the prompt test and verify RED**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py -k 'official_prompt'
```

Expected: missing decision and manifest-contract assertions fail.

- [ ] **Step 3: Replace `AHE_PROMPT` with the official-style workflow**

The prompt must state:

```text
1. Read the debugger overview and relevant task details first.
2. Read change_evaluation.json and the previous change manifest.
3. Decide KEEP, REVISE, or ROLLBACK + PIVOT before editing.
4. Cite specific debugger tasks and distinguish evidence from causal inference.
5. Choose the harness component matching the root cause.
6. If the same failure survived repeated changes at one component, pivot levels.
7. Make one coherent target/** change and run proportionate checks.
8. End with exactly one delimited version-1 change manifest covering every changed file.
```

Explain that the current reports evaluate the selected parent and the new edit will be evaluated by the next loop. Preserve frozen evaluator/model/task/resource boundaries.

- [ ] **Step 4: Embed attribution and prior manifest**

Add strict readers:

```python
def _required_text(path: Path, label: str) -> str:
    try:
        text = path.read_text().strip()
    except OSError as exc:
        raise RuntimeError(f"missing {label}: {path}") from exc
    if not text:
        raise RuntimeError(f"empty {label}: {path}")
    return text
```

Generation 1 embeds baseline attribution and no prior manifest. Later generations require `trace_analyzer/analysis/change_evaluation.json` and `runs/gen-<parent>/meta_agent/change_manifest.json`.

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest -q tests/test_ahe_meta_agent.py
uv run ruff check library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git add library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git commit -m "feat: align the AHE evolve prompt with official reports"
```

---

### Task 7: Compose sequential selection and artifact-valid gating

**Files:**
- Create: `library/select/ahe_latest.py`
- Create: `library/gate/ahe_artifact_valid.py`
- Create: `tests/test_ahe_select.py`
- Create: `tests/test_ahe_gate.py`
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/ahe/README.md`
- Modify: `tests/test_m9_ahe_recipe.py`
- Modify: `tests/test_phase_e_recipes.py`

**Interfaces:**
- Produces: `AheLatestSelect` and `AheArtifactValidGate` using existing operator interfaces.
- Consumes: valid archive parents, canonical child fields, and the validated manifest artifact.

- [ ] **Step 1: Write failing selector and gate tests**

Selector:

```python
def test_ahe_latest_selects_newest_valid_parent_even_when_score_is_lower() -> None:
    archive = SimpleNamespace(valid_parents=lambda: [
        {"genid": "1", "score": 0.9},
        {"genid": "2", "score": 0.1},
    ])
    result = AheLatestSelect().pick(archive, _ctx())
    assert result.parents == ["2"]
```

Gate:

```python
def test_ahe_gate_accepts_lower_score_with_valid_manifest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    manifest = ctx.run_dir / "meta_agent/change_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"schema_version": 1, "generation": ctx.genid, "parent": ctx.parent}))
    child = {"outcome": "benchmark_complete", "selection_eligible": True, "score": 0.1}
    parent = {"score": 0.9}
    assert AheArtifactValidGate().decide(child, parent, ctx).decision == "accept"
```

Also test missing manifest, wrong generation/parent, and non-complete canonical outcome rejection.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/test_ahe_select.py tests/test_ahe_gate.py
```

Expected: modules do not exist.

- [ ] **Step 3: Implement `ahe_latest`**

```python
class AheLatestSelect(SelectOperator):
    def pick(self, archive: ArchiveView, ctx: OperatorContext) -> SelectResult:
        parents = archive.valid_parents()
        if not parents:
            raise SystemExit("no valid AHE parents")
        chosen = max(
            parents,
            key=lambda row: (
                int(str(row.get("genid", "-1")).split("-", 1)[0])
                if str(row.get("genid", "")).split("-", 1)[0].isdigit()
                else -1,
                str(row.get("genid", "")),
            ),
        )
        return SelectResult(parents=[str(chosen["genid"])])
```

- [ ] **Step 4: Implement `ahe_artifact_valid`**

```python
class AheArtifactValidGate(GateOperator):
    def decide(self, child: Row, parent: Row | None, ctx: OperatorContext) -> GateResult:
        if child.get("outcome") != "benchmark_complete" or child.get("selection_eligible") is not True:
            return GateResult(decision="reject", reason="canonical evaluation is not parent-eligible")
        path = ctx.run_dir / "meta_agent" / "change_manifest.json"
        try:
            manifest = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return GateResult(decision="reject", reason="required AHE manifest is missing or malformed")
        identity_ok = (
            isinstance(manifest, dict)
            and str(manifest.get("generation")) == ctx.genid
            and str(manifest.get("parent")) == str(ctx.parent)
            and manifest.get("schema_version") == 1
        )
        return GateResult(
            decision="accept" if identity_ok else "reject",
            reason="validated AHE manifest and canonical evaluation" if identity_ok else "AHE manifest identity mismatch",
        )
```

- [ ] **Step 5: Update recipe and docs**

Change the AHE operator block to the exact composition in the design. Remove `budget_usd` and `max_cases`. Set trace-analyzer `timeout_s: 3600`. Document sequential regression attribution and required debugger failure semantics in `recipes/ahe/README.md`.

- [ ] **Step 6: Update recipe tests**

Assert initialized workspaces contain provenance for `library/select/ahe_latest.py` and `library/gate/ahe_artifact_valid.py`, include official debugger defaults, and omit `budget_usd`, `max_cases`, `greedy`, and `hillclimb` from the AHE config.

- [ ] **Step 7: Run tests and commit**

```bash
uv run pytest -q \
  tests/test_ahe_select.py \
  tests/test_ahe_gate.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_phase_e_recipes.py
uv run ruff check library/select/ahe_latest.py library/gate/ahe_artifact_valid.py tests/test_ahe_select.py tests/test_ahe_gate.py
git add library/select/ahe_latest.py library/gate/ahe_artifact_valid.py recipes/ahe tests/test_ahe_select.py tests/test_ahe_gate.py tests/test_m9_ahe_recipe.py tests/test_phase_e_recipes.py
git commit -m "feat: compose sequential official-style AHE"
```

---

### Task 8: Prove the two-generation AHE lifecycle with fake Harbor

**Files:**
- Create: `tests/test_ahe_official_lifecycle.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: the complete AHE recipe, fake evaluator, fake read-only debugger Harbor jobs, and fake editing Harbor jobs.
- Produces: deterministic proof of baseline, regression retention, attribution, and rollback/pivot.

- [ ] **Step 1: Add a fake Harbor fixture with two modes**

Create `install_ahe_fake_harbor(bin_dir: Path) -> Path`. It must inspect whether `--artifact` is present:

- Without `--artifact`, read the instruction prompt and return a trajectory response beginning `ROOT CAUSE:` for debug prompts or `KEY STRATEGY:` for summary prompts.
- With `--artifact /app/candidate`, copy the candidate bundle, apply the generation-specific target mutation, and return exactly one delimited manifest matching the changed paths.

The fixture must emit valid `result.json`, trajectory, usage, and artifact manifest files using the same structure already exercised by `test_harbor_meta_agent.py`.

- [ ] **Step 2: Write the baseline-to-regression test**

Initialize an AHE workspace with a locked MiniSWE seed and deterministic dataset. Configure the evaluator stub so generation 1 scores below generation 0. Run one generation and assert:

```python
assert rows["1"]["valid_parent"] is True
assert rows["1"]["score"] < rows["0"]["score"]
assert (workspace / "runs/gen-1/trace_analyzer/analysis/overview.md").is_file()
assert (workspace / "runs/gen-1/meta_agent/change_manifest.json").is_file()
```

- [ ] **Step 3: Write the attribution-and-rollback test**

Resume through generation 2. Make the fake debugger expose a `pass_to_fail` transition attributable to generation 1. Make the fake editor return `decision: rollback_pivot` with one rollback and one distinct pivot. Assert generation 2 selected parent `1`, its prompt contained the regression attribution, its manifest validated, and the resulting target contains both the rollback and pivot edits.

- [ ] **Step 4: Write the debugger-failure lifecycle test**

Set `FAKE_AHE_DEBUGGER_FAIL=1`, run generation 1, and assert:

```python
assert rows["1"]["status"] == "operator_failed"
assert rows["1"]["reason"] == "operator trace_analyzer failed"
assert not (workspace / "runs/gen-1/meta_agent/prompt.md").exists()
```

- [ ] **Step 5: Run lifecycle tests and commit**

```bash
uv run pytest -q tests/test_ahe_official_lifecycle.py
uv run ruff check tests/conftest.py tests/test_ahe_official_lifecycle.py
git add tests/conftest.py tests/test_ahe_official_lifecycle.py
git commit -m "test: prove official-style AHE lifecycle"
```

---

### Task 9: Full verification and real-smoke handoff

**Files:**
- Modify only files required to fix failures discovered by verification.
- Verify: complete `main` diff from `0fe40fa` through the implementation head.

**Interfaces:**
- Consumes: all tasks above.
- Produces: a locally verified branch and an exact two-task real-smoke command/configuration.

- [ ] **Step 1: Run focused AHE and Harbor tests**

```bash
uv run pytest -q \
  tests/test_harbor_meta_agent.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_ahe_meta_agent.py \
  tests/test_ahe_select.py \
  tests/test_ahe_gate.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_ahe_official_lifecycle.py
```

Expected: all pass with no skips or xfails.

- [ ] **Step 2: Run the complete local gate**

```bash
uv run pytest -q
uv run ruff check .
uv run ty check
git diff --check 0fe40fa..HEAD
UV_CACHE_DIR=/private/tmp/simple-evolve-ahe-build-cache uv build --out-dir /private/tmp/simple-evolve-ahe-dist
```

Expected: full suite passes, static checks emit no diagnostics, diff check exits zero, and both sdist and wheel build.

- [ ] **Step 3: Verify package contents**

```bash
unzip -l /private/tmp/simple-evolve-ahe-dist/evolve_framework-0.1.0-py3-none-any.whl | \
  rg 'evolve/(library/(trace_analyzer/ahe|meta_agent/(ahe|support/ahe_manifest)|select/ahe_latest|gate/ahe_artifact_valid)|recipes/ahe)'
```

Expected: every AHE operator/helper and recipe file is present.

- [ ] **Step 4: Audit method boundaries and repository state**

```bash
rg -n "ahe|AHE" src/evolve/driver.py src/evolve/frozen/interfaces.py
git status --short
git log --oneline 0fe40fa..HEAD
```

Expected: no new AHE-specific mechanism branches or interface fields; clean status; commits correspond one-to-one with plan tasks.

- [ ] **Step 5: Invoke verification-before-completion**

Use `superpowers:verification-before-completion` and re-run every command it requires before making any readiness claim.

- [ ] **Step 6: Run a real two-task Harbor smoke only after local verification**

Use the actual production AHE recipe with exactly two deterministic train tasks, `k: 1`, `max_concurrent: 2`, and the same meta-agent model configuration used by the intended experiment. Confirm both debugger jobs complete, the overview/detail reports are nonempty, the manifest validates, the candidate evaluates, and the archive marks the child eligible. Record the exact commit, Harbor version, task IDs, run directory, and log paths without recording credentials.

Expected: the generation completes through gate/record. A benchmark score of zero is not itself an infrastructure failure; missing debugger/manifest/evaluation artifacts are failures.

- [ ] **Step 7: Commit verification-only fixes if any**

If verification required code changes:

```bash
git add -u
git commit -m "fix: close AHE verification gaps"
```

Use `git status --short` first. If a verification fix creates a new file, add that
explicit path before `git add -u`. If no verification fix was required, do not
create an empty commit.
