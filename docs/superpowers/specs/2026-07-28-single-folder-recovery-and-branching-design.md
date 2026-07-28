# Single-Folder Recovery and Evolutionary Branching Design

**Date:** 2026-07-28

## Goal

Make interrupted experiments resume safely from the experiment folder and let
an operator branch future evolution from any certified prior candidate.

The implementation must remain small. The experiment folder is the durable,
authoritative state; this feature does not add a backup service, historical
folder snapshots, or a general workflow engine.

## Reliability Boundary

The design assumes the experiment folder survives controller, operator,
container, and host-process failures. A run may be resumed from the same folder
or from a filesystem-level copy of it.

Destruction or corruption of the experiment folder is outside the initial
guarantee. Operators may protect the folder with ordinary infrastructure such
as filesystem snapshots or `rsync`, but `evolve` will not manage those copies.

## Definitions

- A **completed generation** has mechanism-certified terminal archive state and
  no pending gate/record work.
- A **certified parent** satisfies the existing `ArchiveView.valid_parents()`
  rules, including its Git tag, evaluation receipt, evaluation identity,
  selection eligibility, and completed gate/record decision.
- An **unfinished generation** has no terminal mechanism state, or has a
  completed evaluation whose gate/record step remains pending.
- **Recovery** resumes an interrupted run inside one durable experiment folder.
- **Rollback** is non-destructive branching: a prior certified generation
  becomes the parent of new candidates. It never removes later history.

## Invariants

1. Completed generations are immutable during recovery.
2. In-flight work before a candidate tag is disposable and may be rerun.
3. Once `gen/N` exists, recovery never reruns parent selection for that
   candidate.
4. Git and the certified archive must agree. Recovery refuses ambiguous or
   contradictory state rather than guessing.
5. Incomplete operator or evaluation artifacts are never treated as
   authoritative merely because files exist.
6. Branching preserves all existing tags, archive events, receipts, and
   artifacts.
7. Recovery and branching run under the existing exclusive workspace lock.

## Automatic Recovery

`evolve run` performs safe recovery checks before starting normal evolution.
The explicit `evolve doctor` command continues to expose the same diagnosis and
safe cleanup behavior for operators.

### Candidate not tagged

If an unfinished generation has no `gen/N` tag, recovery:

1. Removes its exact stale child worktree and prunes Git worktree metadata.
2. Clears the exact per-generation operator output directory so stale output
   cannot satisfy a later operator invocation.
3. Reruns the generation through the normal driver.

No completed-generation directory or archive event is changed.

### Candidate tagged but lineage event missing

Candidate snapshot creation currently has a crash window between creating
`gen/N` and appending its lineage event. When that state is found, recovery:

1. Reads the tagged candidate commit's direct Git parent.
2. Resolves that commit to exactly one certified `gen/P` parent.
3. Recomputes the candidate's mutated paths from `gen/P..gen/N`.
4. Applies the existing mutable-surface checks.
5. Appends the missing lineage event through the normal archive mechanism.

Recovery stops with a precise error if no certified parent matches, multiple
generation tags make the parent ambiguous, or the reconstructed candidate
violates normal invariants.

### Evaluation interrupted

An incomplete evaluation attempt remains non-authoritative. Resume starts a
new attempt using the existing monotonically increasing attempt directories.
It does not reuse a partial score or partial task vector as a completed result.
Existing mechanism-certified evaluation lifecycle records remain authoritative.

### Evaluation completed but gate/record pending

The current `pending_gate_record` mechanism remains the durable boundary.
Resume runs only the missing gate/record work and then continues normally.

### Terminal failed generation

A mechanism-certified terminal failure is historical evidence, not interrupted
state, so automatic recovery does not erase or silently retry it. The operator
may branch future evolution from an earlier certified parent.

## Non-Destructive Branching

The public interface is:

```text
evolve run <workspace> --from-generation N
```

`--from-generation N` requires `gen/N` to be a certified parent. It applies to
the first wholly unused numeric generation and forces all children in that
generation to use `gen/N` as their parent. Subsequent generations return to the
configured selection operator.

Branching uses a small durable intent file outside per-generation disposable
operator directories. The intent records:

- schema version;
- source generation and tag;
- target numeric generation and target child genids;
- source candidate commit;
- creation time.

The file is written with temporary-file-plus-rename semantics before any branch
operator begins. This makes the forced parent stable across process failure.

If a matching intent already exists, `run --from-generation N` resumes it. A
conflicting `--from-generation` request fails without modifying the workspace.
Creating a new branch intent is refused while an unrelated unfinished
generation exists; normal recovery must finish that generation first.

The intent remains active until every target child genid reaches mechanism
terminal state. A tagged child must record `N` as its parent. Once the target
generation is terminal, the intent is atomically marked consumed or removed.
A restart during this transition is idempotent: terminal archive state wins,
and recovery finishes consuming the intent.

The next numeric generation is greater than every generation number already
present in either Git tags or archive events. Branching therefore never reuses a
genid and never hides the history created after the selected parent.

## Commands and Scope

The command surface remains:

```text
evolve run <workspace>
evolve run <workspace> --from-generation N
evolve doctor <workspace>
```

No `checkpoint`, `snapshot`, `recover`, backup-retention, or remote-storage
command is added. The existing accepted no-op `--resume` remains compatible;
resume continues to be the default.

## Errors and Observability

Recovery errors identify the generation, the conflicting Git/archive evidence,
and the safe operator action. The driver must not convert a recovery invariant
violation into an `operator_failed` generation.

Progress output distinguishes:

- stale untagged work discarded and rerun;
- tagged candidate lineage reconstructed;
- evaluation restarted as a new attempt;
- pending gate/record resumed;
- forced-parent branch intent created, resumed, or consumed.

`evolve doctor` reports an active branch intent and any tagged candidate that
needs lineage reconstruction.

## Testing

Tests inject interruption at each durable boundary and then invoke the ordinary
driver:

1. Before candidate tagging: stale work and stale operator output are discarded
   and the generation reruns.
2. After tagging but before lineage append: the parent and mutation metadata are
   reconstructed from Git without rerunning selection.
3. During evaluation: resume creates a new non-conflicting attempt and ignores
   incomplete output.
4. After evaluation but before gate/record: only gate/record resumes.
5. Before a forced-parent candidate is tagged: branch intent survives restart
   and the selected parent does not change.
6. After a forced-parent candidate is tagged: lineage records the forced parent
   and the intent is consumed idempotently.
7. Multi-child branching: every child in the target generation uses the forced
   parent, including across a partial interruption.
8. Conflicting branch requests and Git/archive contradictions fail without
   changing completed state.

Every interruption test snapshots the completed-generation tags, merged archive
rows, receipt file, and completed artifact paths before recovery and asserts
that they remain unchanged afterward.

## Non-Goals

- Recovering a destroyed or corrupted experiment folder.
- Copying experiments to another disk or machine.
- Resuming inside an individual rollout or operator invocation.
- Reusing incomplete evaluation results as certified evidence.
- Destructively truncating history to make later generations disappear.
- Changing normal selection after the first forced-parent branch generation.
