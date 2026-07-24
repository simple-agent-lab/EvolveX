# Fast Parallel Meta-Agent Preflight Design

## Goal

Provide a single preflight command that determines, in less than five minutes
on DevBoxS, whether a meta-agent image can inspect an evolution workspace, use
the required shell tools, edit the allowed surface, run a check, submit
successfully, and return the expected artifacts.

The preflight must separate three variables that previous experiments changed
together:

1. the image's command-line tool set;
2. the installed MiniSWE version and dependency environment;
3. the Responses API configuration used by the meta-agent.

It is not a benchmark, a quality evaluation, or a full evolution generation.

## Success Criteria

- Static checks finish within 15 seconds on a warm DevBoxS Docker daemon.
- The complete warm-cache preflight finishes within five minutes.
- Independent live cases run concurrently.
- Every result records the exact image ID, MiniSWE version, requested output
  token limit, reasoning effort, elapsed time, exit status, tool-call count,
  changed paths, patch size, and artifact-contract status.
- A passing live case must make a deterministic edit in a tiny synthetic
  workspace, run its supplied check, issue the submission command, and return
  `changed.json`.
- A failed case must identify its failure boundary: image contract, agent
  startup, model protocol, workspace edit, verification, submission, or
  artifact import.
- The command exits nonzero if any required static check fails or if no live
  configuration passes.

## Non-Goals

- Running Terminal-Bench tasks.
- Evaluating whether an agent-generated improvement raises benchmark score.
- Building images as part of the timed preflight.
- Downloading packages during the timed preflight.
- Exercising every Harbor agent adapter.
- Adding tools unrelated to the current Python MiniSWE target.

## Approach

Use a tiered harness with cheap failures first and parallel live work second.
The harness emits one machine-readable JSON report plus a compact terminal
summary.

### Tier 0: Static Image and Configuration Contract

Tier 0 runs without a model call. Checks for different images execute in
parallel.

For each configured image it verifies:

- Docker can resolve the tag locally without pulling;
- the immutable image ID matches the expected value supplied to the harness;
- the image exposes `bash`, `git`, `curl`, `diff`, `file`, `find`, `jq`,
  `patch`, `python`, `rg`, `rsync`, `sed`, `tree`, `uv`, and
  `mini-swe-agent`;
- `mini-swe-agent --version` matches the declared version;
- Python and `uv` start successfully;
- `/app` exists and is writable by the execution user.

Repository-level static tests verify that the file-backed meta-agent Responses
configuration sets `max_output_tokens` to `64000` while preserving an explicit
override. This check targets
`templates/workspace/evolve_harbor_agent/__init__.py`, which constructs the
actual meta-agent request. Candidate-adapter configuration is not accepted as
a substitute.

If Tier 0 fails, the harness reports all static failures and does not spend
money on Tier 1.

### Tier 1: Parallel Live Protocol Matrix

Tier 1 creates one isolated synthetic workspace per case. It starts all cases
concurrently with a bounded concurrency equal to the number of configured
cases, initially three:

1. minimal tool image with MiniSWE 2.4.5;
2. expanded tool image with MiniSWE 2.4.5;
3. expanded tool image with MiniSWE 2.4.6.

All cases receive the same short prompt, model, `low` reasoning effort,
`max_output_tokens=64000`, step limit, and wall-clock timeout. The prompt asks
the agent to:

1. inspect a two-file Python project;
2. use `rg` and `python`;
3. change a known constant in the editable file;
4. run a deterministic local check;
5. submit using the required completion command.

The minimal image case may use a fallback inspection command because `rg` is
intentionally absent. The report records this capability difference; it does
not confuse it with a protocol failure. The two expanded-image cases must use
the full required tool contract.

Each live case has a two-minute timeout. The harness terminates only the timed
out case, allowing other cases to finish and preserving their logs. Because
cases run concurrently, three two-minute cases add approximately two minutes,
not six, to wall-clock time.

## Image Reproducibility

Experiment recipes must stop using a mutable `ubuntu-latest` image identity.
The Dockerfile will:

