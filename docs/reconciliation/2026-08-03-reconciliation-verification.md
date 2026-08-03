# Repository Reconciliation Verification

**Date:** 2026-08-03 (Asia/Shanghai)

**Branch:** `codex/reconcile-ground-truth-20260803`

**Outcome:** Ready for local review. The branch has not been pushed and neither
remote host's `main` checkout has been updated.

## Selected history

| Purpose | Commit |
|---|---|
| Audited GitHub `main` baseline | `ebb00de125244b6a416006524fcdfd2dccdb17bb` |
| Reconciliation design | `48d8302` |
| Reconciliation implementation plan | `c97f847` |
| Sanitized source inventory | `b895497` |
| Exact Codex-target feature tip | `3a2d419cd93dad5d5cc83ef91a60ae7049cae797` |
| History-preserving feature merge | `a6872d3934be1517dd967c47a60faf295e424c04` |
| Harbor runtime trial-limit fix | `53a220fcdd345721c9660d9d53e72fac6a4d22cb` |

Immediately before the merge, read-only GitHub API checks returned the exact
selected `main` and feature commits. The merge completed without conflicts and
affected only:

- `scaffolds/evaluators/harbor/engine.sh`
- `seeds/codex/agent.py`
- `tests/test_harbor_evaluator_template.py`
- `tests/test_m7_codex_seed.py`

## Cutoff evidence

- All 28 discovered MacBook worktrees have private manifests. The initial root
  false-positive was superseded by a stable one-attempt recapture.
- DevBox and DevBoxS mains, six Codex-target snapshots per host, and the two
  adjacent DevBox repositories have stable metadata/patch cutoffs.
- The entire private session archive passes recursive hash and permission
  verification after normalizing directories to `0700` and files to `0600`.
- The private collector passes 12 behavioral tests and ruff.
- `auth.json` is represented only by non-content metadata. It has no captured
  digest or payload.
- No `.codex/reconciliation/` material is tracked by Git.

The cutoff protocol is source-local rather than globally simultaneous. Active
writers were allowed to continue, and each accepted manifest records its own
pre/post consistency boundary.

## Harbor red/green evidence

Before the correction:

```text
FAILED tests/test_harbor_parse_score.py
AssertionError: assert 50 == 2
1 failed
```

After the minimal precedence correction:

```text
19 passed
All checks passed!  # focused ruff
```

The final `scaffolds/evaluators/harbor/parse_score.py` SHA-256 is
`755377dc9326f74a41aef095bf6104b2639291f750dc46682788a1aefeceb6ee`. Fresh
hash commands returned this same value from the reconciliation worktree,
MacBook primary checkout, DevBox `r6`, and DevBoxS `r6`.

## Test and static-analysis evidence

| Check | Result |
|---|---|
| Baseline full suite before integration | 516 passed |
| Codex-target focused tests | 25 passed |
| Codex-target focused ruff | Passed |
| Harbor regression plus evaluator tests | 19 passed |
| Final `uv sync --dev` | 91 packages resolved; 90 checked |
| Final `uv run pytest -q` | 526 passed in 77.18 seconds |
| Final `uv run ruff check .` | Passed |
| Final `uv run ty check` | Passed |
| `git diff --check origin/main...HEAD` | Passed |
| Reconciliation worktree status before this report | Clean |

## Security and publication boundary

The sanitized inventory and final documentation were scanned for credential
patterns before staging. Raw patches, unpublished files, credentials, and bulk
outputs remain outside Git. No secrets were read into the tracked documents.

This run intentionally stops before:

- pushing `codex/reconcile-ground-truth-20260803`;
- opening a pull request;
- updating DevBox or DevBoxS `main`;
- merging any dirty Tau3 or adjacent-repository work;
- deleting, moving, cleaning, or compacting any source worktree or artifact
  root.

## Retention requirements

Keep these sources until their owners review the inventory and confirm a later
archive or integration path:

- `.codex/reconciliation/20260803T160000+0800/` in the primary checkout;
- all six dirty MacBook worktrees listed in the inventory;
- both hosts' detached Codex-target snapshots, especially `r6`;
- DevBox `simple-agent-lab` and `tau3-adapter-safe-worktree`;
- all matching `simple-evolve-agent*`, `tau3-*`, and `harbor-*` bulk roots.

DevBox has complete observed allocated sizes for 140 matching roots. DevBoxS
has path/mode/mtime metadata for 32 roots, but allocated sizes are deliberately
unmeasured after stopping a long read-only traversal of its full89 tree. That
limitation is explicit and does not affect the Git reconciliation result.
