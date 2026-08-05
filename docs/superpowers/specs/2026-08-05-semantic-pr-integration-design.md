# Semantic Integration of PRs 23, 26, 29, and 31

Date: 2026-08-05

## Objective

Create one draft pull request from the latest remote `main` that preserves the
final intended behavior of PRs #23, #26, #29, and #31 without preserving their
divergent branch topology or obsolete intermediate implementations. The result
must remain provider-neutral, keep proxy use optional, pass the complete local
quality suite, and complete real model-backed qualification on DevBox.

## Starting Point and Scope

The integration starts from a freshly fetched `origin/main`. At design time,
that ref is `8f0a745`, the merge of PR #28. The integration branch must refresh
`origin/main` before implementation and again before publication. If it moves,
the branch is reconciled with the new tip and affected tests are rerun.

Included sources of intent:

- PR #23, `3a2d419`: evolved Codex candidate binding and credential isolation.
- PR #26, `befde1c`: PR #23 plus live Harbor expected-trial correction.
- PR #29, `9627eef`: certified evaluation contracts, inline runtime
  configuration, diagnostics, authentication, proxy routing, preflight, and
  public smoke behavior.
- PR #31, `372814f`: explicit MiniSWE roles, authoritative limited task
  selection, runtime-user-owned candidate transport, session identity, and
  model configuration ownership.

Excluded:

- unrelated local commit `0ad0281` and the separate README identity branch;
- private DevBox paths, hosts, credentials, proxy values, task bundles, and
  experiment outputs;
- historical implementation plans or reconciliation records from the source
  PRs;
- intermediate runtime-profile APIs superseded by PR #29's final inline
  `evaluator.runtime` design;
- intermediate world-readable or world-writable candidate staging fixes
  superseded by PR #31's archive transport.

## Chosen Integration Method

The implementation is a behavioral reconstruction, not a merge of branch tips
or a blind cherry-pick series. Tests and public contracts define the desired
behavior; code is adapted to the current `main` architecture.

This method is required because direct merge-tree analysis reports conflicts in
the evaluator engine, score parser, Codex seed, CLI, runtime, evaluation
identity, execution, reporting, recipes, MiniSWE adapters, and their tests.
Those conflicts reflect competing ownership models rather than formatting
differences.

## Semantic Precedence

1. Current remote `main`, including PR #28, owns the present orchestration API,
   unified `evolve-agent` Skill, reporting model, release structure, and public
   documentation baseline.
2. PR #26 subsumes PR #23. The integration carries each behavior once and does
   not preserve PR #23's removed experiment tooling.
3. PR #29 supplies the evaluation receipt and inline runtime model, adapted to
   the APIs on current `main`.
4. PR #31 is later and authoritative where it overlaps PR #29, specifically for
   effective task selection, candidate source transport, MiniSWE role dispatch,
   session identity, and model-variable ownership.
5. Existing compatibility paths remain readable unless a source PR explicitly
   replaces them with an exact alias or an unverified legacy mode.

## Component Design

### 1. Codex Candidate Binding and Subscription Isolation

The Harbor evaluator passes the candidate-owned target path through
`EVOLVE_CANDIDATE_SOURCE`. The built-in Codex wrapper resolves `codex.toml`,
`prompt.md`, and `skills/` per agent instance from that path. A missing or empty
value falls back to the module root; a non-string value fails before reading
settings. Ambient process state must not select a different candidate.

Protected per-agent arguments from `evaluator/agent.kwargs` are forwarded to
Harbor. In subscription mode, agent-visible OpenAI API key and base URL values
are explicitly shadowed while the parent process remains unchanged. Explicit
agent proxy forwarding remains available.

### 2. Certified Evaluation Receipt

Strict evaluations resolve an immutable receipt from trusted inputs. It binds:

- candidate commit and tree;
- evaluator tree and semantic evaluator configuration;
- resolved dataset contents and effective task members;
- purpose, generation, repetition identities, concurrency, and retry policy;
- resolved runtime and endpoint identity without persisting secrets;
- candidate dependency lock when the candidate declares an isolated runtime;
- framework version and a canonical contract digest.

Evidence is accepted only when it matches this contract. Missing trials,
candidate-owned failures, verifier-owned failures, and infrastructure-owned
failures remain typed and bounded; absent evidence is never silently converted
to a benchmark score. Existing workspaces without authoritative manifests or
runtime receipts use an explicit legacy-unverified path.

### 3. One Authoritative Effective Task Set

An optional task limit is validated before execution and applied to the
deterministic split exactly once. The resulting effective members drive:

- persisted task names and split manifest;
- dataset and task-set identity;
- Harbor include filters and defensive task count;
- expected trials after multiplying by repetitions;
- score coverage and diagnostics;
- host/runtime contract agreement.

The live `EVOLVE_TASK_LIMIT` may override a larger persisted split only through
this effective-selection path. A non-positive or malformed value is rejected.
An empty effective set is a configuration error. A host/runtime mismatch is an
infrastructure failure and produces no benchmark claim. A completed trial with
verifier reward zero remains a valid completed trial.

### 4. Inline Runtime, Authentication, and Proxy Configuration

Public recipes declare a small executable `evaluator.runtime` block instead of
referencing named, host-specific runtime profiles. It may describe a candidate
uv project/Python version and optional proxy routing. Resolved runtime identity
contains only non-secret configuration and digests.

`WORKSPACE/.env` remains the single user-facing environment file. API-key
authentication is the default. An explicit Codex `auth.json` path is supported
without falling back to a home-directory credential. Secrets and raw proxy
values are excluded from receipts and generated public configuration.

Proxy routing is optional and disabled by default. When enabled, download and
runtime preparation traffic may use configured proxies, while the configured
model endpoint is added to `NO_PROXY`/`no_proxy`. Empty agent environment values
must shadow ambient values when isolation requires it.

