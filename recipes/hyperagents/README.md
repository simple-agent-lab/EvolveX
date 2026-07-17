# HyperAgents

HyperAgents-style search evolves more than the target agent. The mutable
surface includes the agent, its operators, and its meta prompts, so improvements
can come from behavior, process, or memory. The population stays small but
branchy, and parent choice is randomized to explore different process variants
instead of always following the current best score.

`children_per_gen: 1` creates one candidate per round.
`surface.include` exposes `target/**` plus the meta-agent implementation and prompt.
`select.variant: score_child_prop` balances score with child-proposal behavior.
`rollout.variant: harbor` executes the parent on the frozen train split.
`trace_analyzer.variant: trace_browser` exposes current traces, metrics, and history through the normalized feedback bundle.
`meta_agent.variant: hyperagents` consumes that bundle while retaining self-referential editing.
`gate.variant: parent_eligible` admits evaluated process variants.
`evaluator.engine: harbor` runs the canonical black-box benchmark.
`sampling: static` keeps Phase E comparisons fixed when this recipe is run live.

## Operator Routing

`select: {variant: score_child_prop}` resolves to [`library/select/score_child_prop.py`](../../library/select/score_child_prop.py).
`rollout: {variant: harbor}` resolves to [`library/rollout/harbor.py`](../../library/rollout/harbor.py).
`trace_analyzer: {variant: trace_browser}` resolves to [`library/trace_analyzer/trace_browser.py`](../../library/trace_analyzer/trace_browser.py).
`meta_agent: {variant: hyperagents}` resolves to [`library/meta_agent/hyperagents.py`](../../library/meta_agent/hyperagents.py).
`validate: {variant: hyperagents}` resolves to [`library/validate/hyperagents.py`](../../library/validate/hyperagents.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: hyperagents}` resolves to [`library/record/hyperagents.py`](../../library/record/hyperagents.py).
