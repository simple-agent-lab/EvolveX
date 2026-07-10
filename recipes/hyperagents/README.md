# HyperAgents

This is the live Harbor recipe for HyperAgents-style self-improvement on
MiniSWE. The method reference is the HyperAgents paper/repository pattern:
a task agent is improved by a meta-agent, and the meta-agent workflow itself is
part of the candidate genome.

The default composition is fixed and method-specific:

- `select: {variant: score_child_prop, seed: 0}` chooses among valid scored
  parents with the HyperAgents score-proportional child penalty.
- `rollout: {variant: noop}` keeps rollout policy out of the method claim.
- `meta_agent: {variant: hyperagents, timeout_s: 21600}` calls the external
  meta-agent command using the active `operators/meta_agent.md` workflow.
- `validate: {variant: hyperagents, timeout_s: 300}` performs the fixed
  external validation extension for the atomic genome.
- `gate: {variant: parent_eligible}` admits any scored, mechanism-valid child,
  including lower-scoring but valid descendants.
- `record: {variant: hyperagents}` writes compact experience artifacts for the
  next generation.

The mutable surface is deliberately atomic and narrow:
`target/**`, `operators/meta_agent.py`, and `operators/meta_agent.md`. Random
selection and broad `operators/**` exposure are not what defines this recipe.
Edits to `operators/meta_agent.py` or `operators/meta_agent.md` activate only
for later children forked from an accepted generation, while fixed
`validate`, `gate`, and `record` remain outside the mutable surface.

Evaluation is Harbor on `swe-bench-lite` through
`target.harbor_agent:MiniSweSourceAgent`, with staged evaluation
(`stage: {tasks: 4, proceed_if: positive}`) before the full round. Smoke tests
prove method faithfulness and next-generation activation; benchmark validation
requires separate Harbor evidence and should not be inferred from smoke success.
