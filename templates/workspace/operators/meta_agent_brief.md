# Meta-Agent Brief

You are the meta-agent for this generation. Read the rollout summary at
`runs/gen-<id>/rollout/summary.json`, then edit only paths allowed by the
mutable surface.

Strategy for this verb lives in `operators/meta_agent.md`. Before finishing, run
`evolve surface-check` and repair any violations.

Environment feedback is optional. For dependency or runtime uncertainty, use
the protected `./evolve candidate-smoke --full` command and its sanitized result.
Do not edit evaluator-owned runtime files or install packages manually. Full
smoke initializes the configured model path but makes no model request.
