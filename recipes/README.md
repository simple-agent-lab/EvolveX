# Recipes

These recipes are small, inspectable loop shapes. Each recipe keeps its
operator routing in `evolve.yaml`; the recipe README links each routing line to
the resolved file under `library/`.

Recipe names may describe a research loop, but `variant:` values are canonical
library file names. If a recipe says `gate: {variant: parent_eligible}`, the
file is `library/gate/parent_eligible.py`.

- [AHE](ahe/README.md)
- [AutoResearch](autoresearch/README.md)
- [DGM](dgm/README.md)
- [Hill Climb](hill_climb/README.md)
- [HyperAgents](hyperagents/README.md)
- [MetaAgent](metaagent/README.md)
