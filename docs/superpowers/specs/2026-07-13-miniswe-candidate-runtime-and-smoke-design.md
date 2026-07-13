# MiniSWE Candidate Runtime and Optional Smoke Design

**Date:** 2026-07-13

**Status:** Approved for implementation planning

**Scope:** Complete the candidate-dependency portion of
`codex/framework-hardening` and add a protected, optional diagnostic command
that a meta-agent may run while editing a candidate.

## Context

The MiniSWE Harbor wrapper currently uploads candidate source into every task
container and invokes `uv run --project /installed-agent/miniswe-source` during
both installation and trial execution. The affected target omitted `uv.lock`,
while its `pyproject.toml` allowed a changing LiteLLM version. Each task could
therefore resolve and build a different dependency graph. Observed consequences
included missing FastAPI, LiteLLM build failures, setup timeouts, and different
behavior across trials.

The matching upstream MiniSWE lock pins the intended LiteLLM and FastAPI
versions. Preserving that lock and materializing it with frozen uv semantics
removes the source of dependency drift.

The existing framework-hardening branch already provides exception-first Harbor
classification, canonical evaluation outcomes, runtime identity primitives,
evaluation epochs, and certified archive eligibility. It does not yet implement
the candidate-runtime work described by Task 7 of the shared hardening plan.
This design completes that work and reuses the existing outcome and
certification machinery.

## Goals

1. Reconstruct the same locked MiniSWE dependency graph during training and
   testing on the shared evaluation machine.
2. Prevent unresolved dependency resolution during benchmark trials.
3. Detect missing, stale, or unusable candidate dependencies before model
   execution and classify the failure explicitly.
4. Reuse downloaded and built uv artifacts across smoke runs and Harbor trials.
5. Give the meta-agent a protected command for obtaining environment feedback
   while preserving its freedom to decide whether and when to run it.
6. Keep installation proxies separate from the model runtime environment.
7. Preserve the evaluator, Harbor wrapper, smoke implementation, credentials,
   and proxy configuration outside the mutable candidate surface.

## Non-Goals

- Creating a portable virtualenv archive or reproducing environments across
  different physical machines.
- Requiring the optional smoke command as a candidate-admission gate.
- Making a model API request from the smoke command.
- Automatically adding FastAPI or any other undeclared package after a failure.
- Silently regenerating `uv.lock` during smoke, candidate installation, or
  benchmark execution.
- Allowing the meta-agent to modify or replace the smoke command, Harbor
  wrapper, evaluator, cache configuration, credentials, or proxy configuration.
- Guaranteeing that broken candidate source will pass merely because dependency
  materialization succeeds.

## Design Decisions

### The lock is part of the candidate

A MiniSWE source target consists of source code, `pyproject.toml`, and `uv.lock`.
Workspace initialization copies the upstream lock byte-for-byte and rejects a
MiniSWE source seed without one. `pyproject.toml` may change only with a lock
that uv verifies as current. A lock-only update is allowed when it remains
compatible with the unchanged project declaration.

The framework never repairs this pair during evaluation. A meta-agent may
intentionally update both files when the recipe permits dependency changes, but
the resulting pair must pass `uv lock --check` without mutation before the
candidate is evaluated.

### Frozen materialization is normal runtime setup

Candidate installation in a Harbor task container runs:

```bash
UV_CACHE_DIR=/installed-agent/uv-cache \
  uv sync --project /installed-agent/miniswe-source --frozen
```

This is part of ordinary installed-agent setup, not a separate workflow
admission boundary. It always happens before candidate model execution,
regardless of whether the meta-agent previously used the optional smoke
command.

After synchronization, candidate commands execute:

```text
/installed-agent/miniswe-source/.venv/bin/python
```

The wrapper never runs plain `uv run --project` during a benchmark trial.

Frozen synchronization may retrieve artifacts named by the lock when the shared
cache is cold. An offline regression proves that the same environment can be
materialized again from a warmed cache. Benchmark correctness depends on the
lock, not on whether the cache was warm.

### One shared uv package cache

The evaluator owns one persistent uv cache under `runs/runtime/uv-cache` on the
shared machine and exposes it to MiniSWE task containers at
`/installed-agent/uv-cache`. The cache is shared across candidates and trials so
unchanged graphs do not repeatedly download or rebuild packages. uv's
content-addressed artifacts allow a dependency change to add only newly needed
content.

A small candidate materialization record lives under:

```text
runs/runtime/candidates/<candidate-runtime-hash>/
```

The hash includes the candidate tree, `pyproject.toml`, `uv.lock`, Python
version/ABI, platform, uv version, and task image identity. The record contains
metadata and outcomes, not credentials or a copied virtualenv.

