# Recipes

The recipe set is split in two:

- real recipes (`hill_climb`, `dgm`, `ahe`, `autoresearch`, `hyperagents`, `metaagent`) call Harbor with explicit `evaluator.agent` values and evolve the MiniSWE source checkout through `target.harbor_agent:MiniSweSourceAgent`
- smoke recipes (`hill_climb-smoke`, `dgm-smoke`, `ahe-smoke`, `autoresearch-smoke`, `hyperagents-smoke`, `metaagent-smoke`) are the only deterministic `EVAL_STUB=1` scaffolds

For MiniSWE source evolution, `target/` is the MiniSWE source checkout plus
`target/harbor_agent.py`. Harbor imports
`target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into the
task container, installs that source, and then reuses Harbor's MiniSWE run
behavior.

The non-AHE real recipes use the `agent_command` meta-agent variant. The AHE
recipe instead routes through `ahe_evidence_editor` and `ahe_trace_analysis`;
all of these source-agent integrations intentionally leave their commands unset
until `EVOLVE_AGENT_COMMAND` or the corresponding operator command is supplied.

`ahe` is the fixed 30-task SWE-bench Pro training recipe (`k: 2`, Harbor
`n_concurrent: 5`); `ahe-smoke` keeps the same AHE operator family with the
builtin dummy target and `pass@k`. The AHE prompts are library assets, and its
trace, manifest, task-vector, and evaluation-artifact evidence remains in the
generated workspace rather than the recipe directory.

Each recipe keeps its operator routing in `evolve.yaml`, and each README calls
out the few choices that distinguish that loop from the others.
