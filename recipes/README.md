# Recipes

These recipes are small, inspectable loop shapes. Each recipe keeps its
operator routing in `evolve.yaml`; the recipe README links each routing line to
the resolved file under `library/`.

Recipe names may describe a research loop, but `variant:` values are canonical
library file names. If a recipe says `gate: {variant: parent_eligible}`, the
file is `library/gate/parent_eligible.py`.

- [Hill Climb](hill_climb/README.md)
- `hill_climb-smoke` — deterministic local counterpart
- [A-Evolve](aevolve/README.md)
- [A-Evolve Terminal-Bench Bridge](aevolve_tbench_bridge/README.md)
- [Agentic Harness Engineering](ahe/README.md)
- [Agentic Harness Engineering on HLE Parity](ahe_hle/README.md)
- [GEPA](gepa/README.md)
- [HyperAgents](hyperagents/README.md)
- [HyperAgents on HLE Parity](hyperagents_hle/README.md)
- `hyperagents-smoke` — deterministic local counterpart
