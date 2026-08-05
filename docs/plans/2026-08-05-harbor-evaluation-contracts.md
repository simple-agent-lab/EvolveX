# Harbor Evaluation Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make limited Harbor evaluations use one deterministic task set and install candidate source as the unprivileged runtime owner.

**Architecture:** Extend the existing split-selection boundary so it materializes the effective limited task set before Harbor starts, then use those members for host identity, runtime filters, expected trials, and score coverage. Replace mode-normalized directory upload with a validated source archive that is uploaded once and extracted by the same runtime user that runs `uv sync`.

**Tech Stack:** Python 3.12 standard library (`argparse`, `contextlib`, `pathlib`, `tarfile`), POSIX shell, pytest, Harbor 0.18, uv.

## Global Constraints

- `EVOLVE_TASK_LIMIT` is a supported evaluation input and must be applied before runtime selection is recorded.
- Full evaluations without `EVOLVE_TASK_LIMIT` remain unchanged.
- The original candidate source tree and its modes must remain unchanged.
- Candidate transport must not depend on host umask, container UID mappings, privileged `chmod`, or world-writable source files.
- `EVOLVE_HARBOR_MODEL` remains provider-qualified; only `OPENAI_MODEL` receives an automatic `openai/` prefix.
- Do not add recipe-specific, script-specific, DevBox-specific, or class-name-suffix behavior.
- Write each behavioral test first and observe the expected failure before changing production code.

---

## File map

- `src/evolve/splits.py`: selects and records the effective runtime task members; exposes CLI support for split and task-file limiting.
- `src/evolve/evaluation/identity.py`: derives the host evaluation identity from the same limited members.
- `src/evolve/evaluation/execution.py`: passes the limit into identity construction and rejects host/runtime selection disagreement.
- `scaffolds/evaluators/harbor/engine.sh`: materializes the limited selection before assembling Harbor arguments and exports the effective expected-trial count.
- `scaffolds/evaluators/harbor/parse_score.py`: derives coverage from the effective runtime selection, with explicit-count fallback for unresolved datasets.
- `src/evolve/integrations/harbor/_candidate_source.py`: validates and packages a candidate tree for unprivileged extraction.
- `src/evolve/integrations/harbor/miniswe_candidate.py`: uploads and extracts the package as the runtime user before synchronization.
- `tests/test_m8_dataset_splits.py`, `tests/test_runtime.py`, `tests/test_harbor_evaluator_template.py`: task-selection contract tests.
- `tests/test_miniswe_harbor_wrapper.py`: candidate transport contract tests.
- `ARCHITECTURE.md`, `library/README.md`, `docs/README.md`: maintained module budget and public configuration semantics.

---

### Task 1: Materialize one effective limited task set

**Files:**
- Modify: `src/evolve/splits.py`
- Modify: `src/evolve/evaluation/identity.py`
- Modify: `src/evolve/evaluation/execution.py`
- Modify: `scaffolds/evaluators/harbor/engine.sh`
- Modify: `scaffolds/evaluators/harbor/parse_score.py`
- Test: `tests/test_m8_dataset_splits.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_harbor_evaluator_template.py`

**Interfaces:**
- Consumes: `selected_task_names(manifest, split_name, round_number=None, limit=None)` and existing `TaskSetIdentity`.
- Produces: `write_runtime_selection(..., limit: int | None = None)`, `write_runtime_task_file_selection(task_file: Path, run_dir: Path, *, limit: int)`, and `effective_task_set_identity(..., task_limit: int | None = None)`.
- Runtime artifact: `task-split.json` contains the exact raw task names supplied to Harbor; `task-names.txt` contains their escaped Harbor filters.

- [ ] **Step 1: Add failing split-selection tests**

Add tests that call the real selection functions and CLI:

