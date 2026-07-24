# Fast Parallel Meta-Agent Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reproducible meta-agent image contract and a parallel DevBoxS preflight that isolates tool availability, MiniSWE version, and Responses protocol failures in under five minutes.

**Architecture:** Keep deterministic orchestration in a new `evolve.meta_agent_preflight` module and expose it through a thin script. Tier 0 concurrently inspects prebuilt local images and blocks model spending on contract failure; Tier 1 concurrently runs isolated two-minute live cases and normalizes their retained evidence into one redacted JSON report. Existing Harbor adapters remain responsible for real experiment artifact transport, while the preflight uses the same MiniSWE Responses configuration and completion protocol against a tiny mounted workspace.

**Tech Stack:** Python 3.12+, `asyncio`, `subprocess`, Docker CLI, MiniSWE, Harbor-compatible Responses configuration, pytest with eight xdist workers.

## Global Constraints

- Static checks finish within 15 seconds on a warm DevBoxS Docker daemon.
- The complete warm-cache preflight finishes within five minutes.
- Live cases run concurrently and each has a 120-second timeout.
- Timed preflight execution never builds, pulls, downloads, retags, or deletes images.
- Reports never contain API keys, authorization headers, proxy credentials, or full environment dumps.
- Existing experiments and unrelated containers are never selected by broad name patterns.
- Preserve every pre-existing dirty-worktree change and do not modify the existing untracked `scripts/launch-retry-gen2.sh` or `scripts/run_fast_meta_smoke.py`.
- Use `ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90` as the pinned multi-platform base image identity.
- Keep `uv==0.7.13`; build MiniSWE variants with exact versions `2.4.5` and `2.4.6`.

---

### Task 1: Apply the 64k Responses Default at the Meta-Agent Boundary

**Files:**
- Modify: `tests/test_harbor_file_agent.py`
- Modify: `templates/workspace/evolve_harbor_agent/__init__.py`

**Interfaces:**
- Consumes: the existing `FileTaskMiniSweAgent.exec_as_agent(environment, command, env=None, **kwargs)` command rewrite.
- Produces: uploaded Responses configuration whose `model.model_kwargs.max_output_tokens` is `64000` unless the original MiniSWE command already contains an explicit `model.model_kwargs.max_output_tokens=<integer>` override.

- [ ] **Step 1: Write the failing default-budget test**

Extend `test_file_task_agent_externalizes_large_miniswe_instruction`:

```python
assert model_kwargs["max_output_tokens"] == 64_000
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest -n 0 tests/test_harbor_file_agent.py::test_file_task_agent_externalizes_large_miniswe_instruction -q
```

Expected: FAIL with `KeyError: 'max_output_tokens'`.

- [ ] **Step 3: Add a failing explicit-override test**

Refactor the fake `MiniSweAgent` in `_load` so its generated command reads an optional `max_output_tokens` value from the payload context, then add:

```python
def test_file_task_agent_preserves_explicit_output_budget(monkeypatch) -> None:
    module = _load(monkeypatch, max_output_tokens=12_345)
    environment = Environment()

    asyncio.run(module.FileTaskMiniSweAgent().run("Fix the constant.", environment, object()))

    uploaded = dict(environment.uploads)
    responses_config = json.loads(uploaded[module.RESPONSES_CONFIG_PATH])
    assert "max_output_tokens" not in responses_config["model"]["model_kwargs"]
    assert "model.model_kwargs.max_output_tokens=12345" in environment.commands[-1]
```

The absence in the uploaded file is required because that file is appended as
the final `-c` configuration and must not overwrite the caller's explicit
command-line value.

- [ ] **Step 4: Run the override test and verify RED**

Run:

```bash
uv run pytest -n 0 tests/test_harbor_file_agent.py::test_file_task_agent_preserves_explicit_output_budget -q
```

Expected: FAIL because the adapter always uploads one fixed configuration.

