# Canonical Archive Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all new evaluation events consistently receipted and make `ArchiveView` the only supported interface for experiment archive analysis.

**Architecture:** Keep `archive.jsonl` internal and append-only. Change the existing evaluation writer by one unconditional marker assignment, retain `merged_rows()` as the legacy compatibility boundary, and update the DevBoxS experiment summarizer to consume `ArchiveView.row()` instead of scanning raw events.

**Tech Stack:** Python 3.11+, JSONL, pytest, DevBoxS over SSH.

## Global Constraints

- Work only in `.worktrees/framework-hardening`; do not modify the dirty primary checkout.
- Do not rewrite or migrate historical archives.
- Do not add a schema version, dataclass, new reader API, or JSON CLI.
- Keep raw Harbor results as the exception and verifier-reward evidence source.
- Add only two focused regression tests.
- Preserve the unrelated changes in `.superpowers/sdd/task-2-report.md` and `.superpowers/sdd/task-8-report.md`.

---

### Task 1: Receipt Every New Evaluation Event

**Files:**
- Modify: `tests/test_m1_evaluator_invariants.py`
- Modify: `src/evolve/driver.py:738-766`

**Interfaces:**
- Consumes: `MECHANISM_EVAL_FIELD`, `append_event()`, and `verify_integrity()` from `evolve.archive`.
- Produces: every `_stamp_evaluation()` event carries `MECHANISM_EVAL_FIELD: True`, causing `append_event()` to write its receipt.

- [ ] **Step 1: Add the failing ordinary-evaluation regression**

Extend the archive import in `tests/test_m1_evaluator_invariants.py` and add:

```python
from evolve.archive import MECHANISM_EVAL_FIELD, append_event, verify_integrity


def test_ordinary_evaluation_is_marked_and_receipted(tmp_path: Path) -> None:
    workspace, evolve_home = init_workspace(tmp_path)

    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        env={"EVAL_STUB": "1", "EVOLVE_HOME": str(evolve_home)},
    )

    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in (workspace / "archive.jsonl").read_text().splitlines()]
    evaluation = next(
        event
        for event in events
        if event.get("genid") == "1" and event.get("pending_gate_record") is True
    )
    assert evaluation[MECHANISM_EVAL_FIELD] is True
    assert verify_integrity(workspace) == []
```

- [ ] **Step 2: Run the test and verify the current inconsistency**

Run:

```bash
uv run pytest tests/test_m1_evaluator_invariants.py::test_ordinary_evaluation_is_marked_and_receipted -q
```

Expected: FAIL because the ordinary evaluation event lacks `_evolve_mechanism_eval`.

- [ ] **Step 3: Make the marker unconditional**

In `_stamp_evaluation()` retain the optional purpose fields, then mark every event:

```python
    if round_number is not None:
        event["kind"] = kind
        event["round"] = round_number
    event[MECHANISM_EVAL_FIELD] = True
    append_event(workspace, exp_id, event)
```

- [ ] **Step 4: Run the focused regression**

Run:

```bash
uv run pytest tests/test_m1_evaluator_invariants.py::test_ordinary_evaluation_is_marked_and_receipted -q
```

Expected: PASS.

---

### Task 2: Lock In the Canonical Legacy Reader Contract

**Files:**
- Modify: `tests/test_m1_evaluator_invariants.py`
- Modify: `templates/workspace/README.md`

**Interfaces:**
- Consumes: `ArchiveView(workspace).row(genid)` from `evolve.frozen.interfaces`.
- Produces: a documented, tested rule that analysis reads canonical merged rows and never inspects raw event markers.

- [ ] **Step 1: Add the markerless legacy characterization test**

Add this import and test to `tests/test_m1_evaluator_invariants.py`:

