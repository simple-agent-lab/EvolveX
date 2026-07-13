# Shared Evaluation and Runtime Hardening Design

**Date:** 2026-07-13

**Status:** Approved design; awaiting written-spec review

**Scope:** Introduce one small framework-owned runtime, evaluation-attempt, and
certification boundary for long-running HyperAgents, AHE, and future recipes.
Recipe-specific search behavior remains in library operators.

## Context

The method-faithful HyperAgents and AHE experiments independently exposed the
same framework defect. Harbor trials exited through LiteLLM's MCP/proxy import
path with `ModuleNotFoundError: No module named 'fastapi'`, but the evaluator
accepted the accompanying verifier reward `0.0` before considering the recorded
exception. The framework consequently archived corrupted evaluations as
`complete` and made them valid parents.

This was not evidence that all evolved children became worse. An unchanged
parent later failed in the same way. The evaluator environment could resolve
differently between trials because each trial performed a fresh `uv run` against
an open-ended dependency declaration and no frozen candidate lock.

The newer AHE run also showed a separate recipe problem: 48 of 51 generations
were `operator_failed`, primarily due to manifest and meta-agent output-contract
violations. That issue must not be confused with the shared evaluation defect.

## Confirmed Root Causes

1. Evaluator and candidate dependencies were not separated into immutable,
   fingerprinted environments.
2. Trial parsing allowed reward presence to override `exception_info`.
3. The Harbor wrapper captured its return code but did not use it in final
   classification.
4. Archive parent eligibility trusted coarse `complete` and `partial` labels
   instead of a framework-certified evaluation result.
5. Harbor cost and complete runtime provenance were not propagated into the
   archive.
6. Nested evaluation processes and containers lacked experiment-level ownership,
   so cancellation could leave detached work behind.
7. HyperAgents' local old/new replay admission was an extra mechanism not found
   in the original paper or official repository. Its synthetic genesis score of
   `1.0`, maximum-over-replay comparison, colliding job names, and cancellation
   behavior made it both incorrect and unnecessarily complex.

## Likely Contributing Causes

- Preflight did not exercise or validate the evaluator entry point and dependency
  imports before the evolution loop.
- Infrastructure failures advanced generations instead of retrying the same
  candidate or pausing the experiment.
- Trial artifacts carried useful exceptions, but no single framework boundary
  assigned their canonical meaning.
- The AHE method's strict, multi-file evidence contract was difficult for the
  meta-agent to satisfy repeatedly. This is a recipe-level reliability problem,
  not a reason to weaken framework certification.

## Goals

1. Make the environment used for a score immutable, reproducible, and visible.
2. Give every trial and evaluation one canonical outcome whose exception
   semantics cannot be overridden by a reward.
3. Permit selection only from framework-certified evaluations.
4. Stop deterministic infrastructure failures before they poison more trials or
   generations.
5. Preserve append-only artifacts, complete provenance, and cost.
6. Make cancellation recursively own all subprocesses and containers.
7. Keep the implementation small enough to understand without a service,
   database, workflow engine, or recipe-specific branches in the driver.
8. Preserve the methodological differences between HyperAgents, AHE, and
   ordinary hill climbing.

## Non-Goals

- Automatically repair evaluator dependencies from inside an experiment.
- Allow a meta-agent to mutate the evaluator, benchmark, certification code, or
  evaluator runtime.
- Turn infrastructure failures into benchmark zeros.
- Make partial evaluations parent-eligible.
- Add general distributed scheduling, artifact storage, or cryptographic signing.
- Normalize HyperAgents and AHE into the same search workflow.
- Repair AHE's method-specific output contract before checking its original paper
  and official implementation for a simple, faithful remedy.

## Minimal Architecture

The shared design has three small responsibilities:

```text
runtime materialization -> evaluation attempt -> certification
        immutable            append-only          one decision
```

They may be implemented as focused modules such as `runtime.py`,
`evaluation.py`, and a small supervisor helper. “Certification” is not a service
or security protocol. It means that framework code has validated the attempt's
identity, runtime fingerprint, expected trials, terminal outcomes, artifacts,
and score eligibility, then emitted one immutable record.

Recipes consume that record. They may choose among certified candidates, but
they cannot reinterpret an invalid evaluation as a valid parent.

## Runtime Boundary

### Evaluator capsule

The evaluator, Harbor adapter, benchmark verifier, and their Python dependencies
form an immutable capsule. Its complete dependency graph is frozen before the
experiment. The capsule fingerprint records at least:

- evaluator image or bundle digest;
- evaluator lock-file hash;
- Python and `uv` versions;
- Harbor and benchmark adapter versions;
- benchmark task-set identity and content hash;
- framework commit and relevant evaluator source hashes.

The capsule is built once, used offline during trials, and never changed in
place. Fixing it creates a new fingerprint.

### Candidate environment

Candidate code runs in a separate environment layered beside, not inside, the
evaluator capsule. Candidate dependencies are immutable by default. A recipe may
explicitly allow the meta-agent to modify both `pyproject.toml` and `uv.lock`.
The two files must be consistent, and materialization uses frozen/offline
resolution.

