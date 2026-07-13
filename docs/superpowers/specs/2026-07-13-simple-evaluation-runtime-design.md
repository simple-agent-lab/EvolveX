# Simple Evaluation Runtime Design

**Status:** Approved in discussion on 2026-07-13.  This document supersedes
the package-manager and certificate-lifecycle parts of the earlier shared
runtime and MiniSWE smoke designs where they conflict with this design.

## Problem

The framework currently contains useful hardening components, but they do not
form one authoritative lifecycle.  In particular:

- normal evaluation still uses legacy `complete`/`partial` parent rules while
  an unused certificate path defines stricter rules;
- MiniSWE dependency policy is hard-coded into shared framework code;
- smoke runs against a live directory, which can contain ignored files that
  are absent from the Git object later evaluated;
- smoke replaces actionable errors such as a missing Python module with a
  coarse category;
- generation zero can retain a synthetic selectable score after its real
  evaluation fails; and
- retry, attempt identity, and archive readers are only partly connected.

The failed MiniSWE experiment demonstrated the live-directory mismatch.  Its
`uv.lock` existed in the workspace but was ignored by Git, so it was absent
from `gen/0` and from the detached Harbor checkout.  The run failed with
`lock_missing` before dependency materialization or the FastAPI import.

## Design Goal

Keep one readable lifecycle:

```text
meta-agent edits candidate
        -> optional smoke of the committable snapshot
        -> commit candidate
        -> evaluate the exact commit
        -> append one evaluation record per attempt
        -> ArchiveView exposes certified parents
```

The framework owns honest evidence and selection validity.  The candidate and
meta-agent own environment repair.

## Non-Goals

The shared framework will not:

- understand UV, pip, Poetry, npm, Cargo, Docker, or their dependency files;
- generate or repair candidate locks;
- install candidate dependencies on behalf of the meta-agent;
- parse arbitrary tracebacks into a complete error taxonomy;
- provide a generalized retry or circuit-breaker subsystem; or
- change HyperAgents or AHE method behavior to compensate for a broken
  runtime.

## Responsibility Boundary

### Framework

The framework:

- creates smoke snapshots and candidate commits with the same Git-tree helper;
- invokes an immutable evaluator-provided smoke command;
- captures useful, credential-redacted stdout and stderr;
- evaluates an exact candidate commit;
- classifies each trial exception before considering its reward;
- appends the canonical evaluation record; and
- permits selection only from valid benchmark-complete candidate records.

### Candidate and meta-agent

The meta-agent may inspect errors, edit any file inside the configured mutable
candidate surface, and use ordinary shell tools.  It chooses how to repair the
candidate environment.  For a UV-based MiniSWE target, for example, it may
edit `pyproject.toml`, run `uv lock`, and rerun smoke.  Another target may use
a different tool without shared-framework changes.

The evaluator and smoke machinery remain outside the mutable surface.  A
candidate cannot turn a failed evaluation into a valid record by changing the
judge.

## 1. Exact Candidate Snapshot

One helper constructs a temporary Git tree using the same surface and Git
rules as candidate commit.  It uses a temporary index and never stages or
modifies the user's real index.

The snapshot:

- includes tracked changes and ordinary untracked files;
- excludes ignored untracked files, just as the final commit does;
- rejects paths outside the mutable surface; and
- is materialized in a detached temporary checkout for smoke.

The candidate commit is created from the same tree-building helper.  This
prevents smoke from observing files that evaluation cannot observe.  Smoke
records its tree hash; because smoke is optional, later edits may make that
result stale, and final evaluation of the exact candidate commit remains
authoritative.

The framework does not force-add package-manager-specific files.  A required
file must be tracked or made trackable by the candidate.  Raw smoke output and
ordinary tools such as `git status` and `git check-ignore` give the meta-agent
enough information to diagnose an ignored file.

## 2. Protected Candidate Smoke

`./evolve candidate-smoke --full` remains the single supported spelling.  It:

