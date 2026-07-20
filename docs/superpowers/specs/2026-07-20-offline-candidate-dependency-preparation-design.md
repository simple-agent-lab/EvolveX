# Offline uv Candidate Runtime Design

## Purpose

Make evaluation of mutable uv-managed candidates fast and reproducible without
removing dependency files from the mutation surface.

The framework owns candidate runtime readiness. Evaluation backends consume a
prepared runtime, agent adapters install the mutable local project, and
benchmarks continue to own task execution and verification. Benchmark task
dependencies are not installed into the candidate environment.

The first integration is the MiniSWE Harbor adapter evaluated on Terminal-Bench
2.0, but neither MiniSWE nor Terminal-Bench is part of the component contract.

## Problem

The current Harbor integration uploads every candidate into every task container
and runs a network-capable `uv sync`. In the official four-task MiniSWE smoke,
concurrent syncs repeatedly reached the 360-second agent-setup timeout. Some
trials never called the model. A verifier timeout then caused the driver to
repeat a complete four-task batch, including already completed model rollouts.

This behavior has three undesirable effects:

- network and package-index availability influence benchmark completion;
- repeated dependency installation consumes most of the smoke wall time; and
- one task-level infrastructure result can duplicate unrelated model spending.

Pre-pulled Terminal-Bench images solve image startup cost but do not solve the
agent dependency lifecycle.

## Constraints

- A candidate may modify `pyproject.toml`, `uv.lock`, its source, and any other
  files allowed by the experiment surface.
- A changed dependency declaration must be validated and honored.
- The component supports uv-managed Python projects only in this version.
- Candidate-runtime preparation is benchmark- and agent-independent.
- Evaluation backends must not need to understand uv resolution or cache
  readiness.
- The preparation host and isolated consumers must share OS, architecture, and
  Python ABI compatibility. The first deployment is Linux x86-64 on DevBoxS;
  cross-platform artifact preparation is out of scope.
- Agent-specific source and import validation remains in the agent adapter.
- The implementation must not introduce a cache service, candidate image build
  pipeline, or cross-image shared virtual environment.
- Credentials and proxy values must never be written to experiment artifacts.

## Component Contract

Experiments opt in through evaluator configuration:

```yaml
evaluator:
  candidate_runtime:
    variant: uv
    project: target
```

`project` is relative to the candidate checkout. The frozen framework resolves
and validates that path; it is not supplied by a mutable operator.

The component accepts a candidate checkout, evaluation run directory, and
sanitized runtime configuration. It returns a prepared-runtime result containing:

- preparation outcome and failure ownership;
- environment variables required by a consumer;
- read-only or writable mount declarations for the package cache and managed
  Python directory; and
- a receipt reference suitable for the evaluation archive.

The initial consumer is the Harbor evaluator engine. The contract does not
mention Harbor commands, MiniSWE paths, Terminal-Bench tasks, or experiment
method names. A future evaluation backend can consume the same result without
changing the uv preparer.

## Chosen Architecture

### Candidate preparation

Immediately before an evaluation backend runs a candidate, the frozen evaluator
invokes the uv candidate-runtime component once on the Linux evaluation host.

The step:

1. checks that the configured project contains `pyproject.toml` and `uv.lock`;
2. runs `uv lock --check` to reject a stale or inconsistent lockfile;
3. creates a disposable preparation virtual environment;
4. runs `uv sync --frozen --no-install-local` against the candidate;
5. uses the configured proxy, shared uv package cache, and shared uv-managed
   Python installation directory; and
6. removes the disposable environment after preparation.

`--no-install-local` prepares external dependencies without freezing or
preinstalling the mutable local project. The preparation runs once per
candidate evaluation, not once per benchmark task or rollout replicate. uv's
content-addressed cache supplies reuse when the candidate's dependencies have
not changed, so the framework does not maintain a separate cache index.

Preparation may retry once because benchmark trials and model calls have not yet
started. A second preparation failure stops the candidate evaluation.

### Backend consumption and local installation

The prepared-runtime result supplies mounts and environment variables to the
evaluation backend. The backend passes them to each isolated candidate runtime.
The agent adapter remains responsible for uploading or mounting its current
local source and invoking its normal frozen sync.

For the first Harbor/MiniSWE integration, every Terminal-Bench container
continues to create its own virtual environment. The adapter uploads the current
candidate source and runs:

```text
uv sync --project /installed-agent/miniswe-source --frozen
```

with these effective settings:

```text
UV_OFFLINE=1
UV_LINK_MODE=copy
UV_CACHE_DIR=/installed-agent/uv-cache
UV_PYTHON_INSTALL_DIR=/installed-agent/uv-python
```

The package cache and managed-Python directory are mounted from the prepared
host paths. The package-manager invocation receives no proxy variables. Model
endpoint networking remains independently configurable by the agent adapter.
Offline mode ensures a missing external artifact fails promptly. Copy link mode
is explicit because a host bind-mounted cache and a container virtual
environment are on different filesystems.

