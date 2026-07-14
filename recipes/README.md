# Recipes

These recipes are small, inspectable loop shapes. Each recipe keeps its
operator routing in `evolve.yaml`; the recipe README links each routing line to
the resolved file under `library/`.

Recipe names may describe a research loop, but `variant:` values are canonical
library file names. If a recipe says `gate: {variant: parent_eligible}`, the
file is `library/gate/parent_eligible.py`.

- [Hill Climb](hill_climb/README.md)
- `hill_climb-smoke` — deterministic local counterpart
- [HyperAgents](hyperagents/README.md)
- `hyperagents-smoke` — deterministic local counterpart
