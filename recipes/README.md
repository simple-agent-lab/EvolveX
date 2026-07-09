# Recipes

The recipe set is split in two:

- real recipes (`hill_climb`, `dgm`, `ahe`, `autoresearch`, `hyperagents`, `metaagent`) use MiniSWE source checkout, Harbor, and `agent_command`
- smoke recipes (`*-smoke`) preserve deterministic offline scaffolds for init and loop-shape tests

Each recipe keeps its operator routing in `evolve.yaml`, and each README calls
out the few choices that distinguish that loop from the others.
