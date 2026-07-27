---
name: evolve-agent
description: Operate an Evolve Framework workspace: run generations, inspect lineage health, or repair interrupted state.
---

# Operating an Evolve Framework workspace

A workspace evolves a candidate under a frozen evaluator. Git generation tags
are the lineage and `archive.jsonl` is the ledger. Use the workspace's
`./evolve` console for all workspace actions.

## First actions

1. Enter the workspace; it contains `evolve`, `target/`, and `evaluator/`.
2. If no workspace exists, initialize a supported recipe. Harbor recipes need
   an immutable runtime digest and an existing local Harbor task collection:

   ```bash
   export EVOLVE_RUNTIME_DIGEST=sha256:<immutable-evaluator-image-digest>
   evolve init <workspace> --recipe aevolve --dataset <local-harbor-task-directory>
   ```

3. Read `skills/evolve-workspace/SKILL.md` in the generated workspace, then run
   `./evolve status`. Use `./evolve doctor` when state looks wrong.

## Operating rules

- Run evolution with `./evolve run . --max-generations N`.
- Edit only paths allowed by the workspace's mutable surface.
- Never edit `evaluator/`, `archive.jsonl`, or `best_ever.json` by hand.
- Use `./evolve verify` to recompute and check lineage integrity.

The public recipe inventory is `aevolve`, `ahe`, `gepa`, `hill_climb`, and
`hyperagents`. Smoke recipes are test fixtures and are not workspace choices.
