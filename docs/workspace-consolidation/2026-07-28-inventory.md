# Workspace Consolidation Inventory — 2026-07-28

## Canonical starting points

- Local `main`: `3028f49a75bc524e0920cc348f8f531a1c356df4`
- Remote `origin/main`: `933450b693226ac1131d548ccc46d8a34322b0ba`
- Consolidation branch: `codex/workspace-consolidation`
- PR #17 focused isolation commit: `6f92fd916cfcbb00d7a3c77d367c66fc7bf81967`
- PR #17 bundled runtime commit: `5f9179e350ae0ac39a4d562372d9b5b74f8400d8`

## Baseline verification

- `.venv/bin/pytest -q`: `475 passed, 1 skipped`
- Baseline worktree status: clean
- Preservation directory: `.worktrees/_preservation-20260728`
- Preservation verification: every entry in `SHA256SUMS` passes `shasum -a 256 -c`

## Dirty state requiring preservation

| Location | State |
| --- | --- |
| Primary checkout | `experiments/hle-parity-100-49-100.zip`; `terminal-bench-2-50-19-20/` |
| `.worktrees/current-experiment-lark-report` | untracked `current_shared_optimizer_experiments_report.xml` |
| `.worktrees/framework-hardening` | modified `.superpowers/sdd/task-2-report.md`, `.superpowers/sdd/task-8-report.md` |
| `.worktrees/harbor-evaluator-agent-runner` | five modified and three untracked implementation/test files |

## Stashes

| Stash | Base | Subject | Initial disposition |
| --- | --- | --- | --- |
| `stash@{0}` | `9db408e` | `pre-merge-unified-experiment-runtime-tracked` | likely incorporated; preserve and compare |
| `stash@{1}` | `5f66125` | `local-experiment-scripts-before-meta-agent-pr` | unique scripts; preserve |
| `stash@{2}` | `7e9d7be` | `pre-merge-main-uv-link-mode-20260722` | likely incorporated; preserve and compare |
| `stash@{3}` | `c790f6d` | `codex-pre-remote-sync-20260714` | unique diagrams and historical implementation; preserve |

## Candidate branch groups

### Focused integration

- `codex/experiment-recovery-branching`: replay 11 commits after `a59d438`.
- `codex/open-source-cleanup`: audit 21 commits after merge base `0688c4b`.
- `codex/harden-meta-agent-venv-boundary`: port only the focused isolation behavior; do not merge wholesale.

### Already contained in starting local main

- `codex/ahe-official-alignment`
- `codex/consolidated-ahe-hyperagents`
- `codex/curated-hardening-hyperagents`
- `codex/evaluation-package`
- `codex/fast-test-suite`
- `codex/harbor-miniswe-runtime`
- `codex/merge-python-runtime-ahe-alignment`
- `codex/meta-agent-experiment-hardening`
- `codex/pr16-docker-image-alignment`
- `codex/python-runtime-cleanup`
- `feat/ahe-miniswe-harbor`

### Preserve for later patch-level audit

- `codex/framework-hardening`
- `codex/integrated-hardening-hyperagents` (same tip as framework hardening)
- `codex/method-faithful-ahe`
- `codex/method-faithful-hyperagents`
- `feat/ahe-miniswe`
- `codex/harbor-evaluator-agent-runner`
- `codex/current-experiment-lark-report`

### Historical archive refs

All `archive-20260709-remote-reset-*` branches and older divergent recipe/framework branches remain retained until the consolidated tree is verified.

## Root artifact disposition

- `experiments/hle-parity-100-49-100.zip`: likely duplicates the tracked HLE parity directory; require byte comparison before deletion.
- `terminal-bench-2-50-19-20/`: 53 MB task dataset; preserve or relocate outside source control unless regeneration is proven.

## PR #17 disposition

- Keep the ignored-checkout isolation intent from `6f92fd9`.
- Do not merge `5f9179e`; its useful pieces are already present or superseded on local `main`.
- Add a separate Git-maintenance race fix for sanitized Harbor repositories.
- Close or supersede the draft PR only after the focused replacement branch is verified.