```python
def test_runtime_selection_applies_limit_before_recording_identity(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks", count=6)
    manifest = build_manifest(
        dataset.as_posix(),
        {"train": 1.0, "gate": 0.0, "sealed": 0.0, "seed": 7},
        base_dir=tmp_path,
        sampling="static",
        gate_limit=0,
    )
    manifest_path = tmp_path / "splits.json"
    manifest_path.write_text(json.dumps(manifest))
    run_dir = tmp_path / "run"

    write_runtime_selection(manifest_path, dataset.as_posix(), "train", run_dir, limit=1)

    recorded = json.loads((run_dir / "task-split.json").read_text())
    assert recorded["tasks"] == manifest["tasks"]["train"][:1]
    assert (run_dir / "task-names.txt").read_text().splitlines() == [
        harbor_task_pattern(recorded["tasks"][0])
    ]
    assert (run_dir / "task_set_hash").read_text().strip() == split_selection_digest(
        "train", recorded["tasks"]
    )
```

Add a task-file case with comments and three names; assert `limit=1` records only the first active name. Add CLI cases for `select ... --limit 1` and `limit-file ... --limit 1`.

- [ ] **Step 2: Run the split tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/test_m8_dataset_splits.py
```

Expected: failures because `write_runtime_selection` has no `limit` parameter, task-file selection does not exist, and the CLI has no `--limit` support.

- [ ] **Step 3: Implement selection before recording**

In `src/evolve/splits.py`:

```python
def write_runtime_selection(
    manifest_path: Path,
    dataset: str,
    split_name: str,
    run_dir: Path,
    *,
    round_number: int | None = None,
    limit: int | None = None,
) -> None:
    names, digest = select_dataset_tasks(
        manifest_path,
        dataset,
        split_name,
        round_number=round_number,
        limit=limit,
    )
    _write_runtime_task_selection(run_dir, split_name, names, digest)


def write_runtime_task_file_selection(task_file: Path, run_dir: Path, *, limit: int) -> None:
    if limit < 1:
        raise ValueError("task limit must be at least 1")
    names = [
        line.strip()
        for line in task_file.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ][:limit]
    if not names:
        raise RuntimeError("evaluator task file contains no tasks")
    _write_runtime_task_selection(
        run_dir,
        "task_file",
        names,
        split_selection_digest("task_file", names),
    )
```

Use `argparse` to preserve the existing optional positional round number while adding `--limit` to `select`, plus a `limit-file TASK_FILE RUN_DIR --limit LIMIT` command. Keep `_write_runtime_task_selection` responsible for all three artifacts so their members cannot diverge.

- [ ] **Step 4: Add failing host-identity tests**

Add tests demonstrating that configured task names, task files, and resolved split members are truncated before hashing:

```python
def test_effective_task_identity_uses_limited_split_members(tmp_path: Path) -> None:
    workspace = init_fixture_workspace_with_three_train_tasks(tmp_path)
    evaluator = load_config(workspace / "evolve.yaml")["evaluator"]

    identity = effective_task_set_identity(
        workspace,
        evaluator,
        purpose="candidate",
        task_limit=1,
    )

    assert identity.members == tuple(
        json.loads((workspace / "evaluator" / "splits.json").read_text())["tasks"]["train"][:1]
    )
    assert _expected_trials(evaluator, 1, selected_tasks=len(identity.members)) == evaluator["k"]
```

- [ ] **Step 5: Run the identity tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/test_runtime.py -k 'expected_trials or task_identity'
```

Expected: failure because `effective_task_set_identity` does not accept or apply `task_limit`.

- [ ] **Step 6: Implement limited host identity and consistency validation**

Add `task_limit: int | None = None` to `effective_task_set_identity`. For a resolved split, use `load_manifest` plus `selected_task_names(..., limit=task_limit)` rather than reading the JSON list directly. For configured task names or a task file, preserve declared order and slice before calling `task_set_identity`. Reject limits below one.

