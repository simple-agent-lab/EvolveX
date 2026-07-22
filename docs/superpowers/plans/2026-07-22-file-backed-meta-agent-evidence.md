# File-Backed Meta-Agent Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep detailed HyperAgents and AHE experiment evidence in existing files and replace inline evidence bodies with short path descriptions and required reading orders.

**Architecture:** Change only the two strategy-owned prompt builders. HyperAgents points to its existing feedback bundle; AHE points to its existing analysis, parent-meta-agent, archive, and rollout artifacts. Delete prompt-only file-reading and clipping helpers that become unused, without changing the framework, runners, artifact layout, or evidence producers.

**Tech Stack:** Python 3.12+, `pathlib`, pytest, existing `OperatorContext` and meta-agent strategy modules

## Global Constraints

- Do not modify files under `src/evolve/`.
- Do not change Harbor staging or artifact-return behavior.
- Do not add an evidence directory, evidence schema, generated summary, or shared prompt abstraction.
- Do not change trace analyzer or feedback generation behavior.
- Apply the policy only to HyperAgents and AHE.
- Preserve complete evidence in its existing files; do not copy or truncate it into prompts.
- Preserve the existing durable-artifact guidance and handoff behavior.
- Preserve the user's unrelated `.gitignore` change.

---

## File Map

- `library/meta_agent/hyperagents.py`: render HyperAgents instructions and file-backed evidence reading order.
- `tests/test_hyperagents_meta_agent.py`: enforce HyperAgents paths, reading order, and absence of evidence bodies.
- `library/meta_agent/ahe.py`: render AHE instructions, file-backed evidence reading order, and baseline/parent path guidance.
- `tests/test_ahe_meta_agent.py`: enforce AHE paths, decision sequence, baseline behavior, and absence of evidence bodies.

No files are created by the implementation.

---

### Task 1: Make HyperAgents evidence file-first

**Files:**
- Modify: `tests/test_hyperagents_meta_agent.py:75-145`
- Modify: `library/meta_agent/hyperagents.py:16-129`

**Interfaces:**
- Consumes: `build_prompt(checkout: Path, observation: str, ctx) -> str`, existing run paths, `runner_name(ctx)`, and `render_artifact_guidance(ctx, experiment)`.
- Produces: a HyperAgents prompt containing direct evidence paths and no contents from `selected.md`, `attempts.md`, `last_accepted.diff`, lineage rows, or `observation`.

- [ ] **Step 1: Replace inline-evidence assertions with file-first assertions**

In `test_hyperagents_prompt_points_to_evolvable_codebase_and_prior_artifacts`, change the evidence-body assertions to:

```python
    assert "Evidence reading order" in prompt
    assert "1. Read `/app/task/workspace/runs/gen-1/feedback/index.md`" in prompt
    assert "/app/task/workspace/runs/gen-1/feedback/evidence/selected.md" in prompt
    assert "/app/task/workspace/runs/gen-1/feedback/last_accepted.diff" in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/evidence" in prompt
    assert "/app/task/workspace/runs/gen-1/rollout" in prompt
    assert "SELECTED TRACE EVIDENCE" not in prompt
    assert "LATEST ACCEPTED DIFF" not in prompt
    assert "COMPACT ATTEMPTS FALLBACK" not in prompt
    assert "HISTORY MUST NOT BE INLINED" not in prompt
    assert "fallback observation" not in prompt
```

Replace `test_hyperagents_prompt_bounds_inline_evidence` and
`test_hyperagents_prompt_uses_attempts_fallback` with these two tests:

```python
def test_hyperagents_prompt_does_not_read_large_evidence_bodies(tmp_path: Path) -> None:
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    evidence = run_dir / "feedback" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "selected.md").write_text("LARGE SELECTED BODY " * 10_000)
    (run_dir / "feedback" / "last_accepted.diff").write_text("LARGE DIFF BODY " * 10_000)

    prompt = module.build_prompt(checkout, "OBSERVATION BODY", ctx)

    assert "LARGE SELECTED BODY" not in prompt
    assert "LARGE DIFF BODY" not in prompt
    assert "OBSERVATION BODY" not in prompt
    assert len(prompt) < 10_000


def test_hyperagents_local_prompt_uses_existing_workspace_paths(tmp_path: Path) -> None:
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert f"Repository: {checkout}" in prompt
    assert f"1. Read `{run_dir / 'feedback/index.md'}`" in prompt
    assert f"`{run_dir / 'feedback/evidence/selected.md'}`" in prompt
    assert f"`{run_dir / 'feedback/last_accepted.diff'}`" in prompt
    assert f"`{run_dir / 'rollout'}`" in prompt
```

In the `fake_run_agent` inside
`test_hyperagents_meta_agent_records_complete_patch_for_target_and_workflow_edits`,
replace `assert "observation" in prompt` with:

```python
        assert "Evidence reading order" in prompt
        assert "observation" not in prompt
```

- [ ] **Step 2: Run the focused HyperAgents prompt tests and verify RED**

Run:

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py -k prompt
```

Expected: failures show that selected evidence, the latest diff, or attempts are
still embedded and that the new evidence reading order is absent.

- [ ] **Step 3: Remove inline evidence helpers and render paths directly**

In `library/meta_agent/hyperagents.py`, delete:

```python
MAX_INLINE_EVIDENCE_CHARS = 50_000
LATEST_DIFF_CHARS = 5_000
```

Delete `_read_optional`, `_clip_inline`, `_lineage`, and `_prompt_evidence` in
full. Keep the `sdk` import because `sdk.main` remains in use.

Replace `build_prompt` with:

```python
def build_prompt(checkout: Path, observation: str, ctx) -> str:
    del observation
    if runner_name(ctx) == "harbor":
        repository = Path("/app/task/workspace")
        current_run = repository / "runs" / f"gen-{ctx.genid}"
        experiment = repository
    else:
        repository = checkout
        current_run = ctx.run_dir
        experiment = ctx.workspace
    feedback = current_run / "feedback"
    selected = feedback / "evidence" / "selected.md"
    latest_diff = feedback / "last_accepted.diff"
    trace_evidence = current_run / "trace_analyzer" / "evidence"
    rollout = current_run / "rollout"
    return (
        f"{PROMPT.rstrip()}\n\n"
        "# Evidence reading order\n\n"
        f"1. Read `{feedback / 'index.md'}` for the evidence map.\n"
        f"2. Read `{selected}` and `{latest_diff}` for selected findings and the latest accepted change.\n"
        f"3. Inspect relevant files under `{trace_evidence}`.\n"
        f"4. Open raw rollout artifacts under `{rollout}` only when analyzed evidence is insufficient.\n"
        "5. Edit the candidate only after reviewing the relevant evidence.\n\n"
        f"Repository: {repository}\n"
        f"Feedback bundle: {feedback}\n"
        f"Complete history: {feedback / 'evidence' / 'history.json'}\n"
        f"Archive: {experiment / 'archive.jsonl'}\n"
        f"Prior generation artifacts: {experiment / 'runs'}\n"
        f"Current generation artifacts: {current_run}\n"
        f"\n{render_artifact_guidance(ctx, experiment)}\n\n"
        f"Iterations remaining after this proposal: {_remaining_iterations(ctx)}\n\n"
        "Edit the checkout directly. Do not print a patch instead of editing files.\n"
    )
```

- [ ] **Step 4: Run the HyperAgents module and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_hyperagents_meta_agent.py
```

Expected: all tests in the module pass.

- [ ] **Step 5: Commit the HyperAgents change**

```bash
git add library/meta_agent/hyperagents.py tests/test_hyperagents_meta_agent.py
git commit -m "refactor: make hyperagents evidence file-backed"
```

