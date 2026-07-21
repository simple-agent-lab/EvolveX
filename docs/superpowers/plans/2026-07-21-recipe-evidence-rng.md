# Faithful Recipe RNG and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HyperAgents distinct reproducible parent-selection draws and give AHE/HyperAgents compact, filesystem-backed evidence prompts with official-style AHE decision signals.

**Architecture:** Make one generic correction inside the existing SDK RNG construction, then keep all evidence selection and analysis behavior inside the AHE and HyperAgents recipe operators. Reuse `archive.jsonl`, canonical task vectors, and existing analysis artifacts; add no services, storage formats, operator stages, or automatic rollback behavior.

**Tech Stack:** Python 3.12, `random`, `hashlib`, JSON/JSONL artifacts, pytest, existing Evolve frozen operator SDK.

## Global Constraints

- Preserve existing operator interfaces and `OperatorContext.rng`.
- Do not change AHE or HyperAgents gate behavior.
- Do not add automatic rollback or hill climbing.
- Keep AHE `k=2` and all-task debugger defaults unchanged.
- Keep complete debugger details, bounded cases, and raw traces on disk.
- Keep evidence compaction recipe-local; do not change the shared feedback loader.
- Do not touch the user's existing modifications in `templates/target/harbor/miniswe_source_agent.py`, `templates/workspace/evolve_harbor_adapter/__init__.py`, or `tests/test_miniswe_harbor_wrapper.py`.

---

## File Map

- `src/evolve/frozen/sdk.py`: derive a stable generation-varying seed for the existing context RNG.
- `library/trace_analyzer/ahe.py`: compute official per-change verdicts and append best-ever/stability summaries to the existing overview.
- `library/meta_agent/ahe.py`: inline only the AHE overview and compact attribution, then advertise detail/raw-evidence paths.
- `library/meta_agent/hyperagents.py`: select and bound the recipe's inline evidence without recursively loading history.
- `tests/test_phase_f_interfaces_sdk.py`: RNG determinism and variation tests.
- `tests/test_ahe_trace_analyzer.py`: verdict, best-ever, stability, and artifact-preservation tests.
- `tests/test_ahe_meta_agent.py`: compact AHE prompt and missing-overview tests.
- `tests/test_hyperagents_meta_agent.py`: bounded HyperAgents prompt, fallback, and path tests.

### Task 1: Derive RNG From Existing Invocation Identity

**Files:**
- Modify: `src/evolve/frozen/sdk.py:7-16,152-165`
- Test: `tests/test_phase_f_interfaces_sdk.py`

**Interfaces:**
- Produces: `_rng_seed(seed: object, genid: str, parent: str | None) -> int`
- Preserves: `OperatorContext.rng: random.Random`

- [ ] **Step 1: Write failing RNG tests**

Add tests that call `_context` with controlled SDK environment values:

```python
def test_sdk_rng_is_reproducible_for_same_generation(tmp_path, monkeypatch):
    _set_sdk_env(monkeypatch, tmp_path, genid="5", parent="2", config={"seed": 123})
    first_rng = sdk._context({"seed": 123}).rng
    second_rng = sdk._context({"seed": 123}).rng
    first = [first_rng.random() for _ in range(3)]
    second = [second_rng.random() for _ in range(3)]
    assert first == second


def test_sdk_rng_varies_by_generation_and_parent(tmp_path, monkeypatch):
    _set_sdk_env(monkeypatch, tmp_path, genid="5", parent="2", config={"seed": 123})
    original = sdk._context({"seed": 123}).rng.random()
    monkeypatch.setenv("EVOLVE_GENID", "6")
    by_generation = sdk._context({"seed": 123}).rng.random()
    monkeypatch.setenv("EVOLVE_GENID", "5")
    monkeypatch.setenv("EVOLVE_PARENT", "3")
    by_parent = sdk._context({"seed": 123}).rng.random()
    assert len({original, by_generation, by_parent}) == 3


def test_sdk_rng_accepts_string_generation_ids(tmp_path, monkeypatch):
    _set_sdk_env(monkeypatch, tmp_path, genid="candidate-a", parent="root", config={"seed": 0})
    assert isinstance(sdk._context({"seed": 0}).rng.random(), float)
```

