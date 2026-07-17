# This is an evolve workspace

An evolution run living in a git repo: each generation is a commit tagged
`gen/<id>`, the append-only ledger is `archive.jsonl`, and `evolve report` shows
the lineage. `evolve run` drives the loop; `evolve status` shows where it is.

## Layout

```
target/          the thing being evolved (the candidate). Only paths matched by
                 the mutable surface (see evolve.yaml) may change.
operators/       the ACTIVE evolution logic — one executable script per verb
                 (`<verb>.py`). Generated run artifacts record prompts and output.
  README.md      generated table of the active set + swap-in alternatives
library/         the operator catalog: variants per verb. Copy one over an
                 operators/<verb>.py to change strategy.
evaluator/       the FROZEN ruler — how a candidate is scored. Never changes
                 inside the loop (pinned to gen/0); a harness change is a proposal
                 for a human, not a mutation.
skills/          the mutator's manual (tool-agnostic: Claude Code, codex, …)
evolve.yaml      experiment config: recipe, operator selection, the mutable surface
program.md       loop orchestration prose (agent mode)
PROTOCOL.md      the operator contract in prose (authority: the framework)
archive.jsonl    append-only event ledger (gitignored; the source of truth)
```

## Run visibility

`evolve run` prints stage-level progress. Use `evolve run . --verbose` to
stream Harbor and operator output while preserving `runs/gen-*/**/harbor.log`.
Set `EVOLVE_PROGRESS=0` to suppress the stage messages.

## The one rule

Evolve `target/` and the `operators/`; never the `evaluator/` that judges them —
if the ruler could change, a score would become a lie. That boundary is what
keeps every number in `archive.jsonl` honest.
