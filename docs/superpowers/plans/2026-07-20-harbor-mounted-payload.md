# Harbor Mounted Payload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Harbor agent payloads in Docker-visible files, remove redundant AHE prompt evidence, and preserve primary operator failures when no gate ran.

**Architecture:** AHE will inline diagnoses but leave normalized cases in run-scoped files. A focused Harbor agent subclass will rewrite MiniSWE's `--task=<payload>` launch into a small file-backed shim that reconstructs `sys.argv` inside MiniSWE's own Python process, avoiding Linux `execve` limits without changing MiniSWE behavior. Both methods and AHE debuggers select this adapter explicitly; the runner records prompt size and rejects oversized prompts only when an unsafe adapter is configured.

**Tech Stack:** Python 3.12, Harbor 0.18.0, MiniSWE Agent 2.4.5, pytest, Ruff, Docker/Harbor on DevBoxS.

## Global Constraints

- Implement in `/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/harbor-disposable-workspace`.
- Preserve the existing uncommitted model-name changes in `recipes/ahe/evolve.yaml`, `recipes/hyperagents/evolve.yaml`, and `tests/test_phase_e_recipes.py`.
- Preserve the existing uncommitted `UV_LINK_MODE=copy` changes in the main worktree; they are outside this implementation worktree.
- Payload content travels through Docker-visible files; CLI arguments and environment values contain paths and small control values only.
- Do not clip prompts or evidence.
- Keep credentials outside workspace payload files.
- Do not rewrite `library/meta_agent/runners/harbor.py` or the experiment driver; add only the prompt-size boundary needed by the existing runner.
- The existing surface gate and candidate import behavior remain unchanged.

---

### Task 1: Compact AHE selected evidence

**Files:**
- Modify: `library/trace_analyzer/ahe.py:499-550`
- Modify: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Consumes: `DebuggerResult`, `TaskAnalysisJob`, and the existing run directory layout.
- Produces: `_reports(root: Path, results: list[DebuggerResult]) -> tuple[str, list[str]]`; concise returned Markdown plus unchanged detailed artifact files.

- [ ] **Step 1: Write the failing evidence-selection test**

Extend `test_ahe_analyzer_writes_official_reports_and_baseline` with assertions that the selected view contains diagnoses and detail paths but not case bodies, while detail files and `cases.jsonl` retain them:

```python
    selected = (ctx.run_dir / "trace_analyzer" / "evidence" / "selected.md").read_text()
    detail = (analysis / "detail" / "task-a.md").read_text()
    cases = (ctx.run_dir / "trace_analyzer" / "evidence" / "cases.jsonl").read_text()
    assert "ROOT CAUSE" in selected
    assert "runs/gen-1/trace_analyzer/analysis/detail/task-a.md" in selected
    assert "## Bounded cases" not in selected
    assert "## Bounded cases" in detail
    assert '"trial_name": "fail-1"' in detail
    assert '"trial_name": "fail-1"' in cases
```

- [ ] **Step 2: Run the focused test and verify the old rendering fails**

Run:

```bash
uv run pytest tests/test_ahe_trace_analyzer.py::test_ahe_analyzer_writes_official_reports_and_baseline -q
```

Expected: FAIL because `selected.md` still contains `## Bounded cases` and has no run-scoped detail path.

- [ ] **Step 3: Return concise reports while retaining detailed artifacts**

In `_reports`, keep writing the existing `detail` string, but append only this concise entry to the returned report:

```python
        workspace_relative = f"runs/{root.parent.name}/{relative}"
        details.append(
            f"# Detail: {job.task_name}\n\n"
            f"- Pass: {job.n_pass}\n- Fail: {job.n_fail}\n- Timeout: {job.n_timeout}\n"
            f"- Traces: {', '.join(labels)}\n"
            f"- Full bounded evidence: `{workspace_relative}`\n\n"
            f"## LLM debugger response\n\n{result.response}\n\n"
            f"## Failing verifier evidence\n\n{json.dumps(failing_verifier, indent=2)}\n"
        )
```

Do not change the detailed Markdown written to `root.parent / relative` or the `cases.jsonl` write in `analyze()`.

- [ ] **Step 4: Run AHE analyzer and meta-agent tests**

Run:

