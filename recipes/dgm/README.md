# DGM

Darwin Godel Machine style search keeps an archive of runnable agents and
samples parents from that archive instead of following a single chain. The
important shape is population fan-out plus archive-based parent selection:
several children are tried each round, and any valid child can become future
material. The mechanism still only sequences operators; the recipe expresses
the population policy.

`children_per_gen: 4` creates the small population fan-out.
`surface.include: target/**` keeps this recipe focused on agent changes.
`select.variant: score_weighted` samples from eligible archive rows by score.
`gate.variant: parent_eligible` admits any complete or partial evaluated child.
`evaluator.engine: harbor` supplies the external task reward.
`sampling: static` keeps the comparison set frozen for Phase E.
`budget_usd: 150` is the per-recipe cap for the live experiment.

## Operator Routing

`select: {variant: score_weighted, seed: 0}` resolves to [`library/select/score_weighted.py`](../../library/select/score_weighted.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