In `evaluate`, pass `task_limit` into `effective_task_set_identity`. After the evaluator returns, load `run_dir/task-split.json` when `task_set.members` is non-empty and compare its normalized unique members with `task_set.members`. Selection order may be meaningful before limiting but is not part of `TaskSetIdentity`, which canonicalizes the selected subset. On disagreement, set:

```python
setup_outcome = Outcome.INFRASTRUCTURE_FAILED
setup_reason = "runtime task selection differs from the planned effective task set"
```

Do not score mismatched evidence as a benchmark result.

- [ ] **Step 7: Add a failing evaluator-template regression test**

Build a resolved three-task split, set `EVOLVE_TASK_LIMIT=1` and `EVOLVE_HARBOR_ATTEMPTS=2`, make fake Harbor emit two zero-reward trials for the selected task, then assert:

```python
assert result.returncode == 0
assert (run_dir / "status").read_text().strip() == "complete"
assert json.loads((run_dir / "task-split.json").read_text())["tasks"] == [expected_task]
metrics = json.loads((run_dir / "metrics.json").read_text())["dimensions"]
assert metrics == {
    "completed_trials": 2,
    "expected_trials": 2,
    "harbor_rc": 0,
    "missing_trials": 0,
    "pass_rate": 0.0,
}
```

- [ ] **Step 8: Run the evaluator regression and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/test_harbor_evaluator_template.py -k 'task_limit or limited'
```

Expected: the parser reports the full split count or the runtime selection still contains all three tasks.

- [ ] **Step 9: Wire the effective selection through the Harbor engine**

In `engine.sh`, validate `EVOLVE_TASK_LIMIT` before selection. Pass `--limit` into resolved split selection. When a configured task file and limit are present, run `limit-file`, then replace `EVOLVE_HARBOR_TASK_FILE` with `$EVOLVE_RUN_DIR/task-names.txt`.

After materialization, count active lines in `task-names.txt` and export:

```sh
EVOLVE_HARBOR_EXPECTED_TRIALS=$((effective_tasks * EVOLVE_HARBOR_ATTEMPTS))
```

Keep `--n-tasks` as an equal defensive cap. Update `parse_score.py` so a recorded `task-split.json` is authoritative and an explicit `EVOLVE_HARBOR_EXPECTED_TRIALS` is used only when no runtime selection exists.

- [ ] **Step 10: Verify Task 1 GREEN**

Run:

```bash
.venv/bin/pytest -q tests/test_m8_dataset_splits.py tests/test_runtime.py tests/test_harbor_evaluator_template.py
```

Expected: all selected tests pass, including zero-reward limited evaluation coverage.

- [ ] **Step 11: Commit Task 1**

```bash
git add src/evolve/splits.py src/evolve/evaluation/identity.py src/evolve/evaluation/execution.py scaffolds/evaluators/harbor/engine.sh scaffolds/evaluators/harbor/parse_score.py tests/test_m8_dataset_splits.py tests/test_runtime.py tests/test_harbor_evaluator_template.py
git commit -m "fix: make limited Harbor task selection authoritative"
```

---

### Task 2: Transfer candidate source as the runtime owner

**Files:**
- Create: `src/evolve/integrations/harbor/_candidate_source.py`
- Modify: `src/evolve/integrations/harbor/miniswe_candidate.py`
- Modify: `ARCHITECTURE.md`
- Test: `tests/test_miniswe_harbor_wrapper.py`

**Interfaces:**
- Consumes: a validated candidate project root `Path`.
- Produces: `candidate_source_archive(source: Path) -> AbstractContextManager[Path]` and `UnsafeCandidateSourceError`.
- Adapter transport: upload `/tmp/evolve-miniswe-source.tar`, then extract into `/installed-agent/miniswe-source` through the ordinary runtime user.

- [ ] **Step 1: Write failing archive-contract tests**

Add direct tests for the new module:

```python
def test_candidate_archive_normalizes_owner_modes_without_mutating_source(tmp_path: Path) -> None:
    source = locked_candidate_source(tmp_path / "source", directory_mode=0o700, file_mode=0o600)

    with candidate_source_archive(source) as archive_path:
        with tarfile.open(archive_path) as archive:
            members = {member.name: member for member in archive.getmembers()}
            assert members["./pyproject.toml"].mode == 0o600
            assert members["./src"].mode == 0o700
            assert not (members["./pyproject.toml"].mode & stat.S_IWOTH)

    assert stat.S_IMODE(source.stat().st_mode) == 0o700
    assert stat.S_IMODE((source / "pyproject.toml").stat().st_mode) == 0o600
