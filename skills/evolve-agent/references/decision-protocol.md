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

Name the decision and why it matters, then present one focused packet at a
time with all eight fields:

1. **Options:** realistic supported choices, including deferral when valid.
2. **Differences:** concrete quality, cost, time, complexity, security, and
   reproducibility trade-offs between those options.
3. **Recommendation:** the preferred option.
4. **Rationale:** evidence-linked reasons for that recommendation.
5. **Consequences:** files, services, credentials, or experiment state affected.
6. **Reversibility:** whether changing later requires new source approval or a
   new workspace.
7. **Unknowns:** missing evidence and explicit assumptions.
8. **Explicit selection:** the user's choice before work crosses the boundary.

Do not manufacture a false alternative. When only one safe option exists,
explain why the rejected alternatives violate a named contract.

## Approval checkpoints

**Architecture approval** binds to the recorded target, evaluator and scoring
semantics, partitions, recipe, operators, mutable surface, runtime, budget,
risks, and unknowns.

**Source approval** binds to the reviewed Git diff or commit, normalized
operator configurations, recipe-check resolution/normalization/composition
output, separately named static target/surface and evaluator config/schema
checks, focused tests, calibration evidence already available, documented
limitations, and the frozen recipe rationale.

**Deployment approval** binds to the selected recipe, operator, evaluator,
dataset, exact target-seed snapshot, and runtime identities and their recorded
digests, together with the current preflight result. It authorizes
initialization, not unbounded live evaluation spend.

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
- Changed target-seed snapshot, dataset, runtime identity, credentials mode, or
  preflight input invalidates deployment approval. When that deployment input
  also changes evaluation meaning or the execution or trust boundary, it falls
  under the semantic rule above and invalidates architecture as well.
- Any edit to an approved recipe `README.md`, including appending evidence or
  approval text, changes approved recipe bytes and invalidates source and
  deployment approval. A material decision change may require that edit; update
  the rationale, then obtain renewed source approval instead of concealing it
  in a deployment record.
- Changed frozen experiment content requires a new workspace rather than an
  in-place historical rewrite.

Name the stale approval, the changed input, and the checks that must be rerun.

## Resume interrupted authoring

Recover from repository evidence, not conversational memory:

1. Read the frozen recipe `README.md` rationale and the append-only external
   task record or Git notes keyed to its approved source identity. Inspect the
   Git status and diff, and note any missing rationale as an unresolved gap.
   Recompute current recipe, operator, evaluator, dataset, and runtime
   identities or digests only from local read-only artifacts. Keep unknown
   external identities explicit rather than probing them during recovery.
2. Reconstruct the architecture, source, target-seed, and deployment checkpoint
   bindings. Identify the last gate whose recorded inputs and semantics still
   match the current tree and exact vendored target snapshot.
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
After architecture approval creates a custom recipe, preserve the source-bound
decisions in its `README.md`. Each entry names a stable decision id, options,
differences, recommendation, rationale, consequences, reversibility, unknowns,
the user's explicit selection, and the checkpoint it governs. Record a
superseding decision instead of rewriting history silently.

Source approval freezes the recipe rationale with the approved Git identity.
Record that approval event, then write preflight evidence, remediation
authority, deployment approval, and initialization results only to an
append-only external task record or Git note keyed to the immutable approved
identity and excluded from that identity. Do not append them to the recipe
`README.md`. If new evidence changes a material decision, update the rationale
and return to the approval checkpoint invalidated by that source or semantic
change.

Do not treat chat text alone as durable approval. Before crossing a checkpoint,
summarize the bound artifacts and capture the user's explicit selection in the
appropriate durable record without changing an identity that was already
approved.