```bash
uv run pytest tests/test_ahe_trace_analyzer.py tests/test_ahe_meta_agent.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the compact evidence change**

```bash
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "fix: keep AHE trace payloads out of prompts"
```

---

### Task 2: Add the file-backed MiniSWE Harbor agent

**Files:**
- Create: `templates/workspace/evolve_harbor_agent/__init__.py`
- Modify: `templates/workspace/pyproject.toml`
- Create: `tests/test_harbor_file_agent.py`

**Interfaces:**
- Consumes: Harbor's installed `MiniSweAgent.exec_as_agent(environment, command, env=...)` and `environment.upload_file(source, destination)`.
- Produces: `evolve_harbor_agent:FileTaskMiniSweAgent`, a drop-in Harbor agent import path.

- [ ] **Step 1: Write a failing adapter test with a payload above 128 KiB**

Create a fake Harbor base class whose `run` sends the same command shape as Harbor 0.18.0, and an environment that records uploads and commands. The core assertion is:

```python
def test_file_task_agent_externalizes_large_miniswe_instruction(tmp_path: Path, monkeypatch) -> None:
    module, environment = load_adapter_with_fake_harbor(tmp_path, monkeypatch)
    payload = "evidence\n" + "x" * 200_000

    asyncio.run(module.FileTaskMiniSweAgent().run(payload, environment, object()))

    runtime_command = environment.commands[-1]
    uploaded = dict(environment.uploads)
    assert payload not in runtime_command
    assert uploaded[module.TASK_PATH] == payload
    assert module.TASK_PATH in runtime_command
    assert module.SHIM_PATH in runtime_command
```

Have the fake `upload_file` read the source immediately and append
`(destination, source.read_text())`, because the adapter deletes its host
temporary directory after upload. Also assert that an ordinary non-MiniSWE
setup command passes through unchanged.

- [ ] **Step 2: Run the new test and verify the adapter is absent**

Run:

```bash
uv run pytest tests/test_harbor_file_agent.py -q
```

Expected: FAIL because `templates/workspace/evolve_harbor_agent/__init__.py` does not exist.

- [ ] **Step 3: Implement the focused adapter**

Create `templates/workspace/evolve_harbor_agent/__init__.py` with one responsibility: intercept the final MiniSWE launch, decode its quoted task, upload the task and a fixed shim, and execute the console entry point in its existing interpreter.

```python
from __future__ import annotations

import shlex
import tempfile
from pathlib import Path

from harbor.agents.installed.mini_swe_agent import MiniSweAgent

TASK_PATH = "/tmp/evolve-miniswe-task.md"
SHIM_PATH = "/tmp/evolve-miniswe-file-task.py"
_LAUNCH = "mini-swe-agent --yolo "
_TASK = " --task="
_OUTPUT = " --output="

_SHIM = '''from pathlib import Path
import runpy
import sys

entrypoint = sys.argv[1]
args = sys.argv[2:]
task_flag = next(index for index, value in enumerate(args) if value.startswith("--task-file="))
task_path = args[task_flag].split("=", 1)[1]
args[task_flag] = "--task=" + Path(task_path).read_text()
sys.argv = [entrypoint, *args]
runpy.run_path(entrypoint, run_name="__main__")
'''


class FileTaskMiniSweAgent(MiniSweAgent):
    async def exec_as_agent(self, environment, command: str, env=None, **kwargs):
        launch = command.find(_LAUNCH)
        task = command.find(_TASK, launch)
        output = command.rfind(_OUTPUT)
        if launch < 0 or task < 0 or output < task:
            return await super().exec_as_agent(environment, command=command, env=env, **kwargs)

        quoted = command[task + len(_TASK) : output]
        values = shlex.split(quoted)
        if len(values) != 1:
            raise RuntimeError("unable to decode MiniSWE task argument")

        with tempfile.TemporaryDirectory(prefix="evolve-miniswe-task-") as tempdir:
            root = Path(tempdir)
            task_file = root / "task.md"
            shim_file = root / "runner.py"
            task_file.write_text(values[0])
            shim_file.write_text(_SHIM)
            await environment.upload_file(task_file, TASK_PATH)
            await environment.upload_file(shim_file, SHIM_PATH)

        prefix = command[:launch]
        flags_before_task = command[launch + len("mini-swe-agent") : task]
        flags_after_task = command[output:]
        file_launch = (
            'MSWEA_BIN="$(command -v mini-swe-agent)"; '
            'MSWEA_PY="$(head -n 1 "$MSWEA_BIN")"; MSWEA_PY="${MSWEA_PY#\\#!}"; '
            f'"$MSWEA_PY" {SHIM_PATH} "$MSWEA_BIN"'
        )
        rewritten = prefix + file_launch + flags_before_task + f" --task-file={TASK_PATH}" + flags_after_task
        return await super().exec_as_agent(environment, command=rewritten, env=env, **kwargs)
