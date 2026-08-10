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
`rollout.variant: harbor` runs the current parent on the frozen train split.
`analyze.variant: failure_patterns` distills verifier-grounded failures and passing behavior for the meta-agent.
`mutate.variant: hyperagents` applies the selected evidence; `runner: harbor` runs its editing agent in an isolated Harbor task.
`gate.variant: hillclimb` compares child and parent on the same task hash.
`evaluator.engine: harbor` runs the canonical black-box benchmark.
`sampling: static` keeps every recipe on the same frozen validation set.

## Operator Routing

`select: {variant: greedy}` resolves to [`library/select/greedy.py`](../../library/select/greedy.py).
`rollout: {variant: harbor, ...}` resolves to [`library/rollout/harbor.py`](../../library/rollout/harbor.py).
`analyze: {variant: failure_patterns, ...}` resolves to [`library/analyze/failure_patterns.py`](../../library/analyze/failure_patterns.py).
`mutate: {variant: hyperagents, runner: harbor, ...}` resolves to [`library/mutate/hyperagents.py`](../../library/mutate/hyperagents.py), which calls [`library/mutate/_runners/harbor.py`](../../library/mutate/_runners/harbor.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
