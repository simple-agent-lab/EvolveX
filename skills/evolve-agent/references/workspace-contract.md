# Evolution workspace contract

Use one workspace and one operating contract for every evolution method. The
workspace is both the experiment record and the stable interface through which
an agent invokes the framework's existing capabilities.

## Contents

- [Layout and ownership](#layout-and-ownership)
- [Create a workspace](#create-a-workspace)
- [Orient in an existing workspace](#orient-in-an-existing-workspace)
- [Choose a control path](#choose-a-control-path)
- [Run an agent-led generation](#run-an-agent-led-generation)
- [Use operator capabilities progressively](#use-operator-capabilities-progressively)
- [Change the evolution process](#change-the-evolution-process)
- [Recover and verify](#recover-and-verify)
- [Completion contract](#completion-contract)

## Layout and ownership

```text
workspace/
├── target/                 mutable candidate under study
├── evaluator/              frozen scoring contract and assets
├── operators/              active evolution-stage implementations
├── library/                reference implementations available for adaptation
├── runs/                   immutable per-generation execution evidence
├── artifacts/
│   ├── user/               durable user-supplied context
│   └── generations/        durable generation-scoped handoffs
├── skills/evolve-agent/    this operating and method guidance
├── evolve.yaml             experiment and active-operator configuration
├── program.md              loop orchestration guidance
├── archive.jsonl           append-only generation record
└── best_ever.json          mechanism-derived champion record
```

| Area | Owner | Rule |
| --- | --- | --- |
| `target/` | meta agent or outer agent | Change only inside the mutable surface. |
| `evaluator/` | frozen evaluation side | Never let candidate or mutation code edit it. |
| `operators/` | active method | Change only when process evolution is declared. |
| `library/` | framework or researcher | Consult or adapt; these files do not run directly. |
| `runs/` | execution mechanism | Retain raw evidence; never rewrite a decision. |
| `artifacts/user/` | user | Treat as context, not evaluator proof. |
| `artifacts/generations/` | current generation | Write only in that generation's namespace. |
| `archive.jsonl`, `best_ever.json` | lineage mechanism | Never hand-edit; derive from stamped evidence. |

Use the same stage vocabulary across methods:

```text
select → rollout → trace_analyzer → meta_agent
       → validate → novelty → gate → record
```

A method may omit a stage, but method-specific evidence remains under
`runs/gen-<id>/<stage>/` rather than creating another workspace layout.

## Create a workspace

Initialize a new experiment from the framework install, then do all later work
through the vendored `./evolve` console inside the generated workspace:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable evaluator runtime digest>"
evolve preflight <workspace-dir> --recipe <recipe> \
  --seed <local seed directory or git URL> \
  --dataset <local task directory>
evolve init <workspace-dir> --recipe <recipe> \
  --seed <local seed directory or git URL> \
  --dataset <local task directory>
cd <workspace-dir>
```

`preflight` takes the same arguments as `init`, writes nothing, and reports
every unmet precondition as one checklist. The preconditions it checks and
`init` enforces:

- `EVOLVE_RUNTIME_DIGEST` must name the immutable evaluator runtime before
  `init` runs; there is no default.
- The public recipes are `aevolve`, `ahe`, `gepa`, `gepa_local`, `hill_climb`,
  and `hyperagents`; `gepa` is the default and evolves the built-in seed with
  no external clone. `gepa_local` runs real trials as local processes with no
  container runtime or model key and is the fastest way to exercise the full
  loop. Smoke recipes are test fixtures, not experiment choices.
- `--seed` needs a real local directory or git URL; built-in test seeds are
  rejected outside the test suite.

Then certify generation zero before creating any child:

```bash
./evolve run . --max-generations 0
./evolve status .
```

This scores the untouched seed with the frozen evaluator and records it as the
first champion; every later candidate is compared against this baseline.

## Orient in an existing workspace

Run:

```bash
./evolve status .
./evolve verify .
./evolve operator list . --json
```

Read `evolve.yaml` for the mutable surface, `program.md` for loop semantics, and
the matching `archive.jsonl` row when resuming a generation. File presence does
not prove that an operator is active: `operator list --json` is authoritative.

Identify the champion, next generation id, configured operators, their access
mode, pending transitions, and child worktrees before acting. Certify
generation zero (`./evolve run . --max-generations 0`) before creating a child.

## Choose a control path

Use the configured driver when its mutation stage should own the edit:

```bash
./evolve run . --max-generations 1
```

Increase the bounded generation count only after one generation closes cleanly.
Use agent-led orchestration when the outer coding agent should inspect evidence,
form the hypothesis, and edit the target itself. Do not start the driver while a
child worktree is open.

## Run an agent-led generation

Discover capabilities first, then use mechanism-owned state transitions:

```bash
./evolve operator list . --json
generation_id=1
./evolve operator run . select --genid "$generation_id"
```

Read `runs/gen-1/parents.json` and copy one returned numeric parent exactly:

```bash
parent_id="<selected numeric id>"
child_checkout="runs/worktrees/gen-$generation_id"

./evolve fork . "$parent_id" "$child_checkout"
./evolve operator run . rollout --genid "$generation_id" \
  --parent "$parent_id" --checkout "$child_checkout"
# Run only if operator list marks it configured with direct access:
./evolve operator run . trace_analyzer --genid "$generation_id" \
  --parent "$parent_id" --checkout "$child_checkout"
```

Read retained rollout and analysis artifacts. Before editing, name the source
artifacts, observed failure pattern, proposed change, and predicted effect. A
configured `meta_agent` is optional when the outer agent owns the mutation.

Edit only the mutable surface. To sanity-check the child against the
evaluator's smoke before spending evaluation budget, run
`./evolve candidate-smoke --checkout "$child_checkout"`. After the final edit,
complete the guarded path:

```bash
./evolve surface-check "$child_checkout" --parent "$parent_id"
# Run every configured direct admission stage after the final edit:
./evolve operator run . validate --genid "$generation_id" \
  --parent "$parent_id" --checkout "$child_checkout"
./evolve operator run . novelty --genid "$generation_id" \
  --parent "$parent_id" --checkout "$child_checkout"

./evolve commit . "$child_checkout" --parent "$parent_id" \
  --genid "$generation_id"
./evolve eval . "$generation_id"
./evolve finalize . "$generation_id" --parent "$parent_id"
./evolve verify .
```

Admission receipts bind to the exact candidate Git tree. Rerun every configured
admission stage after any later edit. `finalize` alone applies gate and record;
never invoke or construct mechanism-owned decisions directly. A successful
commit snapshots the candidate and removes its child worktree.

## Use operator capabilities progressively

Use the least context needed for the current decision:

1. Run `operator list --json` to discover active stages, access mode, variant,
   and active script path.
2. Run configured direct operators and inspect `runs/gen-<id>/<stage>/`.
3. Override one invocation with a recursively merged JSON object when only its
   bounds need tuning:

   ```bash
   ./evolve operator run . trace_analyzer --genid 1 \
     --parent "$parent_id" --checkout "$child_checkout" \
     --config '{"max_tasks":5,"max_concurrent":3}'
   ```

4. Read `PROTOCOL.md`, `operators/README.md`, or adjacent operator guidance when
   inputs, outputs, or access rules are unclear.
5. Read `operators/<stage>.py` only to diagnose the running implementation or
   make an explicitly allowed process change.
6. Read `library/<stage>/<variant>.py` to compare or adapt a reference variant;
   copy or implement the change in the active operator when it must take effect.

Reruns retain prior output under
`runs/gen-<id>/operator-attempts/<stage>/attempt-<n>/`; only the newest active
output satisfies downstream prerequisites.

## Change the evolution process

Treat `operators/` as mutable only when the mutable surface includes it. Before
changing an operator, read `PROTOCOL.md`, its active implementation, adjacent
guidance, and only the relevant `library/<stage>/` references. Preserve the
operator protocol and run surface plus process-admission checks after the final
change.

Methods are overlays on this workspace. Hill Climb, A-Evolve, GEPA, AHE, and
HyperAgents vary active operators, evidence exposure, selection, validation,
and mutable scope; they do not require new top-level layouts.

## Recover and verify

- Run `./evolve doctor` only for interrupted or stale state. It removes clean
  stale managed worktrees and preserves dirty or external worktrees.
- Treat every linked worktree outside `runs/worktrees/` as user-owned. `doctor`
  may report it, but never remove, commit, or modify it merely to unblock the
  driver. Report its exact path and ask its owner to finish it or explicitly
  authorize disposal. Until then, the driver remains blocked.
- Run `./evolve verify .` whenever lineage, scores, or champion state conflicts.
- Retry the next mechanism transition indicated by the failing command; do not
  repair archive fields by hand.
- Resume the driver only after managed children are intentionally committed or
  recovered, every external worktree has been resolved by its owner, and
  verification passes.
- Never re-create a deleted workspace under the same name with the same
  `EVOLVE_HOME`: the retained receipt mirror no longer matches the new history,
  so certification refuses silently (champion stays `none` while integrity
  reports ok). Use a fresh name or a fresh `EVOLVE_HOME`.

Preserve stable generation identity, parent links, exact candidate snapshots,
evaluator stamps, rejected candidates, and pending decisions. Recompute champion
state from trusted records rather than mutable summaries.

## Completion contract

A generation is complete only when the final tree has current receipts for
every configured admission stage, commit and canonical evaluation succeeded,
`finalize` applied gate and record, `verify` passes, and its child worktree is
gone. Every evaluated candidate maps to one parent, snapshot, stamp, and
decision; every process change remains inside its mutable surface.
