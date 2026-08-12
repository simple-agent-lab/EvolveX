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

All eight fields are required. Omission of any one makes the packet incomplete;
do not treat an otherwise strong `8/10` packet as approval-ready or cross the
boundary without recommendation, rationale, or explicit selection.

Do not manufacture a false alternative. When only one safe option exists,
explain why the rejected alternatives violate a named contract.

## Approval checkpoints

**Architecture approval** binds to the recorded target, evaluator and scoring
semantics, partitions, recipe, operators, mutable surface, runtime, budget,
risks, and unknowns.

**Source approval** binds either to a clean commit or a complete source-tree
manifest/digest naming its base and covering staged, unstaged, untracked,
ignored, and excluded paths. It also binds a digest of the complete packet:
normalized operator configurations, narrowly scoped recipe-check output,
target-digest-bound static target/surface evidence, evaluator config/schema
checks, focused tests, calibration evidence, limitations, and frozen rationale.
The approval event is authoritative only when immutable or append-only and hash
chained with approver identity, timestamp/event id, predecessor, and source and
packet identities.

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
- Any target byte or layout change invalidates target-digest-bound target or
  surface checks and therefore their source approval, even when the recipe is
  unchanged. Rerun those checks for the new target digest. Reopen architecture
  when the target behavior, layout contract, or another semantic input changed.
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

1. Read the frozen recipe `README.md` rationale and authoritative external
   approval chain. Validate every event id, timestamp, approver identity,
   predecessor hash, source identity, and packet digest back to its immutable
   anchor. Treat an ordinary Git note only as a pointer or mirror unless that
   chain externally anchors it. Inspect Git status and diff, and note any
   missing rationale as unresolved. Recompute current recipe, operator, target,
   evaluator, dataset, and runtime identities only from local read-only
   artifacts. Keep unknown external identities explicit rather than probing.
2. Reconstruct the architecture, source, target-seed, and deployment checkpoint
   bindings. Identify the last gate whose recorded inputs and semantics still
   match the current tree and exact vendored target snapshot.
3. Preserve approved decisions whose bound inputs are unchanged. Do not reopen,
   rewrite, or discard settled work merely because the previous Agent stopped.
4. Rerun inexpensive checks belonging to the current checkpoint: static
   import-safety review, isolated operator describe/check, focused tests, and
   recipe check as applicable, all inside the required isolation boundary.
   Copied command output is history, not current verification.
5. Treat an approval with no valid authoritative hash-chained event as absent.
   Never infer source or deployment approval from a Git note, diff, passing
   check, or old chat summary.
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

Source approval freezes the recipe rationale with its clean commit or complete
source-tree identity and packet digest. Record that approval, then preflight
evidence, remediation authority, deployment approval, and initialization
results only as immutable or append-only hash-chained external events excluded
from the source identity. Each event names approver or actor identity,
timestamp/event id, predecessor, and bound source/packet identities. An
ordinary Git note may mirror or point to an externally anchored event but is
not authority alone. Do not append these events to recipe `README.md`. If new
evidence changes a material decision or target-bound evidence, return to the
invalidated approval checkpoint.

Do not treat chat text alone as durable approval. Before crossing a checkpoint,
summarize the bound artifacts and capture the user's explicit selection in the
appropriate durable record without changing an identity that was already
approved.
