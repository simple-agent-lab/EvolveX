---
name: evolve-agent
description: Operate a self-evolving agent workspace — run evolution generations, act as the mutator, inspect lineage health, or repair interrupted state. Use when working inside a simple-evolve-agent workspace, or when asked to evolve/improve a candidate agent under a frozen evaluation harness.
---

# Operating an evolve-agent workspace

A workspace evolves a candidate under a frozen scoring harness; git is the
lineage archive (commit = candidate, tag `gen/<id>`), `archive.jsonl` the
ledger. Everything goes through the workspace's `./evolve` console. This is the
**outer** skill — a router; the operating manual travels inside each workspace.

**First actions, always:**
1. `cd` into the workspace (it contains `evolve`, `evaluator/`, `target/`).
   No workspace yet? Create one: `evolve init <dir> --recipe hill_climb` from
   the framework repo (or an installed `evolve` CLI).
2. The workspace's own `evolve-workspace` skill (its `SKILL.md`) is the
   operating manual — it auto-discovers on `cd`-in.
3. `./evolve status` before anything else; `./evolve doctor` if state looks wrong.

**Two modes:**
- Autonomous: `./evolve run N` — the operators mutate (no LLM needed in stub
  mode: `EVAL_STUB=1`).
- You-as-mutator: edit within the mutable surface, then let `./evolve run`
  drive eval/gate/record (interactive `gen begin` / `gen finish` is designed
  but not yet a CLI surface — see `DESIGN.md`).

**Hard rules** (enforced, do not fight them): `evaluator/` is read-only; scores
are stamped by the frozen side only; never hand-edit `archive.jsonl` or
`best_ever.json` — `./evolve verify` recomputes and exposes tampering.

See `DESIGN.md` in the framework repo for the whole architecture; the five
invariants are in `skills/_invariants.md`.