- [ ] **Step 2: Run the tests and verify the variation test fails**

Run:

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_phase_f_interfaces_sdk.py -k 'rng'
```

Expected: reproducibility passes, while generation/parent variation fails because every context currently uses `Random(123)`.

- [ ] **Step 3: Implement stable seed derivation**

Add `hashlib` and this helper, then use it in `_context`:

```python
def _rng_seed(seed: object, genid: str, parent: str | None) -> int:
    base_seed = int(seed)
    identity = json.dumps(
        [base_seed, str(genid), str(parent or "")],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], "big")


def _context(config: dict[str, Any]) -> OperatorContext:
    seed = config.get("seed", 0)
    genid = os.environ["EVOLVE_GENID"]
    parent = os.environ.get("EVOLVE_PARENT") or None
    fan_out = config.get("fan_out", 1)
    return OperatorContext(
        workspace=Path(os.environ["EVOLVE_WORKSPACE"]),
        checkout=Path(os.environ["EVOLVE_CHECKOUT"]),
        run_dir=Path(os.environ["EVOLVE_RUN_DIR"]),
        genid=genid,
        parent=parent,
        round=None,
        fan_out=int(fan_out),
        config=config,
        rng=random.Random(_rng_seed(seed, genid, parent)),
    )
```

- [ ] **Step 4: Run SDK and selector tests**

Run:

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_phase_f_interfaces_sdk.py tests/test_hyperagents_select.py \
  tests/test_ahe_select.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit the RNG correction**

```bash
git add src/evolve/frozen/sdk.py tests/test_phase_f_interfaces_sdk.py
git commit -m "fix: vary deterministic operator rng by generation"
```

### Task 2: Add Official AHE Decision Signals

**Files:**
- Modify: `library/trace_analyzer/ahe.py:409-552`
- Test: `tests/test_ahe_trace_analyzer.py`

**Interfaces:**
- Produces: `_change_verdict(predicted: list[str], fixed: list[str], realized: list[str]) -> str`
- Produces: `_archive_analysis(ctx: OperatorContext) -> dict[str, Any]`
- Extends: `trace_analyzer/analysis/change_evaluation.json`
- Extends: `trace_analyzer/analysis/overview.md`

- [ ] **Step 1: Write failing attribution verdict tests**

Add a parameterized unit test matching the upstream rules:

```python
@pytest.mark.parametrize(
    ("predicted", "fixed", "realized", "expected"),
    [
        (["a"], ["a"], [], "EFFECTIVE"),
        (["a", "b"], ["a"], [], "PARTIALLY_EFFECTIVE"),
        (["a"], ["a"], ["risk"], "MIXED"),
        (["a"], [], [], "INEFFECTIVE"),
        (["a"], [], ["risk"], "HARMFUL"),
    ],
)
def test_ahe_change_verdict_matches_upstream(predicted, fixed, realized, expected):
    module = _module()
    assert module._change_verdict(predicted, fixed, realized) == expected
```

Extend `test_ahe_analyzer_attributes_prior_manifest` so its manifest includes `id`, `description`, and `files`, then assert a `MIXED` evaluation and no unattributed regressions.

- [ ] **Step 2: Run attribution tests and verify they fail**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_ahe_trace_analyzer.py -k 'verdict or attributes_prior_manifest'
```

Expected: fail because `_change_verdict` and `change_evaluations` do not exist.

- [ ] **Step 3: Implement verdicts and unattributed regressions**

Add the helper:

```python
def _change_verdict(predicted: list[str], fixed: list[str], realized: list[str]) -> str:
    if realized and not fixed:
        return "HARMFUL"
    if realized and fixed:
        return "MIXED"
    if predicted and len(fixed) == len(predicted):
        return "EFFECTIVE"
    if fixed:
        return "PARTIALLY_EFFECTIVE"
    return "INEFFECTIVE"
```

