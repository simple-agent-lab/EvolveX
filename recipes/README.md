# Recipe Roadmap

Recipes are research methods, not names for small config differences. A public
recipe must have a distinct candidate genome, loop transition, evidence
artifacts, selection or admission rule, and a test that demonstrates its defining
behavior. Fan-out, selector, gate, or mutable-surface changes alone are operator
presets.

The mechanism, method, and benchmark stay separate:

- the frozen mechanism owns execution, lineage, evaluation integrity, and permissions;
- a recipe composes evolvable operators and method-specific artifacts;
- a benchmark profile supplies the target, tasks, evaluator, and budget.

## V1: five flagship recipes

V1 favors depth over coverage. Existing recipe directories are scaffolds until
they satisfy the method conditions below; a real Harbor call does not by itself
make a recipe method-faithful.

| Recipe | Defining loop | V1 condition |
| --- | --- | --- |
| `hill_climb` | mutate one champion, evaluate, keep only improvement | Remain the simple, reproducible control used by every advanced recipe. |
| `autoresearch` | edit a bounded experiment, run a fixed budget, measure, keep/revert, log | Use real experiment code, one objective, and a durable hypothesis/result log. |
| `dgm` | sample an archive parent, self-edit the agent, evaluate, retain qualified descendants | Implement branching lineage, exploration-aware parent choice, and persistent self-improvement evidence. |
| `ahe` | evaluate, debug traces, attribute the prior edit, revise or rollback-and-pivot | Require task evidence, layered analysis, falsifiable change manifests, and next-round attribution. |
| `hyperagents` | task agent acts; meta-agent edits the task agent, itself, or their interaction | Make both agents explicit and evolvable, with external admission of self-referential changes. |

`metaagent` is not a V1 method: using a meta-agent is a mechanism shared by
several recipes. The current directory may remain temporarily for compatibility,
then should be retired or migrated into a named method.

## V2: reusable search and memory methods

V2 starts only after all five V1 recipes are method-faithful and benchmarked.

| Candidate | Distinct contribution | Required foundation |
| --- | --- | --- |
| `alphaevolve` | population-based program discovery with bounded evolvable regions | General program evaluator and population archive |
| `shinkaevolve` | offspring-balanced sampling, novelty rejection, successful-pattern scratchpad | Population statistics, semantic novelty, reflective memory |
| `promptbreeder` | co-evolution of task prompts and mutation prompts | Prompt-addressable tasks and reliable fitness |
| `gepa` | trajectory reflection drives diverse prompt candidates | Rich trajectories, reflection, and Pareto retention |
| `ace` | generator, reflector, and incremental curator maintain an identified playbook | Insight IDs, use attribution, credit, update, and retirement |
| `self_harness` | weakness mining, bounded harness proposals, held-in/held-out validation | Causal failure records and frozen regression evaluation |
| `stop` | the candidate is the improver; fitness is downstream meta-utility | Nested task suite and frozen meta-evaluator |

## V3: nested workflows and weight updates

V3 depends on capabilities that should not be forced into the current fixed
operator loop.

| Candidate | Distinct contribution | Required foundation |
| --- | --- | --- |
| `mce` | outer skill evolution plus inner context optimization | Isolated nested runs and train/validation objectives |
| `meta_harness` | search over complete inner harness implementations | Nested evaluation, Pareto frontier, recursive cost accounting |
| `adas` | meta-agent programs new workflows from an archive | Executable workflow representation and workflow novelty |
| `aflow` | MCTS over workflow graphs | Graph runtime, node mutation, and search-tree statistics |
| `sia` | feedback chooses between harness edits and weight updates | Training, checkpoint lineage, decontamination, sealed-data enforcement |

Autodata, AI Scientist, and ScientistOne are domain applications to build from
these methods, not foundational recipes. Their challenger, researcher, reviewer,
or evidence roles belong inside operators while evaluation remains frozen.

## Admission and release conditions

Every named recipe must have:

1. a cited method claim and an explicit evolvable genome;
2. method-specific control flow, artifacts, memory, and acceptance semantics;
3. no method-specific policy in the frozen driver;
4. a deterministic faithfulness test for its defining behavior;
5. a real candidate-liveness smoke run and a documented baseline comparison;
6. benchmark evidence before it is called validated.

Track two statuses independently:

- execution: `proposed -> scaffolded -> smoke-verified -> benchmark-validated`;
- fidelity: `placeholder -> partial -> method-faithful`.

Each implemented method may have an explicit `<name>-smoke` scaffold for cheap
mechanism tests. Smoke success never upgrades method fidelity.

`hyperagents-smoke` is the deterministic scaffold for the HyperAgents method:
it keeps the same `score_child_prop` selector, `hyperagents` meta-agent,
`hyperagents` validator/record, `parent_eligible` gate, staged evaluation shape,
and atomic genome (`target/**`, `operators/meta_agent.py`,
`operators/meta_agent.md`) while replacing the real MiniSWE benchmark target
with stub-friendly counts.
