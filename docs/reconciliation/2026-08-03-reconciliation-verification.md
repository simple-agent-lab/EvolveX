# Repository Reconciliation Verification

**Date:** 2026-08-03 (Asia/Shanghai)

**Branch:** `codex/reconcile-ground-truth-20260803`

**Outcome:** Ready for draft pull-request review. This verification run ended
before publication; publication is separately authorized. Neither remote
host's `main` checkout has been updated.

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
| Draft-publication boundary wording | `05cc9e66eafebf252419ebb7449be2c067c54706` |
| Harbor fallback regression coverage | `f9ddb81171948ccad7197d87d4595cd7badfff0d` |

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
- Every copied file and patch referenced by a manifest's final top-level
  selection passes hash verification. Retained failed-attempt entries are not
  covered by that hash verifier. A separate filesystem mode audit found no
  directory outside `0700` and no file outside `0600` in the private session
  archive.
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

Review-added compatibility cases then verified the unchanged task-split,
attempt-count, `EVOLVE_HARBOR_EXPECTED_TRIALS`, and `EVOLVE_HARBOR_N`
fallbacks. The expanded focused run passed 22 tests.

The final `scaffolds/evaluators/harbor/parse_score.py` SHA-256 is
`755377dc9326f74a41aef095bf6104b2639291f750dc46682788a1aefeceb6ee`. Fresh
hash commands returned this same value from the reconciliation worktree,
MacBook primary checkout, DevBox `r6`, and DevBoxS `r6`.

## Exact verification evidence

The final code-and-test tip verified before this report-only amendment was
`f9ddb81171948ccad7197d87d4595cd7badfff0d`. Branch commands ran from
`/Users/bytedance/Desktop/simple-evolve-agent/.worktrees/reconcile-ground-truth-20260803`;
private-evidence commands ran from
`/Users/bytedance/Desktop/simple-evolve-agent`. Every command below records its
observed process exit code.

### Branch commands

| Exact command | Exit | Result |
|---|---:|---|
| `uv sync --dev` | 0 | 91 packages resolved; 90 checked. |
| `uv run pytest -q` | 0 | 529 passed in 105.61 seconds. |
| `uv run ruff check .` | 0 | All checks passed. |
| `uv run ty check` | 0 | All checks passed. |
| `sh -n scaffolds/evaluators/harbor/engine.sh` | 0 | No shell syntax diagnostics. |
| `git diff --check origin/main...HEAD` | 0 | No whitespace errors. |
| `git status --short` | 0 | No output at the verified code tip. |

Earlier stage-specific evidence remains part of the audit trail: the baseline
suite passed 516 tests, the exact Codex-target merge passed 25 focused tests,
and the initial Harbor red/green run failed with `50 == 2` before passing 19
tests after the correction.

### Private-evidence commands

| Exact command | Exit | Result |
|---|---:|---|
| `uv run python .codex/reconciliation/tools/capture_cutoff.py verify --archive .codex/reconciliation/20260803T160000+0800` | 0 | `OK`; checks all archive directory modes, final top-level copy/patch modes and hashes, and forbidden secret-entry digest fields. |
| `uv run python .codex/reconciliation/tools/test_capture_cutoff.py -v` | 0 | 12 tests passed. |
| `uv run ruff check .codex/reconciliation/tools/capture_cutoff.py .codex/reconciliation/tools/test_capture_cutoff.py` | 0 | All checks passed. |
| `find .codex/reconciliation/20260803T160000+0800 -type d ! -perm 700 -print` | 0 | No output. |
| `find .codex/reconciliation/20260803T160000+0800 -type f ! -perm 600 -print` | 0 | No output. |

### Credential-pattern command

This exact scan ran from the reconciliation worktree:

```bash
rg -n '(gho_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|OPENAI_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]+|password[[:space:]]*=[[:space:]]*[^[:space:]]+)' docs/reconciliation
```

It exited `1` with no output, which is ripgrep's expected no-match result. The
report-only amendment that records these results is separately checked with
`git diff --check`, the same credential scan, and an exact staged-path review
before commit.

## Security and publication boundary

The sanitized inventory and final documentation were scanned for credential
patterns before staging. Raw patches, unpublished files, credentials, and bulk
outputs remain outside Git. No secrets were read into the tracked documents.

This verification run itself stopped before publication. A later explicit
request may push this branch and open a draft pull request, but does not
authorize:

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
