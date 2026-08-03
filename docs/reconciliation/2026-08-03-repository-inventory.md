# Repository Reconciliation Inventory

**Cutoff session:** `20260803T160000+0800`

**Inventory status:** Integration and final verification complete; review and
publication pending

**Policy:** Active worktrees are read-only inputs and remain deferred unless a
clean, exact commit is selected below.

## Canonical anchors

| Role | Selected authority | Commit | Decision |
|---|---|---|---|
| Stable shared baseline | GitHub `main` | `ebb00de125244b6a416006524fcdfd2dccdb17bb` | Base the isolated reconciliation branch here. |
| Codex-target feature | GitHub `codex/codex-target-experiments` | `3a2d419cd93dad5d5cc83ef91a60ae7049cae797` | Merged exactly with history preserved as `a6872d3934be1517dd967c47a60faf295e424c04`. |
| Replicated Harbor trial-limit correction | Identical private unstaged patches on MacBook root, DevBox `r6`, and DevBoxS `r6` | SHA-256 `e4f1387d33c77a093a597062a81354827e660b387770bf3b1ca9574ee02390d6` (1,143 bytes) | Reproduced test-first and committed as `53a220fcdd345721c9660d9d53e72fac6a4d22cb`. |
| Active Tau3 and adjacent development | Timestamped private cutoffs | Multiple, listed below | Preserve and defer; do not promote a dirty checkout wholesale. |
| Experiment outputs | Host-resident roots plus private metadata | Not a Git commit | Retain in place; do not copy bulk payloads into Git. |

The reconciliation branch was created from the selected `main` commit. The
Codex-target feature has merge base
`e23a847f2358ac22246372bff94a163903d71c7b`; its `r6` commit is an ancestor of
the selected tip, followed by `81c0ecf` and `3a2d419`. Its net feature diff is
limited to four files: the Harbor engine wrapper, the Codex seed agent, and
their two test modules.

## Integration result

The live GitHub refs were re-verified immediately before integration and still
matched the selected commits. Merge commit
`a6872d3934be1517dd967c47a60faf295e424c04` completed without conflicts and
changed only the expected four feature files. The two focused feature test
modules passed 25 tests and their Python files passed ruff.

The Harbor regression first failed with `assert 50 == 2`, demonstrating that
the persisted split incorrectly won over the live runtime limit. After the
minimal precedence correction, the regression and evaluator-template tests
passed 19 tests. The final `parse_score.py` SHA-256 is
`755377dc9326f74a41aef095bf6104b2639291f750dc46682788a1aefeceb6ee`, exactly
matching the MacBook root, DevBox `r6`, and DevBoxS `r6` copies.

## Private cutoff evidence

Raw manifests, patches, and selected small unpublished files are stored only
under `.codex/reconciliation/20260803T160000+0800/` in the primary MacBook
checkout. They are excluded from Git, use owner-only permissions, and pass the
collector's hash and permission verification for MacBook, DevBox, and DevBoxS.

The first MacBook-root attempt was marked inconsistent because the collector
observed its own output under `.codex/`. After a regression-tested exclusion
fix, a fresh non-overwriting root recapture completed consistently on its first
attempt. The recapture supersedes the first root attempt; both are retained as
evidence. Failed pre-capture compatibility attempts on the remote hosts are
also retained but are not classified as valid cutoffs.

The private collector has 12 passing behavioral tests, including active-write
retry, tamper detection, secret exclusion, old-Git compatibility, shell-safe
remote metadata, and an option to omit expensive recursive size walks.

## MacBook worktrees

Six worktrees contained active changes at their accepted cutoff. None was
paused, switched, stashed, reset, cleaned, or committed by reconciliation.
"Tracked" and "untracked" below describe captured status, not material selected
for integration.

