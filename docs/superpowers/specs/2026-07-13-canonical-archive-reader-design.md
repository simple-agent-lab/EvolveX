# Canonical Archive Reader Design

## Goal

Make archive consumption stable across old and new AHE and HyperAgents experiments without exposing raw `archive.jsonl` event shapes as a public API.

## Contract

- `archive.jsonl` remains an internal, append-only evidence ledger.
- External framework and experiment code reads generations through `ArchiveView.rows()`, `ArchiveView.row(genid)`, and `ArchiveView.valid_parents()`.
- `ArchiveView` continues to normalize events through `merged_rows()`.
- Existing archives are read in place and are never migrated or rewritten.
- Raw internal fields such as `_evolve_mechanism_eval` are not analysis APIs.

## Evaluation Writes

Every newly written evaluation event carries the existing internal mechanism marker. This includes ordinary, forced, genesis, and per-round evaluations. `append_event()` therefore writes a matching evaluation receipt consistently for every new evaluation.

The existing `kind` field continues to describe evaluation purpose. No new event schema, dataclass, schema version, or migration command is introduced.

## Legacy Compatibility

Markerless historical evaluation events remain readable through the existing stamped-field normalization in `merged_rows()`. Reading legacy evidence does not synthesize markers or receipts and does not change archive bytes.

Selection and reporting use the canonical merged row. They do not scan raw JSONL for a particular marker or infer recipe-specific row formats.

## Experiment Reporting

The selection-correctness summarizer reads parent eligibility, status, score, and verdict through `ArchiveView.row(genid)`. Raw Harbor trial results remain the evidence source for exceptions and verifier rewards.

The stopped original HyperAgents task-04 pair is excluded. Its completed, preregistered replacement pair is substituted without rerunning any other task.

## Failure Behavior

- Missing generations or required canonical fields fail reporting explicitly.
- Malformed JSON remains a read error.
- Reporting failures never append archive events or alter selection state.
- Evaluation and archive writes remain append-only.

## Verification

Add two focused regressions:

1. An ordinary evaluation receives the mechanism marker and matching receipt.
2. `ArchiveView.row()` reads a legacy markerless HyperAgents evaluation without changing the archive.

Run the existing relevant archive and selection tests, then recompute the DevBoxS experiment summary from the existing original and replacement artifacts.

## Non-goals

- Publishing raw archive event shapes.
- Rewriting historical archives.
- Adding normalized dataclasses or another reader API.
- Adding a JSON reporting CLI.
- Expanding recipe policy or changing selection semantics.
