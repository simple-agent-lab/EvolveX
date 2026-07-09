# AHE

AHE treats evolution as adversarial hardening: propose a change, evaluate it,
and rely on a stricter gate to keep only versions that survive the current
evidence. In this framework the falsification and rollback idea lives in the
gate variant, while the rest of the loop stays the same black-box evaluation
contract. The recipe is intentionally narrow so the hardening claim can be
compared against hill climb on the same task set.

`children_per_gen: 1` makes a single proposed hardening step per round.
`surface.include: target/**` evolves the agent scaffold only.
`select.variant: greedy` chooses the strongest eligible archive parent.
`gate.variant: parent_eligible` maps to the valid-child rollback gate.
`evaluator.engine: harbor` supplies pass/fail reward evidence.
`sampling: static` prevents task cherry-picking during Phase E.

## Operator Routing

`select: {variant: greedy}` resolves to [`library/select/greedy.py`](../../library/select/greedy.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
