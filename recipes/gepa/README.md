# GEPA

This recipe integrates the core GEPA reflective-mutation loop with the existing
Harbor evaluator:

1. sample a parent according to its per-task Pareto-front coverage;
2. run the parent on a generation-shuffled train minibatch with Harbor;
3. turn each Harbor trajectory into component-specific reflective examples;
4. ask the GEPA meta-agent to improve one configured component;
5. run the child with Harbor on the exact same minibatch and require a strict
   total-score improvement;
6. evaluate an improving child on the canonical gate set and add every eligible
   result to the population.

The default components are `target/prompt.md` and the task-execution skill. The
component strategy is round-robin, so one component is changed per generation.
Set `component_strategy: all` to expose all configured components to one
proposal.

This implements GEPA's Pareto selection, execution-aware reflection, component
mutation, and minibatch acceptance. GEPA's optional system-aware merge proposal
is not enabled: it needs a two-parent/common-ancestor lineage contract, while
the current driver creates each child from one parent.

Initialize and run it with:

```bash
evolve init ./my-gepa-run \
  --recipe gepa \
  --dataset /absolute/path/to/harbor/tasks
cd ./my-gepa-run
./evolve run .
```

The most useful artifacts are:

- `runs/gen-*/select/pareto.json`
- `runs/gen-*/trace_analyzer/evidence/reflective_dataset.json`
- `runs/gen-*/meta_agent/proposal.json`
- `runs/gen-*/validate/comparison.json`
- `runs/gen-*/record/gepa-experience.json`
