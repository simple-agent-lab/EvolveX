# Informed decisions and approvals

Use this protocol whenever an experiment choice changes scientific meaning,
trust, cost, source, or frozen workspace content. Recommend a choice, but keep
the decision with the user.

## Material choices

A choice is material when it changes the measurement contract or supported
claims, trust or credential boundary, external spend, source implementation,
or content frozen into an initialized workspace. Examples include evaluator
semantics, data exposure, recipe composition, new operator source, execution
isolation, authentication, deployment, and live model or evaluation spend.

A low-risk mechanical default may be applied without interrupting the user only
when it cannot change those boundaries and is disclosed in the next review.

## Decision packet

Present one focused packet at a time:

1. **Decision:** what must be chosen and why it matters.
2. **Options:** realistic supported choices, including deferral when valid.
3. **Recommendation:** the preferred option and concrete reasons.
4. **Trade-offs:** quality, cost, time, complexity, security, and reproducibility.
5. **Consequences:** files, services, credentials, or experiment state affected.
6. **Reversibility:** whether changing later requires new source or a workspace.
7. **Unknowns:** missing evidence and explicit assumptions.
8. **Selection:** the user's choice before work crosses the boundary.

Do not manufacture a false alternative. When only one safe option exists,
explain why the rejected alternatives violate a named contract.

## Approval checkpoints

**Architecture approval** binds to the recorded target, evaluator, partitions,
recipe, operators, mutable surface, runtime, budget, risks, and unknowns.

**Source approval** binds to the reviewed Git diff or commit, normalized
operator configurations, recipe-check output, focused tests, calibration
evidence already available, and documented limitations.

**Deployment approval** binds to the selected recipe, operator, evaluator,
dataset, and runtime identities and their recorded digests, together with the
current preflight result. It authorizes initialization, not unbounded live
evaluation spend.

## Approval invalidation

- Changed scoring semantics or partitions invalidate architecture and every
  downstream approval.
- Changed operator behavior or recipe source invalidates source and deployment
  approval.
- Changed dataset, runtime identity, credentials mode, or preflight input
  invalidates deployment approval.
- Changed frozen experiment content requires a new workspace rather than an
  in-place historical rewrite.

Name the stale approval, the changed input, and the checks that must be rerun.

## Durable decision record

Record material decisions in the custom recipe `README.md`. Each entry names a
stable decision id, selected option, alternatives, recommendation, trade-offs,
consequences, reversibility, unknowns, approval checkpoint, and binding source
identity. Record superseding decisions instead of rewriting history silently.

Do not treat chat text alone as durable approval. Before crossing a checkpoint,
summarize the bound artifacts and capture the user's explicit selection in the
current task record and recipe rationale.