The isolated sync still builds and installs the current local project, so source
and build-system mutations take effect. It does not install or alter benchmark
dependencies.

### Why not mount one virtual environment

A complete virtual environment may embed interpreter paths and native artifacts
that are not portable across all 89 task images. Keeping task-local environments
preserves isolation and avoids platform-family detection. A prepared-runtime or
candidate-image optimization may be reconsidered only if offline task-local
sync remains a measured bottleneck after this design is implemented.

## Failure Ownership

Failures are classified at the boundary where they occur:

- `uv lock --check` failure: candidate invalid;
- missing configured candidate project or lockfile: candidate invalid;
- candidate local package build or import failure: candidate invalid;
- proxy, registry, host-cache, or managed-Python failure during preparation:
  infrastructure failure;
- external artifact missing during task-local offline sync: infrastructure
  failure, because preparation claimed readiness;
- Docker, Harbor, mount, or artifact-collection failure: infrastructure
  failure;
- agent execution timeout: completed benchmark task with reward zero;
- verifier timeout: retry that task once; a repeated verifier timeout after a
  completed agent rollout is a completed benchmark task with reward zero; and
- other task-level infrastructure failures: retry only the affected task once,
  then leave the candidate evaluation incomplete if the retry also fails.

The distinction between candidate-invalid and infrastructure outcomes prevents
package-index outages from becoming model scores while still rejecting broken
dependency mutations.

## Retry Semantics

The driver must not repeat a complete Harbor batch after an infrastructure
result. The existing whole-evaluation infrastructure retry is removed from the
candidate evaluation path.

Retries occur only at their owning layer:

- dependency preparation: one retry before any task starts;
- LLM API call: the configured model-layer retry;
- Harbor task infrastructure: one retry of that task; and
- verifier timeout: one retry of that task, followed by reward zero if the
  verifier times out again after agent completion.

Completed task results are retained and never regenerated merely because
another task failed. A candidate receives a score only when its expected task
vector is complete under these rules.

## Pre-launch Smoke Experiments

The following are one-time launch gates, not per-generation stages.

### Smoke 1: full-image install compatibility

Prepare the seed candidate once and run Harbor install-only mode across all 89
pre-pulled Terminal-Bench 2.0 images with four workers and no LLM calls.

Success requires:

- all 89 agent installations and import preflights complete;
- all task-container dependency syncs are offline;
- no setup timeout, missing artifact, Python incompatibility, or image pull; and
- setup durations and outcomes are recorded.

This smoke is repeated only after an infrastructure-sensitive change such as a
uv version, Python version, Harbor adapter, cache layout, or benchmark-image
change.

### Smoke 2: real evolution path

Run AHE and HyperAgents concurrently on four official tasks already observed to
finish normally and quickly. Use four workers for each experiment, AHE `k=2`,
HyperAgents `k=1`, and run generation zero plus two child generations.

Success requires:

- every candidate evaluation has a complete expected task vector;
- neither experiment records an infrastructure failure;
- both meta-agent paths produce valid candidate artifacts;
- dependency preparation runs once per candidate rather than once per task;
- no complete task batch is replayed; and
- all experiment-owned processes, containers, and networks are cleaned up after
  completion.

The smoke score may be zero. This gate validates execution and evidence flow,
not model quality.

After both smokes pass, the full 89-task experiments may launch. During a full
generation, the only added stage is one candidate dependency preparation before
the normal 89-task evaluation.

## Evidence and Observability

Each candidate evaluation writes `candidate-runtime.json` containing:

- schema version;
- runtime variant (`uv`);
- configured project path;
- candidate commit;
- SHA-256 digest over `pyproject.toml`, `uv.lock`, and `.python-version` when
  present;
- uv version;
- preparation attempt count, outcome, and wall-clock duration;
- whether required external artifacts were already present in cache; and
- redacted failure classification and message when unsuccessful.

The record contains no environment dump, proxy URL, token, credential, or cache
file listing. Existing Harbor results retain task-level setup, agent, verifier,
cost, and wall-clock evidence.

## Verification

Framework-level automated tests cover:

- candidate-runtime configuration and path containment;
- unchanged and changed lockfiles;
- stale lockfile rejection;
- preparation retry and terminal infrastructure failure;
- proxy use only during preparation;
- the backend-neutral environment and mount result;
- Harbor consumption of offline settings and cache/Python mounts;
- missing offline artifact classification;
- local project build/import classification;
- removal of complete-batch infrastructure retry;
- task-only retry preserving completed sibling results; and
- repeated verifier timeout becoming reward zero only after agent completion.

Remote verification on DevBoxS consists of the two approved smoke experiments.
No full experiment launches until both succeed.

## Operational Simplicity

This design intentionally adds one uv candidate-runtime component, two shared
runtime paths, a small evidence record, one Harbor consumption path, and narrower
retry behavior. It does not add a package-manager-neutral plugin system, daemon,
registry mirror, candidate Dockerfile, per-lock cache directory, or shared
virtual environment. A proxy accelerates preparation, but measured candidate
execution is independent of package-index availability.