Dependency changes do not require downloading everything again. `uv` and the
container/build cache reuse content-addressed package artifacts; only uncached or
changed packages need materialization. The resulting candidate bundle and lock
hash become part of the attempt fingerprint.

The framework never performs an ad hoc `pip install` in response to a trial
failure. An undeclared dependency in candidate-owned code is a candidate defect.
An undeclared dependency in evaluator-owned code is an infrastructure defect.

## Preflight and Runtime Certification

Before generation 0, the framework performs a cheap preflight under the exact
capsule that will run the experiment:

1. verify frozen/offline environment materialization;
2. import evaluator-owned entry points and known optional paths used by the
   configured evaluator;
3. start the Harbor/evaluator entry point;
4. execute one inexpensive canary trial;
5. record the successful capsule fingerprint.

The loop cannot begin if preflight fails. A frozen but broken environment is not
certified merely because it is reproducible.

If a deterministic evaluator setup, startup, or import failure appears later,
the framework immediately opens the experiment circuit. It cancels outstanding
trials, records `infrastructure_failed`, does not consume the transient retry
allowance, does not advance the generation, and pauses for repair.

Potentially transient failures, such as worker or network loss, retry the same
candidate and generation. The default is one initial attempt plus two retries.
Each retry has a new attempt identifier and a `retry_of` reference; it is not a
new evolutionary generation.

## Canonical Outcomes

Each trial has exactly one terminal outcome:

| Outcome | Meaning | Reward score-eligible? |
|---|---|---|
| `benchmark_complete` | Benchmark agent and verifier completed without a disqualifying exception | Yes |
| `candidate_invalid` | Candidate-owned source, declaration, startup, or contract made a valid benchmark run impossible | No |
| `infrastructure_failed` | Evaluator, Harbor, worker, model service, container, or framework failed | No |
| `timeout` | A named owner exceeded its deadline | Only when `owner=benchmark_agent` and the benchmark contract defines that timeout as a valid zero |
| `cancelled` | Experiment or parent attempt deliberately stopped the work | No |

Classification always considers exceptions and process return codes before
reward. Reward presence can never erase an exception. A reward is used only when
the canonical outcome and benchmark contract make it score-eligible.

Ownership determines candidate versus infrastructure failure. Failures in the
immutable evaluator before candidate entry are infrastructure failures. Failures
in candidate-owned code or its declared environment are candidate-invalid. When
ownership is genuinely ambiguous, the framework runs one unchanged control under
the same capsule. If the control fails equivalently, the circuit opens as an
infrastructure failure. This diagnostic is exceptional, not a per-child replay.

An evaluation is `benchmark_complete` only when all required task/trial slots
have score-eligible terminal results. Incomplete evidence may be retained as a
diagnostic partial result, but partial evaluations are never selection-eligible.

## Evaluation Attempt and Certificate

One simple framework record carries the decision. It contains:

- experiment, evaluation-epoch, generation, candidate, purpose, and attempt IDs;
- `retry_of`, when applicable;
- evaluator and candidate runtime fingerprints;
- task-set and artifact-index hashes;
- canonical outcome and reason;
- trial vector;
- score only when the required vector is score-eligible;
- `selection_eligible` derived by framework code;
- complete observed cost, including failed and cancelled work;
- start/end timestamps and process/container provenance.

`selection_eligible` is true only for a full framework-certified evaluation in
the current evaluation epoch. It is derived, not supplied by an evaluator or
recipe. Archive code must reject any attempt to mark other rows as valid parents.

The framework reuses AHE's useful `harbor_artifacts.py`, task-vector, task-set
binding, and artifact-hash abstractions. Their outcome semantics are corrected in
place rather than duplicated in a parallel HyperAgents mechanism.

## Identity and Append-Only Evidence

Human-readable paths remain simple while IDs remain globally unambiguous:

```text
experiments/<experiment>/evaluations/epoch-<e>/
  <purpose>/gen-<g>/candidate-<id>/attempt-<a>/
```

Every retry writes a new directory. Existing evidence is never overwritten.
Purpose distinguishes normal candidate evaluation, preflight, canary, control,
and re-certification. HyperAgents-specific replay is not a purpose because that
mechanism is removed.

Artifact indexes reference retained Harbor output and include hashes for
portable evidence. Cost and provenance flow from individual trials to the
attempt certificate and archive without being discarded on failure.

## Evaluation Epochs

Repairing an evaluator capsule changes its fingerprint and begins a new
evaluation epoch:

1. preserve the old archive and attempts as historical evidence;
2. certify the repaired capsule with preflight and canary;
3. re-evaluate the current active parent under the new epoch before continuing;
4. make only current-epoch certified evaluations parent-eligible;
5. lazily re-certify an older archived candidate only if a recipe later
   nominates it; it becomes selectable only after that certification succeeds.

The framework never silently compares old- and new-capsule scores. If the active
parent cannot be certified in the new epoch, the experiment remains paused for
an explicit researcher decision.