```

If Harbor's base signature exposed by the fake and real 0.18.0 source differs, preserve every keyword using `**kwargs`; do not duplicate Harbor's `run`, model configuration, or credential logic.

- [ ] **Step 4: Package and verify the adapter**

Add `"evolve_harbor_agent"` to the template workspace Hatch package list. Run:

```bash
uv run pytest tests/test_harbor_file_agent.py tests/test_phase_f_init_binding.py -q
uv run ruff check templates/workspace/evolve_harbor_agent tests/test_harbor_file_agent.py
```

Expected: all tests and Ruff PASS; no lockfile change is required because no dependency changes.

- [ ] **Step 5: Commit the adapter**

```bash
git add templates/workspace/evolve_harbor_agent templates/workspace/pyproject.toml tests/test_harbor_file_agent.py
git commit -m "feat: transport Harbor MiniSWE tasks through files"
```

---

### Task 3: Route both methods through the safe transport and enforce its boundary

**Files:**
- Modify: `recipes/ahe/evolve.yaml`
- Modify: `recipes/hyperagents/evolve.yaml`
- Modify: `library/meta_agent/runners/harbor.py`
- Modify: `tests/test_ahe_trace_analyzer.py`
- Modify: `tests/test_m9_ahe_recipe.py`
- Modify: `tests/test_hyperagents_harbor_recipe.py`
- Modify: `tests/test_harbor_meta_agent.py`
- Preserve and extend: `tests/test_phase_e_recipes.py`

**Interfaces:**
- Consumes: `evolve_harbor_agent:FileTaskMiniSweAgent`.
- Produces: `_instruction_transport(agent: str, prompt_path: Path) -> dict[str, object]` and `instruction-transport.json` for editing and read-only Harbor runs.

- [ ] **Step 1: Write failing recipe and unsafe-transport tests**

Update recipe assertions to expect the shared import path for both AHE and HyperAgents. Add focused runner tests:

```python
def test_harbor_rejects_oversized_instruction_with_unsafe_agent(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x" * (96 * 1024 + 1))
    with pytest.raises(RuntimeError, match="harbor_instruction_transport_unsafe"):
        runner._instruction_transport("mini-swe-agent", prompt)


def test_harbor_accepts_oversized_instruction_with_file_agent(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("x" * 200_000)
    result = runner._instruction_transport("evolve_harbor_agent:FileTaskMiniSweAgent", prompt)
    assert result == {"bytes": 200_000, "mode": "mounted-file", "safe": True}
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py tests/test_harbor_meta_agent.py -q
```

Expected: FAIL because recipes still select the installed agent and the transport invariant does not exist.

- [ ] **Step 3: Implement and record the transport invariant**

Add to `library/meta_agent/runners/harbor.py`:

```python
_FILE_TASK_AGENT = "evolve_harbor_agent:FileTaskMiniSweAgent"
_SAFE_INLINE_INSTRUCTION_BYTES = 96 * 1024


def _instruction_transport(agent: str, prompt_path: Path) -> dict[str, object]:
    size = prompt_path.stat().st_size
    safe = agent == _FILE_TASK_AGENT
    mode = "mounted-file" if safe else "inline-argument"
    if size > _SAFE_INLINE_INSTRUCTION_BYTES and not safe:
        raise RuntimeError(
            "harbor_instruction_transport_unsafe: "
            f"agent={agent} bytes={size} limit={_SAFE_INLINE_INSTRUCTION_BYTES}"
        )
    return {"bytes": size, "mode": mode, "safe": safe}
```

Immediately after each editing or read-only `prompt_path.write_text(...)`, call the helper and write its result to `instruction-transport.json`. Use `str(config.get("agent") or "codex")`; do not infer safety from prompt size.

- [ ] **Step 4: Select the adapter in both recipes**

Change only each meta-agent `agent` value:

```yaml
agent: evolve_harbor_agent:FileTaskMiniSweAgent
```

Keep the currently edited `openai/gpt-5.4-2026-03-05` model values unchanged. AHE's `_debugger_runner_config` already copies the meta-agent `agent`, so its debugger automatically uses the same transport.

- [ ] **Step 5: Run runner, recipe, and analyzer tests**

Run:

```bash
uv run pytest tests/test_harbor_meta_agent.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py tests/test_phase_e_recipes.py tests/test_ahe_trace_analyzer.py -q
```

Expected: all tests PASS and both recipe files retain the intended model name.

- [ ] **Step 6: Commit the shared wiring without absorbing unrelated recipe edits**

Review `git diff` first. Stage the complete recipe files only because their existing model edits are part of the active experiment configuration, then commit:

```bash
git add library/meta_agent/runners/harbor.py recipes/ahe/evolve.yaml recipes/hyperagents/evolve.yaml tests/test_ahe_trace_analyzer.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py tests/test_harbor_meta_agent.py tests/test_phase_e_recipes.py
git commit -m "fix: enforce file-backed Harbor instructions"
```

---

### Task 4: Preserve primary operator failures during terminal recording

**Files:**
- Modify: `library/record/jsonl.py:13-44`
- Modify: `tests/test_m5_driver_operators.py`

**Interfaces:**
- Consumes: optional `run_dir/gate.json`, optional meta-agent rationale and usage.
- Produces: `_record_fields_from_run_dir(run_dir: Path) -> dict[str, Any]` that returns annotation-only fields when the gate never ran.

- [ ] **Step 1: Write the missing-gate regression test**

```python
def test_jsonl_record_without_gate_preserves_terminal_annotation(tmp_path: Path) -> None:
    workspace, _ = init_workspace(tmp_path)
    run_dir = workspace / "runs" / "operator-failed"
    (run_dir / "meta_agent").mkdir(parents=True)
    (run_dir / "meta_agent" / "rationale.md").write_text("meta-agent failed before gate\n")
    ctx = OperatorContext(
        workspace=workspace,
        checkout=workspace,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={},
        rng=random.Random(0),
    )
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "library" / "record" / "jsonl.py"))

    fields = module["JsonlRecord"]().annotate({"genid": "1", "parent": "0"}, ctx).fields

    assert fields == {"note": "meta-agent failed before gate"}
