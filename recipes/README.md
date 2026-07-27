# Recipes

These recipes are small, inspectable loop shapes. Each recipe keeps its
operator routing in `evolve.yaml`; the recipe README links each routing line to
the resolved file under `library/`.

Recipe names may describe a research loop, but `variant:` values are canonical
library file names. If a recipe says `gate: {variant: parent_eligible}`, the
file is `library/gate/parent_eligible.py`.

- [Hill Climb](hill_climb/README.md)
- [A-Evolve](aevolve/README.md)
- [Agentic Harness Engineering](ahe/README.md)
- [Agentic Harness Engineering on HLE Parity](ahe_hle/README.md)
- [GEPA](gepa/README.md)
- [HyperAgents](hyperagents/README.md)
- [HyperAgents on HLE Parity](hyperagents_hle/README.md)

Development-only recipe fixtures live under `tests/fixtures/recipes/`.
Unsupported research bridges live under `experiments/recipes/`.
