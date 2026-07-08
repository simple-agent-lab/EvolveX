---
name: evolve-agent
description: Operate a self-evolving agent workspace — run evolution generations, act as the mutator (gen begin/finish), inspect lineage health, or repair interrupted state. Use when working inside a simple-evolve-agent workspace, or when asked to evolve/improve a candidate agent under a frozen evaluation harness.
---

# Operating an evolve-agent workspace

A workspace evolves a candidate under a frozen scoring harness; git is the
lineage archive, `archive.jsonl` the ledger. Everything goes through the
workspace's `./evolve` CLI.

**First actions, always:**
1. `cd` into the workspace (it contains `evolve`, `FROZEN/`, `candidate/`).
   No workspace yet? Create one: `bin/init-workspace.sh <dir>` from the framework repo.
2. Read the workspace `SKILL.md` (~60 lines) — it is the operating manual.
3. `./evolve status` before anything else; `./evolve doctor` if the state looks wrong.

**Two modes:**
- Autonomous: `./evolve run N` — the operators mutate (no LLM needed in stub mode:
  `HARNESS_STUB=1`).
- You-as-mutator: `./evolve gen begin` → edit files within the printed write
  scope → `./evolve gen finish --note "..." [--predict task_N]`.

**Hard rules** (enforced, do not fight them): FROZEN/ is read-only; scores are
stamped by the frozen side only; never hand-edit `archive.jsonl` or
`best_ever.json` — `./evolve verify` recomputes and exposes tampering.