- [ ] **Step 5: Implement the minimal defaulting rule**

In `FileTaskMiniSweAgent.exec_as_agent`, detect the exact command-line prefix
before creating `responses_config`:

```python
has_output_budget = "model.model_kwargs.max_output_tokens=" in command
model_kwargs = {
    "include": ["reasoning.encrypted_content"],
    "prompt_cache_key": cache_key,
    "extra_headers": {
        "extra": json.dumps({"session_id": cache_key}, separators=(",", ":"))
    },
}
if not has_output_budget:
    model_kwargs["max_output_tokens"] = 64_000
responses_config = {"model": {"model_kwargs": model_kwargs}}
```

- [ ] **Step 6: Verify GREEN with the focused file**

Run:

```bash
uv run pytest -n 0 tests/test_harbor_file_agent.py -q
```

Expected: all tests in the file PASS.

- [ ] **Step 7: Commit the isolated protocol fix**

```bash
git add tests/test_harbor_file_agent.py templates/workspace/evolve_harbor_agent/__init__.py
git commit -m "fix: give meta-agent responses a 64k budget"
```

### Task 2: Make Meta-Agent Images Reproducible Without Removing Tools

**Files:**
- Modify: `tests/test_phase_e_recipes.py`
- Modify: `containers/meta-agent/Dockerfile`
- Modify: `containers/meta-agent/uv-wrapper`
- Create: `containers/meta-agent/required-tools.txt`

**Interfaces:**
- Consumes: Docker build argument `MINISWE_VERSION`, defaulting to `2.4.5`.
- Produces: versioned images with labels `org.opencontainers.image.revision`, `io.evolve.miniswe.version`, and `io.evolve.uv.version`; exact tool names in `required-tools.txt` are shared with Tier 0.

- [ ] **Step 1: Replace the current Dockerfile assertion with failing reproducibility assertions**

Update `test_meta_agent_image_provides_harbor_workspace_parent` to assert:

```python
assert contents.startswith(
    "FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"
)
assert "ARG MINISWE_VERSION=2.4.5" in contents
assert "ARG SOURCE_REVISION=unknown" in contents
assert '"mini-swe-agent==${MINISWE_VERSION}"' in contents
assert 'io.evolve.miniswe.version="${MINISWE_VERSION}"' in contents
assert 'org.opencontainers.image.revision="${SOURCE_REVISION}"' in contents
```

Add a new test that reads `required-tools.txt` and asserts the exact ordered
list:

```python
assert tools == [
    "bash", "git", "curl", "diff", "file", "find", "jq", "patch",
    "python", "rg", "rsync", "sed", "tree", "uv", "mini-swe-agent",
]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
uv run pytest -n 0 tests/test_phase_e_recipes.py::test_meta_agent_image_provides_harbor_workspace_parent -q
```

Expected: FAIL because the base and MiniSWE package are unpinned.

- [ ] **Step 3: Add the shared required-tools contract**

Create `containers/meta-agent/required-tools.txt` with one command per line in
the exact order asserted above.

- [ ] **Step 4: Pin the Dockerfile inputs and add labels**

Change the Dockerfile header and MiniSWE installation to:

```dockerfile
FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

ARG MINISWE_VERSION=2.4.5
ARG SOURCE_REVISION=unknown
ARG BUILD_TIMESTAMP=unknown
ARG UV_VERSION=0.7.13

LABEL org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.created="${BUILD_TIMESTAMP}" \
      io.evolve.miniswe.version="${MINISWE_VERSION}" \
      io.evolve.uv.version="${UV_VERSION}"
```

Use `${UV_VERSION}` in the installer URL and:

```dockerfile
RUN uv tool install --python 3.13 --with fastapi --with orjson "mini-swe-agent==${MINISWE_VERSION}"
COPY required-tools.txt /opt/evolve/required-tools.txt
```

Keep the entire expanded apt package list unchanged.