| Worktree | Branch | Cutoff `HEAD` | Captured changes | Classification |
|---|---|---|---|---|
| Primary checkout | `codex/tau3-tb2-experiment-setup` | `6d86fd1fa312` | 1 tracked; 1,024 untracked files | Active Tau3/Harbor WIP; consistent recapture; defer. |
| `current-experiment-lark-report` | `codex/current-experiment-lark-report` | `cd5231f0e90f` | 1 untracked | Active report WIP; defer. |
| `framework-hardening` | `codex/framework-hardening` | `bbb2ca47a82a` | 2 tracked | Active hardening WIP; defer. |
| `harbor-evaluator-agent-runner` | `codex/harbor-evaluator-agent-runner` | `dac538b4c22a` | 5 tracked; 3 untracked | Active evaluator WIP; defer. |
| `tau3-adapter-implementation` | `codex/tau3-adapter-implementation` | `ceb51b62952a` | 12 tracked; 28 untracked | Active Tau3 adapter WIP; defer. |
| `tau3-ten-minute-qualification` | `codex/tau3-ten-minute-qualification` | `a4b75d6c8d81` | 1 untracked | Active qualification WIP; defer. |

The primary checkout also contains one anomalous command-shaped untracked
filename. It was inventoried by Git status but not read or copied. This should
be reviewed with the owner after active work completes.

The other 22 MacBook worktrees were clean and consistent at their individual
cutoffs:

| Worktree | Branch | Cutoff `HEAD` | Classification |
|---|---|---|---|
| `ahe-miniswe` | `feat/ahe-miniswe` | `69349980905d` | Clean branch; retain. |
| `codex-ahe-official-alignment` | `codex/ahe-official-alignment` | `8cfbced43f6e` | Clean branch; retain. |
| `codex-target-experiments` | `codex/codex-target-experiments` | `3a2d419cd93d` | Exact selected feature authority. |
| `curated-hardening-hyperagents` | `codex/curated-hardening-hyperagents` | `13fd9839ef82` | Clean branch; retain. |
| `evaluation-package` | `codex/evaluation-package` | `0610f6438d3f` | Clean branch; retain. |
| `experiment-recovery-branching` | `codex/experiment-recovery-branching` | `df4b5cfab394` | Clean branch; retain. |
| `fast-test-suite` | `codex/fast-test-suite` | `d3bac2881b6d` | Clean branch; retain. |
| `framework-anchor-evaluation` | `codex/framework-anchor-evaluation` | `7e014de49568` | Clean branch; retain. |
| `harden-meta-agent-venv-boundary` | `codex/harden-meta-agent-venv-boundary` | `5f9179e350ae` | Clean branch; retain. |
| `integrated-hardening-hyperagents` | `codex/integrated-hardening-hyperagents` | `bbb2ca47a82a` | Clean branch; retain. |
| `merge-python-runtime-ahe-alignment` | `codex/merge-python-runtime-ahe-alignment` | `a0f65a14fba0` | Clean branch; retain. |
| `method-faithful-ahe` | `codex/method-faithful-ahe` | `afb15a7dc47e` | Clean branch; retain. |
| `method-faithful-hyperagents` | `codex/method-faithful-hyperagents` | `dcb8b4e137f6` | Clean branch; retain. |
| `open-source-cleanup` | `codex/open-source-cleanup` | `c22959ed3b06` | Clean branch; retain. |
| `pr16-docker-image-alignment` | `codex/pr16-docker-image-alignment` | `09dd70afbc4b` | Clean branch; retain. |
| `pr5-ahe-miniswe-integration` | `feat/ahe-miniswe-harbor` | `7b9e988f518e` | Clean branch; retain. |
| `private-task-boundary` | `codex/fix-private-task-boundary` | `8dc9e6bba2ab` | Clean branch; retain. |
| `python-runtime-cleanup` | `codex/python-runtime-cleanup` | `f02fe54ec94b` | Clean branch; retain. |
| `reconcile-ground-truth-20260803` | `codex/reconcile-ground-truth-20260803` | `c97f847e63f3` | Isolated reconciliation worktree at capture time. |
| `tau3-tb2-experiment-impl` | `codex/tau3-tb2-experiment-impl` | `fb94430b88c6` | Clean branch; retain. |
| `workspace-consolidation` | `codex/workspace-consolidation` | `54529a84caa1` | Clean branch; retain. |
| `/private/tmp/simple-evolve-readme` | `codex/readme-evolve-your-agent` | `46488ada7b17` | Clean branch; retain. |

## DevBox and DevBoxS repositories

Both `simple-evolve-agent-main` checkouts were clean and stable at
`d44d723e04a0a86505381a7587d535b45b70404d`. They were ten commits behind the
selected GitHub `main`, so they are stale mirrors, not ground truth, and remain
unchanged in this phase.