```

- [ ] **Step 2: Run the regression and verify the missing file failure**

Run:

```bash
uv run pytest tests/test_m5_driver_operators.py::test_jsonl_record_without_gate_preserves_terminal_annotation -q
```

Expected: FAIL with `FileNotFoundError: gate.json`.

- [ ] **Step 3: Make gate fields conditional**

Initialize `fields` with the note, then add gate-owned fields only when the file exists:

```python
    fields: dict[str, Any] = {"note": note}
    gate_path = run_dir / "gate.json"
    if gate_path.is_file():
        gate = json.loads(gate_path.read_text())
        fields.update(
            valid_parent=gate["valid_parent"],
            verdict=gate["verdict"],
            reason=gate["reason"],
        )
```

Keep prediction and verified-fix behavior unchanged.

- [ ] **Step 4: Run record and driver tests**

Run:

```bash
uv run pytest tests/test_m5_driver_operators.py tests/test_runtime.py -q
```

Expected: all tests PASS; a terminal record attempt no longer masks the existing `operator_failed` row.

- [ ] **Step 5: Commit the recording fix**

```bash
git add library/record/jsonl.py tests/test_m5_driver_operators.py
git commit -m "fix: record failures before gate execution"
```

---

### Task 5: Verify locally and on DevBoxS

**Files:**
- No production files.
- Inspect: the implementation diff and DevBoxS run artifacts.

**Interfaces:**
- Consumes: the four committed tasks above.
- Produces: local verification evidence and a one-generation AHE smoke before a concurrent two-method smoke.

- [ ] **Step 1: Run formatting, lint, and focused tests**

```bash
uv run ruff format --check library templates tests
uv run ruff check library templates tests
uv run pytest tests/test_ahe_trace_analyzer.py tests/test_ahe_meta_agent.py tests/test_harbor_file_agent.py tests/test_harbor_meta_agent.py tests/test_m9_ahe_recipe.py tests/test_hyperagents_harbor_recipe.py tests/test_phase_e_recipes.py tests/test_m5_driver_operators.py -q
```

Expected: all commands exit 0.

- [ ] **Step 2: Run the full local suite**

```bash
uv run pytest -q
```

Expected: all tests PASS with no new warnings or failures.

- [ ] **Step 3: Audit the final diff and workspace state**

```bash
git diff HEAD~4 --check
git status --short
git log -4 --oneline
```

Expected: no whitespace errors; only explicitly preserved pre-existing changes may remain uncommitted.

- [ ] **Step 4: Deploy the exact committed tree to a fresh DevBoxS experiment directory**

Reuse the existing pre-pulled Terminal-Bench 2.0 images and UV cache. Do not modify the completed `v6` artifact tree. Record the deployed commit in the new experiment directory.

- [ ] **Step 5: Run one AHE generation and inspect transport evidence**

Expected artifacts:

```text
runs/gen-1/meta_agent/harbor/instruction-transport.json
runs/gen-1/meta_agent/harbor/jobs/*/*/agent/mini-swe-agent.trajectory.json
runs/gen-1/meta_agent/change_manifest.json
```

Expected conditions: transport mode is `mounted-file`; prompt size is recorded; no `E2BIG`; the model runs and produces a candidate or an ordinary model/agent failure.

- [ ] **Step 6: Run concurrent AHE and HyperAgents smoke experiments**

Use four workers per method, four Terminal-Bench 2.0 tasks, `k=2` for AHE and the configured HyperAgents sampling, and one generation initially. Extend to three generations only after both gen-1 meta-agents complete.

Expected: both methods use `gpt-5.4-2026-03-05`, both record mounted-file transport, and neither produces `Argument list too long` or a secondary missing-`gate.json` record error.
