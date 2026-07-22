# HyperAgents

HyperAgents-style search evolves more than the target agent. The mutable
surface includes the agent and all operators, so improvements
can come from behavior, process, or memory. The population stays small but
branchy, and parent choice is randomized to explore different process variants
instead of always following the current best score.

`children_per_gen: 1` creates one candidate per round.
`surface.include` exposes `target/**` plus `operators/**`.
`select.variant: score_child_prop` balances score with child-proposal behavior.
`rollout.variant: evaluation_replay` exposes the selected parent's certified gate evaluation to the trace browser without launching a second task run.
`trace_analyzer.variant: trace_browser` exposes current traces, metrics, and history through the normalized feedback bundle.
`meta_agent.variant: hyperagents` consumes that bundle through Harbor's installed MiniSWE agent while retaining self-referential editing.
`gate.variant: parent_eligible` admits evaluated process variants.
`evaluator.engine: harbor` runs the canonical black-box benchmark.
`sampling: static` freezes 10 train, 10 gate, and 10 sealed task identities when the workspace is initialized from the project root.

The selected parent's retained gate evaluation is available before the child
is produced, and every installable child is then immediately evaluated on the
same frozen gate partition. Generation 0 and generations 1 through 10 therefore
form a 10-task gate optimization curve. Sealed tasks remain isolated from
meta-agent feedback.

Build the workspace image once before running:

```bash
docker build -t evolve-meta-agent-app:ubuntu-latest containers/meta-agent
```

## Operator Routing

`select: {variant: score_child_prop}` resolves to [`library/select/score_child_prop.py`](../../library/select/score_child_prop.py).
`rollout: {variant: evaluation_replay}` resolves to [`library/rollout/evaluation_replay.py`](../../library/rollout/evaluation_replay.py) and uses the normalized collector vendored from [`library/rollout/harbor.py`](../../library/rollout/harbor.py).
`trace_analyzer: {variant: trace_browser}` resolves to [`library/trace_analyzer/trace_browser.py`](../../library/trace_analyzer/trace_browser.py).
`meta_agent: {variant: hyperagents}` resolves to [`library/meta_agent/hyperagents.py`](../../library/meta_agent/hyperagents.py).
`validate: {variant: hyperagents}` resolves to [`library/validate/hyperagents.py`](../../library/validate/hyperagents.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
`record: {variant: hyperagents}` resolves to [`library/record/hyperagents.py`](../../library/record/hyperagents.py).

Operator changes use natural stage semantics: they become active the next time
the changed operator is invoked. The prompt requires every proposal to include
a substantive target change; canonical evaluation remains frozen.
