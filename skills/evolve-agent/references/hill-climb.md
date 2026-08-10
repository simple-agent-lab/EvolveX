# Hill Climb

Use Hill Climb as the simplest controlled evolution baseline: choose one parent,
propose one bounded child, evaluate both with one frozen evaluator, and accept under
a declared comparison rule.

## Use it when

- The target is narrow and evaluation is affordable.
- One clear lineage and attributable comparison matter more than exploration.
- The experiment needs a control before testing a more complex method.

Do not rely on it when component-specific feedback, competing candidates, or
process evolution is essential to the research question.

## Use the shipped capabilities

Run `./evolve operator list . --json` rather than inferring activation from
files. The shipped Hill Climb profile normally composes `greedy` selection,
task rollout, a `failure_patterns` analyze, and a `hillclimb` gate. Invoke
the configured direct stages and inspect their `runs/gen-<id>/` artifacts before
forming the child hypothesis; let `finalize` apply the gate and record.

Read `operators/<stage>.py` only when a direct invocation or its artifact needs
diagnosis. If the selection or acceptance policy itself must change, compare
the relevant `library/select/` or `library/gate/` variants and adapt the active
operator only after process mutation is explicitly in scope.

## Apply the method

1. Establish a deterministic baseline.
2. Select the current eligible parent.
3. Form one mutation hypothesis from retained evidence.
4. Produce one child inside the mutable surface.
5. Evaluate parent and child under the same task and runtime contract.
6. Apply the predeclared strict-improvement or non-regression rule.
7. Record the child and decision even when it is rejected.

## Inspect evidence

Inspect the selected parent, pre-mutation evidence, hypothesis, patch,
evaluation, acceptance decision, and lineage record. Report Hill Climb as a
single-frontier control rather than broad search.

## Completion check

The parent and child were scored by the same frozen contract; the acceptance
rule was declared before the result; and the evidence, patch, score, decision,
and rejected child remain linked in lineage.