In `_change_evaluation`, build one evaluation per manifest entry with `change_id`, `description`, `files`, `predicted_fixes`, `actually_fixed`, `still_failed`, `predicted_risks`, `risk_realized`, and `verdict`. Preserve `transitions`, `prediction_results`, and `risk_results`. Compute `unattributed_regressions` as pass-to-fail tasks absent from the union of all declared predictions and risks.

- [ ] **Step 4: Write failing archive-summary tests**

Add a fixture helper that writes canonical-looking merged archive rows directly to `archive.jsonl`, including `selection_eligible`, numeric `score`, and task vectors. Cover:

```python
rows = [
    _archive_row("0", 0.20, {"always-pass": ["passed", "passed"], "flip": ["failed", "failed"]}),
    _archive_row("1", 0.30, {"always-pass": ["passed", "passed"], "flip": ["passed", "passed"]}),
    _archive_row("2", 0.25, {"always-pass": ["passed", "passed"], "flip": ["failed", "failed"]}),
]
```

Assert best-ever is generation 1; `always-pass` is stable; and `flip` is unstable after three observations. Add a two-generation fixture asserting `flip` is possibly unstable. Add an ineligible higher-scoring row and assert it is ignored.

- [ ] **Step 5: Run archive-summary tests and verify they fail**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_ahe_trace_analyzer.py -k 'best_ever or stability'
```

Expected: fail because `_archive_analysis` and overview history sections do not exist.

- [ ] **Step 6: Implement archive-derived best-ever and stability**

Read merged rows with the existing archive helpers. Only include rows whose `selection_eligible` is true and whose `task_vector.tasks` is a mapping. For each task, map trials to:

```python
def _task_vector_outcome(task: dict[str, Any]) -> str:
    statuses = [str(trial.get("status") or "") for trial in task.get("trials", [])]
    if statuses and all(status == "passed" for status in statuses):
        return "pass"
    if any(status in {"passed", "failed"} for status in statuses):
        return "fail"
    return "exception"