```

Add parameterized cases for an absolute symlink and a `../` escaping symlink; both must raise `UnsafeCandidateSourceError` before an archive is yielded.

- [ ] **Step 2: Run the archive tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/test_miniswe_harbor_wrapper.py -k 'candidate_archive'
```

Expected: import failure because `_candidate_source.py` and its interfaces do not exist.

- [ ] **Step 3: Implement the candidate archive boundary**

Create `_candidate_source.py` with:

```python
class UnsafeCandidateSourceError(ValueError):
    pass


@contextmanager
def candidate_source_archive(source: Path) -> Iterator[Path]:
    root = source.resolve()
    _validate_symlinks(root)
    with tempfile.TemporaryDirectory(prefix="evolve-miniswe-source-") as tempdir:
        archive_path = Path(tempdir) / "source.tar"
        with tarfile.open(archive_path, "w", dereference=False) as archive:
            archive.add(root, arcname=".", recursive=True, filter=_runtime_owned_member)
        archive_path.chmod(0o644)
        yield archive_path
```

`_runtime_owned_member` clears stored uid/gid names and sets directories to `0700`, ordinary files to `0600`, and files executable anywhere in the source snapshot to `0700`. Symlink validation resolves each link relative to its parent and requires the result to remain under `root`.

- [ ] **Step 4: Change the adapter test to require archive upload and unprivileged extraction**

Update the fake environment so `upload_file` inspects the tar while the context is active. Assert:

```python
assert not environment.uploaded_directories
assert environment.uploaded_archive_destination == "/tmp/evolve-miniswe-source.tar"
assert environment.archive_modes["./pyproject.toml"] == 0o600
assert "tar -xf /tmp/evolve-miniswe-source.tar" in environment.commands[0]
assert "--no-same-owner" in environment.commands[0]
assert "chmod -R" not in "\n".join(environment.commands)
assert stat.S_IMODE(target.stat().st_mode) == 0o700
```

Also assert the extraction command is executed through `_runtime_phase`, not `exec_as_root`.