### 5. Explicit MiniSWE Trust Roles

The two Evolve-owned adapters are named by role:

- `InstalledMiniSweAgent` for trusted installed meta-agent execution;
- `CandidateMiniSweAgent` for evaluator-only candidate source execution.

The previous first-party identifiers remain exact compatibility aliases. Role
detection uses exact predicates for first-party classes; arbitrary Harbor agent
classes do not gain privileges through class-name suffixes.

`EVOLVE_SESSION_ID` is optional. When configured, its literal value is used for
both session metadata and prompt-cache identity. The AHE prompt derives behavior
from the declared mutable surface and does not assume a particular target.

### 6. Runtime-User-Owned Candidate Transport

The reviewed candidate snapshot is packaged into a temporary archive. Archive
paths reject absolute paths, parent traversal, and escaping symlinks. Member
modes are normalized to owner read/write, with execution retained only for
directories and files that were executable in the snapshot. Host source modes
are not changed.

Harbor uploads the archive and extracts it without privilege as the same runtime
user that performs candidate synchronization. The extracted tree is therefore
runtime-user-owned without `chmod 777`, privileged repair, UID assumptions, or
world-writable source. Local temporary archives are removed after upload;
Harbor owns cleanup of uploaded transport artifacts and disposable environments.

### 7. Model Configuration Ownership

`EVOLVE_HARBOR_MODEL` is a provider-qualified Harbor identifier such as
`openai/<model>`. `OPENAI_MODEL` is the convenience input for a bare OpenAI
model name. Evolve does not guess providers for arbitrary bare Harbor values,
and Harbor's original configuration diagnostic remains visible.

## Error Ownership

- Invalid task limits and invalid runtime declarations are configuration
  failures before Harbor starts.
- Unsafe candidate archive content is candidate-invalid.
- Archive upload/extraction and host/runtime selection disagreement are
  infrastructure failures.
- Candidate dependency synchronization retains candidate/runtime diagnostic
  ownership defined by the certified contract.
- Missing or mismatched evidence is incomplete or infrastructure-owned, never a
  fabricated score.
- Invalid provider-qualified model syntax remains caller-owned.

## Test Strategy

Implementation follows regression-first development for each behavior group.
Focused tests must cover:

1. Candidate-local Codex config, prompt, and skills; instance isolation;
   malformed values; protected kwargs; subscription credential shadowing.
2. Contract digest stability and sensitivity for candidate, evaluator, dataset,
   task members, runtime, endpoint, dependency lock, trials, and retry policy.
3. Typed missing/candidate/verifier/infrastructure diagnostics and valid zero
   rewards.
4. Limited deterministic selection for one task, oversized limits, repeated
   trials, identity agreement, and legacy fallbacks.
5. Inline runtime validation, secret-free receipts, API-key and explicit Codex
   authentication, optional proxies, endpoint bypass, and empty-value shadowing.
6. Exact MiniSWE role dispatch, aliases, arbitrary third-party agent behavior,
   optional literal session IDs, and target-neutral AHE prompts.
7. Restrictive `0700`/`0600` candidate sources, safe archive validation,
   unprivileged extraction, preserved host modes, and transport cleanup
   ownership.

The final local gate is:

- full `pytest` suite;
- `ruff check .`;
- `ruff format --check .`;
- `ty check` for the configured source set;
- architecture/coherence tests;
- shell syntax checks for changed scripts;
- `git diff --check origin/main...HEAD`;
- clean tracked worktree status.

## DevBox Qualification

DevBox is the authoritative real-run host. Its existing private environment
files and caches may be used but are never copied into Git. Download and package
preparation may use DevBox's proxies. Before LLM calls, the model endpoint must
be explicitly covered by `NO_PROXY` and `no_proxy`; evidence must confirm the
effective routing without printing credentials or proxy values.

Qualification proceeds only after local gates pass:

1. install/sync the exact integration commit from a bundle or fetched ref;
2. run focused Harbor/Codex/MiniSWE/runtime/evaluation contract tests;
3. run an installed MiniSWE Harbor smoke;
4. run candidate installation from restrictive host modes under the rootless
   cross-user container setup;
5. run a real limited one-task candidate evaluation and verify one selected,
   expected, and completed trial, zero missing trials, no Harbor exception, and
   acceptance of a valid zero reward;
6. run a real model-backed certified AHE smoke with three tasks across genesis
   plus three candidate generations;
7. verify generation tags, certified contract receipts, task members, expected
   trials, archive integrity, and `evolve verify` success;
8. preserve a redacted command/result manifest and artifact path for the PR.

A failed gate blocks publication until diagnosed and fixed. A retry is recorded
with its predecessor rather than replacing failure evidence.

## Publication and Supersession

Immediately before publication, refresh `origin/main`. If it changed, integrate
the new tip and rerun every gate affected by the delta, including DevBox smokes
when runtime or evaluation behavior changed.

Push `codex/semantic-integration-prs-23-26-29-31` and create one draft PR. Its
description includes:

- behavioral traceability from each source PR;
- precedence decisions for overlapping behavior;
- local and DevBox verification results with exact commit SHA;
- explicit proxy-optional and secret-free public guarantees;
- compatibility and migration notes;
- either an explicit statement that no known limitations remain or a concrete
  list of non-blocking limitations with their impact and follow-up owner.

After the draft exists, close PRs #23, #26, #29, and #31 with comments linking
to the superseding PR. Do not close a source PR before the new draft is visible.

## Completion Criteria

The work is complete only when all required behavior is represented by tests,
all local gates pass, the DevBox qualification matrix passes against the exact
published commit, the draft PR is open against current `main`, and all four
source PRs link to it and are closed.