1. creates the committable snapshot;
2. runs the immutable evaluator-provided smoke command from that snapshot;
3. captures stdout, stderr, exit code, duration, and snapshot tree hash; and
4. writes a new append-only attempt directory.

The immutable entry point is `evaluator/smoke.sh`.  If it is absent, the CLI
reports that smoke is unsupported and does not fall back to a full evaluation.
MiniSWE can implement the script with one Harbor install-only task and
initialize its real model path.  Other evaluators may do something different.
The shared runner does not inspect the package manager.

Each attempt contains:

```text
result.json
stdout.log
stderr.log
```

`result.json` contains only generic execution facts and artifact paths.  The
logs preserve command output and tracebacks, with credential values, proxy
userinfo, and common token forms redacted.  The CLI prints a bounded redacted
stderr tail and the paths to the complete logs.  Raw diagnostic text is not
used for selection classification.

Smoke is optional diagnostic evidence.  It never creates a score or a parent.
Normal evaluation repeats the actual setup path and remains authoritative.

## 3. One Evaluation Record

The current parallel `EvaluationResult` and `EvaluationCertificate` paths are
replaced by one `EvaluationRecord` used by the driver, archive, selectors, and
reports.

It contains:

- experiment, generation, candidate commit, purpose, and attempt;
- evaluator, task-set, and runtime fingerprints;
- canonical outcome and nullable score;
- structured per-trial evidence;
- cost and duration; and
- paths and hashes for retained artifacts.

There is one append-only record per attempt.  A recipe gate writes a separate
verdict event that references the record identity; it cannot replace the
record's outcome, score, or evidence.  No gate or archive merge step
recomputes evaluation validity.

### Trial and aggregate outcomes

The five outcomes are:

- `benchmark_complete`
- `candidate_invalid`
- `infrastructure_failed`
- `timeout`
- `cancelled`

An exception is processed before any verifier reward.  Structured ownership
from the immutable evaluator determines whether an exception is candidate- or
infrastructure-owned.  Unknown ownership is treated as infrastructure failure
for selection safety; raw logs remain available for diagnosis.

Aggregate precedence is deliberately small:

1. an infrastructure-owned failure, or missing required evidence without a
   structured candidate-wide failure, makes the attempt
   `infrastructure_failed`;
2. otherwise, a candidate-owned trial or candidate-wide setup failure makes
   it `candidate_invalid`;
3. otherwise, cancellation makes it `cancelled`;
4. otherwise, an explicit non-scoreable timeout makes it `timeout`;
5. only a complete set of scoreable trials makes it `benchmark_complete`.

Reward presence never overrides an exception.  Partial evidence may retain
individual rewards for diagnosis, but the aggregate score is null.

A benchmark may explicitly declare an agent-task timeout to be a legitimate
zero-score trial.  Without that explicit evaluator rule, a timeout is not
scoreable.

## 4. Genesis and Retry

Generation zero starts as `pending`, with no score and no parent eligibility.
The exact committed `gen/0` object must be evaluated before evolution begins.

- `benchmark_complete`: generation zero becomes selectable.
- `infrastructure_failed`: retry the same object once as attempt 2.
- a second infrastructure failure: pause the experiment.
- any other failure: stop and repair the seed.

There is no synthetic genesis score.

For later candidates, an infrastructure failure receives the same single
retry without advancing the generation.  A candidate-invalid result is not
automatically retried: it remains visible, the previous valid parent remains
selectable, and the next meta-agent receives the failed candidate's diagnostic
artifacts.

This is the complete retry policy.  No general retry engine or failure-count
state machine is introduced.

## 5. Archive and Selection

`ArchiveView` is the only supported archive reader for operators, reports, and
meta-agent context.

It exposes a parent only when the canonical record is:

- `benchmark_complete`;
- for purpose `candidate` or the real genesis evaluation;
- from the experiment's fixed evaluator, task-set, and runtime identity; and
- not subsequently rejected by a recipe gate.

