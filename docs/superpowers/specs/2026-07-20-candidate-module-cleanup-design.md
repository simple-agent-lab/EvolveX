# Candidate Module Cleanup Design

## Goal

Remove an artificial asset-discovery module and make the candidate smoke boundary accurately named, without weakening the exact-snapshot integrity guarantees shared by candidate commit, patch generation, and smoke execution.

## Current responsibilities

`asset_discovery.py` contains one helper used only by `workspace.py` to vendor root-level Python helpers from the operator library. `workspace.py` already owns the surrounding asset traversal and text-file filtering, so the separate module does not define a reusable boundary.

`candidate_snapshot.py` constructs an exact Git tree from candidate working-tree changes, checks the mutable-surface policy, materializes that tree in a temporary detached worktree, and verifies that a final candidate commit has the same tree. It is shared by `driver.py`, `patching.py`, and candidate smoke execution.

`candidate_runtime.py` implements only the `candidate-smoke` workflow: snapshot materialization, evaluator smoke invocation, owned-process execution, secret redaction, and diagnostic result persistence. Its current name overstates its scope.

## Design

1. Delete `src/evolve/asset_discovery.py` and move its root-Python-helper filtering into `workspace.py` alongside `_walk_files`, `_text_files`, and `_operator_assets`. Preserve deterministic ordering, hidden/private-file filtering, symlink rejection, and undecodable-file skipping.
2. Keep `src/evolve/candidate_snapshot.py` as the focused candidate-integrity boundary. Its public functions and behavior remain unchanged.
3. Rename `src/evolve/candidate_runtime.py` to `src/evolve/candidate_smoke.py`. Update the CLI and tests to import the new module. Do not add a compatibility shim because these are internal modules and retaining one would defeat the cleanup.
4. Rename `tests/test_candidate_runtime.py` to `tests/test_locked_runtime.py`. That test verifies offline rematerialization of a locked Python environment and does not exercise candidate smoke behavior.
5. Update the enforced module inventory and architecture map so both describe the resulting source tree and responsibilities accurately.

## Data flow and invariants

The `candidate-smoke` CLI resolves the checkout and workspace, then calls `candidate_smoke.run_candidate_smoke`. Candidate smoke obtains the mutable-surface policy and asks `candidate_snapshot` to build the exact candidate tree. It materializes that snapshot in a temporary detached checkout, invokes `evaluator/smoke.sh` through the owned-process helper, redacts secrets, and writes the attempt result.

This refactor must preserve these invariants:

- Candidate smoke never executes directly from a dirty working checkout.
- Staged candidate changes remain rejected as ambiguous input.
- Changed paths outside the mutable surface remain rejected.
- The tree committed for a generation must equal the previously reviewed snapshot tree.
- Smoke output persists with environment and common credential forms redacted.
- Vendored asset ordering and filtering remain deterministic.

## Error handling

Existing exception behavior remains unchanged. Asset symlinks continue to raise `ValueError`; undecodable text assets continue to be skipped. Candidate snapshot violations continue to raise `CandidateSnapshotError`. Smoke status and CLI exit-code behavior remain unchanged.

## Testing

- Update candidate smoke tests to patch and import `evolve.candidate_smoke`.
- Keep candidate snapshot tests separate because they validate the shared integrity boundary.
- Preserve the locked-runtime test under its corrected filename.
- Update coherence assertions for the removed and renamed modules.
- Run focused candidate, workspace/init, coherence, and import-hygiene tests, followed by the complete test suite.

## Non-goals

- Combining snapshot integrity and smoke orchestration into one module.
- Changing the `candidate-smoke` CLI contract or smoke result schema.
- Changing candidate surface policy or Git snapshot semantics.
- Adding backward-compatible aliases for internal module paths.