## Selection and Recipe Invariants

The framework enforces only these universal rules:

1. Only current-epoch, full, certified evaluations can become selection
   candidates.
2. Recipe gates may choose or reject among valid candidates but cannot certify an
   invalid evaluation.
3. Partial evaluations are diagnostic only and never parent-eligible.
4. Infrastructure failure retries or pauses the same candidate; it never creates
   evolutionary evidence or advances a generation.
5. `operator_failed` is not an evaluation. After three consecutive operator
   failures, following any recipe-owned repair opportunity, the framework pauses
   rather than burning the remaining generation budget.

## Process and Container Ownership

Every subprocess and container receives the experiment and attempt identity.
The supervisor owns a process group for the full attempt and labels containers
with the same identity. Timeout, cancellation, and circuit opening recursively:

1. stop scheduling new trials;
2. terminate the attempt process group;
3. stop/remove owned containers;
4. wait for cleanup and record any cleanup failure;
5. emit the terminal certificate.

The top-level experiment return code reflects a paused or failed terminal state;
it must not report success merely because the driver loop itself exited cleanly.

## Workflow Self-Modification

### HyperAgents

The local old/new replay and non-inferiority admission path is removed rather
than repaired. Neither the [HyperAgents paper](https://arxiv.org/pdf/2603.19461)
nor the [official generate loop](https://github.com/facebookresearch/HyperAgents/blob/main/generate_loop.py)
uses that online gate. The paper's `Improvement@k` is an analysis metric, not
workflow admission.

The faithful flow is:

1. the recipe selects a parent using its HyperAgents policy;
2. the meta-agent produces a complete child across its permitted mutation
   surface;
3. structural validation either accepts the full child or rejects it atomically;
4. the shared framework evaluates the child once and certifies the outcome;
5. a benchmark-complete child enters the archive even if its score is lower;
6. the recipe's parent-selection policy determines future use.

Researchers and meta-agents may see broad task traces, exceptions, costs, and
prior artifacts through context. Visibility does not grant mutation access to
the evaluator, runtime capsule, benchmark, or certification machinery.

### AHE

AHE retains its sequential evidence analysis, attribution, rollback/pivot
behavior, manifests, and evidence-path validation in library operators. Its task
vectors and Harbor artifact indexes become the shared substrate after their
outcome semantics are fixed.

The repeated manifest/schema failures remain an AHE method-level problem. The
first hardening step is the generic consecutive-operator-failure pause. Any
additional repair must be both simple and supported by the original AHE paper or
official repository; otherwise it is omitted. No AHE-specific recovery branch is
added to the framework driver.

## Error Policy Summary

```text
candidate produced
  -> structural/dependency validation fails: candidate_invalid; reject child
  -> evaluation starts
       -> score-eligible terminal vector: certify; archive; recipe may select
       -> transient infrastructure failure: retry same candidate/epoch/generation
       -> deterministic evaluator failure: cancel remainder; open circuit; pause
       -> ambiguous ownership: run one unchanged control, then classify
       -> partial/cancelled: retain evidence; never select
```

## Verification Strategy

The implementation plan must include deterministic tests for:

- exception plus reward `0.0` classifies by exception, not reward;
- nonzero Harbor return codes cannot produce `benchmark_complete`;
- framework-owned missing imports open the circuit immediately;
- candidate-owned missing imports produce `candidate_invalid`;
- transient retries keep generation and candidate identity while changing only
  attempt identity;
- partial evaluations cannot become parents through any recipe gate;
- epoch changes invalidate old parent eligibility and lazily re-certify selected
  candidates;
- costs survive failed, timed-out, and cancelled attempts;
- append-only paths never collide;
- recursive cancellation leaves no owned processes or containers;
- HyperAgents no longer invokes old/new meta-replay;
- AHE task vectors preserve exception outcome and artifact hashes;
- the unchanged HyperAgents and AHE control candidates classify identically
  under the same runtime capsule and task fingerprint.

After unit and integration tests, run a small DevBoxS canary for both recipes
under the same evaluator capsule before starting another long experiment.

## Delivery and Branch Strategy

Development proceeds in the dedicated clean worktree
`.worktrees/framework-hardening` on `codex/framework-hardening`, based on
`c790f6d`. The dirty primary checkout and dirty historical Harbor worktree remain
untouched.

Implementation should first establish the shared runtime/evaluation contract,
then integrate the clean HyperAgents work, then the clean AHE work. Useful AHE
artifact abstractions are reused rather than reimplemented. Recipe-specific
method changes remain separate commits after the shared contract is verified.

## Decisions Explicitly Rejected

- Installing `fastapi` interactively and continuing the same capsule.
- Letting the meta-agent repair evaluator dependencies.
- Logging deterministic infrastructure failure while continuing later trials or
  generations.
- Treating Harbor reward `0.0` as valid when an exception exists.
- Making partial results parents.
- Repairing HyperAgents meta-replay with more replay machinery.
- Re-evaluating the full archive eagerly after an environment repair.
- Solving AHE contract failures with recipe-specific branches in core framework
  code.
