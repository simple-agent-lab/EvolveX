# HyperAgents

HyperAgents-style search evolves more than the target agent. The mutable
surface includes the agent, its operators, and its meta prompts, so improvements
can come from behavior, process, or memory. The population stays small but
branchy, and parent choice is randomized to explore different process variants
instead of always following the current best score.

`children_per_gen: 2` gives two parallel process variants per round.
`surface.include` exposes `target/**` and `operators/**` (scripts + strategy prose).
`select.variant: random` keeps exploration in the archive.
`gate.variant: parent_eligible` admits evaluated process variants.
`evaluator.engine: docker-report` expects a report.json style score source.
`sampling: static` keeps Phase E comparisons fixed when this recipe is run live.

## Operator Routing

`select: {variant: random, seed: 0}` resolves to [`library/select/random.py`](../../library/select/random.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
