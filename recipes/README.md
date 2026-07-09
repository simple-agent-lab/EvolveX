# Recipes

The recipe set is split in two:

- real recipes (`hill_climb`, `dgm`, `ahe`, `autoresearch`, `hyperagents`, `metaagent`) call Harbor with explicit `evaluator.agent` values and evolve the MiniSWE source checkout through `target.harbor_agent:MiniSweSourceAgent`
- smoke recipes (`hill_climb-smoke`, `dgm-smoke`, `ahe-smoke`, `autoresearch-smoke`, `hyperagents-smoke`, `metaagent-smoke`) are the only deterministic `EVAL_STUB=1` scaffolds

For MiniSWE source evolution, `target/` is the MiniSWE source checkout plus
`target/harbor_agent.py`. Harbor imports
`target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into the
task container, installs that source, and then reuses Harbor's MiniSWE run
behavior.

Every real recipe uses the `agent_command` meta-agent variant. Run them only after
supplying a meta-agent command via `EVOLVE_AGENT_COMMAND` or
`operators.meta_agent.command`; the real recipes intentionally leave that command
unset.

Each recipe keeps its operator routing in `evolve.yaml`, and each README calls
out the few choices that distinguish that loop from the others.
