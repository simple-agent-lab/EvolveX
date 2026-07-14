# MetaAgent

MetaAgent-style accumulation keeps solving traces and reflection context as the
artifact. The loop does not need a competitive parent selector or a rejecting
gate: each complete child can add useful context for later work. This recipe is
therefore about memory surface and accumulation rather than score ascent.

`children_per_gen: 1` appends one new reflective artifact per round.
`surface.include` exposes the target and operator strategy prose (`operators/*.md`), not the operator scripts.
`select.variant: newest` continues from the latest eligible generation.
`gate.variant: parent_eligible` accepts complete accumulation steps.
`evaluator.engine: reflection` expects reflection traces rather than harbor rewards.
`sampling: static` keeps the common evaluator fields present in reports.

## Operator Routing

`select: {variant: newest}` resolves to [`library/select/newest.py`](../../library/select/newest.py).
`rollout: {variant: failure_focused, budget_tasks: 32}` resolves to [`library/rollout/failure_focused.py`](../../library/rollout/failure_focused.py).
`trace_analyzer: {variant: trace_browser}` resolves to [`library/trace_analyzer/trace_browser.py`](../../library/trace_analyzer/trace_browser.py).
`mutate: {variant: fixed, timeout_s: 3600}` resolves to [`library/mutate/fixed.py`](../../library/mutate/fixed.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