- [ ] **Step 5: Pin the wrapper's compatibility reinstall**

Change the wrapper's special case to require
`EVOLVE_MINISWE_VERSION` and install the exact value:

```sh
version="${EVOLVE_MINISWE_VERSION:-2.4.5}"
exec /root/.local/bin/uv-real tool install --python 3.13 --with fastapi --with orjson "mini-swe-agent==$version"
```

- [ ] **Step 6: Verify GREEN**

Run:

```bash
uv run pytest -n 0 tests/test_phase_e_recipes.py -q
```

Expected: all phase-E recipe tests PASS.

- [ ] **Step 7: Commit the image contract**

```bash
git add containers/meta-agent/Dockerfile containers/meta-agent/uv-wrapper containers/meta-agent/required-tools.txt tests/test_phase_e_recipes.py
git commit -m "build: pin meta-agent image inputs"
```

### Task 3: Implement Matrix Validation, Redaction, and Static Image Checks

**Files:**
- Create: `src/evolve/meta_agent_preflight.py`
- Create: `tests/test_meta_agent_preflight.py`

**Interfaces:**
- Produces:
  - `PreflightCase.from_dict(data: Mapping[str, object]) -> PreflightCase`
  - `load_matrix(path: Path) -> tuple[PreflightCase, ...]`
  - `redact(value: str, environment: Mapping[str, str]) -> str`
  - `async inspect_image(case: PreflightCase, runner: CommandRunner) -> dict[str, object]`
  - `async run_static(cases: Sequence[PreflightCase], runner: CommandRunner) -> dict[str, object]`
- `CommandRunner` is an async callable receiving `argv: tuple[str, ...]`, `timeout_s: float`, and optional `env: Mapping[str, str]`; it returns `CommandResult(returncode, stdout, stderr, elapsed_s)`.

- [ ] **Step 1: Write failing matrix-validation tests**

Add tests for a valid three-case matrix and reject:

```python
@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda case: case.pop("expected_image_id"), "expected_image_id"),
        (lambda case: case.update(timeout_s=121), "timeout_s must be between 1 and 120"),
        (lambda case: case.update(name="../escape"), "case name"),
        (lambda case: case.update(miniswe_version="latest"), "semantic version"),
    ],
)
def test_load_matrix_rejects_invalid_case(tmp_path, mutation, message):
    ...
```

- [ ] **Step 2: Verify matrix tests RED**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py -q
```

Expected: collection FAIL because `evolve.meta_agent_preflight` does not exist.

- [ ] **Step 3: Implement immutable data types and validation**

Create:

```python
@dataclass(frozen=True)
class PreflightCase:
    name: str
    image: str
    expected_image_id: str
    miniswe_version: str
    expanded_tools: bool
    timeout_s: int = 120
```

Validate names with `^[A-Za-z0-9][A-Za-z0-9_.-]*$`, image IDs with
`^sha256:[0-9a-f]{64}$`, MiniSWE versions with `^\d+\.\d+\.\d+$`, uniqueness
of case names, and a nonempty matrix.

- [ ] **Step 4: Add failing redaction tests**

Cover environment-provided secrets, Bearer tokens, common key assignments, URL
userinfo, and ensure ordinary diagnostics remain unchanged:

```python
assert "secret-value" not in redact(
    "OPENAI_API_KEY=secret-value Authorization: Bearer abc",
    {"OPENAI_API_KEY": "secret-value"},
)
assert "missing executable: rg" in redact("missing executable: rg", {})
```

- [ ] **Step 5: Implement redaction and verify GREEN**

Reuse the credential patterns already established in
`library/meta_agent/runners/harbor.py`, but keep the preflight implementation
independent so importing the module does not load Harbor.

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py -q
```

Expected: validation and redaction tests PASS.

- [ ] **Step 6: Add failing parallel static-check tests**

Use an async fake runner with `asyncio.Event` to prove both image inspections
start before either completes. Cover:

- exact image-ID match;
- MiniSWE version match;
- expanded image requires every line of `required-tools.txt`;
- minimal image does not require `jq`, `rg`, `rsync`, or `tree`;
- timeout classification as `image_contract`;
- elapsed time is the maximum concurrent duration, not the sum.

- [ ] **Step 7: Implement argv-only Docker inspection**

Use only tuple argv commands:

```python
("docker", "image", "inspect", case.image, "--format", "{{json .}}")
("docker", "run", "--rm", "--entrypoint", "bash", case.image, "-lc", STATIC_PROBE)
```

The probe prints one JSON object with observed MiniSWE/Python/uv versions,
present commands, `/app` existence, and writability. Parse stdout strictly;
never use `shell=True` on the host.

- [ ] **Step 8: Verify static checks and parallelism GREEN**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py -q
```

Expected: all tests PASS in under one second.

- [ ] **Step 9: Commit the static core**

```bash
git add src/evolve/meta_agent_preflight.py tests/test_meta_agent_preflight.py
git commit -m "feat: add parallel meta-agent image checks"
```

### Task 4: Add Isolated Parallel Live Protocol Cases

**Files:**
- Modify: `src/evolve/meta_agent_preflight.py`
- Modify: `tests/test_meta_agent_preflight.py`

**Interfaces:**
- Produces:
  - `create_synthetic_workspace(root: Path, *, require_rg: bool) -> Path`
  - `async run_live_case(case: PreflightCase, output: Path, runner: CommandRunner, environment: Mapping[str, str]) -> dict[str, object]`
  - `async run_live(cases: Sequence[PreflightCase], output: Path, runner: CommandRunner, environment: Mapping[str, str]) -> dict[str, object]`
- A passing workspace contains `target/value.py`, `check.py`, and receives `changed.json` plus a nonempty Git patch.

- [ ] **Step 1: Add the failing synthetic-workspace test**

Assert the generated project starts with `VALUE = 1`, its check requires
`VALUE == 2`, and its prompt requires Python plus `rg` only for expanded cases.
The prompt must require the exact final command:

```text
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py::test_create_synthetic_workspace -q
```

Expected: FAIL because the function is absent.

- [ ] **Step 3: Implement the deterministic synthetic workspace**

Create files without network dependencies. Initialize Git with argv-only
commands and commit the baseline so patch size and changed paths are
unambiguous. The prompt instructs the agent to write:

```json
["target/value.py"]
```

to `changed.json` after `python check.py` succeeds.

- [ ] **Step 4: Add failing live-case classification tests**

Parameterize retained outcomes:

```python
[
    ("RepeatedFormatError", "model_protocol"),
    ("finish_reason=length", "model_protocol"),
    ("Submitted without changed.json", "artifact_import"),
    ("check.py failed", "verification"),
    ("no git diff", "workspace_edit"),
    ("agent process timeout", "agent_startup"),
]
```

Also assert a valid submission records effective
`max_output_tokens=64000`, tool calls, changed paths, patch bytes, exact image
ID, and log paths.

- [ ] **Step 5: Implement per-case Docker execution**

For each case:

1. create `output/cases/<case.name>/workspace`;
2. write a Responses config with `max_output_tokens: 64000`,
   `reasoning.effort: low`, encrypted reasoning inclusion, and a stable
   case-specific cache key;
3. invoke the image with the workspace mounted at `/app/task/workspace`;
4. set only the allowlisted model endpoint/key and proxy variables in the
   child environment;
5. retain stdout, stderr, trajectory, patch, and case JSON under that case
   directory;
6. inspect the trajectory's exit role and effective model configuration;
7. run `python check.py`, `git diff --binary`, and validate `changed.json`;
8. classify the first failing boundary without discarding raw redacted logs.

Use `asyncio.create_subprocess_exec`, `asyncio.wait_for`, and the exact
container name `evolve-preflight-<case.name>-<nonce>`. On timeout, stop only
that exact name.

- [ ] **Step 6: Add the failing concurrency and timeout-isolation test**

Prove three fake live cases enter the runner together, one timeout does not
cancel successful siblings, and total elapsed time tracks the slowest case.

- [ ] **Step 7: Implement bounded parallel scheduling**

Use `asyncio.TaskGroup` plus one task per validated case. Convert expected
per-case failures into result objects inside each task so a TaskGroup exception
does not cancel siblings.

- [ ] **Step 8: Verify the full unit file GREEN**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py -q
```

