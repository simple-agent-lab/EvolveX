---
name: evolve-workspace
description: The operating manual for a single evolve-agent workspace — you work one generation as the mutator. Travels into every workspace under a unified, tool-agnostic skills/ folder (Claude Code, codex, …); the workspace AGENTS.md points to it.
---

# Operating this evolution workspace (the mutator's manual)

You've landed in an evolve-agent workspace. It evolves a candidate (code +
prompts + config, possibly a weights pointer), scoring each generation with a
frozen ruler (`evaluator/eval.sh`). Git is the lineage archive (commit =
candidate, tag `gen/<id>`); `archive.jsonl` is the ledger.
**Everything goes through `./evolve`. Run `./evolve status` first.**

## The golden path (you work one generation as the mutator)

```bash
./evolve status              # where things stand: champion, recent gens, anything pending
./evolve run 1               # one generation: select → rollout → trace_analyzer → mutate → gate → record
# Or edit target/ (and optionally operators/) yourself within the mutable surface,
# then let the next `./evolve run` pick up from a clean tree.
```

`run` drives the loop: novelty (if configured), the self-reference admission
gate, frozen eval + stamping, gate, ledger, reflection (if configured).
Let the loop run itself: `./evolve run 10`.

## The five invariants (enforced — don't fight them)

1. **The ruler (`evaluator/`) is frozen.** It's outside the mutable surface, and
   every eval asserts its tree still matches `gen/0` — a changed ruler fails the eval.
2. **You never report scores.** score/task_vector are stamped by the frozen side.
3. **best-ever is recomputed by a frozen rule**; champion changes need re-eval.
4. **Training data never contains gate/sealed tasks.**
5. **Checkpoints enter the lineage only through canonical eval.**

Your writable area is the mutation scope: `target/ operators/ program.md
evolve.yaml` (plus whatever `surface` includes). Touching `operators/` =
self-reference — it triggers contract tests + a meta-eval replay admission
gate; failing it reverts only the operator part of your diff. **Never
hand-edit `archive.jsonl` / `best_ever.json`** — `./evolve verify` recomputes
and will expose it.

## Reference operators — consult, don't reinvent

When you want to change how an operator behaves, read the framework's
`library/<verb>/*.py` catalog for worked implementations, then **adapt one into**
your active `operators/<verb>.py`. Only your in-tree operator runs; the catalog
is reference. Strategy for each verb lives beside the script as
`operators/<verb>.md`.

## When things go wrong

- Any command errored: **read the error** — it names your next command.
- Confused state / previous session crashed: `./evolve doctor`.
- Suspect the ledger: `./evolve verify`.
- What happened in one generation: `./evolve show <gen>`.

## Deeper material (read on demand)

- `PROTOCOL.md` — authoritative operator interfaces / write scopes / exit codes
  (mandatory before editing operators).
- `program.md` — loop orchestration; `operators/<verb>.md` — per-verb strategy;
  `operators/mutation_brief.md` — the brief template shown to agentic mutators.
