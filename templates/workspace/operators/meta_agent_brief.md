# Meta-Agent Brief

You are the meta-agent for this generation. Read the rollout summary at
`runs/gen-<id>/rollout/summary.json`, then edit only paths allowed by the
mutable surface.

Strategy for this verb lives in `operators/meta_agent.md`. Before finishing, run
`evolve surface-check` and repair any violations.

When runtime uncertainty is relevant, run `./evolve candidate-smoke --full`.
Read its stdout/stderr artifacts, repair the candidate environment with the
candidate's own tools, and rerun smoke. Do not edit evaluator-owned files.
