# Hill Climb

Hill climb is the simplest evolution loop: keep one parent, ask for one
mutation, evaluate it, and keep the child only when it is at least as good as
the parent. It is useful as the control condition because every improvement
claim has one clear lineage and one clear comparison. The archive is the whole
population memory, but the population has only one active frontier.

`children_per_gen: 1` makes exactly one child per round.
`mode: driver` keeps the framework as the loop runner.
`surface.include: target/**` allows only the seed agent to evolve.
`select.variant: greedy` picks the best eligible parent.
`mutate.variant: fixed` is the CI-safe scaffold; live experiments may replace it with the shared agent command adapter.
`gate.variant: hillclimb` compares child and parent on the same task hash.
`evaluator.engine: harbor` runs the canonical black-box benchmark.
`sampling: static` keeps every recipe on the same frozen validation set.

## Operator Routing

`select: {variant: greedy}` resolves to [`library/select/greedy.py`](../../library/select/greedy.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