Expected: all tests PASS in under two seconds without Docker or credentials.

- [ ] **Step 9: Commit live orchestration**

```bash
git add src/evolve/meta_agent_preflight.py tests/test_meta_agent_preflight.py
git commit -m "feat: run meta-agent protocol smokes in parallel"
```

### Task 5: Add the CLI, Aggregate Report, and Fast Test Entry Points

**Files:**
- Create: `scripts/meta_agent_preflight.py`
- Modify: `src/evolve/meta_agent_preflight.py`
- Modify: `tests/test_meta_agent_preflight.py`
- Modify: `META_AGENTS.md`
- Modify: `recipes/ahe/README.md`
- Modify: `recipes/hyperagents/README.md`

**Interfaces:**
- Produces:
  - `async run_preflight(matrix: Path, output: Path, *, static_only: bool, selected_case: str | None) -> tuple[int, dict[str, object]]`
  - CLI options `--matrix`, `--output`, `--static-only`, and `--case`.
  - `output/report.json` with `schema_version: 1`.

- [ ] **Step 1: Add failing aggregation tests**

Cover:

- static failure skips live work and exits nonzero;
- static-only success exits zero;
- full run exits zero when all required static checks pass and at least one
  live case passes;
- full run exits nonzero when no live case passes;
- `--case` selects exactly one named case;
- unknown `--case` fails before Docker execution;
- report contains `budget_s: 300`, tier elapsed times, and sorted case results;
- JSON contains no configured secret values.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py -q
```

Expected: FAIL because aggregate orchestration is absent.

- [ ] **Step 3: Implement report aggregation and atomic JSON output**

Write `report.json.tmp`, flush and close it, then replace `report.json`.
Round elapsed seconds to three decimals. Print one terminal line per case plus
the final report path; keep the terminal output free of full environment data.

- [ ] **Step 4: Add the thin executable script**

The script imports `evolve.meta_agent_preflight.main` and exits with its return
code:

```python
#!/usr/bin/env python3
from evolve.meta_agent_preflight import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Document fast and focused usage**

Document:

```bash
uv run python scripts/meta_agent_preflight.py \
  --matrix /path/to/meta-agent-preflight.json \
  --output artifacts/user/meta-agent-preflight
```

Also document `--static-only`, `--case expanded-2.4.5`, the 15-second and
five-minute budgets, the fact that builds happen beforehand, and how failure
boundaries differ from generic image failures. Replace recipe instructions
that recommend `evolve-meta-agent-app:ubuntu-latest` with versioned image tags.

- [ ] **Step 6: Run focused tests GREEN**

Run:

```bash
uv run pytest -n 0 tests/test_meta_agent_preflight.py tests/test_harbor_file_agent.py tests/test_phase_e_recipes.py -q
```

Expected: all focused tests PASS.

- [ ] **Step 7: Run fast parallel repository verification**

Run:

```bash
uv run pytest -q
```

Expected: the repository uses its configured `-n 8 --dist worksteal`; all tests
PASS. Record total wall time.

- [ ] **Step 8: Run static analysis only on touched Python files**

Run:

```bash
uv run ruff check src/evolve/meta_agent_preflight.py scripts/meta_agent_preflight.py tests/test_meta_agent_preflight.py tests/test_harbor_file_agent.py
git diff --check
```

Expected: both commands exit zero.