Because current experiments use one evaluation machine, this design does not
add cross-machine cache transport or distributed cache coordination.

## Protected Optional Smoke Command

The vendored protected console exposes:

```bash
./evolve candidate-smoke
```

The meta-agent may run it at any point while editing the uncommitted candidate,
revise the candidate, and run it again. Skipping the command does not block
candidate evaluation. Its purpose is earlier feedback and cache warming, not
certification or admission.

The command implementation lives in protected framework code under `.evolve/`.
It reads the current candidate checkout but writes only append-only run
artifacts outside the candidate mutation surface.

### Modes

The command defaults to the most informative mode and offers narrower modes for
fast iteration:

```bash
./evolve candidate-smoke --quick
./evolve candidate-smoke --container
./evolve candidate-smoke --full
```

- `--quick` verifies file presence, project/lock consistency, candidate source
  structure, and inexpensive static checks without creating a Harbor container.
- `--container` performs frozen synchronization in a representative Harbor task
  container and imports MiniSWE from the resulting virtualenv.
- `--full` performs the container checks and constructs the configured MiniSWE
  LiteLLM model path. It makes no model API request. `--full` is the default.

The modes call the same protected phase implementations used by normal
candidate installation where applicable. They do not maintain a second set of
dependency semantics.

### Smoke output

Every invocation receives an append-only attempt directory under the current
generation's run area. It writes a short terminal summary and `result.json`
containing:

- schema version, attempt identity, mode, start time, duration, and status;
- candidate tree, project, lock, runtime, task-image, and cache fingerprints;
- named phase outcomes for lock check, frozen sync, MiniSWE import, and LiteLLM
  initialization;
- candidate or infrastructure ownership for a terminal failure;
- a concise sanitized error category such as `missing_lock`, `stale_lock`,
  `materialization_failed`, `missing_import`, or `model_init_failed`;
- cache hit/miss information and phase durations;
- proxy-variable presence as booleans only.

The result never contains credential values, proxy values, `.env` contents,
raw environment dumps, or arbitrary retained tracebacks. The immediate command
output is concise enough for the meta-agent to act on during the same editing
turn; the structured result remains available to later analysis.

### Prompt guidance

Meta-agent prompts describe the command as optional and protected:

> A protected diagnostic command, `./evolve candidate-smoke`, is available. Use
> it at your judgment when changes or failure evidence may involve dependencies,
> imports, model initialization, container compatibility, or other
> environment-sensitive behavior. You may revise the candidate and rerun it.
> The command and its artifacts are read-only framework machinery. Do not
> replace its checks with ad hoc package installation or silent lock
> regeneration.

The prompt recommends `--quick` for inexpensive iteration and the default
`--full` when environment behavior is material to the proposal. It does not
claim that a smoke pass guarantees benchmark correctness.

## Runtime Preflight Inside Candidate Installation

After frozen synchronization, the Harbor wrapper uses the virtualenv Python to:

1. import `minisweagent` from the uploaded candidate source;
2. import the agent, environment, configuration, and configured LiteLLM model
   modules used by the real runner;
3. load the same MiniSWE configuration used by benchmark execution;
4. construct the configured LiteLLM model object without making a model call.

This exercises the historical missing-FastAPI path. A correct upstream lock
installs FastAPI. A missing optional dependency causes a deterministic setup
failure rather than a later arbitrary trial traceback.

Frozen synchronization failure raises the stable marker:

```text
EVOLVE_CANDIDATE_INVALID: frozen dependency materialization failed
```

Source import or model initialization failure raises a separate stable
candidate-preflight marker. The existing Harbor artifact classifier consumes
these markers before reward and assigns `candidate_invalid`. The implementation
does not classify failures by searching arbitrary traceback text.

## Proxy and Credential Boundary

System-package installation, uv bootstrap, and frozen synchronization may use
the configured installation proxy. The model initialization and benchmark
runner explicitly remove:

```text
HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
```

Explicit model configuration continues to propagate normally, including model
name, API base/endpoint, and provider credentials. Those values are never
written to smoke artifacts or logs by the framework.

Smoke model initialization receives only the configuration necessary to
construct the configured path and does not send a request. Normal benchmark
execution receives the existing explicit credentials and endpoint settings.

## Mutable-Surface Boundary

The framework treats the following as immutable for every MiniSWE recipe:

- `.evolve/**` and the `./evolve` console;
- `target/harbor_agent.py`;
- evaluator and Harbor engine files;
- smoke implementation and artifact schema;
- runtime cache configuration;
- model and proxy configuration.

