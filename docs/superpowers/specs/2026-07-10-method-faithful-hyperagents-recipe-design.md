# Method-Faithful HyperAgents Recipe Design

**Date:** 2026-07-10

**Status:** Approved for implementation

**Scope:** Replace the current HyperAgents placeholder with a framework-native,
behaviorally faithful implementation of the original HyperAgents generation loop.

## Sources and Method Claim

The canonical method is Zhang et al., [*Hyperagents*](https://arxiv.org/abs/2603.19461),
implemented in the official
[`facebookresearch/HyperAgents`](https://github.com/facebookresearch/HyperAgents)
repository. The defining upstream behavior is visible in
[`generate_loop.py`](https://github.com/facebookresearch/HyperAgents/blob/main/generate_loop.py),
[`run_meta_agent.py`](https://github.com/facebookresearch/HyperAgents/blob/main/run_meta_agent.py),
and
[`utils/gl_utils.py`](https://github.com/facebookresearch/HyperAgents/blob/main/utils/gl_utils.py).

HyperAgents is a self-referential archive search. A selected parent supplies both
the task agent and the meta-agent workflow. The meta-agent may edit the task
agent, itself, or their interaction. A selected descendant runs its modified
meta-agent in the next generation. Valid descendants remain in a branching
archive even when they score below their parents.

## Context

Before this design, the `hyperagents` recipe was only a scaffold: it used the
generic MiniSWE editor, random parent selection, a framework-written feedback
bundle, and a broad operator surface. The method-faithful recipe replaces that
with fixed `score_child_prop` selection, the dedicated HyperAgents meta-agent,
validation and record variants, and the atomic surface `target/**`,
`operators/meta_agent.py`, and `operators/meta_agent.md`.

The replacement should preserve the framework's git-tag lineage, operator
protocol, Harbor evaluator, and append-only archive. It should reproduce the
upstream algorithm wherever those mechanisms already provide an equivalent
representation. It must not introduce a second HyperAgents-specific driver.

## Goals

1. Make the task agent and meta-agent workflow explicit, independently visible,
   and jointly evolvable as one atomic candidate.
2. Activate meta-agent workflow edits in descendants through the existing fresh
   operator process and selected-parent checkout.
3. Reproduce the upstream `score_child_prop` parent selector.
4. Validate the modified task agent and meta-agent externally before evaluation.
5. Preserve every valid scored child as a possible stepping stone; do not turn
   the method into hill climbing.
6. Reproduce upstream staged evaluation: a cheap stage controls whether the
   expensive full evaluation runs.
7. Let method code read all evidence produced during evolution directly through
   `OperatorContext` paths and persist HyperAgents-specific experience through
   its record operator.
8. Run the sealed benchmark only after evolution has ended.

## Non-Goals

- Copy the upstream Docker orchestrator or archive format wholesale.
- Reproduce incidental source layout when the framework has an equivalent
  mechanism.
- Allow parent-selection, validation, gate, record, driver, or evaluator logic
  to evolve in V1.
- Implement upstream's optional editable parent selector in V1.
- Add a general multi-file operator-package system before a recipe requires it.
- Hide ordinary training evidence from research operators.
- Preserve upstream's behavior of invalidating a good parent after a transient
  model-provider or infrastructure failure.
- Claim benchmark validation from deterministic or smoke tests.

## Trust and Mutability Boundary

The candidate has one atomic repository patch with two mutable regions:

```yaml
surface:
  include:
    - target/**
    - operators/meta_agent.py
    - operators/meta_agent.md
  exclude: []
```

- `target/**` is the task agent and its task-facing tools.
- `operators/meta_agent.py` is the meta-agent workflow.
- `operators/meta_agent.md` is its evolvable strategy prompt.

The following remain readable but fixed by the surface contract:

- `operators/select.py`
- `operators/validate.py`
- `operators/gate.py`
- `operators/record.py`
- `evolve.yaml`
- the driver, evaluator, archive integrity code, and admission mechanism

The meta-agent may propose task-agent and workflow changes together, but the
framework never constructs a hybrid descendant. If surface enforcement,
validation, or self-modification admission rejects the proposal, the complete
child is discarded.

## Recipe Composition

The method uses dedicated variants rather than generic operators with small
configuration differences:

```text
library/
├── meta_agent/
│   ├── hyperagents.py
│   └── hyperagents.md
├── select/
│   └── score_child_prop.py
├── validate/
│   └── hyperagents.py
├── gate/
│   └── parent_eligible.py
└── record/
    └── hyperagents.py
```

`hyperagents.py` and `hyperagents.md` are installed as
`operators/meta_agent.py` and `operators/meta_agent.md`. Workspace initialization
gains one generic companion-resource convention: when an active operator variant
has a sibling `<variant>.md`, install it as `operators/<kind>.md`.

Each V1 variant remains a self-contained Python file. Supporting packages or a
general operator-bundle resolver are deferred until real method code cannot stay
clear within this layout.

An illustrative recipe is:

```yaml
experiment:
  id: hyperagents
  max_generations: 8
  budget_usd: 150
  children_per_gen: 1
  mode: driver
  seed: 0

target:
  seed: https://github.com/SWE-agent/mini-swe-agent.git
  harbor_agent: miniswe-source

surface:
  include:
    - target/**
    - operators/meta_agent.py
    - operators/meta_agent.md
  exclude: []

operators:
  select: {variant: score_child_prop, seed: 0}
  rollout: {variant: noop}
  meta_agent: {variant: hyperagents, timeout_s: 21600}
  validate: {variant: hyperagents, timeout_s: 300}
  gate: {variant: parent_eligible}
  record: {variant: hyperagents}
  timeout_s: 600

evaluator:
  engine: harbor
  dataset: swe-bench-lite
  agent: target.harbor_agent:MiniSweSourceAgent
  sampling: static
  tasks_per_round: 16
  stage: {tasks: 4, proceed_if: positive}
  k: 1
  n_concurrent: 16
  partial_floor: 0.8
  anchor: {final: true, every_rounds: 0}
```

`rollout` is `noop` because the selected meta-agent reads prior experiment
artifacts directly. HyperAgents does not need the framework's current
failure-focused rollout or a framework-authored feedback narrative.

## Generation Flow

1. Evaluate generation zero so the initial task agent is a real scored archive
   candidate.
2. Select one valid scored parent with `score_child_prop`.
3. Fork the complete parent tag into an isolated child checkout.
4. Run the meta-agent inherited from that parent in a fresh Python process.
5. Give it the checkout, remaining-iteration budget, archive path, prior run
   directories, and current run directory through `OperatorContext`.
6. Let it edit the task agent, the meta-agent workflow and prompt, or their
   shared interaction.
7. Capture the complete diff. A missing or empty diff ends as `no_proposal`.
8. Enforce the mutable surface before executing any post-proposal recipe code.
9. Run the fixed HyperAgents validator against the complete candidate.
10. If the workflow changed, run frozen self-modification admission. A rejection
    discards the complete candidate rather than reverting only workflow files.
11. Commit and tag the atomic child.
12. Run staged evaluation. If every staged domain score is positive, run the full
    evaluation; otherwise retain the staged score without running the full set.
13. Apply the parent-eligibility gate: every successfully evaluated child with a
    numeric score is a valid parent.
14. Persist the terminal result and HyperAgents experience record.
15. If this child is selected later, its edited meta-agent is loaded by the fresh
    operator process and governs the next proposal.

There is no same-generation hot reload. Generation `N` uses workflow `W_N` to
propose `W_(N+1)` and task agent `A_(N+1)`. A selected descendant starts a fresh
process that loads `W_(N+1)`. This matches the original method.

## Parent Selection

Selection has one validity predicate and one weighting rule:

> A child is selectable when it has a nonempty in-surface patch, passes external
> validation and admission, and receives a numeric research-evaluation score.

The child does not need to improve on its parent. A valid zero staged score
remains selectable. Failures may remain recorded, but they are not selection
candidates.

For each valid scored candidate `i`, reproduce upstream
`score_child_prop`:

```text
midpoint_i-independent = mean(top three candidate scores)
score_weight_i = 1 / (1 + exp(-10 * (score_i - midpoint)))
child_penalty_i = exp(-((direct_child_count_i / 8) ** 3))
weight_i = score_weight_i * child_penalty_i
```

`score_i` is the full research score when full evaluation ran and the staged
score otherwise. A multi-domain profile averages its available per-domain
selection scores before applying the weighting rule; the V1 Harbor profile has
one domain.

When fewer than three candidates exist, the midpoint is the mean of all
candidates. Direct-child counts derive from archive parent links and include all
recorded child attempts, matching upstream bookkeeping. Normalize positive
weights and sample with `ctx.rng`; fall back to uniform weights only when their
sum is zero.

The default selector is fixed. Upstream's optional self-editing
`select_next_parent.py` becomes a later explicit recipe variant rather than an
implicit V1 capability.

## External Validation

Add a generic optional operator kind:

```python
class ValidateOperator(ABC):
    def validate(self, checkout: Path, ctx: OperatorContext) -> ValidateResult: ...

@dataclass(frozen=True)
class ValidateResult:
    accept: bool
    reason: str
    artifacts: list[str]
```

The driver runs `validate` after the meta-agent and surface check but before
commit and evaluation. `library/validate/hyperagents.py` performs the upstream
equivalent of importing the modified `MetaAgent` and `TaskAgent`, adapted to the
actual MiniSWE/Harbor entrypoints. It writes structured results and captured
output under `runs/gen-N/validate/`.

`validate` is fixed by the recipe surface. A rejected validation records the
attempt and discards the whole child. Validation policy lives in the library
variant; the driver knows only the generic lifecycle hook and result contract.

## Atomic Self-Modification Admission

The framework's existing external `meta_eval` is an intentional safety extension
beyond upstream HyperAgents. It remains frozen and applies when
`operators/meta_agent.py` or its prompt changes.

Current partial reversion is removed. A failed admission does not keep task-agent
edits while reverting workflow edits, because that would create a descendant the
meta-agent never proposed. Admission accepts or rejects the complete combined
candidate.

## Evidence, Records, and Sealed Evaluation

Retire automatic `write_feedback_bundle()`. The framework should not decide that
attempt summaries, falsification prose, or a last-accepted diff are universally
relevant.

Operators already receive the capabilities needed to inspect experiment state:

- `ctx.workspace` for the append-only archive and all prior run directories;
- `ctx.checkout` for the selected parent candidate;
- `ctx.run_dir` for current-generation artifacts;
- `ctx.parent`, `ctx.genid`, configuration, budget context, and deterministic
  randomness.

The HyperAgents meta-agent chooses which prior scores, patches, trajectories,
logs, and failures to place in its own context. `record/hyperagents.py` writes a
compact `experience.json` that references existing artifacts rather than
duplicating large traces or diffs. Archive rows keep searchable scalar fields and
the experience-record path; child counts remain derived data.

Every attempted generation receives a framework terminal status. The fixed
record operator then runs once as a best-effort terminal finalizer, including for
failed attempts. A record failure is annotated without replacing the primary
outcome or making an otherwise valid candidate invalid.

All evidence generated during evolution is readable by research operators. No
per-artifact visibility system is introduced. The sealed final benchmark is
protected by lifecycle instead: it is not run until evolution ends, and no later
mutation may consume its outputs. Credentials and evaluator secrets remain
outside experiment artifacts.

## Failure Semantics

Failure handling does not complicate selection: failed attempts are recorded and
excluded from the valid-parent set.

A transient timeout, provider error, or evaluation infrastructure failure does
not invalidate the selected parent. A parent becomes invalid only when fixed
preflight proves that its inherited meta-agent workflow is deterministically
unloadable or uncompilable. A candidate that introduces a broken workflow or
task agent invalidates only that candidate.

This deliberately improves on upstream behavior, which can mark a parent invalid
after a failed meta-agent process, while preserving the algorithmic selection and
self-improvement semantics.

## Generic Framework Changes

The implementation requires only method-neutral mechanism changes:

1. Register the optional `validate` operator contract and execute it between the
   surface check and commit.
2. Replace partial workflow reversion with atomic full-child rejection.
3. Add optional staged evaluation to the frozen evaluator pipeline.
4. Retire automatic `write_feedback_bundle()` and let operators inspect paths in
   `OperatorContext`.
5. Run the fixed record operator once after every terminal generation outcome.
6. Install a sibling Markdown companion for an active operator variant.
7. Evaluate generation zero through the real configured evaluator rather than
   treating its scaffold score as benchmark evidence.
8. Ensure the final sealed anchor runs only after the evolutionary loop and
   cannot feed another proposal.

None of these changes embeds HyperAgents selection, prompting, compilation
commands, or record fields in the driver.

## Verification and Release Conditions

Deterministic tests must establish:

1. **Next-generation activation:** an edited meta-agent affects a selected
   descendant, not the generation currently executing it.
2. **Atomic rejection:** rejected workflow admission retains neither workflow nor
   task-agent edits.
3. **External validation:** a broken meta-agent or task agent never becomes a
   valid parent.
4. **Upstream selection:** fixed scores and child counts produce the exact
   `score_child_prop` weights and only valid scored nodes can be sampled.
5. **Staged evaluation:** zero skips full evaluation but remains a valid scored
   candidate; positive proceeds to the full set.
6. **Evidence lifecycle:** in-loop artifacts are readable, automatic feedback is
   absent, and the sealed result cannot influence a later generation.
7. **Terminal recording:** unsuccessful attempts retain their primary status and
   method record when recording succeeds.

A real Harbor smoke run must demonstrate:

```text
select parent
-> run inherited meta-agent
-> produce nonempty atomic patch
-> validate both agents
-> receive a staged or full score
-> record a selectable descendant
```

The recipe reaches `method-faithful` after these defining tests and the live
candidate smoke pass. It reaches `benchmark-validated` only after a documented
comparison against the V1 hill-climb control under a shared benchmark profile
and budget.

The worktree baseline has one accepted pre-existing failure:
`tests/test_coherence.py::test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback`
expects the string `hyperagents-smoke` in public documentation. HyperAgents work
must introduce no additional failures and should resolve that expectation when
the smoke scaffold is named.