- [ ] **Step 9: Commit the CLI and documentation**

```bash
git add scripts/meta_agent_preflight.py src/evolve/meta_agent_preflight.py tests/test_meta_agent_preflight.py META_AGENTS.md recipes/ahe/README.md recipes/hyperagents/README.md
git commit -m "feat: expose fast parallel meta-agent preflight"
```

### Task 6: Build the A/B Images and Run the DevBoxS Acceptance Matrix

**Files:**
- No tracked files.
- Create remotely under the selected experiment's `artifacts/user/meta-agent-preflight/`: `matrix.json`, per-case logs, and `report.json`.

**Interfaces:**
- Consumes: committed Dockerfile, preflight CLI, DevBoxS Docker daemon, existing model credentials.
- Produces: exact image IDs and one acceptance report proving the five-minute budget.

- [ ] **Step 1: Build both expanded variants in parallel outside the timed run**

On DevBoxS, use two distinct versioned tags and the same source revision:

```bash
docker build --build-arg MINISWE_VERSION=2.4.5 --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" -t evolve-meta-agent-app:20260724-tools-mswe245 containers/meta-agent
docker build --build-arg MINISWE_VERSION=2.4.6 --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" -t evolve-meta-agent-app:20260724-tools-mswe246 containers/meta-agent
```

Launch these as two independent background jobs and wait for both exact PIDs.
Do not include build time in the five-minute acceptance measurement.

- [ ] **Step 2: Resolve and record immutable IDs**

Run:

```bash
docker image inspect evolve-meta-agent-app:ubuntu-latest --format '{{.Id}}'
docker image inspect evolve-meta-agent-app:20260724-tools-mswe245 --format '{{.Id}}'
docker image inspect evolve-meta-agent-app:20260724-tools-mswe246 --format '{{.Id}}'
```

Create `matrix.json` with cases `minimal-2.4.5`,
`expanded-2.4.5`, and `expanded-2.4.6`, using the returned exact IDs,
`expanded_tools: false/true/true`, and `timeout_s: 120`.

- [ ] **Step 3: Run the untimed static gate**

Run:

```bash
time uv run python scripts/meta_agent_preflight.py \
  --matrix artifacts/user/meta-agent-preflight/matrix.json \
  --output artifacts/user/meta-agent-preflight/static \
  --static-only
```

Expected: exit zero and elapsed time below 15 seconds. If it fails, do not run
live cases.

- [ ] **Step 4: Run the timed parallel acceptance matrix**

Run:

```bash
time uv run python scripts/meta_agent_preflight.py \
  --matrix artifacts/user/meta-agent-preflight/matrix.json \
  --output artifacts/user/meta-agent-preflight/live
```

Expected: wall time below five minutes; three live cases overlap; at least one
case passes; every case has an exact failure boundary or complete success
evidence.

- [ ] **Step 5: Reproduce only a failed case if necessary**

Run:

```bash
uv run python scripts/meta_agent_preflight.py \
  --matrix artifacts/user/meta-agent-preflight/matrix.json \
  --output artifacts/user/meta-agent-preflight/repro-expanded-246 \
  --case expanded-2.4.6
```

Use this only when the matrix reports an actionable 2.4.6-specific failure; do
not rerun passing cases.

- [ ] **Step 6: Select the experiment image**

Choose the newest expanded image that passes the complete protocol. Record its
tag, immutable ID, MiniSWE version, preflight report path, and elapsed time in
the experiment handoff. Do not reuse or retag `ubuntu-latest`.

- [ ] **Step 7: Final verification**

Run locally:

```bash
uv run pytest -q
uv run ruff check src/evolve/meta_agent_preflight.py scripts/meta_agent_preflight.py tests/test_meta_agent_preflight.py tests/test_harbor_file_agent.py
git diff --check
```

Expected: all tests PASS in eight-worker parallel mode, lint passes, and the
diff has no whitespace errors.