Candidate MiniSWE source remains mutable. Recipes may also permit
`target/pyproject.toml` and `target/uv.lock`, but the framework validates them as
a dependency pair. Smoke artifacts are evidence and are never copied into the
candidate commit.

## Relationship to Existing Framework Hardening

This design extends rather than replaces the branch's existing abstractions:

- `RuntimeFingerprint` and candidate materialization records identify the
  runtime used by smoke and evaluation.
- Existing exception-first Harbor parsing interprets stable setup markers.
- Canonical outcomes and certificates prevent setup failures from becoming
  benchmark scores or valid parents.
- Existing evaluation epochs continue to represent evaluator-capsule changes;
  ordinary candidate dependency changes alter the candidate fingerprint, not
  the evaluator epoch.
- The optional smoke result is diagnostic evidence and does not itself create
  an evaluation certificate.

## End-to-End Flow

```text
initialize MiniSWE target
  -> preserve and validate pyproject.toml + uv.lock
  -> meta-agent edits candidate
       -> optionally run protected candidate-smoke one or more times
       -> inspect sanitized feedback and revise
  -> normal Harbor evaluation
       -> upload source and lock
       -> frozen sync using shared cache
       -> import MiniSWE and initialize configured LiteLLM path
       -> execute .venv/bin/python directly
       -> classify result exception-first
       -> certify only a complete benchmark evaluation
```

If the meta-agent skips smoke, normal Harbor installation still follows the
same frozen runtime path. There is no separate smoke admission gate.

## Failure Semantics

| Failure | Ownership | Result |
|---|---|---|
| Missing `uv.lock` | Candidate | Reject at initialization or candidate validation |
| Stale/incompatible project and lock | Candidate | Reject candidate without lock regeneration |
| Locked LiteLLM build failure | Candidate | Explicit frozen-materialization failure |
| Missing FastAPI on configured LiteLLM path | Candidate | Explicit model-preflight failure |
| uv binary, cache mount, container, or evaluator unavailable | Infrastructure | Infrastructure failure; never benchmark zero |
| Model endpoint unavailable during actual benchmark execution | Infrastructure/model service | Existing exception-first evaluation policy |
| Smoke skipped | None | Candidate proceeds to normal frozen Harbor setup |

## Verification Strategy

Test-first implementation must include regressions for:

- preservation of the exact upstream `target/uv.lock` during initialization;
- rejection of a missing lock;
- rejection of a changed `pyproject.toml` with a stale or missing compatible
  lock update;
- acceptance of a compatible project/lock update;
- frozen synchronization without runtime lock regeneration;
- offline re-materialization from a warmed shared cache;
- reuse of the unchanged cache across smoke and trial setup;
- no plain runtime `uv run --project` in the MiniSWE wrapper;
- direct virtualenv Python execution;
- MiniSWE imports from the materialized candidate environment;
- configured LiteLLM model initialization and the missing-FastAPI path;
- explicit LiteLLM build/materialization failure classification;
- installation proxies present only during installation phases;
- generic proxy variables absent during model initialization and execution;
- propagation of explicit model endpoints and credentials without artifact
  disclosure;
- immutability of the Harbor wrapper and smoke implementation;
- optional smoke behavior: all modes, repeated invocations, append-only
  artifacts, sanitized output, and no candidate-tree mutation;
- smoke skipping without creating an admission failure;
- integration with existing candidate-invalid outcomes and archive eligibility.

Run focused dependency, wrapper, smoke, Harbor-artifact, and surface-policy
tests, followed by the complete suite. Final validation includes a small real
Harbor container canary on the shared evaluation machine. The protected
`candidate-smoke --full` canary validates materialization and model
initialization without an API call; one minimal normal Harbor trial separately
validates the complete model-execution path. Neither command prints `.env`
contents, credentials, or proxy values.

## Acceptance Criteria

The design is complete when:

1. The historical matching MiniSWE project and lock materialize the pinned
   LiteLLM and FastAPI graph.
2. Repeated training and testing trials on the shared machine use the same
   candidate lock and direct virtualenv interpreter.
3. No benchmark trial performs unresolved `uv run --project` resolution.
4. Missing or incompatible dependency state is explicit and cannot produce a
   score or parent-eligible archive row.
5. The shared cache avoids repeated package downloads and builds for unchanged
   graphs.
6. The meta-agent can optionally obtain useful, sanitized environment feedback
   without gaining control of evaluator-owned machinery.
7. Skipping smoke does not block evaluation, while normal Harbor setup remains
   frozen and reproducible.
8. Focused tests, the full suite, and the real Harbor canary all pass.
