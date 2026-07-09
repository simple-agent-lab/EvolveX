# Shared skill conventions

- Everything goes through the workspace `./evolve` console — never hand-run the
  operators or hand-edit the ledger.
- Point the agent at files to read; don't pre-chew. The workspace is the medium
  between operators.
- State hard constraints up front (write scope, what's frozen). Keep prose short
  — it's read under load.
- On any error, the console message names the next command. Read it.