```

Classify histories using the upstream three-observation threshold. Return:

```python
{
    "best_ever": {"genid": str(best["genid"]), "score": float(best["score"])} if best else None,
    "stability": {
        "stable_pass": sorted(stable_pass),
        "stable_fail": sorted(stable_fail),
        "unstable": sorted(unstable),
        "possibly_unstable": sorted(possibly_unstable),
        "infra_only": sorted(infra_only),
    },
}
```

Append a compact “Best Ever” and “Task Stability” section to the existing overview in `_reports`; do not add these fields to every task detail or to `selected.md` case bodies.

- [ ] **Step 7: Run all AHE analyzer tests**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_ahe_trace_analyzer.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit AHE analysis signals**

```bash
git add library/trace_analyzer/ahe.py tests/test_ahe_trace_analyzer.py
git commit -m "feat: add faithful AHE attribution signals"
```

### Task 3: Compose AHE Prompt From Overview and Paths

**Files:**
- Modify: `library/meta_agent/ahe.py:14-15,78-135`
- Test: `tests/test_ahe_meta_agent.py`

**Interfaces:**
- Produces: `_overview(ctx: OperatorContext) -> str`
- Preserves: `build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str`

- [ ] **Step 1: Update the AHE prompt fixture and write failing tests**

Change `_case` to create `trace_analyzer/analysis/overview.md` with a unique overview sentinel and a detail file with a unique detail-body sentinel. Add:

```python
def test_ahe_prompt_inlines_overview_but_not_detail_bodies(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    prompt = module.build_prompt(checkout, "fallback", ctx)
    assert "OVERVIEW ROOT CAUSE" in prompt
    assert "DETAIL BODY MUST STAY ON DISK" not in prompt
    assert f"runs/gen-{ctx.genid}/trace_analyzer/analysis/detail" in prompt
    assert f"runs/gen-{ctx.genid}/trace_analyzer/evidence/cases.jsonl" in prompt
    assert f"runs/gen-{ctx.genid}/rollout" in prompt


def test_ahe_prompt_requires_nonempty_overview(tmp_path: Path) -> None:
    module = _module()
    checkout, _run_dir, ctx = _case(tmp_path)
    (ctx.run_dir / "trace_analyzer/analysis/overview.md").write_text("")
    with pytest.raises(RuntimeError, match="empty AHE debugger overview"):
        module.build_prompt(checkout, "fallback", ctx)
```

- [ ] **Step 2: Run prompt tests and verify they fail**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_ahe_meta_agent.py -k 'prompt'
```

Expected: overview/detail behavior fails because `build_prompt` currently uses recursive `load_feedback`.

- [ ] **Step 3: Implement overview-only prompt composition**

Remove the AHE operator's dependency on `load_feedback`. Read the overview with `_required_text` and add stable workspace-relative paths:

```python
def _overview(ctx: OperatorContext) -> str:
    return _required_text(
        ctx.run_dir / "trace_analyzer" / "analysis" / "overview.md",
        "AHE debugger overview",
    )


def _evidence_paths(ctx: OperatorContext) -> str:
    root = f"runs/gen-{ctx.genid}"
    return "\n".join(
        [
            f"- Per-task details: `{root}/trace_analyzer/analysis/detail/`",
            f"- Bounded cases: `{root}/trace_analyzer/evidence/cases.jsonl`",
            f"- Raw rollout artifacts: `{root}/rollout/`",
        ]
    )
```

Use `# Current Debugger Overview` for the inline overview and `# Evidence Paths` for these paths. Keep attribution, prior manifest, archive outcomes, surface rules, and manifest output requirements unchanged.

- [ ] **Step 4: Run AHE meta-agent and analyzer tests**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_ahe_meta_agent.py tests/test_ahe_trace_analyzer.py
```

Expected: all tests pass; the detail artifacts still contain their complete bodies.

- [ ] **Step 5: Commit compact AHE prompt composition**

```bash
git add library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git commit -m "fix: keep AHE detail evidence out of prompts"
```

### Task 4: Bound HyperAgents Inline Evidence

**Files:**
- Modify: `library/meta_agent/hyperagents.py:14-70`
- Test: `tests/test_hyperagents_meta_agent.py`

**Interfaces:**
- Produces: `MAX_INLINE_EVIDENCE_CHARS: int`
- Produces: `_prompt_evidence(observation: str, ctx) -> str`
- Preserves: `build_prompt(checkout: Path, observation: str, ctx) -> str`

- [ ] **Step 1: Write failing prompt-selection tests**

Extend the prompt test fixture with a linked `history.json` containing `HISTORY MUST NOT BE INLINED`, an `attempts.md` fallback, and `last_accepted.diff`. Add assertions that selected evidence is inline, the history sentinel is absent, and the full history path is present.

Add oversized and fallback tests:

```python
def test_hyperagents_prompt_bounds_inline_evidence(tmp_path: Path) -> None:
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    evidence = run_dir / "feedback/evidence"
    evidence.mkdir(parents=True)
    (evidence / "selected.md").write_text("x" * (module.MAX_INLINE_EVIDENCE_CHARS + 1000))
    prompt = module.build_prompt(checkout, "fallback", ctx)
    assert "[inline evidence truncated; complete artifact:" in prompt
    assert len(prompt) < module.MAX_INLINE_EVIDENCE_CHARS + 15_000


def test_hyperagents_prompt_uses_attempts_fallback(tmp_path: Path) -> None:
    module = _load_hyperagents_meta_agent()
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(run_dir.parents[1], checkout, run_dir)
    feedback = run_dir / "feedback"
    feedback.mkdir(parents=True)
    (feedback / "attempts.md").write_text("COMPACT ATTEMPTS")
    assert "COMPACT ATTEMPTS" in module.build_prompt(checkout, "fallback", ctx)
```

- [ ] **Step 2: Run HyperAgents prompt tests and verify they fail**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_hyperagents_meta_agent.py -k 'prompt'
```

Expected: fail because recursive `load_feedback` includes history and no bound/fallback constant exists.

- [ ] **Step 3: Implement recipe-local evidence selection**

Remove this operator's use of `load_feedback`. Add:

```python
MAX_INLINE_EVIDENCE_CHARS = 50_000
LATEST_DIFF_CHARS = 5_000


def _read_optional(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _clip_inline(text: str, source: Path) -> str:
    if len(text) <= MAX_INLINE_EVIDENCE_CHARS:
        return text
    marker = f"\n\n[inline evidence truncated; complete artifact: {source}]"
    return text[: MAX_INLINE_EVIDENCE_CHARS - len(marker)] + marker


def _lineage(ctx) -> str:
    rows = sdk.rows(ctx.workspace)[-8:]
    return "\n".join(
        "- gen %s: parent=%s score=%s status=%s"
        % (row.get("genid"), row.get("parent"), row.get("score"), row.get("status"))
        for row in rows
    ) or "- No recorded generations"
```

`_prompt_evidence` must choose `feedback/evidence/selected.md`, then `feedback/attempts.md`, then the supplied observation. Clip the chosen source. Include compact lineage and at most `LATEST_DIFF_CHARS` from `feedback/last_accepted.diff`, with its complete path when clipped.

Keep all existing artifact path lines in `build_prompt` and add an explicit complete-history path to `feedback/evidence/history.json`. Do not read `feedback/index.md` or follow links from it.

- [ ] **Step 4: Run HyperAgents tests**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_hyperagents_meta_agent.py tests/test_hyperagents_semantics.py \
  tests/test_hyperagents_harbor_recipe.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit bounded HyperAgents prompt composition**

```bash
git add library/meta_agent/hyperagents.py tests/test_hyperagents_meta_agent.py
git commit -m "fix: bound HyperAgents inline evidence"
```

### Task 5: Cross-Recipe Regression Verification

**Files:**
- No production changes expected.
- Modify only a directly failing focused test when it encodes the intentionally changed RNG or prompt semantics.

**Interfaces:**
- Consumes all changes from Tasks 1-4.
- Produces final verification evidence.

- [ ] **Step 1: Run focused formatting and lint checks**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run ruff check \
  src/evolve/frozen/sdk.py \
  library/trace_analyzer/ahe.py \
  library/meta_agent/ahe.py \
  library/meta_agent/hyperagents.py \
  tests/test_phase_f_interfaces_sdk.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_ahe_meta_agent.py \
  tests/test_hyperagents_meta_agent.py
```

Expected: exit 0 with no findings.

- [ ] **Step 2: Run the complete focused regression group**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_phase_f_interfaces_sdk.py \
  tests/test_hyperagents_select.py \
  tests/test_hyperagents_meta_agent.py \
  tests/test_hyperagents_semantics.py \
  tests/test_hyperagents_harbor_recipe.py \
  tests/test_ahe_select.py \
  tests/test_ahe_gate.py \
  tests/test_ahe_trace_analyzer.py \
  tests/test_ahe_meta_agent.py \
  tests/test_m9_ahe_recipe.py \
  tests/test_m5_driver_operators.py
```

Expected: all tests pass.

- [ ] **Step 3: Run initialized-recipe smoke tests**

```bash
UV_CACHE_DIR=/tmp/codex-uv-cache-evolve uv run pytest -q -n 0 \
  tests/test_m0_init.py \
  tests/test_phase_e_recipes.py \
  tests/test_phase_f_init_binding.py \
  tests/test_recipe_inventory.py
```

Expected: all tests pass without starting Harbor or model-backed evaluation.

- [ ] **Step 4: Verify scope and workspace state**

```bash
git diff --check
git status --short
git diff --stat HEAD~4..HEAD
```

Expected: only the files listed in this plan are changed by the implementation commits; the three pre-existing user modifications remain uncommitted and are not included in implementation commits.

- [ ] **Step 5: Record any intentional test expectation updates**

If an existing test fails because it requires recursively inlined history or identical RNG draws across generations, update only that assertion to the approved semantics, rerun its full test file, and include it in the relevant task commit. Do not weaken gate, archive-integrity, or artifact-preservation assertions.
