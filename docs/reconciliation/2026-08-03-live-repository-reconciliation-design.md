# Live Repository Reconciliation Design

**Status:** Approved and executed to the local review boundary as of 2026-08-03

## Context

The repository has meaningful state in four places: GitHub, the MacBook
checkout and its linked worktrees, DevBox, and DevBoxS. Several MacBook
worktrees are actively being written while reconciliation proceeds. The audit
established these initial anchors:

- GitHub `main`: `ebb00de125244b6a416006524fcdfd2dccdb17bb`
- GitHub `codex/codex-target-experiments`:
  `3a2d419cd93dad5d5cc83ef91a60ae7049cae797`
- DevBox and DevBoxS `simple-evolve-agent-main`:
  `d44d723e04a0a86505381a7587d535b45b70404d`, clean but ten commits behind
  the audited GitHub `main`
- DevBox and DevBoxS detached `r6` experiment snapshot:
  `07f6e049afc2a5547707a71603ec4c714d25646a`, with the same uncommitted
  `scaffolds/evaluators/harbor/parse_score.py` change on both hosts

The MacBook contains local-only Tau3 branches and dirty worktrees. One of
those branches advanced during the audit, so reconciliation must not depend on
all sources being globally paused at the same instant.

## Goals

1. Establish GitHub `main` as the stable shared baseline without discarding
   feature work or experiment evidence.
2. Capture reproducible, timestamped cutoffs from changing worktrees without
   pausing or mutating their writers.
3. Preserve small source, configuration, and result-metadata files while
   avoiding copies of large generated artifacts.
4. Integrate the clean Codex-target experiment branch and the replicated
   Harbor parser correction in a separate reconciliation worktree.
5. Produce a sanitized, reviewable inventory that explains what is canonical,
   preserved as work in progress, superseded, or retained only as evidence.

## Non-goals

- Do not pause, stash, reset, clean, switch, commit, or update any active
  writer's worktree.
- Do not delete or rewrite local branches, server snapshots, bundles, or
  experiment outputs.
- Do not copy bulk experiment payloads into Git or into the first-pass local
  snapshot archive.
- Do not merge dirty Tau3 work into the reconciliation branch in this phase.
- Do not update the DevBox or DevBoxS `main` checkouts in this phase.
- Do not push the reconciliation branch until its inventory, integration, and
  verification results have been reviewed.

## Ground-truth model

Ground truth is role-specific:

| Role | Authority |
|---|---|
| Stable shared code | Audited GitHub `main` commit |
| Codex-target experiment feature | Clean GitHub feature-branch commit |
| Active Tau3 development | Timestamped MacBook cutoff snapshots until reviewed and committed |
| Experiment observations and outputs | Host-resident artifacts plus sanitized inventories and hashes |
| Detached DevBox experiment clones | Historical execution snapshots, not canonical development branches |

No existing checkout is promoted wholesale. Reconciliation constructs a new
reviewable line from the stable baseline and explicitly selected deltas.

## Architecture

The workflow has three layers:

1. **Local raw snapshot archive.** Store private, non-Git snapshot material at
   `.codex/reconciliation/<cutoff-id>/` in the primary MacBook checkout. Create
   directories with mode `0700` and files with mode `0600`. This layer may
   contain binary Git patches and copied unpublished source files. It must
   never be staged or pushed.
2. **Isolated reconciliation worktree.** Use
   `.worktrees/reconcile-ground-truth-20260803` on branch
   `codex/reconcile-ground-truth-20260803`, based on the audited GitHub
   `main`. All integration commits and tests run here.
3. **Sanitized repository inventory.** Commit only non-secret summaries,
   paths, commit identifiers, sizes, content hashes, classifications, and
   verification outcomes under `docs/reconciliation/`. Do not commit raw
   patches, copied WIP files, credentials, or bulk output.

## Cutoff snapshot protocol

Each source is captured independently. A cutoff is valid without claiming
that every source shared one global timestamp.

For each MacBook worktree or server checkout in scope, record:

- cutoff identifier and timestamps in ISO 8601 with timezone;
- host and absolute source path;
- branch or detached state, `HEAD`, tree object, upstream, and remote URL;
- `git status --porcelain=v2 --branch` output;
- staged and unstaged binary patches, stored only in the private archive;
- selected untracked source/configuration/metadata copies;
- SHA-256, byte size, file mode, and modification time for captured files;
- bulk-artifact locations, observed sizes, and selected metadata hashes;
- whether the capture passed the consistency check.

### Consistency check

For an active worktree:

1. Capture a pre-state containing `HEAD`, porcelain status, staged-diff hash,
   unstaged-diff hash, and selected-file hashes.
2. Copy the selected files and patches into a new attempt directory.
3. Capture the same post-state.
4. Accept the attempt only when `HEAD`, status, diff hashes, and selected-file
   hashes match and every copied file matches its recorded source hash.
