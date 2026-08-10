# A-Evolve

Use A-Evolve to improve prompts and reusable skills from repeated observations.
Choose one evidence mode: behavior-only trajectories when evaluator labels must
stay hidden, or generated-artifact rubrics when the output itself is the object
being improved.

## Use it when

- The target exposes prompts or skills as meaningful mutable components.
- Complete behavioral trajectories are available, or the evaluator retains
  generated artifacts with structured rubric judgments.
- The meta agent or outer agent can identify recurring, transferable failure
  patterns from the selected evidence mode.
- The evaluated agent actually consumes every component being evolved.

## Use the shipped capabilities

Run `./evolve operator active . --json` and follow the live access metadata. The
shipped A-Evolve profile normally provides task rollout, a `trajectory_only`
analyze, and an `aevolve` meta agent. Artifact-oriented experiments may
instead compose `library/rollout/evaluation_replay.py` with
`library/analyze/artifact_rubric.py` and the same
`library/mutate/aevolve.py` mutation strategy. For an outer-agent edit,
invoke `rollout` and `analyze` directly, read their retained evidence, then
modify the prompt or complete Skill directory yourself; the configured
`mutate` remains available for an unattended driver or second opinion.

Do not open source merely to obtain retained evidence. Read
`operators/analyze.py` only if its evidence contract is unclear or its
behavior needs diagnosis; consult `library/analyze/trajectory_only.py`
or `library/analyze/artifact_rubric.py` and
`library/mutate/aevolve.py` only when adapting the evolution process.

## Apply the method

1. Obtain the selected parent's evidence. Replay certified artifacts when they
   match the current fixed task and evaluator identity; otherwise run it.
2. In trajectory mode, compress behavioral events and infer likely outcomes
   without evaluator labels. In artifact mode, rank hard failures and weak
   rubrics from retained outputs without requiring a trajectory.
3. Group recurring patterns and review any proposed skill drafts.
4. Mutate the prompt and reusable skills within the mutable surface.
5. Execute the child freshly on the fixed optimization task set.
6. Compare parent and child only when their task-set and evaluator identities
   match; reserve held-out or sealed tasks for a later generalization claim.
7. Preserve the selected evidence, patch, evaluation, and decision.

## Guard the claim

Treat inferred trajectory verdicts as mutation guidance, not ground-truth
evaluation. Treat artifact rubrics as optimization evidence, not held-out proof.
Do not claim memory, tool, or skill evolution when the evaluated target does not
load those layers. Attribute improvement only to the frozen evaluation actually
executed.

## Completion check

Every changed prompt or skill is consumed by the evaluated target; its mutation
is traceable to the selected trajectory or artifact evidence; and the final
claim relies on evaluator-stamped results from a partition not exposed during
mutation.