```python
from evolve.frozen.interfaces import ArchiveView


def test_archive_view_reads_markerless_legacy_evaluation_without_rewrite(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    archive = workspace / "archive.jsonl"
    archive.write_text(
        json.dumps(
            {
                "genid": "1",
                "parent": "0",
                "tag": "gen/1",
                "score": 0.0,
                "status": "complete",
                "task_set_hash": "legacy-task-set",
                "task_vector": None,
                "evaluator_tree": "legacy-evaluator",
                "valid_parent": True,
                "verdict": "keep",
                "reason": "mechanism evaluation stamp",
                "pending_gate_record": True,
                "note": "mechanism evaluation recorded before gate/record",
                "cost": {"usd": 0, "wall_s": 1.0},
            }
        )
        + "\n"
    )
    before = archive.read_bytes()

    row = ArchiveView(workspace).row("1")

    assert row is not None
    assert row["status"] == "complete"
    assert row["score"] == 0.0
    assert row["valid_parent"] is True
    assert archive.read_bytes() == before
```

- [ ] **Step 2: Run the characterization test**

Run:

```bash
uv run pytest tests/test_m1_evaluator_invariants.py::test_archive_view_reads_markerless_legacy_evaluation_without_rewrite -q
```

Expected: PASS, confirming that the existing `merged_rows()` compatibility path is sufficient and needs no new reader implementation.

- [ ] **Step 3: Document the supported consumer boundary**

Add this paragraph after the `archive.jsonl` description in `templates/workspace/README.md`:

```markdown
Analysis code should read generations through `ArchiveView` rather than parse
raw `archive.jsonl` events. Raw event fields are internal and may differ across
framework versions; `ArchiveView` preserves compatibility with older ledgers.
```

- [ ] **Step 4: Run the relevant existing tests**

Run:

```bash
uv run pytest \
  tests/test_m1_evaluator_invariants.py \
  tests/test_selection_certification.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the framework change**

Run:

```bash
git add src/evolve/driver.py tests/test_m1_evaluator_invariants.py templates/workspace/README.md
git commit -m "Make ArchiveView the stable evaluation reader"
```

---

### Task 3: Recompute the Existing DevBoxS Experiment

**Files:**
- Modify remotely: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/run-selection-correctness-summary.py`
- Read remotely: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-20260713-192510/**`
- Read remotely: `/data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-recovery-20260713-194342/**`
- Create remotely: `summary.json` and `summary.md` under the original experiment root.

**Interfaces:**
- Consumes: raw Harbor `result.json` for exception/reward evidence and `ArchiveView.row(genid)` for canonical archive state.
- Produces: the preregistered paired McNemar results using the replacement HyperAgents task-04 pair.

- [ ] **Step 1: Replace raw archive-event filtering**

Load `ArchiveView` from the recorded hardened workspace framework:

```python
CANONICAL_FRAMEWORK = pathlib.Path(
    "/data00/home/zimuwang/simple-evolve-agent-project/experiments/"
    "framework-hardening-selection-correctness-20260713-192510/"
    "arms/ahe-hardened/task-01/workspace/.evolve"
)
sys.path.insert(0, str(CANONICAL_FRAMEWORK))

from evolve.frozen.interfaces import ArchiveView
```

Then replace the marker filter with:

```python
genid = "0" if arm.startswith("ahe-") else "1"
row = ArchiveView(out / "workspace").row(genid)
if row is None:
    raise RuntimeError(f"{arm} task {index}: canonical row {genid} is missing")
```

Keep the original raw Harbor result parsing unchanged.

- [ ] **Step 2: Validate the remote summarizer without launching trials**

Run:

```bash
python3 -m py_compile \
  /data00/home/zimuwang/simple-evolve-agent-project/experiments/run-selection-correctness-summary.py
```

Expected: exit code 0.

- [ ] **Step 3: Recompute from existing artifacts**

Run:

```bash
python3 /data00/home/zimuwang/simple-evolve-agent-project/experiments/run-selection-correctness-summary.py \
  /data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-20260713-192510 \
  /data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-recovery-20260713-194342
```

Expected: `all_recipes_pass: true`; no Harbor evaluation is launched.

- [ ] **Step 4: Verify evidence and cleanup state**

Verify:

```bash
test -s /data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-20260713-192510/summary.json
test -s /data00/home/zimuwang/simple-evolve-agent-project/experiments/framework-hardening-selection-correctness-20260713-192510/summary.md
test "$(docker ps -q | wc -l)" -eq 0
```

Expected: all commands exit 0.