---

### Task 2: Make AHE debugger evidence file-first

**Files:**
- Modify: `tests/test_ahe_meta_agent.py:31-213`
- Modify: `library/meta_agent/ahe.py:89-201`

**Interfaces:**
- Consumes: `build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str`, `ctx.parent`, existing AHE analysis paths, `runner_name(ctx)`, and `render_artifact_guidance(ctx, experiment)`.
- Produces: an AHE prompt containing a direct evidence reading order, a baseline-specific prior-change statement or selected-parent artifact path, and no experiment artifact bodies.

- [ ] **Step 1: Add unmistakable on-disk sentinels to the AHE fixture**

In `_case`, replace the change-evaluation and archive writes with:

```python
    (analysis / "change_evaluation.json").write_text(
        json.dumps(
            {
                "status": "baseline" if parent == "0" else "evaluated",
                "transitions": {},
                "sentinel": "ATTRIBUTION BODY MUST STAY ON DISK",
            }
        )
    )
```

```python
    (workspace / "archive.jsonl").write_text(
        '{"genid":"0","score":0,"sentinel":"ARCHIVE BODY MUST STAY ON DISK"}\n'
    )
```

- [ ] **Step 2: Change the main AHE prompt test to require paths but reject bodies**

In `test_ahe_prompt_uses_official_decisions_and_required_manifest`, replace the
overview assertion and extend the path assertions with:

```python
    assert "Evidence reading order" in prompt
    assert "OVERVIEW ROOT CAUSE" not in prompt
    assert "ATTRIBUTION BODY MUST STAY ON DISK" not in prompt
    assert "ARCHIVE BODY MUST STAY ON DISK" not in prompt
    assert "DETAIL BODY MUST STAY ON DISK" not in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/analysis/overview.md" in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/analysis/change_evaluation.json" in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/analysis/detail" in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/evidence/cases.jsonl" in prompt
    assert "/app/task/workspace/runs/gen-1/rollout" in prompt
    assert "No selected-parent meta-agent change exists for this baseline generation." in prompt
```

Keep the existing assertions for the KEEP/REVISE/ROLLBACK sequence, manifest
contract, repository, archive, durable artifacts, and protected runtime prompt
instructions.

- [ ] **Step 3: Replace body-reading tests with non-reading and parent-path tests**

Replace `test_ahe_prompt_requires_nonempty_overview` with:

```python
def test_ahe_prompt_does_not_require_readable_evidence_bodies(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    (ctx.run_dir / "trace_analyzer/analysis/overview.md").write_text("")
    (ctx.run_dir / "trace_analyzer/analysis/change_evaluation.json").unlink()

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert "/app/task/workspace/runs/gen-1/trace_analyzer/analysis/overview.md" in prompt
    assert "/app/task/workspace/runs/gen-1/trace_analyzer/analysis/change_evaluation.json" in prompt
```

Replace `test_ahe_prompt_includes_prior_raw_change_context` with:

```python
def test_ahe_prompt_points_to_prior_change_without_inlining_it(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path, genid="2", parent="1")
    prior = ctx.workspace / "runs/gen-1/meta_agent"
    (prior / "output.txt").write_text("PREVIOUS REASONING BODY")
    (prior / "changed.json").write_text('["target/previous.py"]')
    (prior / "patch.diff").write_text("PREVIOUS PATCH BODY")

    prompt = module.build_prompt(checkout, "fallback", ctx)

    assert "Selected parent meta-agent artifacts" in prompt
    assert "/app/task/workspace/runs/gen-1/meta_agent" in prompt
    assert "PREVIOUS REASONING BODY" not in prompt
    assert "target/previous.py" not in prompt
    assert "PREVIOUS PATCH BODY" not in prompt
    assert "No selected-parent meta-agent change exists" not in prompt
```

- [ ] **Step 4: Run the focused AHE prompt tests and verify RED**

