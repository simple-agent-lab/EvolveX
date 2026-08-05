# GEPA

This recipe integrates the core GEPA reflective-mutation loop with the existing
Harbor evaluator:

1. sample a parent according to its per-task Pareto-front coverage;
2. run the parent on a generation-shuffled train minibatch with Harbor;
3. write each component's reflective examples to a structured evidence file;
4. give the GEPA meta-agent a short proposal brief pointing to those evidence
   files and let it edit the live target;
5. run the child with Harbor on the exact same minibatch and require a strict
   total-score improvement;
6. evaluate an improving child on the canonical gate set and add every eligible
   result to the population.

The default components are `target/prompt.md` and the task-execution skill. The
component strategy is round-robin, so one component's evidence and paths guide
each generation. Set `component_strategy: all` to expose all configured
components to one proposal. Components are proposal focus areas, not narrower
mutation permissions: the meta-agent may edit any path allowed by the mutable
surface.

This implements GEPA's Pareto selection, execution-aware reflection, component
mutation, and minibatch acceptance. GEPA's optional system-aware merge proposal
is not enabled: it needs a two-parent/common-ancestor lineage contract, while
the current driver creates each child from one parent.

Initialize and run it with:

```bash
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"
evolve init ./my-gepa-run \
  --recipe gepa \
  --dataset "$HARBOR_TASKS"
cd ./my-gepa-run
./evolve run .
```

The most useful artifacts are:

- `runs/gen-*/select/pareto.json`
- `runs/gen-*/trace_analyzer/evidence/reflective_dataset.json`
- `runs/gen-*/trace_analyzer/evidence/reflection/*.json`
- `runs/gen-*/meta_agent/proposal.json`
- `runs/gen-*/validate/comparison.json`
- `runs/gen-*/record/gepa-experience.json`
