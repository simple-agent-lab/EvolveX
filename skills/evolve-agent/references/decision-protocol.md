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

- A changed target contract, recipe composition, operator selection or
  behavior, configuration semantics, evaluator or scoring semantics,
  partitions, mutable surface, execution or trust boundary, budget, material
  risk, or material unknown invalidates architecture and every downstream
  approval.
- A byte-only implementation change that remains inside the approved
  composition, behavior, configuration semantics, and other architecture
  decisions does not automatically invalidate architecture. It does invalidate
  source and deployment approval because the reviewed and frozen bytes changed.
- Any changed approved source or recipe bytes invalidate source and deployment
  approval, even when architecture remains valid.
- Changed dataset, runtime identity, credentials mode, or preflight input
  invalidates deployment approval. When that deployment input also changes
  evaluation meaning or the execution or trust boundary, it falls under the
  semantic rule above and invalidates architecture as well.
- Changed frozen experiment content requires a new workspace rather than an
  in-place historical rewrite.

Name the stale approval, the changed input, and the checks that must be rerun.

## Resume interrupted authoring

Recover from repository evidence, not conversational memory:

1. Read the recipe `README.md` rationale and current task record, inspect the
   Git status and diff, and note any missing rationale as an unresolved gap.
   Recompute current recipe, operator, evaluator, dataset, and runtime
   identities or digests only from local read-only artifacts. Keep unknown
   external identities explicit rather than probing them during recovery.
2. Reconstruct the architecture, source, and deployment checkpoint bindings.
   Identify the last gate whose recorded inputs and semantics still match the
   current tree.
3. Preserve approved decisions whose bound inputs are unchanged. Do not reopen,
   rewrite, or discard settled work merely because the previous Agent stopped.
4. Rerun inexpensive checks belonging to the current checkpoint: static
   import-safety review, isolated operator describe/check, focused tests, and
   recipe check as applicable, all inside the required isolation boundary.
   Copied command output is history, not current verification.
5. Treat an approval with no durable record as absent. Never infer source or
   deployment approval from a diff, a passing check, or an old chat summary.
6. Continue from the last valid gate. If source approval is absent, prepare a
   fresh source packet after current checks; do not initialize or otherwise
   deploy as part of recovery.

This is source-authoring recovery. Do not invoke initialized-workspace doctor
or repair flows unless the complete workspace marker set exists and the task is
actually workspace recovery.

## Durable decision record

Before source exists, record material decisions in the current task record.
After architecture approval creates a custom recipe, preserve those decisions
in its `README.md`. Each entry names a stable decision id, selected option,
alternatives, recommendation, trade-offs, consequences, reversibility,
unknowns, approval checkpoint, and binding source identity. Record superseding
decisions instead of rewriting history silently.

Do not treat chat text alone as durable approval. Before crossing a checkpoint,
summarize the bound artifacts and capture the user's explicit selection in the
current task record and recipe rationale.