Run:

```bash
uv run pytest -q tests/test_ahe_meta_agent.py -k prompt
```

Expected: failures show that overview, attribution, prior-change, or archive
bodies are still inline and that the new absolute reading-order paths are absent.

- [ ] **Step 5: Remove body-reading helpers and build the AHE reading order from paths**

In `library/meta_agent/ahe.py`, delete `_required_text`,
`_prior_change_context`, `_overview`, `_evidence_paths`, and `_recent_archive` in
full.

Replace `build_prompt` with:

```python
def build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str:
    del observation
    template = dict(MANIFEST_TEMPLATE)
    template["iteration"] = int(ctx.genid)
    if runner_name(ctx) == "harbor":
        repository = Path("/app/task/workspace")
        current_run = repository / "runs" / f"gen-{ctx.genid}"
        experiment = repository
    else:
        repository = checkout
        current_run = ctx.run_dir
        experiment = ctx.workspace
    analysis = current_run / "trace_analyzer" / "analysis"
    overview = analysis / "overview.md"
    attribution = analysis / "change_evaluation.json"
    details = analysis / "detail"
    cases = current_run / "trace_analyzer" / "evidence" / "cases.jsonl"
    rollout = current_run / "rollout"
    if ctx.parent in (None, "0"):
        prior_change = "No selected-parent meta-agent change exists for this baseline generation."
    else:
        parent_meta_agent = experiment / "runs" / f"gen-{ctx.parent}" / "meta_agent"
        prior_change = (
            "Inspect the selected parent manifest and patch. "
            f"Selected parent meta-agent artifacts: `{parent_meta_agent}`"
        )
    return (
        f"{AHE_PROMPT.rstrip()}\n\n"
        "# Evidence reading order\n\n"
        f"1. Read `{overview}`.\n"
        f"2. Read `{attribution}` and decide KEEP, REVISE, or ROLLBACK + PIVOT.\n"
        f"3. Read only the relevant per-task reports under `{details}`.\n"
        f"4. {prior_change}\n"
        f"5. Use `{cases}` and raw rollout artifacts under `{rollout}` only to resolve missing or conflicting evidence.\n"
        "6. Edit the candidate and write the required AHE change manifest.\n\n"
        "# Evidence Locations\n\n"
        f"Repository: {repository}\n"
        f"Archive: {experiment / 'archive.jsonl'}\n"
        f"Current generation artifacts: {current_run}\n"
        f"Raw trace evidence: {current_run / 'trace_analyzer' / 'evidence'}\n\n"
        f"{render_artifact_guidance(ctx, experiment)}\n\n"
        f"# Surface Rules\n\n{_surface_rules(checkout)}\n\n"
        "# Required Final Output\n\nEdit the candidate directly. After checks and before the submission action, "
        f"write the following JSON object to `{MANIFEST_FILE}`. Write JSON only; this control file is removed "
        "before the candidate patch is created. Then submit normally.\n\n"
        f"```json\n{json.dumps(template, indent=2)}\n```\n"
    )
```

- [ ] **Step 6: Run both affected modules and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_ahe_meta_agent.py tests/test_hyperagents_meta_agent.py
```

Expected: all tests in both modules pass.

- [ ] **Step 7: Run formatting and import checks**

Run:

```bash
uv run ruff check library/meta_agent/ahe.py library/meta_agent/hyperagents.py tests/test_ahe_meta_agent.py tests/test_hyperagents_meta_agent.py
```

Expected: command exits successfully with no diagnostics.

- [ ] **Step 8: Commit the AHE change**

```bash
git add library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git commit -m "refactor: make ahe evidence file-backed"
```

---

## Completion Check

Run:

```bash
git diff --check HEAD~2..HEAD
git status --short
```

Expected: no whitespace errors. The only remaining uncommitted path is the
user's pre-existing `.gitignore` modification.
