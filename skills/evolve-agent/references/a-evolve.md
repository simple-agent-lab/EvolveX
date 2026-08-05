# A-Evolve

Use A-Evolve to improve prompts and reusable skills from behavioral execution
traces while keeping direct labels, rewards, and verifier feedback out of the
mutation context.

## Use it when

- The target exposes prompts or skills as meaningful mutable components.
- Complete behavioral trajectories are available.
- The meta agent or outer agent must infer failure patterns without seeing
  privileged evaluator outputs.
- The evaluated agent actually consumes every component being evolved.

## Use the shipped capabilities

Run `./evolve operator list . --json` and follow the live access metadata. The
shipped A-Evolve profile normally provides task rollout, a `trajectory_only`
trace_analyzer, and an `aevolve` meta agent. For an outer-agent edit, invoke
the `rollout` and `trace_analyzer` stages directly, read their retained trajectory and
inferred-verdict artifacts, then modify the prompt or skills yourself; the
configured `meta_agent` remains available for an unattended driver or second
opinion.

Do not open source merely to obtain trajectories. Read
`operators/trace_analyzer.py` only if its evidence contract is unclear or its
behavior needs diagnosis; consult `library/trace_analyzer/trajectory_only.py`
and `library/meta_agent/aevolve.py` only when adapting the evolution process.

## Apply the method

1. Run the current candidate and retain ordered behavioral events.
2. Compress long trajectories into failure-focused behavioral evidence.
3. Infer likely outcomes and failure categories through a read-only assessment
   step that cannot edit the candidate.
4. Group recurring patterns and review any proposed skill drafts.
5. Mutate the prompt and reusable skills within the mutable surface.
6. Evaluate the child with the frozen evaluator and a held-out gate.
7. Preserve the trajectory evidence, inferred verdicts, patch, and decision.

## Guard the claim

Treat inferred verdicts as mutation guidance, not ground-truth evaluation.
Do not claim memory, tool, or skill evolution when the evaluated target does not
load those layers. Attribute improvement only to the frozen evaluation actually
executed.

## Completion check

Every changed prompt or skill is consumed by the evaluated target; its mutation
is traceable to behavioral evidence and an inferred verdict; and the final
claim relies on evaluator-stamped results rather than the inferred verdict.
