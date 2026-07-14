# AutoResearch

AutoResearch turns the agent into the loop owner: a research program edits its
own small target file, runs a training/evaluation script, and hill-climbs on the
measured objective. This recipe is not a SWE-bench recipe; Phase E uses it only
for stub-mode loop-shape verification because its evaluator is a `train.py`
contract rather than harbor task solving.

`mode: agent` records that the agent owns more of the loop intent.
`surface.include: target/agent.py` keeps the mutable object single-file.
`select.variant: greedy` follows the best current research artifact.
`gate.variant: hillclimb` keeps only non-regressing simple changes.
`evaluator.engine: train-bpb` expects a training script score.
`sampling: static` is present for uniform report shape, though this is stub-only in Phase E.

## Operator Routing

`select: {variant: greedy}` resolves to [`library/select/greedy.py`](../../library/select/greedy.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`trace_analyzer: {variant: execution_records}` resolves to [`library/trace_analyzer/execution_records.py`](../../library/trace_analyzer/execution_records.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