5. Retry a moving worktree up to three times without changing or locking it.
6. If all attempts observe movement, retain the final attempt with
   `consistent: false`, both boundary states, and an explicit concurrent-write
   warning. Do not block its writer.

Bulk directories are inventories rather than atomic snapshots. Their manifest
must record its observation time and must not claim whole-directory
consistency while jobs are producing output.

## Inclusion and exclusion policy

### Copy into the private archive

- tracked staged and unstaged Git patches;
- untracked source and test files;
- untracked configuration, plans, scripts, and human-readable reports;
- files no larger than 5 MiB with these relevant suffixes:
  `.py`, `.sh`, `.md`, `.toml`, `.yaml`, `.yml`, `.json`, `.jsonl`, `.csv`,
  `.txt`, `.xml`, `.lock`, `.diff`, and `.patch`;
- small files at the repository root or under `docs/`, `scripts/`, `tests/`,
  `reports/`, and `experiments/`, subject to the secret exclusions below.

### Inventory without copying payloads

- files larger than 5 MiB;
- dataset trees, model/runtime caches, virtual environments, container data,
  and generated benchmark task trees;
- `analysis_artifacts/`, `analysis_selected/`, and large Terminal-Bench or Tau3
  payload directories;
- server experiment output trees.

For these entries, record paths, observed sizes, modification times, and hashes
of selected summary metadata. Do not recursively hash an actively growing bulk
tree as if the result were stable.

### Never copy

- `auth.json`, `.env`, `.env.*`, credential stores, private keys, access-token
  files, or files whose names indicate secrets;
- `.git/`, `.venv/`, caches, sockets, FIFOs, device files, or container runtime
  storage.

For an excluded secret-like file, record only its relative path, size, mode,
modification time, and `copied: false`; do not hash or read its contents. Scan
the sanitized inventory and any proposed committed patch for credential-like
material before staging.

## Reconciliation sequence

1. Verify the live GitHub `main` and
   `codex/codex-target-experiments` tips again and record the observed values.
2. Capture MacBook worktree cutoffs, prioritizing dirty and local-only Tau3
   worktrees.
3. Capture DevBox and DevBoxS source-checkout metadata and patches. Inventory
   experiment-result roots without copying their payloads.
4. Write and verify the sanitized inventory.
5. Merge the exact audited `codex/codex-target-experiments` commit into the
   reconciliation branch with a non-fast-forward merge, preserving its
   history. Resolve conflicts only in the isolated worktree and document each
   resolution.
6. Add the untracked Harbor parser regression test first and demonstrate that
   it fails against the integrated pre-fix tree.
7. Apply the replicated parser correction as a separate change and demonstrate
   that the regression test passes.
8. Run focused tests after each integration and the full documented test suite
   before declaring the reconciliation branch ready for review.
9. Leave Tau3 dirty files in their original worktrees and private cutoff
   archives. Integrate them only through a later reviewed branch or plan.

## Error handling

- A moving worktree produces a clearly marked concurrent cutoff rather than a
  pause request or a mutation.
- An unreachable host remains pending in the inventory with the last verified
  commit and the connection error; no state is inferred.
- A missing or changed remote branch stops integration of that branch until
  its new commit is reviewed. It does not stop independent snapshot work.
- A merge conflict is resolved only in the reconciliation worktree. The
  resolution and affected paths are listed in the sanitized inventory.
- A failing baseline or post-merge test is reported verbatim and blocks a
  readiness claim, but does not trigger resets or deletion.
- A suspected secret in material proposed for Git blocks staging of that
  material until the secret is excluded or redacted.

## Verification

The reconciliation is ready for review only when all of the following are
freshly demonstrated:

- the isolated worktree starts from the recorded GitHub `main` commit;
- the clean Codex-target branch tip equals the recorded GitHub commit;
- each captured source has a manifest and explicit consistency status;
- copied snapshot files match their recorded SHA-256 values;
- no secret-like file content appears in committed inventory material;
- the parser regression test fails before the parser correction and passes
  after it;
- focused integration tests pass;
- `uv run pytest -q` completes with zero failures on the final integrated tree;
- `git status --short` in the reconciliation worktree contains only deliberate
  committed or review-ready changes;
- no active source worktree, DevBox checkout, or DevBoxS checkout was switched,
  reset, cleaned, stashed, or committed by the reconciliation process.

## Deliverables

- the private cutoff archive under `.codex/reconciliation/<cutoff-id>/`;
- a committed sanitized inventory under `docs/reconciliation/`;
- the isolated `codex/reconcile-ground-truth-20260803` branch;
- a history-preserving Codex-target integration commit;
- a separate Harbor parser regression-fix commit;
- a verification report that states what was tested, what remains WIP, and
  which host-resident artifacts must still be retained.
