# GEPA

Use GEPA when per-example outcomes or feedback can support reflective component
mutation and candidates may trade off across tasks.

## Use it when

- The target can be separated into meaningful prompt or skill components.
- Evaluation retains per-example feedback rather than only an aggregate score.
- A small validation batch can cheaply reject unpromising mutations.
- Pareto coverage across tasks is more informative than one scalar ranking.

## Use the shipped capabilities

Run `./evolve operator active . --json` first. The shipped GEPA profile normally
connects a `pareto` select, task rollout, and a `gepa` analyzer for component
reflection, and a `minibatch_improvement` validate stage. Invoke the configured direct stages, read
the parent set, sampled cases, component examples, and validation decision under
`runs/gen-<id>/`, then make the component edit. The configured GEPA
`mutate` is optional when the outer agent owns that edit.

Use `operators/select.py`, the active analyzer implementation, and
`operators/validate.py` only to diagnose the active implementations. When the
process itself is mutable, compare the shipped references at
`library/select/pareto.py`, `library/analyze/gepa.py` (the compatibility
location for the `analyze` stage), and
`library/validate/minibatch_improvement.py`, then adapt the active operator.
Editing a library reference alone does not change a run.

## Apply the method

1. Select a parent using its coverage of per-task Pareto fronts.
2. Run the parent on a sampled optimization minibatch.
3. Convert executions and feedback into reflective examples for each component.
   Read `Feedback.natural_language_feedback` and
   `analyze/feedback.md` as the primary prose signal when the evaluator
   returns one. Treat any binary completion reward as an execution signal, not
   as a quality score.
4. Choose one or more components and propose an evidence-linked mutation. For
   a Skill component, scope the component to its directory so `SKILL.md` and
   bundled references, scripts, assets, and agent metadata evolve together.
5. Run the child on the exact same minibatch and require declared improvement.
6. Evaluate surviving candidates on the canonical gate.
7. Add every eligible result to the population and retain its experience.

## Guard the claim

Component focus is not filesystem permission; keep the mutable surface
explicit. Same-minibatch validation is a proposal filter, not held-out proof.
Use the canonical gate or sealed evaluation for generalization claims.

## Completion check

The parent and child share the exact proposal minibatch; every changed component
has reflective evidence; the proposal decision and canonical evaluation are
recorded separately; and rejected candidates remain in the population record.