- [ ] **Step 5: Run the adapter test and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/test_miniswe_harbor_wrapper.py -k 'installs_candidate_source or unsafe_candidate_source'
```

Expected: failure because the adapter still calls `upload_dir` with a world-writable staging copy.

- [ ] **Step 6: Implement runtime-user extraction and remove the staging workaround**

In `miniswe_candidate.py`, remove `_installable_source_copy`, `shutil`, and `tempfile`. Import the archive context and error. Package and upload the candidate source, mapping unsafe-source errors to:

```python
raise EvolveCandidateInvalidError("EVOLVE_CANDIDATE_INVALID: unsafe_source_tree") from error
```

Before uv bootstrap, execute an infrastructure-owned runtime phase equivalent to:

```sh
set -euo pipefail
mkdir -p /installed-agent/miniswe-source
trap 'rm -f /tmp/evolve-miniswe-source.tar' EXIT
tar -xf /tmp/evolve-miniswe-source.tar --no-same-owner --directory /installed-agent/miniswe-source
```

Use error code `source_extract_failed`. The default environment user must run this phase; do not use `exec_as_root`.

- [ ] **Step 7: Verify Task 2 GREEN**

Run:

```bash
.venv/bin/pytest -q tests/test_miniswe_harbor_wrapper.py tests/test_harbor_agent_roles.py tests/test_harbor_file_agent.py
```

Expected: all selected tests pass and no assertion permits world-writable archive members or privileged permission repair.

- [ ] **Step 8: Update architecture budgets and commit Task 2**

Add `_candidate_source.py` to `ARCHITECTURE.md`, reduce the candidate adapter budget after removing staging logic, and adjust the total exactly.

```bash
git add ARCHITECTURE.md src/evolve/integrations/harbor/_candidate_source.py src/evolve/integrations/harbor/miniswe_candidate.py tests/test_miniswe_harbor_wrapper.py
git commit -m "fix: install candidate source as the Harbor runtime user"
```

---

### Task 3: Document boundaries and verify end to end

**Files:**
- Modify: `library/README.md`
- Modify: `docs/designs/2026-08-05-harbor-evaluation-contracts-design.md` only if implementation reveals a reviewed factual correction.
- Test: existing full suite and DevBox smoke artifacts.

**Interfaces:**
- Consumes: the effective-selection and candidate-archive contracts from Tasks 1 and 2.
- Produces: maintained user guidance and verified local/DevBox evidence.

- [ ] **Step 1: Add the model-variable ownership documentation**

Near the existing evaluator environment description in `library/README.md`, state:

```markdown
`EVOLVE_HARBOR_MODEL` must be a provider-qualified Harbor model identifier.
For OpenAI endpoints, `OPENAI_MODEL` accepts a bare model name and the evaluator
constructs `openai/<name>` explicitly. Evolve does not guess providers for bare
`EVOLVE_HARBOR_MODEL` values.
```

Also document that `EVOLVE_TASK_LIMIT` selects a deterministic prefix of the effective task set and changes the recorded task-set identity for that run.

- [ ] **Step 2: Run focused static and contract verification**

Run:

```bash
.venv/bin/ruff check src library tests
git diff --check
rg -n 'endswith\([^\n]*(MiniSwe|MiniSWE)|endswith\([^\n]*miniswe' src library
```

Expected: Ruff and diff checks pass; the suffix-dispatch search returns no matches.

- [ ] **Step 3: Run the complete local suite**

Run with normal uv cache access:

```bash
.venv/bin/pytest -q
```

Expected: the full suite passes with no warnings or hangs.

- [ ] **Step 4: Run current focused tests on DevBox**

Transfer the exact branch commit to an isolated DevBox checkout, then run:

```bash
uv run pytest -q \
  tests/test_m8_dataset_splits.py \
  tests/test_harbor_evaluator_template.py \
  tests/test_miniswe_harbor_wrapper.py \
  tests/test_harbor_agent_roles.py \
  tests/test_harbor_file_agent.py
```

Expected: all focused tests pass using DevBox's Python, uv, and Docker-adjacent environment.

- [ ] **Step 5: Run the DevBox adapter gates**

Run three isolated checks without modifying the main DevBox checkout:

1. Installed adapter real Harbor/MiniSWE run with a literal `EVOLVE_SESSION_ID`.
2. Candidate installation smoke from a restrictive-mode exact snapshot.
3. Real candidate evaluation with a three-task resolved split and `EVOLVE_TASK_LIMIT=1`.

For the third check, require all of:

```text
outer evaluator exit code = 0
status = complete
expected_trials = 1
completed_trials = 1
missing_trials = 0
Harbor exceptions = 0
runtime task-split members = 1
```

The benchmark reward may be zero; zero is a valid completed result.

- [ ] **Step 6: Commit documentation**

```bash
git add library/README.md docs/designs/2026-08-05-harbor-evaluation-contracts-design.md
git commit -m "docs: clarify Harbor evaluation ownership"
```

- [ ] **Step 7: Record final branch state**

Run:

```bash
git status --short --branch
git log --oneline --decorate main..HEAD
```

Expected: a clean `codex/miniswe-adapter-contracts` worktree with the design commit and three implementation commits.