Both hosts contained matching detached Codex-target snapshots:

| Snapshot | `HEAD` on both hosts | Captured state | Classification |
|---|---|---|---|
| `20260730` | `4e180cd221ce` | Clean | Historical execution snapshot. |
| `20260730-r2` | `198688626012` | Clean | Historical execution snapshot. |
| `20260730-r3` | `c0fd9cc17f65` | Clean | Historical execution snapshot. |
| `20260730-r4` | `f29d205c712a` | Clean | Historical execution snapshot. |
| `20260731-r5` | `097595683a05` | Clean | Historical execution snapshot. |
| `20260731-r6` | `07f6e049afc2` | Same modified `scaffolds/evaluators/harbor/parse_score.py` patch | Historical code snapshot plus replicated correction; selected feature tip supersedes its committed lineage. |

The `r6` unstaged binary patch is byte-identical on DevBox, DevBoxS, and the
MacBook primary checkout (SHA-256 and byte size shown in Canonical anchors).
The patch is preserved privately and will be reconstructed by test-first
implementation rather than copied blindly.

Two adjacent DevBox repositories are separate work and are not candidates for
this repository's ground truth:

| Repository | Branch / `HEAD` | Captured state | Decision |
|---|---|---|---|
| `/data00/home/zimuwang/simple-agent-lab` | `local/main` / `b870950c7516` | 2 tracked changes; 8 untracked logs; patch SHA-256 `6227e1e596ae953b0b921ccc60ed1f62116ef7dcb3ac789a016bad2243d4f69f` | Preserve privately; reconcile in its own repository. |
| `/data00/home/zimuwang/tau3-adapter-safe-worktree` | `codex/tau3-adapter-implementation` / `79f4db761c12` | 18 tracked changes; 9 untracked paths; patch SHA-256 `d571f18c6005fef2c6b17966aac3536d350509e2246df1b6dd905d4bf97f7509` | Preserve privately; defer to Tau3 review. |

## Bulk artifact retention

Bulk outputs remain in place and were never copied into the private cutoff or
Git. DevBox had 140 matching top-level `simple-evolve-agent*`, `tau3-*`, and
`harbor-*` roots totaling an observed 319,099,824 KiB (about 304 GiB). The
largest observations were:

| DevBox root | Observed allocated size |
|---|---:|
| `simple-evolve-agent-full89-20260724` | 271,166,792 KiB |
| `harbor-datasets` | 33,114,112 KiB |
| `harbor-evolve-m1` | 8,566,044 KiB |
| `tau3-codex-control-20260803-r1` | 2,797,280 KiB |

DevBoxS had 32 matching roots. A recursive size observation was stopped while
walking its large `simple-evolve-agent-full89-20260724` tree to avoid sustained
I/O load on an active host. All 32 paths still have mode, entry-size, and mtime
metadata, with `allocated_kib: null` and `size_is_observation: false`. Retain
both hosts' matching roots until the relevant experiment owners confirm that
results have been summarized and archived elsewhere.

## Secret-like exclusions

The primary checkout's `auth.json` was listed twice across the original and
superseding root manifests using only relative path, size, mode, modification
time, `copied: false`, and reason `secret-like`. Its contents were not read,
hashed, copied, printed, or staged. No other secret-like path was reported by
the accepted cutoff manifests.

## Deferred concurrent work

- All six dirty MacBook worktrees remain owned by their active tasks.
- DevBox `simple-agent-lab` and `tau3-adapter-safe-worktree` remain separate,
  dirty repositories and are not merged here.
- DevBox and DevBoxS `main` remain stale but untouched.
- All historical snapshots and bulk experiment roots remain retained in place.
- No branch, worktree, snapshot, artifact root, or unpublished file is deleted
  by this reconciliation phase.

## Current selection boundary

Only the exact clean Codex-target feature tip and the independently tested
Harbor trial-limit correction were integrated into the isolated reconciliation
branch. Every other dirty cutoff is preservation evidence, not an implicit
merge request. Final test, security, and retention evidence is recorded in
`2026-08-03-reconciliation-verification.md`. The branch remains local and
unpublished at the review boundary.