Partial, candidate-invalid, infrastructure-failed, timeout, cancelled, smoke,
and canary records are never parents.  Recipe gates may reject a valid
candidate but may not promote an invalid evaluation.

Attempt history and failed-candidate artifacts remain visible.  A successful
retry becomes the generation's canonical evaluation while the earlier failed
attempt remains append-only evidence.

## 6. Runtime Ownership

Evaluation and smoke operate only in detached temporary checkouts.  The root
workspace and evaluator-owned `target/harbor_agent.py` are never execution
scratch space.  Existing process-group termination is retained and applied to
the evaluator subprocess so cancellation reaches nested work owned by the
attempt.  Evaluators receive the attempt identity and remain responsible for
external resources they launch.  The MiniSWE evaluator cleans only Harbor
containers carrying its attempt identity; the shared framework does not
become a general container manager.

The generated `./evolve` console uses the pinned framework interpreter.  It
must not silently fall back to a system Python that lacks framework
dependencies.  Candidate package-manager neutrality does not require the
framework itself to have an unfrozen runtime.

## MiniSWE Seed Repair

The shared framework does not special-case MiniSWE dependency files.  Before
the next experiment, create fresh recipe-specific seeds that:

- add FastAPI to the seed `pyproject.toml`;
- generate the matching `uv.lock`;
- ensure the seed `.gitignore` does not exclude the lock; and
- commit both dependency files.

Evaluation validates behavior through frozen MiniSWE setup but never
regenerates the lock.  Later dependency changes are made by the meta-agent and
are ordinary candidate changes.

The failed DevBoxS experiments remain immutable evidence and are not repaired
in place.

## Minimal Verification

Focused tests cover only the critical vertical path:

1. an ignored required file is absent from the committable snapshot and smoke
   exposes the useful redacted failure;
2. a failed real genesis evaluation cannot leave generation zero selectable;
3. an exception plus numeric reward is scoreless;
4. candidate-owned failed trials remain candidate-invalid in aggregate;
5. `ArchiveView.valid_parents()` exposes only benchmark-complete records;
6. infrastructure failure retries the same candidate once; and
7. diagnostic logs retain useful errors without credential values.

After focused tests, run the existing full local suite.  Remote validation is
strictly staged:

1. one DevBoxS MiniSWE full smoke;
2. one one-task normal evaluation of the same exact candidate commit; and
3. only after both pass, consider another small comparative experiment.

No held-out evaluation runs unless a non-seed generated candidate has a valid
benchmark-complete training evaluation.

## Reuse and Removal

Keep and connect:

- exception-first Harbor parsing and structured trial artifacts;
- task vectors, costs, and provenance;
- attempt identities and evaluation receipts;
- `ArchiveView`;
- shared cache and proxy handling inside the MiniSWE evaluator;
- AHE evidence/manifests and method-faithful recipe operators; and
- HyperAgents' method-faithful operators and removal of unsupported replay.

Remove or refactor:

- UV-specific validation from shared `candidate_runtime.py`;
- framework rules requiring `pyproject.toml` and `uv.lock`;
- quick/container smoke variants;
- the unused parallel certificate path;
- synthetic genesis scores;
- legacy `complete`/`partial` parent eligibility; and
- destructive reuse of evaluation directories.

## Branch Strategy

Continue only in the dedicated `codex/framework-hardening` worktree.  Preserve
the primary checkout, both recipe worktrees, the historical Harbor worktree,
and unrelated SDD report modifications.  Do not push without explicit
approval.

## Acceptance Criteria

The design is complete when one real DevBoxS candidate demonstrates this
straight-line behavior:

```text
exact snapshot -> useful smoke evidence -> exact-commit evaluation
               -> one canonical record -> certified-only selection
```

A candidate/runtime exception must be scoreless, a failed genesis must be
unselectable, and the meta-agent must be able to read enough raw evidence to
repair an unfamiliar environment failure without shared-framework knowledge
of its package manager.