- use a digest-pinned Ubuntu base;
- keep `uv` pinned to `0.7.13`;
- accept an explicit MiniSWE version at build time and install exactly that
  version;
- retain the expanded command-line tool set;
- expose image labels for the source revision, MiniSWE version, and build
  timestamp.

The A/B images are built before the timed preflight and referenced by versioned
tags plus expected immutable image IDs. The preflight never pulls, rebuilds, or
retags them.

## Responses Protocol Fix

The file-backed meta-agent adapter will add
`model.model_kwargs.max_output_tokens = 64000` to the generated Responses
configuration. It will use defaulting semantics so an explicit caller-provided
value remains authoritative.

The retained trajectory must expose the effective value. A live case that
claims to request 64k but whose retained configuration does not show 64k is an
adapter/configuration failure, even if the model happens to submit.

`RepeatedFormatError`, `finish_reason=length` before a Bash call, missing
submission, and missing returned artifacts remain distinct reported outcomes.
The harness must not collapse them into a generic image failure.

## Result Model

The report is written to a caller-selected directory and contains:

```json
{
  "schema_version": 1,
  "started_at": "ISO-8601 timestamp",
  "elapsed_s": 0.0,
  "budget_s": 300,
  "static": {
    "passed": true,
    "elapsed_s": 0.0,
    "images": []
  },
  "live": {
    "passed": true,
    "elapsed_s": 0.0,
    "cases": []
  }
}
```

Each image and live-case entry includes a stable case name, exact image tag and
ID, declared and observed MiniSWE versions, status, failure boundary, elapsed
time, and paths to retained logs. Live entries additionally include the
effective output-token limit, reasoning effort, agent exit status, tool calls,
changed paths, patch size, check result, submission status, and artifact status.

Reports contain no API keys, authorization headers, proxy credentials, or full
environment dumps.

## Command-Line Interface

The repository will provide one host-side command:

```bash
uv run python scripts/meta_agent_preflight.py \
  --matrix configs/meta-agent-preflight.json \
  --output artifacts/user/meta-agent-preflight
```

The matrix file declares already-built image tags, expected image IDs,
MiniSWE versions, whether the expanded tool contract is required, and live-case
timeouts. Secrets and endpoints continue to come from the existing environment
and are never serialized into the matrix or report.

Useful modes are:

```bash
uv run python scripts/meta_agent_preflight.py --matrix ... --output ... --static-only
uv run python scripts/meta_agent_preflight.py --matrix ... --output ... --case expanded-2.4.5
```

The default command runs Tier 0 and then the complete Tier 1 matrix. `--case`
supports quick reproduction of one failed case without changing the default
parallel behavior.

## Test Strategy

Development follows test-first cycles.

Fast local unit tests cover:

- matrix validation;
- parallel scheduling;
- timeout isolation;
- command construction without shell interpolation;
- image-contract parsing;
- failure-boundary classification;
- secret redaction;
- aggregate exit status;
- report serialization;
- the meta-agent 64k default and explicit override.

Unit tests use fake process results and must run in parallel with the existing
pytest suite. They do not require Docker, Harbor, network access, or model
credentials.

Docker contract tests are opt-in and verify prebuilt local images only. Live
tests are opt-in, require credentials, and use the synthetic workspace. The
single DevBoxS preflight command is the acceptance test for the five-minute
budget.

## Operational Safety

- The harness never deletes or retags existing images.
- Every case uses a unique temporary workspace and Harbor job name.
- Timeouts terminate only processes and containers created by that case.
- Existing experiments and containers are not selected by broad name patterns.
- Logs and reports are written outside candidate mutable surfaces.
- Static failure prevents live model spending.

## Rollout

1. Add the failing configuration test for the missing 64k meta-agent default.
2. Implement the minimal adapter fix and focused tests.
3. Add the preflight report model and static tier with unit tests.
4. Add parallel live scheduling and synthetic workspace checks with unit tests.
5. Pin and build the two expanded MiniSWE variants on DevBoxS outside the
   timed run.
6. Run the three-case preflight once, record exact image IDs, and select the
   proven versioned image for subsequent experiments.
